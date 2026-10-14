"""Phase 5.2: presentation mode, featured cases, the Guided Demo page, the error wrapper and preflight."""

from __future__ import annotations

import builtins
import copy
import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.datasets as datasets
from src import preflight
from src.app_log import log_exception, safe_traceback
from src.dashboard_data import featured_cases, load_all
from src.dashboard_ui import CONFIG_VARIABLE, PRESENTATION_BLOCKED
from src.datasets import (DEMO, PRESENT_VARIABLE, DatasetError, create_dataset, get_active_name, list_datasets,
                          presentation_mode, set_active)

from leak_check import forbidden_mentions
from worlds import build_classified_world, write_config

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 120
NETWORK = ("requests", "urllib", "genai", "http.client", "socket", "dotenv")
LABELS = ("ground_truth", "gt_borrowers", "gt_messages", "gt_lenders", "profile_type")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build_classified_world(tmp_path_factory.mktemp("present_world"))


@pytest.fixture
def world(built, tmp_path, monkeypatch):
    """The demo plus one (empty) real dataset that is the ACTIVE one in active_dataset.txt."""
    cfg = copy.deepcopy(built[0])
    cfg["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    cfg["paths"]["active_dataset_file"] = str(tmp_path / "active.txt")
    cfg["app"]["log_file"] = str(tmp_path / "logs" / "app.log")
    monkeypatch.delenv(PRESENT_VARIABLE, raising=False)
    create_dataset(cfg, "Secret Field Data", "test")
    set_active(cfg, "secret-field-data")
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(cfg, tmp_path / "config.yaml")))
    return cfg


def _run(page: str, **query) -> AppTest:
    at = AppTest.from_file(str(ROOT / page), default_timeout=TIMEOUT)
    for key, value in query.items():
        at.query_params[key] = value
    return at.run()


# --- Presentation mode ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("setting, variable, expected", [
    (False, None, False), (True, None, True), (False, "1", True), (True, "0", False), (False, "true", True),
    (True, "off", False), (False, "", False), (True, "maybe", True),
])
def test_the_environment_variable_wins_over_the_config(world, monkeypatch, setting, variable, expected):
    world["app"]["presentation_mode"] = setting
    if variable is None:
        monkeypatch.delenv(PRESENT_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(PRESENT_VARIABLE, variable)
    assert presentation_mode(world) is expected


def test_presentation_mode_ignores_active_dataset_txt(world, monkeypatch):
    assert get_active_name(world) == "secret-field-data"  # without presentation mode the real one is active
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    assert Path(world["paths"]["active_dataset_file"]).read_text(encoding="utf-8").strip() == "secret-field-data"
    assert get_active_name(world) == DEMO
    assert [d.slug for d in list_datasets(world)] == [DEMO]
    with pytest.raises(DatasetError, match="Presentation mode is on"):
        set_active(world, "secret-field-data")


def test_presentation_mode_never_reads_or_lists_real_folders(world, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    real_root = Path(world["paths"]["datasets_dir"]).resolve()
    active_file = Path(world["paths"]["active_dataset_file"]).resolve()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a real dataset folder or the active-dataset file was touched")

    monkeypatch.setattr(datasets, "_real_exists", forbidden)
    monkeypatch.setattr(datasets, "_real_info", forbidden)
    original_iterdir, original_read = Path.iterdir, Path.read_text

    def guarded_iterdir(self):
        if self.resolve() == real_root:
            forbidden()
        return original_iterdir(self)

    def guarded_read(self, *args, **kwargs):
        if self.resolve() == active_file or real_root in self.resolve().parents:
            forbidden()
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    monkeypatch.setattr(Path, "read_text", guarded_read)
    assert get_active_name(world) == DEMO and [d.slug for d in list_datasets(world)] == [DEMO]
    at = _run("app.py")
    assert not at.exception, [e.value for e in at.exception]
    assert not any("Something went wrong" in e.value for e in at.error)
    assert any("SYNTHETIC" in w.value for w in at.warning)


def test_presentation_mode_on_the_pages(world, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    at = _run("app.py")
    assert not at.exception
    assert any("Presentation mode" in m.value for m in at.sidebar.markdown)
    assert not any(box.key == "active_dataset" for box in at.sidebar.selectbox)
    assert not any(e.value.startswith("REAL DATA") for e in at.error)
    assert any("SYNTHETIC" in w.value for w in at.warning)
    for page in ("pages/5_Data.py", "pages/6_Review.py"):
        at = _run(page)
        assert not at.exception, page
        assert any(PRESENTATION_BLOCKED in i.value for i in at.info), page
        assert len(at.tabs) == 0 and len(at.button) == 0 and len(at.get("file_uploader")) == 0, page


def test_without_presentation_mode_the_real_dataset_shows(world):
    at = _run("app.py")
    assert any(e.value == "REAL DATA - Secret Field Data. Confidential." for e in at.error)
    assert any(box.key == "active_dataset" for box in at.sidebar.selectbox)


# --- Featured cases --------------------------------------------------------------------------------------------

@pytest.fixture
def demo_data(world, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")  # the demo, whatever is active
    return load_all(world)


def test_featured_cases_follow_their_rules(world, demo_data):
    result = featured_cases(demo_data, world)
    cases = {c["key"]: c for c in result["cases"]}
    assert [c["step"] for c in result["cases"]] == list(range(1, len(result["cases"]) + 1))
    b = demo_data.borrowers.set_index("borrower_id")
    high = b[b["band"] == "high"]
    assert cases["top_high"]["id"] == high.sort_values("score", ascending=False, kind="mergesort").index[0]
    assert b.loc[cases["top_high"]["id"], "score"] == high["score"].max()
    forced = b.loc[cases["cycling"]["id"]]
    assert bool(forced["band_forced_by_cycling"]) and forced["band"] == "medium"
    many = b.loc[cases["many_lenders"]["id"]]
    assert many["open_lenders"] >= world["demo"]["many_lenders_min_open"]
    assert many["debt_to_income"] < world["demo"]["many_lenders_max_dti"] and many["band"] != "high"
    harassed = b.loc[cases["harassed"]["id"]]
    eligible = b[(b["late_night_messages"] > 0) | (b["third_party_messages"] > 0)]
    assert harassed["abusive_messages"] == eligible["abusive_messages"].max()
    lenders = demo_data.lenders.set_index("lender_id")
    assert pd_isna(lenders.loc[cases["unranked"]["id"], "rank"])
    assert "too few messages to rank" in cases["unranked"]["say"]
    assert lenders.loc[cases["top_lender"]["id"], "rank"] == 1
    assert featured_cases(demo_data, world) == result  # deterministic


def pd_isna(value) -> bool:
    import pandas as pd
    return bool(pd.isna(value))


def test_featured_case_thresholds_come_from_the_config(world, demo_data):
    strict = copy.deepcopy(world)
    strict["demo"]["many_lenders_min_open"] = 99
    result = featured_cases(demo_data, strict)
    assert "many_lenders" not in [c["key"] for c in result["cases"]]
    assert any("99+ open lenders" in m for m in result["missing"])
    assert len(result["cases"]) == 5 and [c["step"] for c in result["cases"]] == [1, 2, 3, 4, 5]


# --- The Guided Demo page -------------------------------------------------------------------------------------------

def test_guided_demo_page_lists_six_steps(world, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    at = _run("pages/0_Guided_Demo.py")
    assert not at.exception, [e.value for e in at.exception]
    steps = [m.value for m in at.markdown if m.value.startswith("### ")]
    assert [s.split(".")[0] for s in steps] == [f"### {n}" for n in range(1, 7)]
    assert sum(m.value.startswith("**Say:**") for m in at.markdown) == 6
    assert len([b for b in at.button if b.key.startswith("go_")]) == 6
    assert any("the data is synthetic" in m.value for m in at.markdown)


def test_guided_demo_buttons_open_the_right_case(world, monkeypatch, demo_data):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    cases = {c["key"]: c for c in featured_cases(demo_data, world)["cases"]}
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=TIMEOUT).run()
    at.switch_page("pages/0_Guided_Demo.py").run()
    at.button(key="go_harassed").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert f"Borrower {cases['harassed']['id']}" in [h.value for h in at.header]
    assert at.query_params["borrower"] == [cases["harassed"]["id"]] or at.query_params["borrower"] == cases[
        "harassed"]["id"]

    at.switch_page("pages/0_Guided_Demo.py").run()
    at.button(key="go_top_lender").click().run()
    assert not at.exception
    name = demo_data.lenders.set_index("lender_id").loc[cases["top_lender"]["id"], "name"]
    assert any(m.value.startswith(f"{name}: rank 1.") for m in at.markdown)


def test_a_bookmarked_link_opens_the_borrower_once(world, monkeypatch, demo_data):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    target = demo_data.borrowers["borrower_id"].iloc[3]
    at = _run("pages/1_Borrowers.py", borrower=target)
    assert f"Borrower {target}" in [h.value for h in at.header]
    other = demo_data.borrowers["borrower_id"].iloc[5]
    at.selectbox(key="borrower_pick").set_value(other).run()  # the link does not force the choice again
    assert f"Borrower {other}" in [h.value for h in at.header]


def test_guided_demo_on_a_real_dataset_says_switch_to_the_demo(world, monkeypatch):
    from src.import_data import import_upload, read_csvs
    from tiny_data import csv_bytes, tiny_rows
    result = import_upload(read_csvs(csv_bytes(tiny_rows())), world, mode="new", permission_confirmed=True,
                           redact=True, dataset_name="Field Z")
    assert result.ok
    set_active(world, "field-z")
    at = _run("pages/0_Guided_Demo.py")
    assert not at.exception
    assert any("written for the demo dataset" in i.value for i in at.info)
    assert not any(m.value.startswith("### ") for m in at.markdown)


# --- The error wrapper ------------------------------------------------------------------------------------------------

SECRET = "Pay 0772 123 456 B-3f9a1c2d4e5b"


def _log_text(cfg) -> str:
    folder = Path(cfg["app"]["log_file"]).parent
    return "".join(p.read_text(encoding="utf-8") for p in sorted(folder.glob("app.log*")))


def test_an_injected_failure_shows_a_friendly_message_and_logs_no_data(world, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    import src.dashboard_data as dashboard_data

    def broken(*_args, **_kwargs):
        raise KeyError(SECRET)

    monkeypatch.setattr(dashboard_data, "overview_kpis", broken)
    at = _run("app.py")
    assert not at.exception, [e.value for e in at.exception]  # no traceback on the page
    message = next(e.value for e in at.error if "Something went wrong" in e.value)
    code = message.split("error code ")[1].split(")")[0]
    assert code.startswith("FW-") and len(code) == 9
    assert SECRET not in message
    log = _log_text(world)
    assert code in log and "page=Overview" in log and "type=builtins.KeyError" in log
    assert "app.py:" in log and "in broken" in log
    for piece in ("0772", "B-3f9a1c2d4e5b", "Pay "):
        assert piece not in log


def test_the_wrapper_lets_stop_and_rerun_through(world, monkeypatch, tmp_path):
    script = tmp_path / "page.py"
    script.write_text("import streamlit as st\nfrom src.dashboard_ui import guarded\n"
                      "with guarded('T'):\n    st.write('before')\n    st.stop()\n    st.write('after')\n",
                      encoding="utf-8")
    at = AppTest.from_file(str(script), default_timeout=TIMEOUT).run()
    assert not at.exception and not at.error
    assert [m.value for m in at.markdown] == ["before"]


def test_the_log_rotates_and_stays_small(world):
    small = copy.deepcopy(world)
    small["app"]["log_max_bytes"] = 10000
    small["app"]["log_backups"] = 2
    small["app"]["log_file"] = str(Path(world["app"]["log_file"]).with_name("rotating.log"))
    for _ in range(400):
        try:
            raise ValueError(SECRET)
        except ValueError as error:
            log_exception("Test", error, small)
    files = sorted(Path(small["app"]["log_file"]).parent.glob("rotating.log*"))
    assert len(files) == 3  # the log and two backups
    assert all(p.stat().st_size <= 10000 + 500 for p in files)
    assert not any(SECRET in p.read_text(encoding="utf-8") for p in files)


def test_safe_traceback_has_locations_only():
    try:
        value = SECRET
        raise RuntimeError(value)
    except RuntimeError as error:
        frames = safe_traceback(error)
    assert frames and all(":" in f and " in " in f for f in frames)
    assert not any("0772" in f for f in frames)


# --- Preflight --------------------------------------------------------------------------------------------------------

def test_preflight_passes_on_a_good_world(built):
    cfg, config_path = built
    results = {name: (ok, detail) for name, ok, detail in preflight.run(str(config_path))}
    assert all(ok for ok, _ in results.values()), results
    assert len(results) == 7


def test_preflight_fails_when_the_demo_was_changed_or_labels_are_stale(built, tmp_path):
    cfg, _ = built
    copy_cfg = copy.deepcopy(cfg)
    for key in ("lending_db", "predictions_db", "manifest"):
        target = tmp_path / Path(cfg["paths"][key]).name
        target.write_bytes(Path(cfg["paths"][key]).read_bytes())
        copy_cfg["paths"][key] = str(target)
    assert preflight.check_demo_fingerprint(copy_cfg)[0] and preflight.check_predictions(copy_cfg)[0]
    conn = sqlite3.connect(copy_cfg["paths"]["lending_db"])
    conn.execute("UPDATE messages SET text = 'edited' WHERE rowid = 1")
    conn.commit()
    conn.close()
    ok, detail = preflight.check_demo_fingerprint(copy_cfg)
    assert not ok and "does not match its manifest" in detail
    ok, detail = preflight.check_predictions(copy_cfg)
    assert not ok and "stale" in detail
    Path(copy_cfg["paths"]["manifest"]).unlink()
    assert "manifest is missing" in preflight.check_demo_fingerprint(copy_cfg)[1]


def test_preflight_main_prints_pass_fail_and_a_summary(built, capsys, monkeypatch):
    monkeypatch.setattr(preflight, "check_pages", lambda _cfg: (False, "pages/x.py raised an exception"))
    code = preflight.main(["--config", str(built[1])])
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL  every page boots: pages/x.py raised an exception" in out
    assert "PASS  logo files exist" in out
    assert out.strip().splitlines()[-1] == "Preflight: 6 of 7 checks passed. NOT ready: fix the FAIL lines above."


def test_preflight_never_opens_the_env_file(monkeypatch):
    real_open, real_read = builtins.open, Path.read_text

    def no_env_open(file, *args, **kwargs):
        assert Path(str(file)).name != ".env", "preflight opened .env"
        return real_open(file, *args, **kwargs)

    def no_env_read(self, *args, **kwargs):
        assert self.name != ".env", "preflight read .env"
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", no_env_open)
    monkeypatch.setattr(Path, "read_text", no_env_read)
    assert preflight.check_secret_file()[0]


def test_preflight_secret_check_can_fail(monkeypatch, tmp_path):
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "config.toml").write_text("[server]\nenableStaticServing = true\n", encoding="utf-8")
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(preflight, "PAGES", [])
    ok, detail = preflight.check_secret_file()
    assert not ok and "not listed in .gitignore" in detail
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    ok, detail = preflight.check_secret_file()
    assert not ok and "static file serving is on" in detail


# --- Code checks -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["src/preflight.py", "src/app_log.py", "pages/0_Guided_Demo.py",
                                    "src/dashboard_data.py", "src/dashboard_ui.py", "src/datasets.py"])
def test_new_code_never_mentions_labels_or_network(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    names = NETWORK + (LABELS if module != "src/datasets.py" else LABELS[1:])  # datasets names the demo's label FILE
    assert forbidden_mentions(source, names) == []


def test_only_preflight_names_the_env_file_and_only_to_check_gitignore():
    for module in ("src/app_log.py", "pages/0_Guided_Demo.py", "src/dashboard_ui.py", "src/datasets.py"):
        assert forbidden_mentions((ROOT / module).read_text(encoding="utf-8"), (".env",)) == []
    mentions = forbidden_mentions((ROOT / "src/preflight.py").read_text(encoding="utf-8"), (".env",))
    assert set(mentions) == {".env", ".env is not served or listed"}  # the file name constant and a check's title
