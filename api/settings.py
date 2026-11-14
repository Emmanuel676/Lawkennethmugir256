"""API settings, read from environment variables once at start-up. Nothing here is secret.

  FAIRLEND_WEB_ORIGINS     comma-separated front-end origins allowed by CORS (default http://localhost:3000)
  FAIRLEND_API_HOST        address uvicorn listens on (default 127.0.0.1: this computer only)
  FAIRLEND_API_PORT        port (default 8000)
  LENDING_MONITOR_CONFIG   another config.yaml (the same variable the Streamlit app and the tests use)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_ORIGIN = "http://localhost:3000"


def _origins(raw: str | None) -> list[str]:
    values = [part.strip().rstrip("/") for part in (raw or "").split(",")]
    return [value for value in values if value] or [DEFAULT_ORIGIN]


@dataclass(frozen=True)
class Settings:
    web_origins: list[str] = field(default_factory=lambda: [DEFAULT_ORIGIN])
    host: str = "127.0.0.1"
    port: int = 8000
    config_path: str | None = None


def load_settings(environ: dict | None = None) -> Settings:
    env = os.environ if environ is None else environ
    return Settings(
        web_origins=_origins(env.get("FAIRLEND_WEB_ORIGINS")),
        host=env.get("FAIRLEND_API_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(env.get("FAIRLEND_API_PORT", "8000")),
        config_path=env.get("LENDING_MONITOR_CONFIG") or None,
    )
