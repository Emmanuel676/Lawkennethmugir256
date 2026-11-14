"""The audit log: who imported, deleted or changed what, and when (Phase 12B). Admin can read it.

Entries never contain a password, a hash, a session token, a cell value or message text: only the acting user's
email, an action name, the dataset or user it was about, and counts.
"""

from __future__ import annotations

import json

from api import security
from api.appdb import AppDatabase

ACTIONS = {
    "import_new": "Imported a new dataset",
    "import_add": "Added a lender's files to a dataset",
    "import_refused": "Upload refused by the synthetic-only check",
    "import_failed": "Import stopped by validation errors",
    "dataset_delete": "Deleted a dataset",
    "user_create": "Created a user",
    "user_role": "Changed a user's role",
    "user_disable": "Disabled a user",
    "user_enable": "Enabled a user",
    "password_reset": "Reset a user's password",
    "login_locked": "Sign-in locked after too many wrong passwords",
    "review_label": "Checked a message label",
}


class AuditLog:
    def __init__(self, db: AppDatabase):
        self.db = db

    def record(self, actor: str, action: str, target: str = "", detail: dict | None = None) -> None:
        if action not in ACTIONS:
            raise ValueError(f"Unknown audit action {action!r}")
        with self.db.connect() as conn:
            conn.execute("INSERT INTO audit (at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
                         (security.now(), actor, action, target, json.dumps(detail or {}, sort_keys=True)))

    def entries(self, limit: int = 200, offset: int = 0) -> tuple[int, list[dict]]:
        with self.db.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            rows = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ? OFFSET ?",
                                (int(limit), int(offset))).fetchall()
        return total, [{"id": r["id"], "at": r["at"], "actor": r["actor"], "action": r["action"],
                        "action_label": ACTIONS.get(r["action"], r["action"]), "target": r["target"],
                        "detail": json.loads(r["detail"] or "{}")} for r in rows]
