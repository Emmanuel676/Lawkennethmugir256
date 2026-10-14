"""The app's error log (Phase 5.2). No Streamlit, no network.

When a page hits an unexpected error, the page shows "Something went wrong" with a short
error code, and log_exception() writes ONE entry to app.log_file (default data/logs/app.log,
git-ignored, rotating at app.log_max_bytes with app.log_backups old files).

An entry holds the time, the error code, the page, the exception TYPE and the code
locations of the traceback (file, line number, function). It never holds the exception's
message, local variables or source lines, because those can contain data values
(a message text, a borrower code). Real data is confidential.
"""

from __future__ import annotations

import hashlib
import logging
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import PROJECT_ROOT

DEFAULT_LOG = PROJECT_ROOT / "data" / "logs" / "app.log"
_handlers: dict[str, logging.Logger] = {}


def log_path(cfg: dict | None) -> Path:
    if not cfg:
        return DEFAULT_LOG
    path = Path(cfg["app"]["log_file"])
    return path if path.is_absolute() else PROJECT_ROOT / path


def _logger(path: Path, max_bytes: int, backups: int) -> logging.Logger:
    key = str(path.resolve())
    if key not in _handlers:
        path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"fairlend.app.{len(_handlers)}")
        logger.setLevel(logging.ERROR)
        logger.propagate = False  # never echoed to the console
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        _handlers[key] = logger
    return _handlers[key]


def _where(filename: str) -> str:
    """A project file relative to the project folder; other files by name only."""
    path = Path(filename)
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def safe_traceback(error: BaseException) -> list[str]:
    """'file:line in function' for each frame. No message, no source lines, no values."""
    return [f"{_where(frame.filename)}:{frame.lineno} in {frame.name}"
            for frame in traceback.extract_tb(error.__traceback__)]


def error_code(error: BaseException) -> str:
    """A short code to quote when reporting the problem, e.g. FW-3A9C1E."""
    seed = f"{type(error).__name__}{time.time_ns()}".encode("utf-8")
    return "FW-" + hashlib.sha1(seed).hexdigest()[:6].upper()


def log_exception(page: str, error: BaseException, cfg: dict | None = None) -> str:
    """Write one entry for an unexpected error and return its error code. Never raises."""
    code = error_code(error)
    try:
        app = (cfg or {}).get("app", {})
        logger = _logger(log_path(cfg), int(app.get("log_max_bytes", 2_000_000)), int(app.get("log_backups", 3)))
        frames = " | ".join(safe_traceback(error))
        logger.error(f"{code} page={page} type={type(error).__module__}.{type(error).__name__} traceback: {frames}")
    except Exception:  # the log must never break the page
        pass
    return code
