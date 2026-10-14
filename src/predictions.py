"""Storage for classifier labels: data/predictions.db (Phase 3).

A separate SQLite file on purpose. Predictions are never written into
lending.db (what a regulator holds) or into the answer-label database.

Table message_predictions holds one row per (message_id, classifier):
classifier is 'local' or 'gemini', model is the model id and settings,
confidence is the probability of the predicted class (NULL if the classifier
gives none), created_at is the UTC time the row was written.

Table human_labels (Phase 5.1) holds labels a PERSON gave on the Review page:
message_id, label, batch ('random' = part of the unbiased accuracy sample, 'hard' =
picked to help training), reviewer (initials or a code, never required to be a
name), reviewed_at, note. Human labels are not answer labels; they win over the
classifier's label wherever labels are used (apply_human_labels).

The meta table carries the synthetic-data notice and a fingerprint of the
messages the labels belong to. If lending.db is rebuilt with different
messages, the stored labels no longer match; check_matches() catches that.

All data is synthetic.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.config import MESSAGE_CLASSES

_CLASS_LIST = ", ".join(f"'{c}'" for c in MESSAGE_CLASSES)
PREDICTIONS_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_predictions (
    message_id      TEXT NOT NULL,
    classifier      TEXT NOT NULL,
    model           TEXT NOT NULL,
    predicted_class TEXT NOT NULL CHECK (predicted_class IN ({_CLASS_LIST})),
    confidence      REAL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (message_id, classifier)
);

CREATE TABLE IF NOT EXISTS human_labels (
    message_id  TEXT PRIMARY KEY,
    label       TEXT NOT NULL CHECK (label IN ({_CLASS_LIST})),
    batch       TEXT NOT NULL CHECK (batch IN ('random', 'hard')),
    reviewer    TEXT,
    reviewed_at TEXT NOT NULL,
    note        TEXT NULL
);
"""

PREDICTION_COLUMNS = ["message_id", "classifier", "model", "predicted_class", "confidence", "created_at"]
HUMAN_COLUMNS = ["message_id", "label", "batch", "reviewer", "reviewed_at", "note"]
BATCHES = ("random", "hard")
LABEL_SOURCES = ("human", "local", "gemini")


class StalePredictionsError(RuntimeError):
    """predictions.db was made from different messages than the current lending.db."""


_FINGERPRINTS: dict[tuple, str] = {}


def messages_fingerprint(lending_conn: sqlite3.Connection) -> str:
    """A fingerprint of every message in lending.db (ids, senders, times and text).

    Remembered for as long as the database file keeps the same path, modification time and size,
    so reloading the dashboard after a review label (only predictions.db changed) does not hash
    100,000 messages again.
    """
    key = None
    row = lending_conn.execute("PRAGMA database_list").fetchone()
    if row and row[2]:
        try:
            stat = os.stat(row[2])
            key = (os.path.normcase(os.path.abspath(row[2])), stat.st_mtime_ns, stat.st_size)
        except OSError:
            key = None
    if key is not None and key in _FINGERPRINTS:
        return _FINGERPRINTS[key]
    value = _compute_fingerprint(lending_conn)
    if key is not None:
        _FINGERPRINTS[key] = value
    return value


def _compute_fingerprint(lending_conn: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for row in lending_conn.execute(
            "SELECT message_id, lender_id, borrower_id, recipient_type, sent_at, text FROM messages ORDER BY 1"):
        digest.update(repr(row).encode("utf-8"))
    return digest.hexdigest()


def open_predictions(path: Path, lending_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Open (creating if needed) predictions.db for the messages in lending_conn.

    Copies the synthetic flag and notice from lending.db. If the file holds labels
    for different messages (the dataset was rebuilt), those labels are deleted,
    because they would otherwise be attached to the wrong messages. Human labels are
    kept for messages that still exist (adding a batch keeps the earlier messages);
    human labels of messages that are gone are deleted. Older files get the
    human_labels table added (CREATE TABLE IF NOT EXISTS), nothing else changes.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(PREDICTIONS_SCHEMA)
    fingerprint = messages_fingerprint(lending_conn)
    stored = _meta(conn).get("messages_fingerprint")
    if stored is not None and stored != fingerprint:
        conn.execute("DELETE FROM message_predictions")
        current = {row[0] for row in lending_conn.execute("SELECT message_id FROM messages")}
        gone = [(m,) for (m,) in conn.execute("SELECT message_id FROM human_labels") if m not in current]
        conn.executemany("DELETE FROM human_labels WHERE message_id = ?", gone)
    source_meta = dict(lending_conn.execute("SELECT key, value FROM meta WHERE key IN ('synthetic', 'notice')"))
    rows = {"messages_fingerprint": fingerprint, **source_meta}
    conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", list(rows.items()))
    conn.commit()
    return conn


def _meta(conn: sqlite3.Connection) -> dict[str, str]:
    return dict(conn.execute("SELECT key, value FROM meta"))


def check_matches(predictions_conn: sqlite3.Connection, lending_conn: sqlite3.Connection) -> None:
    """Raise StalePredictionsError unless the stored labels belong to the current messages."""
    stored = _meta(predictions_conn).get("messages_fingerprint")
    if stored != messages_fingerprint(lending_conn):
        raise StalePredictionsError(
            "predictions.db does not match the messages in lending.db (the dataset was probably rebuilt). "
            "Run: python -m src.classify_messages --classifier local")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upsert_predictions(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Insert rows, replacing any existing row for the same (message_id, classifier)."""
    columns = ", ".join(PREDICTION_COLUMNS)
    placeholders = ", ".join("?" for _ in PREDICTION_COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in PREDICTION_COLUMNS[2:])
    conn.executemany(
        f"INSERT INTO message_predictions ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (message_id, classifier) DO UPDATE SET {updates}",
        [tuple(row.get(c) for c in PREDICTION_COLUMNS) for row in rows],
    )
    conn.commit()


def read_predictions(conn: sqlite3.Connection, classifier: str | None = None) -> pd.DataFrame:
    """All stored predictions, or only those from one classifier, sorted by message_id."""
    sql = f"SELECT {', '.join(PREDICTION_COLUMNS)} FROM message_predictions"
    params: tuple = ()
    if classifier is not None:
        sql += " WHERE classifier = ?"
        params = (classifier,)
    return pd.read_sql_query(sql + " ORDER BY message_id, classifier", conn, params=params)


def ensure_human_table(conn: sqlite3.Connection) -> None:
    """Add the human_labels table to an older predictions.db (safe to call on any file)."""
    conn.executescript(PREDICTIONS_SCHEMA)


def read_human_labels(conn: sqlite3.Connection) -> pd.DataFrame:
    """All human labels, sorted by message_id. Empty (with the columns) on an older file without the table."""
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'human_labels'").fetchone()
    if not exists:
        return pd.DataFrame(columns=HUMAN_COLUMNS)
    return pd.read_sql_query(f"SELECT {', '.join(HUMAN_COLUMNS)} FROM human_labels ORDER BY message_id", conn)


def apply_human_labels(labels: pd.DataFrame, human: pd.DataFrame, classifier: str) -> pd.DataFrame:
    """Model labels with human labels on top: one row per message, predicted_class is the label to use.

    labels: rows of read_predictions() for one classifier. Adds a 'source' column:
    'human' where a person labelled the message, otherwise the classifier's name.
    A human-labelled message keeps the model's confidence (it is about the model's guess).
    """
    out = labels.copy()
    out["source"] = classifier
    if human.empty:
        return out
    by_id = human.set_index("message_id")["label"]
    hit = out["message_id"].isin(by_id.index)
    out.loc[hit, "predicted_class"] = out.loc[hit, "message_id"].map(by_id)
    out.loc[hit, "source"] = "human"
    return out


def read_effective_labels(conn: sqlite3.Connection, classifier: str) -> pd.DataFrame:
    """read_predictions(conn, classifier) with the human labels applied (see apply_human_labels)."""
    return apply_human_labels(read_predictions(conn, classifier), read_human_labels(conn), classifier)


def human_share(labels: pd.DataFrame) -> float:
    """Share of rows whose label came from a person."""
    if labels.empty or "source" not in labels.columns:
        return 0.0
    return float((labels["source"] == "human").mean())
