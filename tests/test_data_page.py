"""AppTest checks for the Data page and the dataset switcher (Phase 4B)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard_ui import CONFIG_VARIABLE, REAL_LABEL_WARNING
from src.datasets import DEMO, get_active_name, set_active
from src.import_data import import_upload, read_csvs

from tiny_data import csv_bytes, tiny_rows
from worlds import build_classified_world, write_config

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 120


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A classified demo (300 borrowers) plus the tiny dataset imported as real; demo is active."""
    cfg, _ = build_classified_world(tmp_path / "w", n_borrowers=300)
    cfg = copy.deepcopy(cfg)
    config_path = write_config(cfg, tmp_path / "config.yaml")
    result = import_upload(read_csvs(csv_bytes(tiny_rows())), cfg, mode="new", permission_confirmed=True,
                           redact=True, dataset_name="Field A", source_description="test")
    assert result.ok, result.message
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    return cfg


def _run(page: str) -> AppTest:
    return AppTest.from_file(str(ROOT / page), default_timeout=TIMEOUT).run()


def _metric(at: AppTest, label: str) -> str:
    return next(m.value for m in at.metric if m.label == label)


def test_data_page_shows_tabs_datasets_templates_and_health(world):
    at = _run("pages/5_Data.py")
    assert not at.exception, [e.value for e in at.exception]
    assert [t.label for t in at.tabs] == ["Datasets", "Import", "Templates", "Data health"]
    table = at.dataframe[0].value
    assert list(table["Slug"]) == ["demo", "field-a"]
    assert list(table["Active"]) == ["active", ""]
    assert len(at.get("download_button")) == 6  # the workbook and five CSV files
    shared, total = _metric(at, "Borrowers who appear at two or more lenders").split(" of ")
    assert total == "300" and 0 < int(shared) < 300  # the demo's stacked and cycling borrowers use several lenders


def test_data_health_counts_the_shared_borrower(world):
    set_active(world, "field-a")
    at = _run("pages/5_Data.py")
    assert not at.exception
    assert _metric(at, "Borrowers who appear at two or more lenders") == "1 of 6"
    health = at.dataframe[1].value
    assert list(health["Lender"]) == ["Alpha Credit", "Beta Loans"]
    assert all(value.startswith("no:") for value in health["Can be ranked"])  # 12 messages is far below 50


def test_switcher_changes_the_banner_and_the_overview_numbers(world):
    at = _run("app.py")
    assert any("SYNTHETIC" in w.value for w in at.warning)
    assert _metric(at, "Borrowers scored") == "300"

    at.sidebar.selectbox(key="active_dataset").set_value("field-a").run()
    assert not at.exception, [e.value for e in at.exception]
    assert get_active_name(world) == "field-a"
    assert any(e.value == "REAL DATA - Field A. Confidential." for e in at.error)
    assert any(REAL_LABEL_WARNING in w.value for w in at.warning)
    assert not any("SYNTHETIC" in w.value for w in at.warning)
    assert _metric(at, "Borrowers scored") == "6"

    at.sidebar.selectbox(key="active_dataset").set_value(DEMO).run()
    assert get_active_name(world) == DEMO
    assert any("SYNTHETIC" in w.value for w in at.warning)
    assert _metric(at, "Borrowers scored") == "300"


@pytest.mark.parametrize("page", ["pages/0_Guided_Demo.py", "pages/1_Borrowers.py", "pages/2_Lenders.py", "pages/3_Export.py",
                                  "pages/4_About.py", "pages/5_Data.py", "pages/6_Review.py"])
def test_every_page_shows_the_real_data_banner(world, page):
    set_active(world, "field-a")
    at = _run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert any(e.value == "REAL DATA - Field A. Confidential." for e in at.error)


def test_switching_on_the_data_page(world):
    at = _run("pages/5_Data.py")
    at.selectbox(key="switch_choice").set_value("field-a")
    at.button(key="switch_button").click().run()
    assert not at.exception
    assert get_active_name(world) == "field-a"
    assert any("'field-a' is now the active dataset" in s.value for s in at.success)


def test_deleting_from_the_data_page_respects_the_guards(world):
    at = _run("pages/5_Data.py")
    at.selectbox(key="delete_choice").set_value("field-a")
    at.text_input(key="delete_typed").input("wrong name")
    at.button(key="delete_button").click().run()
    assert any("type the dataset name exactly" in e.value for e in at.error)
    assert (Path(world["paths"]["datasets_dir"]) / "field-a").exists()

    at.text_input(key="delete_typed").input("field-a")
    at.button(key="delete_button").click().run()
    assert not at.exception
    assert not (Path(world["paths"]["datasets_dir"]) / "field-a").exists()
