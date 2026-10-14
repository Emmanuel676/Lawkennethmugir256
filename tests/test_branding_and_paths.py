"""Checks for the Phase 4 amendments: product name, logo, and dataset-aware paths."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.config import ConfigError, load_config, validate_config
from src.dashboard_ui import CONFIG_VARIABLE, brand_images, light_logo_image, show_logo
from src.datasets import get_active_paths

from leak_check import names_used, string_literals
from worlds import build_classified_world, config_for, write_config

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["app.py"] + sorted(f"pages/{p.name}" for p in (ROOT / "pages").glob("*.py"))
DASHBOARD_MODULES = PAGES + ["src/dashboard_data.py", "src/dashboard_ui.py", "src/build_all.py"]
DB_FILE_NAMES = ("lending.db", "predictions.db", "ground_truth.db")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return build_classified_world(tmp_path_factory.mktemp("branding_world"))


def _run(page: str) -> AppTest:
    return AppTest.from_file(str(ROOT / page), default_timeout=120).run()


# --- Product name -------------------------------------------------------------------

def test_name_and_tagline_are_in_the_config():
    cfg = load_config()
    assert cfg["project"]["name"] == "FairLend Watch"
    assert cfg["project"]["tagline"] == "Lending conduct monitor"


@pytest.mark.parametrize("page", PAGES)
def test_name_appears_on_every_page(page, world, monkeypatch):
    cfg, config_path = world
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    at = _run(page)
    assert not at.exception
    assert cfg["project"]["name"] in at.title[0].value
    assert any(cfg["project"]["tagline"] in c.value for c in at.caption)


@pytest.mark.parametrize("page", PAGES)
def test_name_is_read_from_the_config_not_hard_coded(page, world, monkeypatch, tmp_path):
    cfg, _ = world
    renamed = copy.deepcopy(cfg)
    renamed["project"]["name"] = "Renamed Product Q"
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(renamed, tmp_path / "config.yaml")))
    at = _run(page)
    assert not at.exception
    assert "Renamed Product Q" in at.title[0].value
    assert "FairLend" not in at.title[0].value


@pytest.mark.parametrize("page", PAGES)
def test_name_appears_even_without_data(page, world, monkeypatch, tmp_path):
    cfg, _ = world
    empty = config_for(tmp_path / "empty", cfg)
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(empty, tmp_path / "config.yaml")))
    at = _run(page)
    assert not at.exception
    assert cfg["project"]["name"] in at.title[0].value


def test_empty_name_or_tagline_is_rejected():
    for key in ("name", "tagline"):
        broken = copy.deepcopy(load_config())
        broken["project"][key] = "  "
        with pytest.raises(ConfigError, match=f"project.{key}"):
            validate_config(broken)


# --- Logo -----------------------------------------------------------------------------

def test_the_logo_files_are_found():
    assert set(brand_images()) == {"logo", "icon"}


def test_logo_helpers_do_not_raise_when_assets_are_missing(tmp_path):
    assert brand_images(tmp_path) == {}
    assert show_logo(tmp_path) is False
    assert light_logo_image(assets_dir=tmp_path) is False


def test_logo_helpers_do_not_raise_on_broken_files(tmp_path):
    for name in ("fairlend-watch-logo.svg", "fairlend-watch-icon.svg"):
        (tmp_path / name).write_bytes(b"\x00not an image")
    show_logo(tmp_path)  # must simply not raise
    light_logo_image(assets_dir=tmp_path)


def test_about_page_shows_the_logo_image(world, monkeypatch):
    _, config_path = world
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    at = _run("pages/4_About.py")
    assert not at.exception
    assert len(at.get("image")) == 1


# --- Dataset-aware paths ---------------------------------------------------------------------

def test_active_paths_are_the_demo_dataset_from_the_config(world):
    cfg, _ = world
    active = get_active_paths(cfg)
    assert active.name == "demo"
    assert str(active.lending_db) == cfg["paths"]["lending_db"]
    assert str(active.predictions_db) == cfg["paths"]["predictions_db"]
    assert str(active.ground_truth_db) == cfg["paths"]["ground_truth_db"]


def test_ground_truth_path_is_optional(world):
    cfg = copy.deepcopy(world[0])
    del cfg["paths"]["ground_truth_db"]
    assert get_active_paths(cfg).ground_truth_db is None


@pytest.mark.parametrize("module", DASHBOARD_MODULES)
def test_no_hard_coded_database_paths(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    hard_coded = [s for s in string_literals(source) if any(name in s for name in DB_FILE_NAMES)]
    assert hard_coded == []


@pytest.mark.parametrize("module", PAGES + ["src/dashboard_data.py", "src/dashboard_ui.py"])
def test_pages_and_data_layer_get_paths_only_from_get_active_paths(module):
    used = names_used((ROOT / module).read_text(encoding="utf-8"))
    assert "resolve_path" not in used


def test_path_check_catches_a_hard_coded_path():
    assert string_literals('"""Reads data/lending.db."""\npath = "data/lending.db"\n') == ["data/lending.db"]
    assert "resolve_path" in names_used("from src.config import resolve_path\n")
