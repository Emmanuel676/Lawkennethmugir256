"""Team access on the public (presentation-mode) deployment (Phase 11). No Streamlit, no network.

The live app runs in presentation mode, which switches the Data and Review pages off for everyone. A small team can
unlock them FOR THEIR OWN BROWSER SESSION with an access code, to demonstrate importing the synthetic sample packs:

  - Codes are never stored anywhere. Only their SHA-256 hashes are configured (FAIRLEND_ACCESS_HASHES, a Streamlit
    secret or environment variable). No hash configured = nobody can unlock (the app behaves as before).
  - A wrong code shows only "Code not recognised." After team_demo.max_attempts wrong codes in one session, that
    session cannot try again for team_demo.lockout_minutes.
  - An unlocked session works on a PRIVATE temporary copy of the demo files (its own folder). Its config points every
    data path there, so the shared demo files are never written. The copy is deleted by "Lock again", by "Reset my
    demo copy", when the session's state is dropped, and by a sweep of folders whose session has ended or that are
    older than team_demo.max_session_hours.
  - Every upload in an unlocked session must pass a synthetic-only gate (synthetic_gate) before anything is checked
    or written: "(Demo)" lenders, "(SYNTHETIC)" messages, no phone-, ID- or email-like strings in names or message
    text, and size and row limits. Real data cannot be imported through the public link.

Nothing here prints or logs a code, a hash or any uploaded value.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
import secrets
import shutil
import tempfile
import time
import weakref
from pathlib import Path

from src.config import resolve_path
from src.import_data import read_csvs, read_xlsx
from src.redaction import build_redactor

HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
NOT_RECOGNISED = "Code not recognised."
SESSION_ROOT_NAME = "fairlend_team_sessions"
MARKER = "session.json"
COPIED_PATHS = ("lending_db", "ground_truth_db", "predictions_db", "manifest", "local_model")
BANNER = ("Team demo session. Synthetic data only. Your changes are private to this session and are deleted when "
          "you leave.")
DEMO_SUFFIX = "(Demo)"
SYNTHETIC_SUFFIX = "(SYNTHETIC)"


# --- Codes and hashes ---------------------------------------------------------------------------------------------

def hash_code(code: str) -> str:
    """The SHA-256 hash (lowercase hex) of an access code, ignoring spaces around it."""
    return hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()


def parse_hashes(value) -> list[str]:
    """Valid hashes from a secret or environment value: a list, or text with commas, spaces or a [..] list.

    Anything that is not 64 hex characters is ignored (never printed). Missing or empty = no hashes.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    else:
        items = re.split(r"[\s,;]+", str(value).strip().strip("[]"))
    cleaned = [item.strip().strip("'\"").lower() for item in items]
    return sorted({h for h in cleaned if HASH_PATTERN.fullmatch(h)})


def matching_hash(code: str, hashes: list[str]) -> str | None:
    """The configured hash this code matches, or None. Every hash is compared (hmac.compare_digest)."""
    if not code or not str(code).strip() or not hashes:
        return None
    candidate = hash_code(code)
    found = None
    for stored in hashes:
        if hmac.compare_digest(candidate, stored):
            found = stored
    return found


# --- Throttle (per session) -----------------------------------------------------------------------------------------

def throttled_for(state: dict, settings: dict, now: float | None = None) -> int:
    """Seconds this session must still wait before another attempt (0 = it may try)."""
    now = time.time() if now is None else now
    until = float(state.get("team_locked_until", 0))
    return max(0, int(round(until - now)))


def record_attempt(state: dict, ok: bool, settings: dict, now: float | None = None) -> None:
    """Count a wrong attempt; after max_attempts, refuse attempts for lockout_minutes. A right one resets the count."""
    now = time.time() if now is None else now
    if ok:
        state["team_failures"] = 0
        state["team_locked_until"] = 0
        return
    state["team_failures"] = int(state.get("team_failures", 0)) + 1
    if state["team_failures"] >= int(settings["max_attempts"]):
        state["team_locked_until"] = now + 60 * float(settings["lockout_minutes"])
        state["team_failures"] = 0


# --- The private copy -----------------------------------------------------------------------------------------------------

def session_root() -> Path:
    return Path(tempfile.gettempdir()) / SESSION_ROOT_NAME


def _demo_sources(cfg: dict) -> dict[str, Path]:
    sources = {key: resolve_path(cfg, key) for key in COPIED_PATHS if cfg["paths"].get(key)}
    if "local_model" in sources:
        sources["local_model_note"] = sources["local_model"].with_suffix(".json")
    return sources


def session_config(cfg: dict, folder: Path) -> dict:
    """A copy of the config whose every data path points into the session's private folder.

    app.team_session marks it: dataset choice then works inside the private folder only (see
    src/datasets.presentation_mode), and the Data page applies the synthetic-only gate.
    """
    private = copy.deepcopy(cfg)
    folder = Path(folder)
    for key, source in _demo_sources(cfg).items():
        if key in private["paths"]:
            private["paths"][key] = str(folder / source.name)
    private["paths"]["datasets_dir"] = str(folder / "datasets")
    private["paths"]["active_dataset_file"] = str(folder / "active_dataset.txt")
    private["app"]["team_session"] = True
    return private


class PrivateCopy:
    """A session's private folder. Kept in the session's state: when that state is dropped (the session ended),
    the folder is deleted (weakref.finalize, also at interpreter exit)."""

    def __init__(self, cfg: dict, session_id: str = "", root: Path | None = None):
        root = Path(root) if root else session_root()
        root.mkdir(parents=True, exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(prefix="team_", dir=root))
        (self.folder / MARKER).write_text(json.dumps({"session": session_id, "created": time.time()}),
                                          encoding="utf-8")
        for key, source in _demo_sources(cfg).items():
            if source.exists():
                shutil.copy2(source, self.folder / source.name)
        (self.folder / "datasets").mkdir()
        self.config = session_config(cfg, self.folder)
        self._finalizer = weakref.finalize(self, shutil.rmtree, str(self.folder), True)

    def delete(self) -> None:
        self._finalizer()

    @property
    def alive(self) -> bool:
        return self._finalizer.alive and self.folder.exists()


def sweep(root: Path | None = None, max_age_hours: float = 6.0, is_active=None, now: float | None = None) -> int:
    """Delete private folders whose session has ended (is_active(session_id) is False) or that are too old.

    Streamlit has no reliable "session ended" event, so this runs whenever any page loads. Returns the number removed.
    """
    root = Path(root) if root else session_root()
    now = time.time() if now is None else now
    removed = 0
    if not root.is_dir():
        return 0
    for folder in root.iterdir():
        if not folder.is_dir() or not folder.name.startswith("team_"):
            continue
        try:
            info = json.loads((folder / MARKER).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {"session": "", "created": folder.stat().st_mtime}
        old = now - float(info.get("created", 0)) > 3600 * float(max_age_hours)
        ended = bool(info.get("session")) and is_active is not None and not is_active(info["session"])
        if old or ended:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


def new_session_token() -> str:
    return secrets.token_hex(8)


# --- The synthetic-only gate --------------------------------------------------------------------------------------------

def _rows(numbers: list[int]) -> str:
    shown = ", ".join(str(n) for n in numbers[:10])
    return shown + (f" and {len(numbers) - 10} more" if len(numbers) > 10 else "")


def synthetic_gate(files: dict[str, bytes], file_type: str, cfg: dict) -> list[str]:
    """Plain reasons to refuse an upload in a team session (empty = it may go on to the normal checks).

    Works on the uploaded bytes in memory; nothing is written. Messages give file, column and row numbers, never values.
    """
    limits = cfg["team_demo"]
    total = sum(len(content) for content in files.values())
    if total > float(limits["max_upload_mb"]) * 1024 * 1024:
        return [f"The upload is {total / 1024 / 1024:.1f} MB; team demo sessions accept at most "
                f"{limits['max_upload_mb']} MB."]
    upload = read_xlsx(next(iter(files.values()))) if file_type == "xlsx" else read_csvs(files)
    problems = []
    redactor = build_redactor(cfg, names=[])
    for table, frame in upload.tables.items():
        source = upload.sources.get(table, table)
        if len(frame) > int(limits["max_rows_per_file"]):
            problems.append(f"{source} has {len(frame):,} rows; team demo sessions accept at most "
                            f"{int(limits['max_rows_per_file']):,} rows per file.")

    def personal_like(column_frame, column: str, source: str, what: str) -> None:
        hits = [int(row) for text, row in zip(column_frame[column].astype(str), column_frame["_row"])
                if any(n for token, n in redactor.redact(text)[1].items() if token in ("PHONE", "ID", "EMAIL"))]
        if hits:
            problems.append(f"{source}: {len(hits)} {what} contain something that looks like a phone number, an ID "
                            f"number or an email address (rows {_rows(hits)}). Team demo sessions accept synthetic "
                            "data only.")

    lenders = upload.tables.get("lenders")
    if lenders is not None and "name" in lenders.columns:
        bad = [int(r) for name, r in zip(lenders["name"].astype(str), lenders["_row"])
               if not name.strip().endswith(DEMO_SUFFIX)]
        if bad:
            problems.append(f"{upload.sources['lenders']}: {len(bad)} lender name(s) do not end with "
                            f"'{DEMO_SUFFIX}' (rows {_rows(bad)}). Only fictional '(Demo)' lenders may be uploaded here.")
        personal_like(lenders, "name", upload.sources["lenders"], "lender name(s)")
    messages = upload.tables.get("messages")
    if messages is not None and "text" in messages.columns:
        bad = [int(r) for text, r in zip(messages["text"].astype(str), messages["_row"])
               if not text.strip().endswith(SYNTHETIC_SUFFIX)]
        if bad:
            problems.append(f"{upload.sources['messages']}: {len(bad)} message(s) do not end with "
                            f"'{SYNTHETIC_SUFFIX}' (rows {_rows(bad)}). Only synthetic messages may be uploaded here.")
        personal_like(messages, "text", upload.sources["messages"], "message(s)")
    return problems
