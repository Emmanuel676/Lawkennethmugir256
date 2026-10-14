"""Streamlit smoke tests and code checks for the dashboard pages (Phase 4).

Each page is run headless with streamlit.testing.v1.AppTest against a small
classified world, and against an empty folder (where it must show the
friendly instructions, not a traceback).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard_data import REVIEW_LINE
from src.dashboard_ui import CONFIG_VARIABLE

from leak_check import forbidden_mentions
from worlds import build_classified_world, config_for, write_config

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["app.py"] + sorted(f"pages/{p.name}" for p in (ROOT / "pages").glob("*.py"))
DASHBOARD_CODE = PAGES + ["src/dashboard_data.py", "src/dashboard_ui.py", "src/build_all.py", "src/app_log.py"]
DASHBOARD_FORBIDDEN = ("ground_truth", "gt_borrowers", "gt_messages", "gt_lenders", "profile_type",
                       ".env", "dotenv", "requests", "urllib", "genai")
TIMEOUT = 120


@pytest.fixture(scope="module")
def world_config(tmp_path_factory):
    _, config_path = build_classified_world(tmp_path_factory.mktemp("pages_world"))
    return config_path


@pytest.fixture
def good_data(world_config, monkeypatch):
    monkeypatch.setenv(CONFIG_VARIABLE, str(world_config))


@pytest.fixture
def no_data(world_config, monkeypatch, tmp_path):
    from src.config import load_config
    empty = config_for(tmp_path / "empty", load_config(world_config))
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(empty, tmp_path / "config.yaml")))


def _run(page: str) -> AppTest:
    return AppTest.from_file(str(ROOT / page), default_timeout=TIMEOUT).run()


def _assert_banner(at: AppTest) -> None:
    assert any("SYNTHETIC" in w.value for w in at.warning), "synthetic-data notice missing"
    assert any(REVIEW_LINE in i.value for i in at.info), "human-review line missing"


# --- Code checks ---------------------------------------------------------------------------

def test_there_are_seven_pages_besides_the_overview():
    assert PAGES == ["app.py", "pages/0_Guided_Demo.py", "pages/1_Borrowers.py", "pages/2_Lenders.py", "pages/3_Export.py", "pages/4_About.py",
                     "pages/5_Data.py", "pages/6_Review.py"]


@pytest.mark.parametrize("module", DASHBOARD_CODE)
def test_dashboard_code_never_mentions_labels_secrets_or_network(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    assert forbidden_mentions(source, DASHBOARD_FORBIDDEN) == []


def test_the_check_catches_secret_and_network_use():
    assert forbidden_mentions('import requests\n', DASHBOARD_FORBIDDEN) == ["requests"]
    assert set(forbidden_mentions('from dotenv import load_dotenv\n', DASHBOARD_FORBIDDEN)) == {"dotenv", "load_dotenv"}
    assert forbidden_mentions('open(".env")\n', DASHBOARD_FORBIDDEN) == [".env"]
    assert forbidden_mentions('"""Never reads .env or gt_lenders."""\nx = 1\n', DASHBOARD_FORBIDDEN) == []


def test_streamlit_never_phones_home():
    settings = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "gatherUsageStats = false" in settings
    assert 'address = "localhost"' in settings


# --- Every page runs, with the banner, on good data ------------------------------------------

@pytest.mark.parametrize("page", PAGES)
def test_page_runs_and_shows_the_notice(page, good_data):
    at = _run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    _assert_banner(at)


@pytest.mark.parametrize("page", PAGES)
def test_page_without_data_shows_instructions_not_a_traceback(page, no_data):
    at = _run(page)
    assert not at.exception, [e.value for e in at.exception]
    _assert_banner(at)
    assert any("No dataset found" in e.value for e in at.error)
    assert any("python -m src.build_all" in c.value for c in at.code)


# --- Interaction ---------------------------------------------------------------------------------

def _match_line(at: AppTest) -> str:
    return next(m.value for m in at.markdown if "borrowers match the filters" in m.value)


def test_borrowers_page_filters_and_opens_a_borrower(good_data):
    at = _run("pages/1_Borrowers.py")
    everyone = _match_line(at)
    assert everyone.startswith("**800 of 800")

    at.sidebar.multiselect(key="bands").set_value(["high"]).run()
    assert not at.exception
    high_only = _match_line(at)
    assert high_only != everyone
    table = at.dataframe[0].value
    assert len(table) > 0 and set(table["Band"]) == {"high"}

    assert "Score breakdown" not in [s.value for s in at.subheader]
    at.selectbox(key="borrower_pick").set_value(table["Borrower"].iloc[0]).run()
    assert not at.exception
    subheaders = [s.value for s in at.subheader]
    assert "Score breakdown" in subheaders
    assert "Loans across all lenders" in subheaders
    assert any("points)" in m.value for m in at.markdown)  # the plain-language explanation lines


def test_lenders_page_drill_down_shows_examples(good_data):
    at = _run("pages/2_Lenders.py")
    assert any("Too few messages to rank" == s.value for s in at.subheader)
    picker = at.selectbox(key="lender_pick")
    at = picker.set_value("L05").run()
    assert not at.exception
    assert any("Example messages labelled threat" in m.value for m in at.markdown)


def test_export_page_counts_rows(good_data):
    at = _run("pages/3_Export.py")
    assert any("borrowers will be exported" in m.value for m in at.markdown)
    before = next(m.value for m in at.markdown if "borrowers will be exported" in m.value)
    at.multiselect(key="export_bands").set_value(["high"]).run()
    after = next(m.value for m in at.markdown if "borrowers will be exported" in m.value)
    assert before != after
