"""Phase 8B: building the synthetic demo on first start (Streamlit Community Cloud has an empty data/)."""

from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.bootstrap as bootstrap
from src.bootstrap import BuildLock, Result, demo_status, ensure_demo, lock_path, progress_path
from src.config import load_config
from src.dashboard_ui import CONFIG_VARIABLE
from src.datasets import PRESENT_VARIABLE, presentation_mode

from leak_check import forbidden_mentions
from worlds import config_for, write_config

ROOT = Path(__file__).resolve().parents[1]
SECRET = "Pay 0772 123 456 B-3f9a1c2d4e5b"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """A config whose demo lives in an EMPTY tmp data folder; small, so a build takes a few seconds."""
    custom = config_for(tmp_path / "data", load_config())
    custom["generator"]["n_borrowers"] = 300
    custom["generator"]["test_set_size"] = 40
    custom["app"]["log_file"] = str(tmp_path / "data" / "logs" / "app.log")
    (tmp_path / "data").mkdir()
    monkeypatch.delenv(PRESENT_VARIABLE, raising=False)
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(custom, tmp_path / "config.yaml")))
    return custom


def _log(cfg) -> str:
    path = Path(cfg["app"]["log_file"])
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- Status ---------------------------------------------------------------------------------------------------

def test_an_empty_folder_is_missing_then_fresh_after_a_build(cfg):
    assert demo_status(cfg)[0] == "missing"
    steps = []
    result = ensure_demo(cfg, on_step=lambda n, t, title: steps.append((n, t)))
    assert result.status == "built" and result.ok
    assert steps == [(1, 3), (2, 3), (3, 3)]
    assert demo_status(cfg) == ("fresh", "")
    note = json.loads(Path(cfg["paths"]["local_model"]).with_suffix(".json").read_text(encoding="utf-8"))
    import sklearn
    assert note["sklearn_version"] == sklearn.__version__  # retrained under the installed scikit-learn
    assert not lock_path(cfg).exists()


def test_a_fresh_demo_is_not_built_again(cfg):
    assert ensure_demo(cfg).status == "built"

    def must_not_run(*_args):
        raise AssertionError("built again")

    assert ensure_demo(cfg, builder=must_not_run).status == "fresh"


@pytest.mark.parametrize("damage, reason", [
    ("edit_message", "does not match its manifest"),
    ("model_version", "different scikit-learn"),
    ("drop_labels", "different messages"),
    ("corrupt_db", "cannot be read"),
    ("delete_model", "have not been made yet"),
])
def test_a_stale_demo_is_rebuilt(cfg, damage, reason):
    assert ensure_demo(cfg).status == "built"
    data = Path(cfg["paths"]["lending_db"]).parent
    if damage == "edit_message":
        conn = sqlite3.connect(cfg["paths"]["lending_db"])
        conn.execute("UPDATE messages SET text = 'changed' WHERE rowid = 1")
        conn.commit()
        conn.close()
    elif damage == "model_version":
        note = Path(cfg["paths"]["local_model"]).with_suffix(".json")
        info = json.loads(note.read_text(encoding="utf-8"))
        info["sklearn_version"] = "0.0.1"
        note.write_text(json.dumps(info), encoding="utf-8")
    elif damage == "drop_labels":
        conn = sqlite3.connect(cfg["paths"]["predictions_db"])
        conn.execute("UPDATE meta SET value = 'other' WHERE key = 'messages_fingerprint'")
        conn.commit()
        conn.close()
    elif damage == "corrupt_db":
        Path(cfg["paths"]["predictions_db"]).write_bytes(b"not a database" * 100)
    else:
        Path(cfg["paths"]["local_model"]).unlink()
    status, why = demo_status(cfg)
    assert status in ("stale", "missing") and reason in why
    assert ensure_demo(cfg).status == "built"
    assert demo_status(cfg)[0] == "fresh"
    assert sorted(p.name for p in data.iterdir() if p.is_file()) == sorted(
        [".demo_build_progress.json", "dataset_manifest.json", "ground_truth.db", "lending.db",
         "local_model.joblib", "local_model.json", "predictions.db"])


# --- Build once ------------------------------------------------------------------------------------------------

def test_two_visitors_at_once_build_only_once(cfg):
    calls, results = [], []
    real = bootstrap.build_demo

    def slow_builder(config, on_step):
        calls.append(threading.get_ident())
        time.sleep(1.0)  # give the second visitor time to arrive while the first one builds
        real(config, on_step)

    seen = {1: [], 2: []}

    def visitor(number):
        results.append(ensure_demo(cfg, on_step=lambda n, t, title: seen[number].append(n),
                                   sleep=lambda s: time.sleep(0.05), builder=slow_builder))

    threads = [threading.Thread(target=visitor, args=(n,)) for n in (1, 2)]
    for thread in threads:
        thread.start()
        time.sleep(0.2)
    for thread in threads:
        thread.join(timeout=300)
    assert len(calls) == 1, "the demo was built more than once"
    assert sorted(r.status for r in results) == ["built", "waited"]
    assert seen[2] and seen[2][-1] >= 2  # the waiting visitor saw the builder's real steps
    assert demo_status(cfg)[0] == "fresh"  # no corruption
    assert not lock_path(cfg).exists()


def test_an_abandoned_lock_is_taken_over(cfg):
    lock = lock_path(cfg)
    lock.write_text("{}", encoding="utf-8")
    old = time.time() - cfg["app"]["bootstrap"]["lock_timeout_seconds"] - 5
    os.utime(lock, (old, old))
    assert ensure_demo(cfg).status == "built"


def test_a_held_lock_makes_others_wait_and_report_the_builders_failure(cfg):
    lock = BuildLock(lock_path(cfg), 900)
    assert lock.acquire()
    assert not BuildLock(lock_path(cfg), 900).acquire()  # only one holder
    progress_path(cfg).write_text(json.dumps({"failed": "FW-ABC123", "step": 0, "total": 3, "title": "Failed"}),
                                  encoding="utf-8")
    released = threading.Timer(0.3, lock.release)
    released.start()
    result = ensure_demo(cfg, sleep=lambda s: time.sleep(0.05))
    released.join()
    assert result == Result("failed", "FW-ABC123", result.reason)


# --- Failure leaks nothing -----------------------------------------------------------------------------------------

def test_a_failed_build_gives_a_code_and_logs_the_type_only(cfg):
    def broken(config, on_step):
        on_step(1, 3, "Generate")
        raise ValueError(SECRET)

    result = ensure_demo(cfg, builder=broken)
    assert result.status == "failed" and re.fullmatch(r"FW-[0-9A-F]{6}", result.code)
    log = _log(cfg)
    assert result.code in log and "type=builtins.ValueError" in log and "page=Demo build" in log
    assert "0772" not in log and "B-3f9a" not in log and "Pay " not in log
    assert json.loads(progress_path(cfg).read_text(encoding="utf-8"))["failed"] == result.code
    assert not lock_path(cfg).exists()  # the lock is released after a failure


def test_an_unwritable_data_folder_fails_politely(cfg, tmp_path):
    blocked = copy.deepcopy(cfg)
    not_a_folder = tmp_path / "blocked"
    not_a_folder.write_text("a file, not a folder", encoding="utf-8")
    for key in ("lending_db", "ground_truth_db", "manifest", "predictions_db", "local_model"):
        blocked["paths"][key] = str(not_a_folder / Path(cfg["paths"][key]).name)
    result = ensure_demo(blocked)
    assert result.status == "failed" and result.code.startswith("FW-")


# --- In the app ----------------------------------------------------------------------------------------------------

def _run(page="app.py", secrets=None) -> AppTest:
    at = AppTest.from_file(str(ROOT / page), default_timeout=600)
    for key, value in (secrets or {}).items():
        at.secrets[key] = value
    return at.run()


def test_the_app_builds_the_demo_on_first_start_in_presentation_mode(cfg, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    assert demo_status(cfg)[0] == "missing"
    at = _run()
    assert not at.exception, [e.value for e in at.exception]
    assert not any("Something went wrong" in e.value or "could not be prepared" in e.value for e in at.error)
    assert any(m.label == "Borrowers scored" and m.value == "300" for m in at.metric)
    assert demo_status(cfg)[0] == "fresh"
    at = _run("pages/0_Guided_Demo.py")  # a second visitor: nothing to build
    assert sum(m.value.startswith("### ") for m in at.markdown) == 6
    for page in ("pages/5_Data.py", "pages/6_Review.py"):
        assert any("switched off in presentation mode" in i.value for i in _run(page).info)
    assert "Try a message" not in [s.value for s in _run("pages/2_Lenders.py").subheader]


def test_a_failed_first_start_shows_a_plain_message(cfg, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")

    def broken(config, on_step):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(bootstrap, "build_demo", broken)
    at = _run()
    assert not at.exception, [e.value for e in at.exception]
    message = next(e.value for e in at.error if "could not be prepared" in e.value)
    assert re.search(r"error code FW-[0-9A-F]{6}", message)
    assert SECRET not in message and "Traceback" not in message
    assert any("Preparing the demo: about 1 minute(s), first start only" in i.value for i in at.info)


@pytest.mark.parametrize("mode, present, builds", [
    ("presentation", None, False), ("presentation", "1", True), ("always", None, True), ("never", "1", False),
])
def test_when_the_app_builds_by_itself(cfg, monkeypatch, tmp_path, mode, present, builds):
    custom = copy.deepcopy(cfg)
    custom["app"]["bootstrap"]["auto_build"] = mode
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(custom, tmp_path / "mode.yaml")))
    if present:
        monkeypatch.setenv(PRESENT_VARIABLE, present)
    at = _run()
    assert not at.exception
    assert (demo_status(custom)[0] == "fresh") is builds
    if not builds:
        assert any("No dataset found" in e.value for e in at.error)  # the old instructions, nothing written


def test_presentation_mode_comes_from_the_environment_variable(cfg, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    assert presentation_mode(cfg)
    monkeypatch.setenv(PRESENT_VARIABLE, "0")
    cfg["app"]["presentation_mode"] = True
    assert not presentation_mode(cfg)


def test_presentation_mode_from_streamlit_secrets_too(cfg, monkeypatch):
    """Streamlit Cloud: a top-level secret. If only st.secrets has it, the app copies it to the environment."""
    custom = copy.deepcopy(cfg)
    custom["app"]["bootstrap"]["auto_build"] = "never"  # only the mode is under test here
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(custom, Path(cfg["app"]["log_file"]).parents[2] / "s.yaml")))
    monkeypatch.delenv(PRESENT_VARIABLE, raising=False)
    try:
        at = _run(secrets={PRESENT_VARIABLE: "1"})
        assert not at.exception
        assert any("Presentation mode" in m.value for m in at.sidebar.markdown)
    finally:
        os.environ.pop(PRESENT_VARIABLE, None)


# --- Requirements split and code checks ---------------------------------------------------------------------------------

def _requirements(name):
    return [line.strip() for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def test_the_app_requirements_are_pinned_and_exclude_dev_tools():
    lines = _requirements("requirements.txt")
    assert lines and all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][0-9A-Za-z.\-]*", line) for line in lines), lines
    names = {line.split("==")[0].lower() for line in lines}
    assert {"pytest", "google-genai"}.isdisjoint(names)
    assert {"streamlit", "pandas", "numpy", "scikit-learn", "pyyaml", "openpyxl", "joblib", "altair"} <= names


def test_dev_requirements_add_the_tools():
    lines = _requirements("requirements-dev.txt")
    assert lines[0] == "-r requirements.txt"
    assert all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][0-9A-Za-z.\-]*", line) for line in lines[1:])
    assert {line.split("==")[0] for line in lines[1:]} == {"pytest", "google-genai"}


THIRD_PARTY = {"altair": "altair", "joblib": "joblib", "numpy": "numpy", "openpyxl": "openpyxl", "pandas": "pandas",
               "sklearn": "scikit-learn", "streamlit": "streamlit", "yaml": "pyyaml"}


def test_every_package_the_app_imports_is_in_requirements():
    import ast
    import sys
    names = {line.split("==")[0].lower() for line in _requirements("requirements.txt")}
    files = ["app.py", *(f"pages/{p.name}" for p in (ROOT / "pages").glob("*.py")),
             *(f"src/{p.name}" for p in (ROOT / "src").glob("*.py") if p.name != "gemini_check.py")]
    missing = set()
    for file in files:
        for node in ast.walk(ast.parse((ROOT / file).read_text(encoding="utf-8"))):
            modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
                       else [])
            for module in modules:
                top = module.split(".")[0]
                if top in sys.stdlib_module_names or top in ("src", "__future__"):
                    continue
                if THIRD_PARTY.get(top, top) not in names:
                    missing.add(f"{file}: {top}")
    assert missing == set()


def test_the_bootstrap_never_names_the_network_or_secrets():
    source = (ROOT / "src" / "bootstrap.py").read_text(encoding="utf-8")
    assert forbidden_mentions(source, ("requests", "urllib", "genai", "socket", "dotenv", ".env", "http")) == []
    assert "print(" not in source


def test_streamlit_settings_hold_no_secret_and_send_no_statistics():
    settings = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "gatherUsageStats = false" in settings
    assert not re.search(r"(?i)(key|token|password|secret)\s*=", settings)
    assert ".streamlit/secrets.toml" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
