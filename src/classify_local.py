"""Local message classifier: TF-IDF word features and logistic regression (Phase 3).

Runs entirely on this computer: no network, no API key, nothing leaves the
machine. It sorts collection messages into four classes:

  normal               neutral reminder
  firm_pressure        insistent but lawful
  threat               threatens harm or action the lender cannot lawfully take
  shaming_third_party  exposes the debt to other people or contacts the borrower's
                       contacts (also covers shaming sent straight to the borrower)

Training uses only the examples it is given. The caller (src/classify_messages.py)
passes it dev messages only, read through src/training_data.py. This module itself
never opens the answer labels.

Lender brand names are replaced by one placeholder word before the text is turned
into features (classifier.local.mask_lender_names). Otherwise the model could learn
"this lender's name means threat" and the lender comparison would partly echo who
sent a message rather than what it says.

A label is a model's guess, not a finding. All data is synthetic.
"""

from __future__ import annotations

import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

LENDER_PLACEHOLDER = "lendername"


def brand_names(lender_names: list[str]) -> list[str]:
    """Short brand names as they appear in messages: 'Sunbird Credit (Demo)' -> 'Sunbird Credit'."""
    return sorted({re.sub(r"\s*\(.*\)\s*$", "", name).strip() for name in lender_names} - {""})


class LenderNameMasker(BaseEstimator, TransformerMixin):
    """Replace each lender brand name (any letter case) with one placeholder word."""

    def __init__(self, brands: list[str] | None = None):
        self.brands = brands

    def fit(self, texts, labels=None):
        return self

    def transform(self, texts):
        brands = sorted(self.brands or [], key=len, reverse=True)  # longest first, so no partial overlaps
        if not brands:
            return list(texts)
        pattern = re.compile("|".join(re.escape(b) for b in brands), flags=re.IGNORECASE)
        return [pattern.sub(LENDER_PLACEHOLDER, text) for text in texts]


def build_pipeline(cfg: dict, brands: list[str]) -> Pipeline:
    """An untrained pipeline with every setting taken from classifier.local in config.yaml."""
    local = cfg["classifier"]["local"]
    return Pipeline([
        ("mask", LenderNameMasker(brands if local["mask_lender_names"] else [])),
        ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=tuple(local["ngram_range"]), min_df=local["min_df"])),
        ("model", LogisticRegression(
            C=float(local["c"]), class_weight=local["class_weight"],
            random_state=int(local["seed"]), max_iter=5000)),
    ])


def model_id(cfg: dict) -> str:
    """A short description of the model and its settings, stored with every prediction."""
    local = cfg["classifier"]["local"]
    low, high = local["ngram_range"]
    return (f"tfidf-logreg ngram={low}-{high} min_df={local['min_df']} C={local['c']} "
            f"class_weight={local['class_weight']} mask={'on' if local['mask_lender_names'] else 'off'}")


def train(texts: list[str], labels: list[str], cfg: dict, brands: list[str]) -> Pipeline:
    """Fit the classifier on the given texts and labels (the caller passes dev messages only)."""
    if len(texts) != len(labels) or not texts:
        raise ValueError("train() needs the same, non-zero number of texts and labels.")
    return build_pipeline(cfg, brands).fit(list(texts), list(labels))


def predict(model: Pipeline, texts: list[str]) -> pd.DataFrame:
    """Classes and probabilities for each text, in the same order.

    Columns: predicted_class, confidence (probability of the predicted class),
    and one prob_<class> column per class.
    """
    probabilities = model.predict_proba(list(texts))
    classes = model.classes_
    out = pd.DataFrame(probabilities, columns=[f"prob_{c}" for c in classes])
    best = probabilities.argmax(axis=1)
    out.insert(0, "predicted_class", classes[best])
    out.insert(1, "confidence", probabilities[np.arange(len(best)), best])
    return out


def save_model(model: Pipeline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_model(path: Path) -> Pipeline:
    return joblib.load(path)
