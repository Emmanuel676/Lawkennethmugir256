"""Passwords, session tokens and the session secret (Phase 12B). No network.

  - Passwords are hashed with argon2id (argon2-cffi, salted per hash). A password or a hash is never logged,
    printed or returned by any endpoint.
  - A session is a random 32-byte token. The browser gets "<token>.<HMAC-SHA256 of the token>" in an httpOnly,
    SameSite=Strict cookie; the database keeps only SHA-256(token), so a stolen database cannot be replayed as
    cookies. The HMAC (keyed with the session secret) lets the server refuse forged cookies before any lookup.
  - The session secret comes from FAIRLEND_SESSION_SECRET or is generated on first start into a git-ignored file.

`now` is the one clock used for sessions and lockouts, so tests can move time forward.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SECRET_FILE = "session_secret.txt"
_hasher = PasswordHasher()  # argon2id with the library's recommended parameters
# A real hash of a random string: checked when an email is unknown, so a wrong email costs as much time as a
# wrong password (the response must not reveal which accounts exist).
_DUMMY_HASH = _hasher.hash(secrets.token_hex(16))


def now() -> float:
    return time.time()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """True when the password matches. Never raises for a wrong password or a damaged hash."""
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(password: str, minimum: int) -> str | None:
    """A plain reason the password is not acceptable, or None."""
    if not isinstance(password, str) or len(password) < minimum:
        return f"The password must be at least {minimum} characters long."
    if password.strip() != password:
        return "The password must not start or end with a space."
    return None


def load_secret(explicit: str | None, data_dir: Path) -> bytes:
    """The session-signing secret: FAIRLEND_SESSION_SECRET if set, else the generated file (created once)."""
    if explicit:
        return explicit.encode("utf-8")
    path = Path(data_dir) / SECRET_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # O_EXCL: two processes starting together cannot both write a different secret.
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    return path.read_text(encoding="utf-8").strip().encode("utf-8")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign(token: str, secret: bytes) -> str:
    mac = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{token}.{mac}"


def unsign(cookie: str | None, secret: bytes) -> str | None:
    """The token inside a signed cookie, or None if the cookie is missing or its signature is wrong."""
    if not cookie or "." not in cookie:
        return None
    token, _, mac = cookie.rpartition(".")
    expected = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return token if token and hmac.compare_digest(mac, expected) else None
