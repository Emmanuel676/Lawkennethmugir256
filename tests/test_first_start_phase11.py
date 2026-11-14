"""Phase 11 regression: the live app (presentation mode, empty data/) must still build the demo on first load.

Report: on Streamlit Cloud the Guided Demo page showed "No dataset found: the demo data is not there". These tests
start from an EMPTY data folder, open Guided Demo FIRST (not the Overview), and check that page_setup builds the demo
before it loads data, that team_config only runs once the demo exists, and that a "missing" result cached before
the build is never served afterwards.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.dashboard_ui as dashboard_ui
from src.bootstrap import demo_status
from src.config import load_config
from src.dashboard_ui import ACCESS_VARIABLE, CONFIG_VARIABLE
from src.datasets import PRESENT_VARIABLE
from src.team_access import hash_code

from worlds import config_for, write_config

ROOT = Path(__file__).resolve().parents[1]
GUIDED = "pages/0_Guided_Demo.py"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """A small config whose demo lives in an EMPTY tmp data folder (as on a fresh Streamlit Cloud server)."""
    custom = config_for(tmp_path / "data", load_config())
    custom["generator"]["n_borrowers"] = 300
    custom["generator"]["test_set_size"] = 40
    custom["app"]["log_file"] = str(tmp_path / "data" / "logs" / "app.log")
    (tmp_path / "data").mkdir()
    for name in (PRESENT_VARIABLE, ACCESS_VARIABLE):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(custom, tmp_path / "config.yaml")))
    return custom


def _run(page=GUIDED, secrets=None) -> AppTest:
    at = AppTest.from_file(str(ROOT / page), default_timeout=600)
    for key, value in (secrets or {}).items():
        at.secrets[key] = value
    return at.run()


def _assert_guided_demo_shown(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]
    errors = [e.value for e in at.error]
    assert not any("No dataset found" in e for e in errors), errors
    assert not any("Something went wrong" in e or "could not be prepared" in e for e in errors), errors
    assert sum(m.value.startswith("### ") for m in at.markdown) == 6  # the six featured cases


def test_guided_demo_first_builds_the_demo_from_an_empty_folder(cfg, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    assert demo_status(cfg)[0] == "missing"
    at = _run()
    assert demo_status(cfg)[0] == "fresh"
    _assert_guided_demo_shown(at)


def test_cloud_secrets_with_access_hashes_still_build_on_first_load(cfg):
    """As on Streamlit Cloud after Phase 11: presentation mode and the access hashes come from st.secrets only."""
    secrets = {PRESENT_VARIABLE: "1", ACCESS_VARIABLE: [hash_code("team-code-for-tests")]}
    try:
        at = _run(secrets=secrets)
        assert demo_status(cfg)[0] == "fresh"
        _assert_guided_demo_shown(at)
    finally:
        import os
        os.environ.pop(PRESENT_VARIABLE, None)  # presentation_from_secrets copied it into the environment


def test_team_config_runs_only_after_the_demo_exists(cfg, monkeypatch):
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    seen: list[str] = []
    original = dashboard_ui.team_config

    def recording(config):
        seen.append(demo_status(config)[0])
        return original(config)

    monkeypatch.setattr(dashboard_ui, "team_config", recording)
    _assert_guided_demo_shown(_run())
    assert seen and set(seen) == {"fresh"}, seen


def test_a_cached_missing_result_is_not_served_after_the_build(cfg, monkeypatch):
    """Load once WITHOUT presentation mode (no build: 'missing' is cached under the empty-folder signature), then
    turn presentation mode on with the same config file: the demo must be built and shown, not the cached miss."""
    monkeypatch.setenv(PRESENT_VARIABLE, "0")
    first = _run()
    assert any("No dataset found" in e.value for e in first.error)
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    at = _run()
    assert demo_status(cfg)[0] == "fresh"
    _assert_guided_demo_shown(at)
