"""Build the synthetic demo on first start (Phase 8B). No Streamlit, no network.

A fresh server (Streamlit Community Cloud) has an empty data/ folder, because everything in
data/ is git-ignored, and it has no shell to run `python -m src.build_all`. So the app builds
the demo itself the first time it starts, and again whenever the demo is stale:

  missing  no lending.db, no manifest, no labels or no saved model
  stale    the data does not match its manifest fingerprint, the labels were made from other
           messages or are incomplete, a file cannot be read, or the saved model was trained
           with a different scikit-learn than the one installed
  fresh    nothing to do

The build regenerates the dataset from config.yaml and the seed, RETRAINS the local classifier
under the running Python and scikit-learn (a saved model is never trusted across versions), and
labels every message. It writes only the demo's own files (paths in config.yaml, data/ by default)
and two small control files next to them (.demo_build.lock and .demo_build_progress.json).

Build once: the first visitor takes a lock file (created with O_EXCL, so only one process or
thread can hold it); everyone else waits, reading the progress file, and sees the same steps.
A lock older than app.bootstrap.lock_timeout_seconds is treated as abandoned.

On failure nothing is shown but a short error code: the exception TYPE and code locations go to
the app log (src/app_log.py), never the message or any value. All data here is synthetic.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from src.app_log import log_exception
from src.config import resolve_path
from src.datasets import DEMO, get_dataset_paths

STEPS = ("Generate the synthetic demo dataset from config.yaml and the seed",
         "Train the message classifier and label every message",
         "Check the result")
LOCK_NAME = ".demo_build.lock"
PROGRESS_NAME = ".demo_build_progress.json"


class BuildFailed(RuntimeError):
    """The build ran but the demo is still not fresh afterwards."""


@dataclass
class Result:
    status: str          # 'fresh' (nothing to do), 'built', 'waited' (another visitor built it), 'failed'
    code: str = ""       # error code for 'failed' (see data/logs/app.log)
    reason: str = ""     # why a build was needed, in plain words (no values)

    @property
    def ok(self) -> bool:
        return self.status != "failed"


def _folder(cfg: dict) -> Path:
    return get_dataset_paths(cfg, DEMO).lending_db.parent


def lock_path(cfg: dict) -> Path:
    return _folder(cfg) / LOCK_NAME


def progress_path(cfg: dict) -> Path:
    return _folder(cfg) / PROGRESS_NAME


def demo_files(cfg: dict) -> list[Path]:
    """Every file the demo build writes (all inside the demo's folder, data/ by default)."""
    paths = get_dataset_paths(cfg, DEMO)
    model = resolve_path(cfg, "local_model")
    return [paths.lending_db, paths.ground_truth_db, resolve_path(cfg, "manifest"), paths.predictions_db,
            model, model.with_suffix(".json")]


def signature(cfg: dict) -> tuple:
    """Changes whenever a demo file changes (used to cache the status check)."""
    out = []
    for path in demo_files(cfg):
        try:
            stat = path.stat()
            out.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            out.append((str(path), None, None))
    return tuple(out)


def demo_status(cfg: dict) -> tuple[str, str]:
    """('fresh' | 'missing' | 'stale', a plain reason). Reads only; never raises for bad files."""
    from src import db
    from src.classify_messages import saved_model_note, sklearn_version
    from src.overlap import connect_read_only
    from src.predictions import StalePredictionsError, check_matches, read_predictions

    paths = get_dataset_paths(cfg, DEMO)
    manifest = resolve_path(cfg, "manifest")
    model = resolve_path(cfg, "local_model")
    if not paths.lending_db.exists() or not manifest.exists() or paths.ground_truth_db is None \
            or not paths.ground_truth_db.exists():
        return "missing", "the demo dataset has not been built yet"
    if not paths.predictions_db.exists() or not model.exists():
        return "missing", "the demo's message labels or model have not been made yet"
    note = saved_model_note(cfg)
    if note.get("sklearn_version") != sklearn_version():
        return "stale", "the saved model was trained with a different scikit-learn"
    try:
        expected = json.loads(manifest.read_text(encoding="utf-8")).get("lending_db_content_hash")
        lending = connect_read_only(paths.lending_db)
        try:
            if db.content_hash(lending) != expected:
                return "stale", "the demo data does not match its manifest"
            predictions = connect_read_only(paths.predictions_db)
            try:
                check_matches(predictions, lending)
                labelled = set(read_predictions(predictions, "local")["message_id"])
                messages = {row[0] for row in lending.execute("SELECT message_id FROM messages")}
            finally:
                predictions.close()
        finally:
            lending.close()
    except StalePredictionsError:
        return "stale", "the message labels were made from different messages"
    except (sqlite3.Error, OSError, ValueError):
        return "stale", "a demo file cannot be read"
    if not messages <= labelled:
        return "stale", "some demo messages have no label"
    return "fresh", ""


def build_demo(cfg: dict, on_step=None) -> None:
    """Generate the demo, retrain and label, then check. on_step(number, total, title) reports each step."""
    from src.classify_messages import classify_dataset, model_id, train_local_model
    from src.generate_data import generate, write_world

    paths = get_dataset_paths(cfg, DEMO)
    report = on_step or (lambda number, total, title: None)
    report(1, len(STEPS), STEPS[0])
    for path in demo_files(cfg):  # start clean: a damaged old file must never be reused
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
    write_world(generate(cfg), paths.lending_db, paths.ground_truth_db, resolve_path(cfg, "manifest"))
    report(2, len(STEPS), STEPS[1])
    model, n_train = train_local_model(cfg)  # retrained here, under the running scikit-learn
    classify_dataset(cfg, paths, model, f"Trained on {n_train:,} demo dev messages.", model_id(cfg))
    report(3, len(STEPS), STEPS[2])
    status, _ = demo_status(cfg)
    if status != "fresh":
        raise BuildFailed("the demo is still not complete after the build")


class BuildLock:
    """A lock FILE taken with O_CREAT | O_EXCL: one holder across processes and threads."""

    def __init__(self, path: Path, timeout_seconds: float):
        self.path = Path(path)
        self.timeout = float(timeout_seconds)
        self.held = False

    def _abandoned(self) -> bool:
        try:
            return time.time() - self.path.stat().st_mtime > self.timeout
        except OSError:
            return False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._abandoned():
                    self.path.unlink(missing_ok=True)  # the builder died: take over once
                    continue
                return False
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(json.dumps({"pid": os.getpid(), "started": time.time()}))
            self.held = True
            return True
        return False

    def busy(self) -> bool:
        return self.path.exists() and not self._abandoned()

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False


def _write_progress(cfg: dict, **values) -> None:
    path = progress_path(cfg)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({**values, "time": time.time()}), encoding="utf-8")
    os.replace(temporary, path)


def read_progress(cfg: dict) -> dict:
    try:
        return json.loads(progress_path(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ensure_demo(cfg: dict, on_step=None, sleep=time.sleep, builder=None) -> Result:
    """Make sure the demo is fresh: build it (once) if not, or wait for whoever is building it.

    on_step(number, total, title) is called for every step, both by the builder and by the waiters.
    Never raises: a failure is Result('failed', code) and the details go to the app log.
    """
    status, reason = demo_status(cfg)
    if status == "fresh":
        return Result("fresh")
    boot = cfg["app"]["bootstrap"]
    lock = BuildLock(lock_path(cfg), boot["lock_timeout_seconds"])
    report = on_step or (lambda number, total, title: None)
    try:
        if lock.acquire():
            try:
                status, reason = demo_status(cfg)  # someone may have finished just before we took the lock
                if status == "fresh":
                    return Result("fresh")

                def step(number, total, title):
                    _write_progress(cfg, step=number, total=total, title=title)
                    report(number, total, title)

                (builder or build_demo)(cfg, step)
                _write_progress(cfg, done=True, total=len(STEPS), step=len(STEPS), title="Ready")
                return Result("built", reason=reason)
            except Exception as error:
                code = log_exception("Demo build", error, cfg)
                try:
                    _write_progress(cfg, failed=code, total=len(STEPS), step=0, title="Failed")
                except OSError:
                    pass
                return Result("failed", code, reason)
            finally:
                lock.release()

        # Someone else is building: follow their progress until the lock is gone.
        started, seen = time.time(), None
        while lock.busy() and time.time() - started < float(boot["lock_timeout_seconds"]):
            progress = read_progress(cfg)
            current = (progress.get("step"), progress.get("title"))
            if progress.get("title") and current != seen:
                report(int(progress.get("step") or 0), int(progress.get("total") or len(STEPS)), progress["title"])
                seen = current
            sleep(float(boot["wait_poll_seconds"]))
        progress = read_progress(cfg)
        if progress.get("failed"):
            return Result("failed", str(progress["failed"]), reason)
        status, _ = demo_status(cfg)
        if status == "fresh":
            return Result("waited", reason=reason)
        return Result("failed", log_exception("Demo build wait", TimeoutError("demo build did not finish"), cfg),
                      reason)
    except Exception as error:  # e.g. data/ cannot be written: still never a traceback
        return Result("failed", log_exception("Demo build", error, cfg), reason)
