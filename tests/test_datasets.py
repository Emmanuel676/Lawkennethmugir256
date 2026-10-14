"""Checks on the dataset registry (Phase 4B): create, list, switch, delete guards, restore, evaluation exits."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from src import evaluate_classifier, evaluate_lenders, evaluate_overlap
from src.datasets import (DEMO, DatasetError, create_dataset, delete_dataset, get_active_name, get_active_paths,
                          get_dataset_paths, is_synthetic, list_datasets, remove_dataset_folder, restore_demo,
                          set_active)
from src.import_data import import_upload, read_csvs

from tiny_data import csv_bytes, tiny_rows
from worlds import build_classified_world, write_config


@pytest.fixture
def world(tmp_path):
    """A fresh small classified demo (with a saved model) and an empty datasets folder, per test."""
    cfg, _ = build_classified_world(tmp_path / "w", n_borrowers=200)
    cfg = copy.deepcopy(cfg)
    cfg["generator"]["n_borrowers"] = 200  # so restore_demo rebuilds a small world quickly
    cfg["generator"]["test_set_size"] = 40
    return cfg, write_config(cfg, tmp_path / "config.yaml")


def _import_tiny(cfg, name="Field A"):
    result = import_upload(read_csvs(csv_bytes(tiny_rows())), cfg, mode="new", permission_confirmed=True,
                           redact=True, dataset_name=name, source_description="test", classify=True)
    assert result.ok, result.message
    return result.dataset


# --- Create, list, switch ---------------------------------------------------------------------------------

def test_demo_is_listed_and_active_by_default(world):
    cfg, _ = world
    assert [d.slug for d in list_datasets(cfg)] == [DEMO]
    assert get_active_name(cfg) == DEMO
    assert get_active_paths(cfg) == get_dataset_paths(cfg, DEMO)
    assert is_synthetic(get_active_paths(cfg)) is True


def test_create_writes_a_folder_with_dataset_json(world):
    cfg, _ = world
    info = create_dataset(cfg, "Field data, Gulu (May)", "Two lenders under agreement", "2026-09-30", "first batch")
    assert info.slug == "field-data-gulu-may"
    folder = Path(cfg["paths"]["datasets_dir"]) / info.slug
    stored = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    assert stored["kind"] == "real" and stored["name"] == "Field data, Gulu (May)"
    assert set(stored) == {"name", "slug", "kind", "created_at", "source_description", "as_of_date", "notes"}
    assert [d.slug for d in list_datasets(cfg)] == [DEMO, info.slug]


def test_create_refuses_reserved_empty_and_repeated_names(world):
    cfg, _ = world
    for bad in ("demo", "  ", "!!!"):
        with pytest.raises(DatasetError):
            create_dataset(cfg, bad, "x")
    create_dataset(cfg, "Field A", "x")
    with pytest.raises(DatasetError, match="already exists"):
        create_dataset(cfg, "field a", "x")


def test_switching_changes_the_active_paths(world):
    cfg, _ = world
    slug = _import_tiny(cfg)
    set_active(cfg, slug)
    assert get_active_name(cfg) == slug
    assert get_active_paths(cfg).lending_db == Path(cfg["paths"]["datasets_dir"]) / slug / "lending.db"
    assert is_synthetic(get_active_paths(cfg)) is False
    set_active(cfg, DEMO)
    assert get_active_name(cfg) == DEMO
    with pytest.raises(DatasetError):
        set_active(cfg, "no-such-dataset")


def test_a_stored_choice_that_no_longer_exists_falls_back_to_demo(world):
    cfg, _ = world
    Path(cfg["paths"]["active_dataset_file"]).write_text("vanished\n", encoding="utf-8")
    assert get_active_name(cfg) == DEMO


# --- Delete guards -------------------------------------------------------------------------------------------

def test_the_active_dataset_cannot_be_deleted(world):
    cfg, _ = world
    slug = _import_tiny(cfg)
    set_active(cfg, slug)
    with pytest.raises(DatasetError, match="Switch to another dataset first"):
        delete_dataset(cfg, slug, slug)
    assert get_dataset_paths(cfg, slug).lending_db.exists()


def test_deleting_needs_the_name_typed_exactly(world):
    cfg, _ = world
    slug = _import_tiny(cfg)
    with pytest.raises(DatasetError, match="type the dataset name"):
        delete_dataset(cfg, slug, "field")
    assert get_dataset_paths(cfg, slug).lending_db.exists()
    assert "deleted" in delete_dataset(cfg, slug, slug)
    assert not (Path(cfg["paths"]["datasets_dir"]) / slug).exists()
    assert [d.slug for d in list_datasets(cfg)] == [DEMO]


def test_deleting_the_demo_needs_the_extra_confirmation(world):
    cfg, _ = world
    set_active(cfg, _import_tiny(cfg))
    with pytest.raises(DatasetError, match="extra confirmation"):
        delete_dataset(cfg, DEMO, DEMO)
    assert get_dataset_paths(cfg, DEMO).lending_db.exists()


def test_deleting_the_demo_needs_a_saved_model(world, tmp_path):
    cfg, _ = world
    set_active(cfg, _import_tiny(cfg))
    no_model = copy.deepcopy(cfg)
    no_model["paths"]["local_model"] = str(tmp_path / "missing_model.joblib")
    with pytest.raises(DatasetError, match="no saved model exists"):
        delete_dataset(no_model, DEMO, DEMO, confirm_demo=True)
    assert get_dataset_paths(cfg, DEMO).lending_db.exists()


def test_delete_and_restore_the_demo(world):
    cfg, _ = world
    real = _import_tiny(cfg)
    set_active(cfg, real)
    demo = get_dataset_paths(cfg, DEMO)
    delete_dataset(cfg, DEMO, DEMO, confirm_demo=True)
    assert not demo.lending_db.exists() and not demo.predictions_db.exists()
    assert not demo.ground_truth_db.exists()
    assert Path(cfg["paths"]["local_model"]).exists()  # the saved classifier is kept
    assert [d.slug for d in list_datasets(cfg)] == [real]

    # Without the demo, a new import is labelled with the saved model.
    assert _import_tiny(cfg, "Field B") == "field-b"

    message = restore_demo(cfg)
    assert "rebuilt" in message
    assert demo.lending_db.exists() and is_synthetic(demo)
    conn = sqlite3.connect(str(demo.lending_db))
    n_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    conn = sqlite3.connect(str(demo.predictions_db))
    n_labels = conn.execute("SELECT COUNT(*) FROM message_predictions").fetchone()[0]
    conn.close()
    assert n_messages == n_labels > 0
    assert get_active_name(cfg) == real  # restoring does not change the active dataset


def test_folder_removal_stays_inside_the_datasets_folder(world):
    cfg, _ = world
    for bad in ("", DEMO, "..", "../w"):
        with pytest.raises(DatasetError):
            remove_dataset_folder(cfg, bad)


# --- Evaluation modules on a dataset without answer labels -----------------------------------------------------

@pytest.mark.parametrize("module, extra", [
    (evaluate_overlap, []), (evaluate_classifier, ["--classifier", "local"]), (evaluate_lenders, []),
])
def test_evaluation_exits_cleanly_without_answer_labels(world, module, extra, capsys):
    cfg, config_path = world
    set_active(cfg, _import_tiny(cfg))
    capsys.readouterr()
    assert module.main(["--config", str(config_path), *extra]) == 0
    assert "No answer labels for this dataset ('field-a')" in capsys.readouterr().out


def test_evaluation_still_works_on_the_demo(world, capsys):
    cfg, config_path = world
    assert evaluate_overlap.main(["--config", str(config_path)]) == 0
    assert "Precision" in capsys.readouterr().out
