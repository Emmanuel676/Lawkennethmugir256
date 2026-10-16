"""Phase 11: team access on the public (presentation-mode) deployment.

Codes used here are made up for the tests. Every page test runs headless with a small classified demo in a
temporary folder; the private copies go to a temporary sessions folder. All data is synthetic.
"""

from __future__ import annotations

import gc
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.team_access as ta
from src import db
from src.config import ConfigError, load_config, resolve_path, validate_config
from src.dashboard_ui import CONFIG_VARIABLE, PRESENTATION_BLOCKED
from src.import_data import TABLES
from src.make_sample_pack import build_scenario

from leak_check import forbidden_mentions
from tiny_data import csv_bytes, tiny_rows
from worlds import build_classified_world

ROOT = Path(__file__).resolve().parents[1]
CODE = "TestCode-Only-42x"            # made up for the tests
OTHER_CODE = "Another-Test-Code9"
DEMO_FINGERPRINT = "3945277a047220916234197d5844183d2ae84313ad9ba5fced6246ffe5d3df9e"
SHARED_KEYS = ("lending_db", "ground_truth_db", "predictions_db", "manifest", "local_model")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    cfg, config_path = build_classified_world(tmp_path_factory.mktemp("team_world"), n_borrowers=300)
    packs = tmp_path_factory.mktemp("team_packs")
    build_scenario(load_config(), "baseline", packs)
    return cfg, config_path, packs


@pytest.fixture
def env(built, tmp_path, monkeypatch):
    """Presentation mode on, one configured hash, private copies in a temporary sessions folder."""
    cfg, config_path, packs = built
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(ta, "session_root", lambda: sessions)
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    monkeypatch.setenv("FAIRLEND_PRESENT", "1")
    monkeypatch.setenv("FAIRLEND_ACCESS_HASHES", sha(CODE))
    return {"cfg": cfg, "packs": packs, "sessions": sessions}


def run(page: str) -> AppTest:
    return AppTest.from_file(str(ROOT / page), default_timeout=300).run()


def unlock(at: AppTest, code: str = CODE) -> AppTest:
    at.text_input(key="team_code_input").input(code)
    return at.button(key="team_unlock").click().run()


def shared_digests(cfg: dict) -> dict[str, str]:
    out = {}
    for key in SHARED_KEYS:
        path = resolve_path(cfg, key)
        out[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        note = path.with_suffix(".json")
        if key == "local_model" and note.exists():
            out["local_model_note"] = hashlib.sha256(note.read_bytes()).hexdigest()
    return out


def visible_text(at: AppTest) -> str:
    parts = []
    for group in (at.markdown, at.error, at.warning, at.info, at.success, at.caption):
        parts += [str(e.value) for e in group]
    return "\n".join(parts)


# --- Codes, hashes and the throttle ------------------------------------------------------------------------------

def test_hashes_are_read_from_a_list_or_text_and_bad_entries_are_ignored():
    good, other = sha(CODE), sha(OTHER_CODE)
    assert ta.parse_hashes([good, other.upper()]) == sorted([good, other])
    assert ta.parse_hashes(f'["{good}", "{other}"]') == sorted([good, other])
    assert ta.parse_hashes(f"{good}, {other}") == sorted([good, other])
    assert ta.parse_hashes("not-a-hash, 1234") == []
    assert ta.parse_hashes(None) == [] and ta.parse_hashes("") == [] and ta.parse_hashes([]) == []


def test_only_the_right_code_matches():
    hashes = ta.parse_hashes([sha(CODE), sha(OTHER_CODE)])
    assert ta.matching_hash(CODE, hashes) == sha(CODE)
    assert ta.matching_hash(f"  {OTHER_CODE} ", hashes) == sha(OTHER_CODE)
    for wrong in ("", "   ", CODE.lower(), CODE + "x", sha(CODE)):
        assert ta.matching_hash(wrong, hashes) is None
    assert ta.matching_hash(CODE, []) is None  # no hash configured: nothing unlocks


def test_the_throttle_refuses_after_five_wrong_attempts_for_ten_minutes():
    settings = load_config()["team_demo"]
    state, now = {}, 1_000_000.0
    for _ in range(4):
        ta.record_attempt(state, False, settings, now)
    assert ta.throttled_for(state, settings, now) == 0
    ta.record_attempt(state, False, settings, now)
    assert ta.throttled_for(state, settings, now) == 600
    assert ta.throttled_for(state, settings, now + 599) == 1 and ta.throttled_for(state, settings, now + 600) == 0
    ta.record_attempt(state, True, settings, now + 700)
    assert state["team_failures"] == 0 and ta.throttled_for(state, settings, now + 700) == 0


@pytest.mark.parametrize("change, message", [
    (lambda c: c.pop("team_demo"), "missing the 'team_demo' section"),
    (lambda c: c["team_demo"].__setitem__("max_attempts", 0), "max_attempts"),
    (lambda c: c["team_demo"].__setitem__("max_upload_mb", -1), "max_upload_mb"),
    (lambda c: c["team_demo"].__setitem__("lockout_minutes", True), "lockout_minutes"),
])
def test_bad_team_demo_settings_give_a_plain_error(change, message):
    broken = load_config()
    change(broken)
    with pytest.raises(ConfigError, match=message):
        validate_config(broken)


# --- The synthetic-only gate --------------------------------------------------------------------------------------------

def _pack_files(packs: Path, folder: str = "lender_A") -> dict[str, bytes]:
    return {f"{t}.csv": (packs / "baseline" / folder / f"{t}.csv").read_bytes() for t in TABLES}


def test_the_gate_accepts_a_sample_pack(built):
    cfg, _, packs = built
    for folder in ("lender_A", "lender_D", "all_lenders"):
        assert ta.synthetic_gate(_pack_files(packs, folder), "csv", cfg) == []


def test_the_gate_refuses_real_looking_data_without_echoing_it(built):
    cfg, _, _ = built
    problems = ta.synthetic_gate(csv_bytes(tiny_rows()), "csv", cfg)
    text = " ".join(problems)
    assert "do not end with '(Demo)'" in text and "do not end with '(SYNTHETIC)'" in text
    assert "looks like a phone number" in text
    for value in ("0772", "Alpha Credit", "collections@beta.example"):
        assert value not in text


def test_the_gate_refuses_phone_like_text_even_in_synthetic_looking_messages(built):
    cfg, _, packs = built
    files = _pack_files(packs)
    lines = files["messages.csv"].decode("utf-8").splitlines()
    lines[1] = lines[1].replace(" (SYNTHETIC)", " Call 0772 123 456. (SYNTHETIC)")
    files["messages.csv"] = ("\n".join(lines) + "\n").encode("utf-8")
    problems = ta.synthetic_gate(files, "csv", cfg)
    assert len(problems) == 1 and "rows 2" in problems[0] and "0772" not in problems[0]


def test_the_gate_enforces_size_and_row_limits(built):
    cfg, _, packs = built
    small = json.loads(json.dumps(cfg))
    small["team_demo"]["max_rows_per_file"] = 10
    assert any("rows per file" in p for p in ta.synthetic_gate(_pack_files(packs), "csv", small))
    small["team_demo"]["max_upload_mb"] = 0.01
    assert "at most 0.01 MB" in ta.synthetic_gate(_pack_files(packs), "csv", small)[0]


# --- The private copy -----------------------------------------------------------------------------------------------------

def test_a_private_copy_points_every_data_path_into_its_own_folder(built, tmp_path):
    cfg, _, _ = built
    copy_ = ta.PrivateCopy(cfg, "s1", root=tmp_path)
    private = copy_.config
    for key in ("lending_db", "ground_truth_db", "predictions_db", "manifest", "local_model", "datasets_dir",
                "active_dataset_file"):
        assert Path(private["paths"][key]).parent == copy_.folder or Path(private["paths"][key]) == \
            copy_.folder / "datasets", key
    assert private["app"]["team_session"] is True and "team_session" not in cfg["app"]
    assert (copy_.folder / Path(cfg["paths"]["lending_db"]).name).exists()
    copy_.delete()
    assert not copy_.folder.exists()


def test_a_private_copy_is_deleted_when_its_session_state_is_dropped(built, tmp_path):
    cfg, _, _ = built
    copy_ = ta.PrivateCopy(cfg, "s2", root=tmp_path)
    folder = copy_.folder
    del copy_
    gc.collect()
    assert not folder.exists()


def test_the_sweep_removes_ended_and_old_sessions_only(built, tmp_path):
    cfg, _, _ = built
    alive, ended, old = (ta.PrivateCopy(cfg, s, root=tmp_path) for s in ("alive", "ended", "old"))
    marker = json.loads((old.folder / ta.MARKER).read_text(encoding="utf-8"))
    (old.folder / ta.MARKER).write_text(json.dumps({**marker, "created": time.time() - 7 * 3600}), encoding="utf-8")
    removed = ta.sweep(tmp_path, max_age_hours=6, is_active=lambda sid: sid in ("alive", "old"))
    assert removed == 2 and alive.folder.exists() and not ended.folder.exists() and not old.folder.exists()


# --- Pages: locked behaviour is unchanged ----------------------------------------------------------------------------------

@pytest.mark.parametrize("page", ["pages/5_Data.py", "pages/6_Review.py"])
def test_without_a_configured_hash_the_pages_are_exactly_as_before(env, monkeypatch, page):
    for value in (None, "", "not-a-hash"):
        if value is None:
            monkeypatch.delenv("FAIRLEND_ACCESS_HASHES", raising=False)
        else:
            monkeypatch.setenv("FAIRLEND_ACCESS_HASHES", value)
        at = run(page)
        assert any(PRESENTATION_BLOCKED in i.value for i in at.info)
        assert len(at.button) == 0 and len(at.text_input) == 0 and len(at.tabs) == 0


def test_with_a_hash_the_locked_page_shows_only_the_team_access_box(env):
    at = run("pages/5_Data.py")
    assert any(PRESENTATION_BLOCKED in i.value for i in at.info)
    assert [s.value for s in at.sidebar.subheader] == ["Team access"]
    assert at.text_input(key="team_code_input").proto.type == 1  # PASSWORD
    assert len(at.tabs) == 0 and len(at.get("file_uploader")) == 0


@pytest.mark.parametrize("page", ["app.py", "pages/1_Borrowers.py", "pages/3_Export.py"])
def test_other_pages_have_no_team_access_box(env, page):
    at = run(page)
    assert not at.exception
    assert not any(box.key == "team_code_input" for box in at.text_input)
    assert "Team access" not in [s.value for s in at.sidebar.subheader]


def test_a_wrong_code_never_unlocks_and_reveals_nothing(env):
    at = unlock(run("pages/5_Data.py"), "wrong-code-123")
    assert [e.value for e in at.error] == ["Code not recognised."]
    assert not at.session_state["team_unlocked"] if "team_unlocked" in at.session_state else True
    assert any(PRESENTATION_BLOCKED in i.value for i in at.info) and len(at.tabs) == 0
    assert at.text_input(key="team_code_input").value == ""  # the box is cleared
    assert "wrong-code-123" not in visible_text(at) and "1 code" not in visible_text(at)


def test_the_throttle_blocks_even_the_right_code_after_five_wrong_ones(env):
    at = run("pages/6_Review.py")
    for number in range(5):
        at = unlock(at, f"wrong-{number}")
    at = unlock(at, CODE)
    assert any("Too many attempts in this session" in e.value for e in at.error)
    assert len(at.tabs) == 0 and not at.session_state["team_unlocked"] if "team_unlocked" in at.session_state \
        else True
    at.session_state["team_locked_until"] = 0  # ten minutes later
    at = unlock(at, CODE)
    assert any(ta.BANNER in w.value for w in at.warning)


def test_the_right_code_unlocks_only_this_session(env):
    at = unlock(run("pages/5_Data.py"))
    assert not at.exception, [e.value for e in at.exception]
    assert any(ta.BANNER == w.value for w in at.warning)
    assert [t.label for t in at.tabs] == ["Datasets", "Import", "Templates", "Data health"]
    assert {b.key for b in at.sidebar.button} >= {"team_reset", "team_lock"}
    assert CODE not in visible_text(at)
    other = run("pages/5_Data.py")  # another browser session
    assert any(PRESENTATION_BLOCKED in i.value for i in other.info) and len(other.tabs) == 0


def test_lock_again_and_reset_delete_the_private_copy(env):
    at = unlock(run("pages/5_Data.py"))
    first = at.session_state["team_copy"].folder
    at = at.button(key="team_reset").click().run()
    second = at.session_state["team_copy"].folder
    assert not first.exists() and second.exists() and second != first
    at = at.button(key="team_lock").click().run()
    assert not second.exists() and any(PRESENTATION_BLOCKED in i.value for i in at.info)


def test_removing_the_hash_revokes_an_unlocked_session(env, monkeypatch):
    at = unlock(run("pages/5_Data.py"))
    folder = at.session_state["team_copy"].folder
    monkeypatch.setenv("FAIRLEND_ACCESS_HASHES", sha(OTHER_CODE))
    at = at.run()
    assert any(PRESENTATION_BLOCKED in i.value for i in at.info) and not folder.exists()


def test_with_presentation_mode_off_nothing_changes(env, monkeypatch):
    monkeypatch.setenv("FAIRLEND_PRESENT", "0")
    at = run("pages/5_Data.py")
    assert [t.label for t in at.tabs] == ["Datasets", "Import", "Templates", "Data health"]
    assert "Team access" not in [s.value for s in at.sidebar.subheader]
    assert not any(ta.BANNER in w.value for w in at.warning)


# --- Pages: an unlocked import touches only the private copy ---------------------------------------------------------------

def _import(at: AppTest, files: dict[str, bytes], name: str) -> AppTest:
    at.radio(key="import_format").set_value("csv").run()
    at.text_input(key="import_name").input(name)
    at.file_uploader(key="upload_csv").set_value([(n, c, "text/csv") for n, c in files.items()])
    at.run()
    return at


def test_an_unlocked_import_writes_only_to_the_private_copy_and_sessions_stay_apart(env):
    cfg, packs = env["cfg"], env["packs"]
    before = shared_digests(cfg)
    at = run("app.py")  # one browser session: Overview, then the Data page, then back
    assert any(m.label == "Borrowers scored" and m.value == "300" for m in at.metric)
    at.switch_page("pages/5_Data.py").run()
    at = _import(unlock(at), _pack_files(packs), "Team pack A")
    assert not any("refused" in e.value for e in at.error)
    at.checkbox(key="import_permission").check()
    at.button(key="validate_button").click().run()
    assert any("No errors found" in s.value for s in at.success)
    at.button(key="import_button").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Imported into 'team-pack-a'" in s.value for s in at.success)
    private = at.session_state["team_copy"]
    assert (private.folder / "datasets" / "team-pack-a" / "lending.db").exists()
    assert shared_digests(cfg) == before  # shared demo files untouched, model included
    assert not (Path(cfg["paths"]["datasets_dir"]) / "team-pack-a").exists()

    at.sidebar.selectbox(key="active_dataset").set_value("team-pack-a").run()  # the importer sees it everywhere
    at.switch_page("app.py").run()
    assert any(m.label == "Borrowers scored" and m.value == "244" for m in at.metric)  # the imported lender A

    other = unlock(run("pages/5_Data.py"))  # another unlocked session
    assert other.session_state["team_copy"].folder != private.folder
    assert "team-pack-a" not in list(other.dataframe[0].value["Slug"])
    locked = run("app.py")  # and a visitor without a code still sees the shared demo
    assert any(m.label == "Borrowers scored" and m.value == "300" for m in locked.metric)


def test_a_real_looking_upload_is_refused_in_an_unlocked_session(env):
    at = _import(unlock(run("pages/5_Data.py")), csv_bytes(tiny_rows()), "Real looking")
    assert any("This upload was refused" in e.value for e in at.error)
    assert not any(b.key == "validate_button" for b in at.button)
    assert not any((at.session_state["team_copy"].folder / "datasets").iterdir())
    assert "0772" not in visible_text(at)


def test_review_labels_in_an_unlocked_session_go_only_to_the_private_copy(env):
    cfg = env["cfg"]
    before = shared_digests(cfg)
    at = unlock(run("pages/6_Review.py"))
    at.text_input(key="reviewer").input("TS")
    at.button(key="start_batch").click().run()
    at.button(key="label_threat").click().run()
    assert not at.exception, [e.value for e in at.exception]
    private = at.session_state["team_copy"].config
    conn = sqlite3.connect(private["paths"]["predictions_db"])
    try:
        assert conn.execute("SELECT COUNT(*) FROM human_labels").fetchone()[0] == 1
    finally:
        conn.close()
    assert shared_digests(cfg) == before


# --- Code checks, the tool, the demo ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["src/team_access.py", "src/dashboard_ui.py", "pages/5_Data.py"])
def test_team_code_never_prints_logs_or_reads_secrets_files(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    assert "print(" not in source and "logging" not in source
    # team_access copies the demo's answer-label FILE into the private folder (retraining reads its dev split
    # there) but never opens it; no team code names the label tables.
    labels = ("gt_messages", "gt_borrowers", "gt_lenders", "profile_type")
    if module != "src/team_access.py":
        labels += ("ground_truth",)
    assert forbidden_mentions(source, (".env", "dotenv", "requests", "urllib") + labels) == []


def test_the_code_tool_prints_a_code_and_its_hash_and_writes_nothing(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is not available.")
    before = sorted(p.name for p in tmp_path.iterdir())
    out = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(ROOT / "tools" / "make_access_code.ps1")], cwd=tmp_path, capture_output=True,
                         text=True, timeout=120, check=True).stdout
    code = re.search(r"not saved\): (\S+)", out).group(1)
    digest = re.search(r"FAIRLEND_ACCESS_HASHES\):\s+([0-9a-f]{64})", out).group(1)
    assert len(code) == 16 and re.fullmatch(r"[A-HJ-NP-Za-km-np-z2-9]{16}", code)
    assert sha(code) == digest
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_the_demo_fingerprint_is_unchanged():
    lending = resolve_path(load_config(), "lending_db")
    if not lending.exists():
        pytest.skip("Demo not built.")
    conn = sqlite3.connect(f"{lending.resolve().as_uri()}?mode=ro", uri=True)
    try:
        assert db.content_hash(conn) == DEMO_FINGERPRINT
    finally:
        conn.close()
