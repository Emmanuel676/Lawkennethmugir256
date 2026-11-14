"""Review labels (Phase 12C): a person checks a sample of the model's message labels on an IMPORTED dataset.

Reuses src.review unchanged: next_batch (random check or hard cases, never a message already reviewed),
message_for_review, save_label, progress, measured_accuracy and reviewed_labels_csv. Human labels are stored in
that dataset's own predictions file (its folder under data/web/datasets), where the engine already reads them:
they replace the model's label everywhere and are counted as "labels a person has checked".

The built-in demo is never changed, so review is refused there with a plain reason.
"""

from __future__ import annotations

import math

from src.config import MESSAGE_CLASSES
from src.datasets import DEMO, get_dataset_paths
from src.review import (ReviewError, message_for_review, measured_accuracy, next_batch, progress,
                        reviewed_labels_csv, save_label)

DEMO_REASON = ("The demo dataset cannot be changed, so its labels cannot be reviewed here. Its accuracy is measured "
               "against answer labels (python -m src.evaluate_classifier). Choose an imported dataset to review.")
KINDS = {"random": "Random check (the fair measure of accuracy)", "hard": "Hard cases (helps find mistakes)"}


class ReviewUnavailable(ValueError):
    """Review cannot be done on this dataset. The message is safe to show."""


def dataset_paths(services, slug: str):
    if not slug or slug == DEMO:
        raise ReviewUnavailable(DEMO_REASON)
    if services.catalog.get(slug) is None:
        raise ReviewUnavailable("No imported dataset with that name.")
    cfg = services.files.engine_config(services.sources.base_config(), slug)
    return cfg, get_dataset_paths(cfg, slug)


def _number(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def summary(services, slug: str) -> dict:
    cfg, paths = dataset_paths(services, slug)
    state = progress(paths)
    accuracy = measured_accuracy(paths, cfg)
    per_class = []
    if accuracy.get("ok"):
        per_class = [{k: _number(v.item() if hasattr(v, "item") else v) for k, v in row.items()}
                     for row in accuracy["per_class"].to_dict("records")]
    review = cfg["classifier"]["review"]
    return {
        "available": True,
        "messages": state["messages"], "reviewed": state["reviewed"], "share_reviewed": state["share_reviewed"],
        "per_batch": state["per_batch"], "per_class": state["per_class"],
        "accuracy": {"ok": bool(accuracy.get("ok")), "sentence": accuracy["sentence"], "n": accuracy["n"],
                     "accuracy": _number(accuracy.get("accuracy")), "low": _number(accuracy.get("low")),
                     "high": _number(accuracy.get("high")), "per_class": per_class},
        "classes": list(MESSAGE_CLASSES), "kinds": KINDS,
        "default_size": int(review["sample_size_default"]),
        "show_model_label": bool(review["show_prediction_before_label"]),
    }


def batch(services, slug: str, kind: str, size: int) -> list[str]:
    cfg, paths = dataset_paths(services, slug)
    if not 1 <= int(size) <= 500:
        raise ReviewError("A batch holds 1 to 500 messages.")
    return next_batch(paths, kind, int(size), int(cfg["classifier"]["review"]["seed"]))


def message(services, slug: str, message_id: str, redact) -> dict:
    _, paths = dataset_paths(services, slug)
    item = message_for_review(paths, message_id)
    item["text"] = redact(item["text"])  # stored redacted at import; redacted again on the way out to be sure
    return item


def label(services, slug: str, message_id: str, chosen: str, kind: str, reviewer: str | None) -> dict:
    _, paths = dataset_paths(services, slug)
    before = message_for_review(paths, message_id)["model_label"]
    save_label(paths, message_id, chosen, kind, reviewer)
    return {"saved": chosen, "model_label": before, "agreed": before == chosen}


def export_csv(services, slug: str, notice: str) -> bytes:
    _, paths = dataset_paths(services, slug)
    return reviewed_labels_csv(paths, notice)
