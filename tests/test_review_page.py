"""AppTest checks for the Review page and the Data page's redaction preview (Phase 5.1)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard_ui import CONFIG_VARIABLE
from src.datasets import get_dataset_paths, set_active
from src.import_data import import_upload, read_csvs
from src.review import progress

from tiny_data import PHONES, csv_bytes, tiny_rows
from worlds import build_classified_world, write_config

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 120


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A classified demo plus the tiny dataset imported as real ('field-a')."""
    cfg, _ = build_classified_world(tmp_path / "w", n_borrowers=300)
    cfg = copy.deepcopy(cfg)
    cfg["privacy"]["name_list_file"] = str(tmp_path / "names.txt")
    (tmp_path / "names.txt").write_text("Nakato\n", encoding="utf-8")
    result = import_upload(read_csvs(csv_bytes(tiny_rows())), cfg, mode="new", permission_confirmed=True,
                           redact=True, dataset_name="Field A", source_description="test")
    assert result.ok, result.message
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(cfg, tmp_path / "config.yaml")))
    return cfg


def _run(page: str) -> AppTest:
    return AppTest.from_file(str(ROOT / page), default_timeout=TIMEOUT).run()


def _metric(at: AppTest, label: str) -> str:
    return next(m.value for m in at.metric if m.label == label)


def _delta(at: AppTest, label: str) -> str:
    return next(m.delta for m in at.metric if m.label == label)


def test_review_page_labels_a_message_and_progress_changes(world):
    set_active(world, "field-a")
    at = _run("pages/6_Review.py")
    assert not at.exception, [e.value for e in at.exception]
    assert any(e.value == "REAL DATA - Field A. Confidential." for e in at.error)
    assert _metric(at, "Messages reviewed") == "0" and _delta(at, "Messages reviewed") == "of 12 (0.0%)"
    assert any("Only 0 randomly checked message(s) so far" in m.value for m in at.markdown)
    assert any("normal**: Neutral reminder" in m.value for m in at.markdown)  # each class explained
    assert any("[About page](/About)" in e.label for e in at.expander)

    at.text_input(key="reviewer").input("MK")
    at.button(key="start_batch").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Message 1 of 12" in m.value for m in at.markdown)
    assert not any("The model's label" in c.value for c in at.caption)  # hidden until the reviewer has chosen

    at.button(key="label_threat").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert _metric(at, "Messages reviewed") == "1" and _delta(at, "Messages reviewed") == "of 12 (8.3%)"
    assert _metric(at, "Random check") == "1"
    assert any(s.value.startswith("Saved as threat. The model") for s in at.success)
    assert any("Message 2 of 12" in m.value for m in at.markdown)

    at.button(key="label_skip").click().run()  # skipped: not stored
    assert _metric(at, "Messages reviewed") == "1" and _delta(at, "Messages reviewed") == "of 12 (8.3%)"
    assert any("Message 3 of 12" in m.value for m in at.markdown)

    state = progress(get_dataset_paths(world, "field-a"))
    assert state["reviewed"] == 1 and state["per_class"]["threat"] == 1
    assert any("Not possible yet" in m.value and "59 more human label(s)" in m.value for m in at.markdown)
    assert at.button(key="retrain_button").disabled


def test_review_page_shows_the_prediction_when_configured(world, tmp_path, monkeypatch):
    shown = copy.deepcopy(world)
    shown["classifier"]["review"]["show_prediction_before_label"] = True
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(shown, tmp_path / "shown.yaml")))
    set_active(shown, "field-a")
    at = _run("pages/6_Review.py")
    at.button(key="start_batch").click().run()
    assert any(c.value.startswith("The model's label: ") for c in at.caption)


def test_review_page_on_the_demo_shows_a_note(world):
    at = _run("pages/6_Review.py")
    assert not at.exception, [e.value for e in at.exception]
    assert any("This is the demo dataset. It has answer labels elsewhere" in i.value for i in at.info)
    assert at.button(key="retrain_button").disabled


def test_data_page_shows_a_redaction_preview_before_import(world):
    rows = tiny_rows()
    rows["messages"][6][5] = "Nakato says: your NIN CM1234567890AB is on file."
    files = csv_bytes(rows)
    at = _run("pages/5_Data.py")
    at.radio(key="import_format").set_value("csv").run()
    at.file_uploader(key="upload_csv").set_value([(name, content, "text/csv") for name, content in files.items()])
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert _metric(at, "[PHONE]") == str(PHONES)
    assert _metric(at, "[ID]") == "1" and _metric(at, "[NAME]") == "1" and _metric(at, "[EMAIL]") == "1"
    preview = next(d.value for d in at.dataframe if list(d.value.columns) == ["Row", "Original", "Redacted"])
    assert len(preview) == 12
    changed = preview[preview["Original"] != preview["Redacted"]]
    assert len(changed) == 4 and list(changed.index) == [0, 1, 2, 3]  # changed messages come first
    assert not preview["Redacted"].str.contains("CM1234567890AB|Nakato|0772 123 456").any()
    assert "[NAME] says: your NIN [ID] is on file." in preview["Redacted"].tolist()

    at.button(key="validate_button").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("No errors found" in s.value for s in at.success)
    assert any(e.label == "Possible names to add to the name list" for e in at.expander)
