"""Training examples for the local message classifier: dev messages and their labels.

TRAINING IS ALLOWED TO READ THE ANSWER LABELS, BUT ONLY FOR split = 'dev'.
This module is that one door. It is the only module outside the evaluation
modules that opens ground_truth.db, and it only ever returns rows whose split
is 'dev'. Messages in 'test' (held out, accuracy only) and 'reserve' (held-out
phrasings not picked for the test set) never come out of here, so they cannot
leak into training or tuning.

The classifier itself (src/classify_local.py) does not know where its labels
come from; it trains on whatever texts and labels it is given.

All data is synthetic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.datasets import DEMO, get_dataset_paths
from src.overlap import connect_read_only

TRAINING_SPLIT = "dev"


def labels_path(cfg: dict) -> Path:
    """Where the demo's answer labels live. Training always uses the demo: real datasets have no labels."""
    path = get_dataset_paths(cfg, DEMO).ground_truth_db
    if path is None:
        raise FileNotFoundError("config.yaml has no paths.ground_truth_db, so there is nothing to train on.")
    return path


def training_data_available(cfg: dict) -> bool:
    """True when the demo's messages and answer labels are both present, so the classifier can be trained."""
    demo = get_dataset_paths(cfg, DEMO)
    return demo.lending_db.exists() and demo.ground_truth_db is not None and demo.ground_truth_db.exists()


def load_dev_examples(lending_conn: sqlite3.Connection, path: Path) -> pd.DataFrame:
    """Return message_id, text and label for every dev message, sorted by message_id."""
    labels_conn = connect_read_only(path)
    try:
        labels = pd.read_sql_query(
            "SELECT message_id, true_class AS label, split FROM gt_messages WHERE split = ?",
            labels_conn, params=(TRAINING_SPLIT,))
    finally:
        labels_conn.close()
    if (labels["split"] != TRAINING_SPLIT).any():  # belt and braces: never hand out other splits
        raise RuntimeError("Training data contains messages outside the dev split.")

    texts = pd.read_sql_query("SELECT message_id, text FROM messages", lending_conn)
    examples = labels.merge(texts, on="message_id", how="inner", validate="one_to_one")
    if len(examples) != len(labels):
        raise ValueError("Some dev labels have no message in lending.db. Were the two databases built together?")
    return examples[["message_id", "text", "label"]].sort_values("message_id").reset_index(drop=True)
