"""Label every collection message in a dataset and store the labels (Phase 3, datasets in Phase 4B).

    python -m src.classify_messages --classifier local                 # the active dataset
    python -m src.classify_messages --classifier local --dataset demo  # a named dataset

The local classifier is trained on the DEMO dataset's dev messages only (via
src/training_data.py): that is the only labelled text there is. It is saved to
paths.local_model. If the demo has been deleted, the saved model is used instead.
It then labels ALL messages of the chosen dataset and stores them in that
dataset's predictions.db with classifier = 'local'. Running it again gives the
same labels and replaces the old rows, so it is safe to repeat.

Phase 5.1: once people have checked enough messages of a real dataset, the Review
page can retrain a model for THAT dataset (src/review.py). It is saved inside the
dataset's folder (dataset_model.joblib, with a dataset_model.json note) and, when
it exists, this module uses it for that dataset instead of the demo-trained model.
The demo's saved model is never overwritten by it.

A label is a model's guess, not a finding. On real data the labels come from a
model trained on synthetic text and are unreliable until a person has checked a sample.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from sklearn.pipeline import Pipeline

from src.classify_local import brand_names, load_model, model_id, predict, save_model, train
from src.config import MESSAGE_CLASSES, load_config, resolve_path
from src.datasets import DEMO, DatasetError, DatasetPaths, get_dataset_paths, paths_for
from src.overlap import DEFAULT_NOTICE, connect_read_only
from src.predictions import now_utc, open_predictions, upsert_predictions
from src.training_data import labels_path, load_dev_examples, training_data_available

CLASSIFIER_CHOICES = ("local",)  # 'gemini' is added in Part B
DATASET_MODEL_FILE = "dataset_model.joblib"
DATASET_MODEL_INFO = "dataset_model.json"


class NoModelError(RuntimeError):
    """Neither the demo's training data nor a saved model is available."""


def lender_brands(lending_conn: sqlite3.Connection) -> list[str]:
    return brand_names([row[0] for row in lending_conn.execute("SELECT name FROM lenders")])


def train_local_model(cfg: dict) -> tuple[Pipeline, int]:
    """Train on the demo's dev messages and save the model. Returns (model, number of training messages)."""
    demo = get_dataset_paths(cfg, DEMO)
    if not demo.lending_db.exists():
        raise NoModelError("The demo dataset is not there to train on. Restore the demo first.")
    conn = connect_read_only(demo.lending_db)
    try:
        brands = lender_brands(conn)
        examples = load_dev_examples(conn, labels_path(cfg))
    finally:
        conn.close()
    model = train(examples["text"].tolist(), examples["label"].tolist(), cfg, brands)
    saved = resolve_path(cfg, "local_model")
    save_model(model, saved)
    _write_json(saved.with_suffix(".json"), {"n_train": len(examples), "trained_at": now_utc(),
                                             "trained_on": "dev messages of the demo (synthetic)",
                                             "model_id": model_id(cfg), "sklearn_version": sklearn_version()})
    return model, len(examples)


def sklearn_version() -> str:
    """The installed scikit-learn version. A saved model is only trusted with the same version."""
    import sklearn

    return str(sklearn.__version__)


def _write_json(path: Path, info: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def saved_model_note(cfg: dict) -> dict:
    """What the demo's saved model was trained on (empty if no note was written)."""
    return _read_json(resolve_path(cfg, "local_model").with_suffix(".json"))


def dataset_model_path(paths: DatasetPaths) -> Path | None:
    """Where a real dataset's own retrained model lives (inside its folder). None for the demo."""
    if paths.name == DEMO:
        return None
    return paths.lending_db.parent / DATASET_MODEL_FILE


def dataset_model_info(paths: DatasetPaths) -> dict:
    path = dataset_model_path(paths)
    return _read_json(path.with_name(DATASET_MODEL_INFO)) if path else {}


def save_dataset_model(paths: DatasetPaths, model: Pipeline, info: dict) -> Path:
    """Save a dataset's own model and its note. Refuses the demo, so the demo's model is never replaced."""
    path = dataset_model_path(paths)
    if path is None:
        raise ValueError("The demo dataset cannot have a retrained model; it keeps the demo-trained one.")
    save_model(model, path)
    _write_json(path.with_name(DATASET_MODEL_INFO), info)
    return path


def model_for_dataset(cfg: dict, paths: DatasetPaths) -> tuple[Pipeline, str, str]:
    """(model, sentence saying where it came from, model id to store with each label).

    A real dataset's own retrained model is used when it exists; otherwise the demo-trained one.
    """
    own = dataset_model_path(paths)
    if own is not None and own.exists():
        info = dataset_model_info(paths)
        label = info.get("model_id", f"dataset-retrained {model_id(cfg)}")
        return load_model(own), f"Used this dataset's own retrained classifier ({own.name}).", label
    model, note = get_local_model(cfg)
    return model, note, model_id(cfg)


def get_local_model(cfg: dict) -> tuple[Pipeline, str]:
    """A trained model and a sentence saying where it came from.

    Trains on the demo when it is available (same result every time); otherwise loads the saved model.
    """
    saved = resolve_path(cfg, "local_model")
    if training_data_available(cfg):
        model, n_train = train_local_model(cfg)
        return model, f"Trained the local classifier on {n_train:,} dev messages of the demo ({model_id(cfg)})."
    if saved.exists():
        return load_model(saved), f"Used the saved local classifier ({saved.name}); the demo data is not present."
    raise NoModelError("No classifier is available: the demo data is gone and no saved model exists. "
                       "Restore the demo on the Data page (or run: python -m src.build_all).")


def label_messages(model: Pipeline, lending_conn: sqlite3.Connection) -> pd.DataFrame:
    messages = pd.read_sql_query("SELECT message_id, text FROM messages ORDER BY message_id", lending_conn)
    if messages.empty:
        return pd.DataFrame(columns=["message_id", "predicted_class", "confidence"])
    labels = predict(model, messages["text"].tolist())
    labels.insert(0, "message_id", messages["message_id"].to_numpy())
    return labels


def classify_dataset(cfg: dict, paths: DatasetPaths, model: Pipeline | None = None,
                     model_note: str = "", model_label: str | None = None) -> int:
    """Label every message of one dataset with the local classifier and store the labels. Returns the count.

    Without a model, the dataset's own retrained model is used if it exists (model_for_dataset).
    """
    if model is None:
        model, model_note, model_label = model_for_dataset(cfg, paths)
    lending_conn = connect_read_only(paths.lending_db)
    try:
        labels = label_messages(model, lending_conn)
        predictions_conn = open_predictions(paths.predictions_db, lending_conn)
    finally:
        lending_conn.close()
    created = now_utc()
    rows = [
        {"message_id": r.message_id, "classifier": "local", "model": model_label or model_id(cfg),
         "predicted_class": r.predicted_class, "confidence": round(float(r.confidence), 6), "created_at": created}
        for r in labels.itertuples(index=False)
    ]
    try:
        upsert_predictions(predictions_conn, rows)
    finally:
        predictions_conn.close()
    return len(rows)


# Kept for callers from Phase 3: train on the demo, label the given connection's messages.
def classify_local(lending_conn: sqlite3.Connection, cfg: dict) -> tuple[pd.DataFrame, int]:
    model, n_train = train_local_model(cfg)
    return label_messages(model, lending_conn), n_train


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Label every collection message and store the labels.")
    parser.add_argument("--classifier", choices=CLASSIFIER_CHOICES, default="local")
    parser.add_argument("--dataset", help="Dataset to label (default: the active dataset).")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    try:
        paths = paths_for(cfg, args.dataset)
    except DatasetError as error:
        print(error)
        return 1
    if not paths.lending_db.exists():
        print(f"Dataset '{paths.name}' has no data yet. For the demo run: python -m src.build_all")
        return 1

    try:
        model, note, label = model_for_dataset(cfg, paths)
    except NoModelError as error:
        print(error)
        return 1
    count = classify_dataset(cfg, paths, model, note, label)

    conn = connect_read_only(paths.lending_db)
    try:
        notice = dict(conn.execute("SELECT key, value FROM meta")).get("notice", DEFAULT_NOTICE)
    finally:
        conn.close()
    pred_conn = connect_read_only(paths.predictions_db)
    try:
        counts = pd.read_sql_query(
            "SELECT predicted_class, COUNT(*) AS n FROM message_predictions WHERE classifier = 'local' "
            "GROUP BY predicted_class", pred_conn).set_index("predicted_class")["n"]
    finally:
        pred_conn.close()

    print(notice)
    print("Labels are a model's guesses, not findings.")
    print("")
    print(note)
    print(f"Dataset '{paths.name}': labelled {count:,} messages:")
    for name in MESSAGE_CLASSES:
        print(f"  {name:<22}{int(counts.get(name, 0)):>8,}")
    print("")
    print(f"Wrote {paths.predictions_db}  (classifier = 'local')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
