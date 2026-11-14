"""API settings, read from environment variables once at start-up.

  FAIRLEND_WEB_ORIGINS       comma-separated front-end origins allowed by CORS and by the cross-site check on every
                             state-changing request (default http://localhost:3000)
  FAIRLEND_API_HOST          address uvicorn listens on (default 127.0.0.1: this computer only)
  FAIRLEND_API_PORT          port (default 8000)
  FAIRLEND_WEB_DATA          folder for users, sessions, dataset metadata, the audit log and imported datasets
                             (default data/web, git-ignored like everything in data/)
  FAIRLEND_SESSION_SECRET    session-signing secret. If unset, one is generated on first start into
                             <FAIRLEND_WEB_DATA>/session_secret.txt (git-ignored). Never commit it.
  FAIRLEND_SESSION_HOURS     how long a sign-in lasts (default 8)
  FAIRLEND_COOKIE_SECURE     1 = send the session cookie over HTTPS only (set it when serving over HTTPS)
  LENDING_MONITOR_CONFIG     another config.yaml (the same variable the Streamlit app and the tests use)

The login throttle (5 wrong passwords lock that account's sign-in for 10 minutes) and the 10-character password
minimum are fixed by the Phase 12B brief and live here, not in config.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.config import PROJECT_ROOT

DEFAULT_ORIGIN = "http://localhost:3000"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "web"
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 10
PASSWORD_MIN_LENGTH = 10


def _origins(raw: str | None) -> list[str]:
    values = [part.strip().rstrip("/") for part in (raw or "").split(",")]
    return [value for value in values if value] or [DEFAULT_ORIGIN]


@dataclass(frozen=True)
class Settings:
    web_origins: list[str] = field(default_factory=lambda: [DEFAULT_ORIGIN])
    host: str = "127.0.0.1"
    port: int = 8000
    config_path: str | None = None
    data_dir: Path = DEFAULT_DATA_DIR
    session_secret: str | None = None
    session_hours: float = 8.0
    cookie_secure: bool = False
    max_login_attempts: int = MAX_LOGIN_ATTEMPTS
    lockout_minutes: float = LOCKOUT_MINUTES
    password_min_length: int = PASSWORD_MIN_LENGTH


def load_settings(environ: dict | None = None) -> Settings:
    env = os.environ if environ is None else environ
    data_dir = env.get("FAIRLEND_WEB_DATA")
    return Settings(
        web_origins=_origins(env.get("FAIRLEND_WEB_ORIGINS")),
        host=env.get("FAIRLEND_API_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(env.get("FAIRLEND_API_PORT", "8000")),
        config_path=env.get("LENDING_MONITOR_CONFIG") or None,
        data_dir=Path(data_dir) if data_dir else DEFAULT_DATA_DIR,
        session_secret=env.get("FAIRLEND_SESSION_SECRET") or None,
        session_hours=float(env.get("FAIRLEND_SESSION_HOURS", "8")),
        cookie_secure=env.get("FAIRLEND_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes", "on"),
    )
