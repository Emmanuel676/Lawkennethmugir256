"""SQLite helpers: schemas, creating a fresh database, inserting rows, hashing.

Two separate database files are used on purpose (PRD requirement FR-D3):

  lending.db        What the detectors and the dashboard are allowed to see.
  ground_truth.db   The answer labels. Used only to measure accuracy, never as a model input.

Dates are stored as ISO text ('2026-09-30') and timestamps as 'YYYY-MM-DD HH:MM:SS'.
Money is stored as whole shillings (integers).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

LENDING_SCHEMA = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE lenders (
    lender_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    size_category TEXT NOT NULL CHECK (size_category IN ('micro', 'small', 'medium', 'large'))
);

CREATE TABLE borrowers (
    borrower_id    TEXT PRIMARY KEY,
    region         TEXT NOT NULL,
    monthly_income INTEGER NOT NULL CHECK (monthly_income > 0),
    joined_date    TEXT NOT NULL
);

CREATE TABLE loans (
    loan_id            TEXT PRIMARY KEY,
    borrower_id        TEXT NOT NULL REFERENCES borrowers (borrower_id),
    lender_id          TEXT NOT NULL REFERENCES lenders (lender_id),
    principal          INTEGER NOT NULL CHECK (principal > 0),
    amount_outstanding INTEGER NOT NULL CHECK (amount_outstanding >= 0),
    issue_date         TEXT NOT NULL,
    due_date           TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('active', 'repaid', 'in_arrears'))
);

CREATE TABLE transactions (
    txn_id            TEXT PRIMARY KEY,
    borrower_id       TEXT NOT NULL REFERENCES borrowers (borrower_id),
    txn_date          TEXT NOT NULL,
    amount            INTEGER NOT NULL CHECK (amount > 0),
    direction         TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    counterparty_type TEXT NOT NULL CHECK (counterparty_type IN ('lender', 'merchant', 'employer', 'agent', 'peer')),
    linked_loan_id    TEXT REFERENCES loans (loan_id)
);

CREATE TABLE messages (
    message_id     TEXT PRIMARY KEY,
    lender_id      TEXT NOT NULL REFERENCES lenders (lender_id),
    borrower_id    TEXT NOT NULL REFERENCES borrowers (borrower_id),
    recipient_type TEXT NOT NULL CHECK (recipient_type IN ('borrower', 'third_party')),
    sent_at        TEXT NOT NULL,
    text           TEXT NOT NULL
);

CREATE INDEX idx_loans_borrower        ON loans (borrower_id);
CREATE INDEX idx_loans_lender          ON loans (lender_id);
CREATE INDEX idx_transactions_borrower ON transactions (borrower_id);
CREATE INDEX idx_transactions_loan     ON transactions (linked_loan_id);
CREATE INDEX idx_messages_lender       ON messages (lender_id);
CREATE INDEX idx_messages_borrower     ON messages (borrower_id);
"""

GROUND_TRUTH_SCHEMA = """
CREATE TABLE gt_borrowers (
    borrower_id  TEXT PRIMARY KEY,
    profile_type TEXT NOT NULL CHECK (profile_type IN ('typical', 'stacked', 'cycling', 'harassed', 'look_alike'))
);

-- split: 'dev'     written from development templates, free to use for tuning and training
--        'test'    written from held-out templates, used ONLY to measure accuracy
--        'reserve' also written from held-out templates but not picked for the test set;
--                  keep it out of tuning and training too, or the test phrasings leak
CREATE TABLE gt_messages (
    message_id  TEXT PRIMARY KEY,
    true_class  TEXT NOT NULL CHECK (true_class IN ('normal', 'firm_pressure', 'threat', 'shaming_third_party')),
    template_id TEXT NOT NULL,
    split       TEXT NOT NULL CHECK (split IN ('dev', 'test', 'reserve'))
);

CREATE TABLE gt_lenders (
    lender_id TEXT PRIMARY KEY,
    behaviour TEXT NOT NULL CHECK (behaviour IN ('clean', 'borderline', 'abusive'))
);
"""

# Column order for each table, used when inserting rows given as dictionaries.
COLUMNS = {
    "meta": ["key", "value"],
    "lenders": ["lender_id", "name", "size_category"],
    "borrowers": ["borrower_id", "region", "monthly_income", "joined_date"],
    "loans": [
        "loan_id", "borrower_id", "lender_id", "principal",
        "amount_outstanding", "issue_date", "due_date", "status",
    ],
    "transactions": [
        "txn_id", "borrower_id", "txn_date", "amount",
        "direction", "counterparty_type", "linked_loan_id",
    ],
    "messages": ["message_id", "lender_id", "borrower_id", "recipient_type", "sent_at", "text"],
    "gt_borrowers": ["borrower_id", "profile_type"],
    "gt_messages": ["message_id", "true_class", "template_id", "split"],
    "gt_lenders": ["lender_id", "behaviour"],
}


def create_database(path: Path | str, schema: str) -> sqlite3.Connection:
    """Delete any old file at path, then create a new empty database with the given schema."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema)
    return conn


def insert_rows(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    """Insert rows (a list of dicts keyed by column name) into a known table."""
    columns = COLUMNS[table]
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(row[c] for c in columns) for row in rows])


def table_names(conn: sqlite3.Connection) -> list[str]:
    """Names of all user tables in the database, sorted."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Number of rows in every table."""
    return {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in table_names(conn)}


def content_hash(conn: sqlite3.Connection) -> str:
    """A fingerprint of everything stored in the database.

    Two builds from the same seed and config must give the same fingerprint.
    That is how we prove the dataset is reproducible (PRD requirement FR-D2).
    """
    digest = hashlib.sha256()
    for name in table_names(conn):
        digest.update(name.encode("utf-8"))
        for row in conn.execute(f"SELECT * FROM {name} ORDER BY 1"):
            digest.update(repr(row).encode("utf-8"))
    return digest.hexdigest()
