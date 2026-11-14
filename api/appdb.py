"""The API's own SQLite database: users, sessions, dataset metadata and the audit log (Phase 12B).

One file, <data_dir>/app.db, created on first use (never at import time, and never by read-only demo calls).
Each store (api.accounts, api.store, api.audit) only talks to its own tables, so any of them can move to Postgres
later without touching the others. Nothing here stores a password or a session token in clear: only an argon2 hash
of each password and a SHA-256 hash of each session token.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'importer', 'admin')),
    password_hash TEXT NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    created_by TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    added_by TEXT NOT NULL,
    added_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    as_of_date TEXT NOT NULL DEFAULT '',
    counts TEXT NOT NULL DEFAULT '{}',
    imports INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
"""


class AppDatabase:
    """A small wrapper: one connection per call, created lazily, with foreign keys on and one writer at a time."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._ready = False
        self._lock = threading.RLock()

    def _init(self) -> None:
        if self._ready:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        self._ready = True

    @contextmanager
    def connect(self):
        """A connection inside one transaction (committed on success, rolled back on error)."""
        with self._lock:
            self._init()
            conn = sqlite3.connect(str(self.path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
