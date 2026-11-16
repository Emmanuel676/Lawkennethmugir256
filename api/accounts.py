"""Users, roles, sign-in, sessions and the login throttle (Phase 12B).

Roles, each including the one before it:
  viewer    read every dataset
  importer  viewer, plus add datasets (import)
  admin     importer, plus manage users, delete datasets and read the audit log

Accounts are created by an Admin (and the first Admin by `python -m api.create_admin`), or REQUESTED on the public
Request access page (Phase 14): a request creates a PENDING account that cannot sign in until an Admin approves it
as Viewer or Importer, or rejects it (which deletes it). No email is ever sent. Throttle: after `max_login_attempts` wrong passwords for one account, that
account cannot sign in for `lockout_minutes`, even with the right password. Every failure (unknown email, wrong
password, locked, disabled) gives the same answer, NOT_RECOGNISED, so the response never reveals which applies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from api import security
from api.appdb import AppDatabase

ROLES = ("viewer", "importer", "admin")
RANK = {role: number for number, role in enumerate(ROLES)}
NOT_RECOGNISED = "Email or password not recognised."
PENDING_MESSAGE = ("Your account is waiting for approval by an administrator. No email is sent, so check back "
                   "later.")
USER_TYPES = {"regulator": "Regulator or consumer body", "lender": "Lender",
              "researcher": "Researcher or student", "other": "Other"}
APPROVABLE_ROLES = ("viewer", "importer")
LIMITS = {"full_name": 100, "organisation": 120, "reason": 500, "email": 200}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(ValueError):
    """A request about accounts that cannot be done. The message is safe to show."""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    role: str
    disabled: bool
    created_at: float
    created_by: str
    locked: bool = False
    status: str = "active"
    full_name: str = ""
    organisation: str = ""
    user_type: str = ""
    reason: str = ""
    requested_at: float = 0.0

    def can(self, role: str) -> bool:
        return self.status == "active" and not self.disabled and RANK[self.role] >= RANK[role]

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "role": self.role, "disabled": self.disabled,
                "created_at": self.created_at, "created_by": self.created_by, "locked": self.locked,
                "status": self.status, "full_name": self.full_name, "organisation": self.organisation,
                "user_type": self.user_type, "user_type_label": USER_TYPES.get(self.user_type, ""),
                "reason": self.reason, "requested_at": self.requested_at}


def normalise_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if not EMAIL.fullmatch(value) or len(value) > 200:
        raise AccountError("Enter a valid email address.")
    return value


def _user(row, at: float | None = None) -> User:
    at = security.now() if at is None else at
    return User(id=row["id"], email=row["email"], role=row["role"], disabled=bool(row["disabled"]),
                created_at=row["created_at"], created_by=row["created_by"], locked=row["locked_until"] > at,
                status=row["status"] or "active", full_name=row["full_name"] or "",
                organisation=row["organisation"] or "", user_type=row["user_type"] or "",
                reason=row["reason"] or "", requested_at=float(row["requested_at"] or 0))


def _text(value, name: str, label: str, required: bool = True) -> str:
    text = " ".join(str(value or "").split())
    if required and not text:
        raise AccountError(f"Enter your {label}.")
    if len(text) > LIMITS[name]:
        raise AccountError(f"Your {label} can be at most {LIMITS[name]} characters.")
    return text


class AccountStore:
    def __init__(self, db: AppDatabase, secret, *, session_hours: float, max_attempts: int,
                 lockout_minutes: float, password_min_length: int):
        """secret: the session-signing key, or a function returning it (called once, on first use)."""
        self.db = db
        self._secret = secret
        self.session_seconds = float(session_hours) * 3600
        self.max_attempts = int(max_attempts)
        self.lockout_seconds = float(lockout_minutes) * 60
        self.password_min_length = int(password_min_length)

    @property
    def secret(self) -> bytes:
        if callable(self._secret):
            self._secret = self._secret()
        return self._secret

    # --- Users ---------------------------------------------------------------------------------------------------

    def _check_password(self, password: str) -> None:
        problem = security.password_problem(password, self.password_min_length)
        if problem:
            raise AccountError(problem)

    def create_user(self, email: str, role: str, password: str, created_by: str) -> User:
        email = normalise_email(email)
        if role not in ROLES:
            raise AccountError("Choose a role: viewer, importer or admin.")
        self._check_password(password)
        with self.db.connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                raise AccountError("A user with that email already exists.")
            new_id = conn.execute(
                "INSERT INTO users (email, role, password_hash, created_at, created_by) VALUES (?, ?, ?, ?, ?) "
                "RETURNING id", (email, role, security.hash_password(password), security.now(), created_by)
            ).fetchone()["id"]
            row = conn.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone()
        return _user(row)

    def get(self, user_id: int) -> User | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        return _user(row) if row else None

    def list_users(self) -> list[User]:
        """Active accounts (pending requests are listed by list_pending)."""
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM users WHERE status = 'active' ORDER BY email").fetchall()
        at = security.now()
        return [_user(row, at) for row in rows]

    # --- Access requests (Phase 14) ----------------------------------------------------------------------------

    def list_pending(self) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM users WHERE status = 'pending' ORDER BY requested_at, id").fetchall()
        return [_user(row) for row in rows]

    def count_pending(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM users WHERE status = 'pending'").fetchone()["n"]

    def request_access(self, *, full_name: str, email: str, organisation: str, user_type: str, reason: str,
                       password: str, password_again: str) -> str:
        """Create a PENDING account. Returns 'created', or 'exists' when the email is already known (the caller shows
        the same confirmation either way, so the form cannot reveal which emails have accounts)."""
        full_name = _text(full_name, "full_name", "full name")
        email = normalise_email(email)
        organisation = _text(organisation, "organisation", "organisation")
        reason = _text(reason, "reason", "reason for access")
        if user_type not in USER_TYPES:
            raise AccountError("Choose the type of user.")
        if password != password_again:
            raise AccountError("The two passwords are different.")
        self._check_password(password)
        with self.db.connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                return "exists"
            at = security.now()
            conn.execute(
                """INSERT INTO users (email, role, password_hash, created_at, created_by, status, full_name, organisation,
                                      user_type, reason, requested_at)
                   VALUES (?, 'viewer', ?, ?, 'access request', 'pending', ?, ?, ?, ?, ?)""",
                (email, security.hash_password(password), at, full_name, organisation, user_type, reason, at))
        return "created"

    def approve(self, user_id: int, role: str) -> User:
        if role not in APPROVABLE_ROLES:
            raise AccountError("Approve as Viewer or Importer. Make someone an Admin later, from the user list.")
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ? AND status = 'pending'", (int(user_id),)).fetchone()
            if row is None:
                raise AccountError("That request is not pending any more.")
            conn.execute("UPDATE users SET status = 'active', role = ?, failed_attempts = 0, locked_until = 0 "
                         "WHERE id = ?", (role, row["id"]))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return _user(row)

    def reject(self, user_id: int) -> User:
        """Delete a pending request. Returns what it was (for the audit log), never the password or its hash."""
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ? AND status = 'pending'", (int(user_id),)).fetchone()
            if row is None:
                raise AccountError("That request is not pending any more.")
            conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))
        return _user(row)

    def count_admins(self, conn) -> int:
        return conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND disabled = 0 "
                            "AND status = 'active'").fetchone()["n"]

    def update_user(self, user_id: int, *, role: str | None = None, disabled: bool | None = None,
                    acting: User) -> User:
        if role is not None and role not in ROLES:
            raise AccountError("Choose a role: viewer, importer or admin.")
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
            if row is None:
                raise AccountError("No such user.")
            losing_admin = row["role"] == "admin" and not row["disabled"] and (
                (role is not None and role != "admin") or disabled is True)
            if losing_admin and row["id"] == acting.id:
                raise AccountError("You cannot remove your own Admin role or disable yourself. Ask another Admin.")
            if losing_admin and self.count_admins(conn) <= 1:
                raise AccountError("This is the last active Admin. Make another user an Admin first.")
            if role is not None:
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, row["id"]))
            if disabled is not None:
                conn.execute("UPDATE users SET disabled = ? WHERE id = ?", (1 if disabled else 0, row["id"]))
                if disabled:
                    conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            if role is not None and role != row["role"]:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))  # sign in again with the new role
            row = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return _user(row)

    def reset_password(self, user_id: int, password: str) -> User:
        self._check_password(password)
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
            if row is None:
                raise AccountError("No such user.")
            conn.execute("UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = 0 WHERE id = ?",
                         (security.hash_password(password), row["id"]))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return _user(row)

    # --- Sign-in -------------------------------------------------------------------------------------------------

    def authenticate(self, email: str, password: str) -> tuple[User | None, str]:
        """(user, event). user is None on any failure; event is 'ok', 'pending', 'failed', 'locked_now' or 'refused'.

        The caller shows NOT_RECOGNISED on every failure, except 'pending': a pending account with the RIGHT password
        is told it is waiting for approval (a wrong password still gets the generic message and counts as a failure).
        """
        try:
            email = normalise_email(email)
        except AccountError:
            security.verify_password(None, str(password or ""))
            return None, "refused"
        at = security.now()
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row is None:
                security.verify_password(None, str(password or ""))  # same cost as a wrong password
                return None, "refused"
            if row["locked_until"] > at:
                security.verify_password(None, str(password or ""))
                return None, "refused"
            ok = security.verify_password(row["password_hash"], str(password or ""))
            if ok and not row["disabled"] and row["status"] == "pending":
                return None, "pending"
            if ok and not row["disabled"]:
                conn.execute("UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE id = ?", (row["id"],))
                return _user(row, at), "ok"
            if row["disabled"]:
                return None, "refused"
            failures = (0 if row["locked_until"] and row["locked_until"] <= at else row["failed_attempts"]) + 1
            if failures >= self.max_attempts:
                conn.execute("UPDATE users SET failed_attempts = 0, locked_until = ? WHERE id = ?",
                             (at + self.lockout_seconds, row["id"]))
                return None, "locked_now"
            conn.execute("UPDATE users SET failed_attempts = ?, locked_until = 0 WHERE id = ?",
                         (failures, row["id"]))
            return None, "failed"

    def start_session(self, user: User) -> str:
        """A new session for the user. Returns the signed cookie value."""
        token = security.new_token()
        at = security.now()
        with self.db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (at,))  # tidy expired sessions
            conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                         (security.token_hash(token), user.id, at, at + self.session_seconds))
        return security.sign(token, self.secret)

    def session_user(self, cookie: str | None) -> User | None:
        """The signed-in user for a cookie, or None (missing, forged, expired, logged out, or user disabled)."""
        token = security.unsign(cookie, self.secret)
        if token is None:
            return None
        at = security.now()
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT users.*, sessions.expires_at FROM sessions JOIN users ON users.id = sessions.user_id
                   WHERE sessions.token_hash = ?""", (security.token_hash(token),)).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= at or row["disabled"] or row["status"] != "active":
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (security.token_hash(token),))
                return None
        return _user(row, at)

    def end_session(self, cookie: str | None) -> None:
        token = security.unsign(cookie, self.secret)
        if token is None:
            return
        with self.db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (security.token_hash(token),))

    def has_users(self) -> bool:
        with self.db.connect() as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
