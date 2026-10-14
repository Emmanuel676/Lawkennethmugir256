"""Checks on the local message classifier and the predictions store (Phase 3).

Uses a synthetic world of 1,500 borrowers (seed 11, 40 test messages). Answer
labels are read here only to check the classifier, and through
src/training_data.py only for dev messages.
"""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.classify_local import LenderNameMasker, brand_names, predict, train
from src.classify_messages import lender_brands
from src.classify_messages import main as classify_main
from src.config import ConfigError, MESSAGE_CLASSES, load_config, validate_config
from src.evaluate_classifier import classification_metrics, load_message_labels
from src.generate_data import generate, write_world
from src.predictions import (StalePredictionsError, check_matches, now_utc, open_predictions,
                             read_predictions, upsert_predictions)
from src.training_data import load_dev_examples

from leak_check import forbidden_mentions

SRC = Path(__file__).resolve().parents[1] / "src"
LABEL_FREE_MODULES = ("classify_local.py", "predictions.py", "classify_messages.py", "lender_comparison.py", "overlap.py")
LABEL_NAMES = ("ground_truth", "gt_borrowers", "gt_messages", "gt_lenders")


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def world(cfg, tmp_path_factory):
    small = copy.deepcopy(cfg)
    small["generator"]["test_set_size"] = 40
    folder = tmp_path_factory.mktemp("classifier_world")
    write_world(generate(small, seed=11, n_borrowers=1500), folder / "lending.db", folder / "ground_truth.db")
    conn = sqlite3.connect(str(folder / "lending.db"))
    examples = load_dev_examples(conn, folder / "ground_truth.db")
    brands = lender_brands(conn)
    messages = pd.read_sql_query("SELECT message_id, text FROM messages ORDER BY message_id", conn)
    conn.close()
    model = train(examples["text"].tolist(), examples["label"].tolist(), cfg, brands)
    predicted = predict(model, messages["text"].tolist())
    predicted.insert(0, "message_id", messages["message_id"].to_numpy())
    return {
        "folder": folder, "examples": examples, "brands": brands, "messages": messages,
        "predicted": predicted, "truth": load_message_labels(folder / "ground_truth.db"),
    }


# --- Training only ever sees dev messages ---------------------------------

def test_training_ids_contain_no_test_or_reserve_ids(world):
    truth = world["truth"]
    training_ids = set(world["examples"]["message_id"])
    held_out = set(truth.loc[truth["split"].isin(["test", "reserve"]), "message_id"])
    assert held_out  # the world really has held-out messages to leak
    assert training_ids.isdisjoint(held_out)
    assert training_ids == set(truth.loc[truth["split"] == "dev", "message_id"])


def test_same_seed_gives_identical_predictions_twice(world, cfg):
    examples = world["examples"]
    again = train(examples["text"].tolist(), examples["label"].tolist(), cfg, world["brands"])
    second = predict(again, world["messages"]["text"].tolist())
    second.insert(0, "message_id", world["messages"]["message_id"].to_numpy())
    pd.testing.assert_frame_equal(world["predicted"], second)


def test_predictions_are_valid_classes_with_probabilities(world):
    predicted = world["predicted"]
    assert set(predicted["predicted_class"]) <= set(MESSAGE_CLASSES)
    assert predicted["confidence"].between(0.25, 1.0).all()
    prob_columns = [f"prob_{c}" for c in MESSAGE_CLASSES]
    assert ((predicted[prob_columns].sum(axis=1) - 1).abs() < 1e-9).all()


def test_local_classifier_generalises_to_held_out_test_phrasings(world):
    data = world["truth"].merge(world["predicted"], on="message_id")
    test = data[data["split"] == "test"]
    assert len(test) == 40
    metrics = classification_metrics(test["true_class"].tolist(), test["predicted_class"].tolist())
    assert metrics["macro_f1"] > 0.7
    for name, recall in metrics["per_class"]["recall"].items():
        assert recall > 0.5, f"recall for {name} is only {recall:.2f}"


def test_lender_names_are_masked_in_any_letter_case():
    brands = brand_names(["Sunbird Credit (Demo)", "Redstone Loans (Demo)"])
    assert brands == ["Redstone Loans", "Sunbird Credit"]
    masked = LenderNameMasker(brands).transform(["Pay Sunbird Credit now", "pay sunbird credit now", "Hello"])
    assert masked == ["Pay lendername now", "pay lendername now", "Hello"]


def test_classification_metrics_by_hand():
    metrics = classification_metrics(["threat", "threat", "normal", "normal"], ["threat", "normal", "normal", "normal"])
    assert metrics["accuracy"] == pytest.approx(0.75)
    assert metrics["per_class"].loc["threat", "recall"] == pytest.approx(0.5)
    assert metrics["per_class"].loc["normal", "precision"] == pytest.approx(2 / 3)
    assert metrics["confusion"].loc["threat", "normal"] == 1


# --- predictions.db ---------------------------------------------------------

def _row(message_id, classifier="local", predicted_class="normal", confidence=0.9):
    return {"message_id": message_id, "classifier": classifier, "model": "test-model",
            "predicted_class": predicted_class, "confidence": confidence, "created_at": now_utc()}


@pytest.fixture
def store(world, tmp_path):
    lending = sqlite3.connect(str(world["folder"] / "lending.db"))
    conn = open_predictions(tmp_path / "predictions.db", lending)
    yield conn, lending
    conn.close()
    lending.close()


def test_predictions_schema_rejects_an_unknown_class(store):
    conn, _ = store
    with pytest.raises(sqlite3.IntegrityError):
        upsert_predictions(conn, [_row("M00001", predicted_class="rude")])


def test_upsert_replaces_the_same_message_and_classifier(store):
    conn, _ = store
    upsert_predictions(conn, [_row("M00001", predicted_class="threat", confidence=0.6)])
    upsert_predictions(conn, [_row("M00001", predicted_class="normal", confidence=0.8)])
    upsert_predictions(conn, [_row("M00001", classifier="gemini", predicted_class="threat", confidence=None)])
    local = read_predictions(conn, "local")
    assert len(local) == 1
    assert local.loc[0, "predicted_class"] == "normal"
    assert local.loc[0, "confidence"] == pytest.approx(0.8)
    assert len(read_predictions(conn)) == 2  # the gemini row is kept separately


def test_predictions_db_carries_the_synthetic_notice(store):
    conn, _ = store
    meta = dict(conn.execute("SELECT key, value FROM meta"))
    assert meta["synthetic"] == "true"
    assert "SYNTHETIC" in meta["notice"]


def test_predictions_for_other_messages_are_detected_as_stale(store, cfg, tmp_path):
    conn, lending = store
    check_matches(conn, lending)  # matches the world it was made from
    write_world(generate(cfg, seed=99, n_borrowers=200), tmp_path / "other.db", tmp_path / "other_truth.db")
    other = sqlite3.connect(str(tmp_path / "other.db"))
    try:
        with pytest.raises(StalePredictionsError):
            check_matches(conn, other)
    finally:
        other.close()


# --- The CLI is idempotent and deterministic -------------------------------

def test_classify_messages_twice_gives_the_same_stored_labels(world, cfg, tmp_path):
    custom = copy.deepcopy(cfg)
    custom["paths"] = {
        "lending_db": str(world["folder"] / "lending.db"),
        "ground_truth_db": str(world["folder"] / "ground_truth.db"),
        "manifest": str(tmp_path / "manifest.json"),
        "predictions_db": str(tmp_path / "predictions.db"),
        "local_model": str(tmp_path / "local_model.joblib"),
        "datasets_dir": str(tmp_path / "datasets"),
        "active_dataset_file": str(tmp_path / "active_dataset.txt"),
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(custom), encoding="utf-8")

    stored = []
    for _ in range(2):
        assert classify_main(["--classifier", "local", "--config", str(config_path)]) == 0
        conn = sqlite3.connect(str(tmp_path / "predictions.db"))
        stored.append(read_predictions(conn, "local").drop(columns="created_at"))
        conn.close()
    assert len(stored[0]) == len(world["messages"])
    pd.testing.assert_frame_equal(stored[0], stored[1])
    assert (tmp_path / "local_model.joblib").exists()
    # Nothing was written into the lending database.
    lending = sqlite3.connect(str(world["folder"] / "lending.db"))
    assert "message_predictions" not in {r[0] for r in lending.execute("SELECT name FROM sqlite_master")}
    lending.close()


# --- Classifier and lender code never names the answer labels --------------

@pytest.mark.parametrize("module", LABEL_FREE_MODULES)
def test_classifier_and_lender_modules_never_mention_the_answer_labels(module):
    source = (SRC / module).read_text(encoding="utf-8")
    assert forbidden_mentions(source, LABEL_NAMES) == []


# --- Config checks ------------------------------------------------------------

@pytest.mark.parametrize("change, message", [
    (lambda c: c["classifier"].__setitem__("primary", "chatgpt"), "primary"),
    (lambda c: c["classifier"]["gemini"].__setitem__("batch_size", 0), "batch_size"),
    (lambda c: c["lender_comparison"].__setitem__("confidence", 1.2), "confidence"),
    (lambda c: c["lender_comparison"].__setitem__("confidence", 0.3), "confidence"),
    (lambda c: c["lender_comparison"].__setitem__("abusive_classes", ["threat", "rude"]), "unknown class"),
])
def test_bad_classifier_settings_are_rejected(cfg, change, message):
    broken = copy.deepcopy(cfg)
    change(broken)
    with pytest.raises(ConfigError, match=message):
        validate_config(broken)
