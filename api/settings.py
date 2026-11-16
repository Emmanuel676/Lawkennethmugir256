"""API settings, read from environment variables once at start-up.

  FAIRLEND_WEB_ORIGINS       comma-separated front-end origins allowed by CORS and by the cross-site check on every
                             state-changing request (default http://localhost:3000)
  FAIRLEND_API_HOST          address uvicorn listens on (default 127.0.0.1: this computer only)
  FAIRLEND_API_PORT / PORT   port (default 8000; PORT is what hosts such as Render provide)
  FAIRLEND_WEB_DATA          local storage: users, sessions, dataset metadata, the audit log and imported datasets
                             (default data/web, git-ignored like everything in data/). Not used with DATABASE_URL.
  DATABASE_URL               Postgres for users, sessions, the audit log, the dataset catalog and the imported
                             datasets' files (Phase 13). Read ONLY from the environment; never printed or logged.
                             When it is set, FAIRLEND_SESSION_SECRET is required and cookies are always Secure.
  FAIRLEND_CACHE_DIR         where Postgres-stored datasets are cached as files (default: a temporary folder)
  FAIRLEND_SESSION_SECRET    session-signing secret. Locally, if unset, one is generated on first start into
                             <FAIRLEND_WEB_DATA>/session_secret.txt (git-ignored). Never commit it.
  FAIRLEND_SESSION_HOURS     how long a sign-in lasts (default 8)
  FAIRLEND_PROXY_HOPS        trusted proxies in front of the API, for the visitor's address in X-Forwarded-For
                             (default 0: use the connection address; Vercel in front of Render: 2)
  FAIRLEND_REQUESTS_PER_HOUR access requests accepted per address per rolling hour (default 5)
  FAIRLEND_MAX_PENDING       most access requests waiting for an Admin at once (default 50)
  FAIRLEND_COOKIE_SECURE     1 = send the session cookie over HTTPS only (always on with DATABASE_URL)
  LENDING_MONITOR_CONFIG     another config.yaml (the same variable the Streamlit app and the tests use)

The login throttle (5 wrong passwords lock that account's sign-in for 10 minutes) and the 10-character password
minimum are fixed by the Phase 12B brief and live here, not in config.yaml.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.config import PROJECT_ROOT

DEFAULT_ORIGIN = "http://localhost:3000"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "web"
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 10
PASSWORD_MIN_LENGTH = 10
SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class SettingsError(RuntimeError):
    """The settings cannot be used. The message never contains a secret or the database URL."""


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
    session_secret: str | None = field(default=None, repr=False)
    session_hours: float = 8.0
    cookie_secure: bool = False
    max_login_attempts: int = MAX_LOGIN_ATTEMPTS
    lockout_minutes: float = LOCKOUT_MINUTES
    password_min_length: int = PASSWORD_MIN_LENGTH
    database_url: str | None = field(default=None, repr=False)   # never shown in a printout of the settings
    database_schema: str | None = None                            # tests only: a fresh Postgres schema per run
    cache_dir: Path | None = None
    proxy_hops: int = 0
    requests_per_hour: int = 5
    max_pending: int = 50

    @property
    def backend(self) -> str:
        return "postgres" if self.database_url else "sqlite"

    @property
    def secure_cookies(self) -> bool:
        """Secure cookies when asked for, and always when Postgres is used (that means a hosted deployment)."""
        return self.cookie_secure or bool(self.database_url)

    @property
    def files_cache(self) -> Path:
        return self.cache_dir or Path(tempfile.gettempdir()) / "fairlend-dataset-cache"

    def check(self) -> None:
        """Refuse settings that are unsafe for the chosen backend."""
        if self.database_url and not self.session_secret:
            raise SettingsError("DATABASE_URL is set, so FAIRLEND_SESSION_SECRET must be set too (a fixed secret from "
                                "the host's secret settings). The API will not start without it.")
        if self.database_schema and not SCHEMA_NAME.fullmatch(self.database_schema):
            raise SettingsError("FAIRLEND_DATABASE_SCHEMA must be lowercase letters, digits and underscores.")


def load_settings(environ: dict | None = None) -> Settings:
    env = os.environ if environ is None else environ
    data_dir = env.get("FAIRLEND_WEB_DATA")
    cache_dir = env.get("FAIRLEND_CACHE_DIR")
    return Settings(
        web_origins=_origins(env.get("FAIRLEND_WEB_ORIGINS")),
        host=env.get("FAIRLEND_API_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(env.get("FAIRLEND_API_PORT") or env.get("PORT") or "8000"),
        config_path=env.get("LENDING_MONITOR_CONFIG") or None,
        data_dir=Path(data_dir) if data_dir else DEFAULT_DATA_DIR,
        session_secret=env.get("FAIRLEND_SESSION_SECRET") or None,
        session_hours=float(env.get("FAIRLEND_SESSION_HOURS", "8")),
        cookie_secure=env.get("FAIRLEND_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes", "on"),
        database_url=(env.get("DATABASE_URL") or "").strip() or None,
        database_schema=(env.get("FAIRLEND_DATABASE_SCHEMA") or "").strip() or None,
        cache_dir=Path(cache_dir) if cache_dir else None,
        proxy_hops=max(0, int(env.get("FAIRLEND_PROXY_HOPS", "0") or 0)),
        requests_per_hour=max(1, int(env.get("FAIRLEND_REQUESTS_PER_HOUR", "5") or 5)),
        max_pending=max(1, int(env.get("FAIRLEND_MAX_PENDING", "50") or 50)),
    )
