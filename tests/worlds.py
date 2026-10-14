"""Shared helper for the tests: build a small classified world in a temporary folder.

Writes lending.db and the answer-label file, a config file whose paths point at
that folder, and labels every message with the local classifier, exactly as
`python -m src.build_all` does for the real dataset.
"""

from __future__ import annotations

import contextlib
import copy
import io
from pathlib import Path

import yaml

from src.classify_messages import main as classify_main
from src.config import load_config
from src.generate_data import generate, write_world


def config_for(folder: Path, base: dict) -> dict:
    """A copy of the config whose data paths all point into folder."""
    custom = copy.deepcopy(base)
    custom["paths"] = {
        "lending_db": str(folder / "lending.db"),
        "ground_truth_db": str(folder / "ground_truth.db"),
        "manifest": str(folder / "dataset_manifest.json"),
        "predictions_db": str(folder / "predictions.db"),
        "local_model": str(folder / "local_model.joblib"),
        "datasets_dir": str(folder / "datasets"),
        "active_dataset_file": str(folder / "active_dataset.txt"),
    }
    return custom


def write_config(cfg: dict, path: Path) -> Path:
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def build_classified_world(folder: Path, n_borrowers: int = 800, seed: int = 11) -> tuple[dict, Path]:
    """Generate, write and classify a world in folder. Returns (config, config file path)."""
    folder.mkdir(parents=True, exist_ok=True)
    cfg = config_for(folder, load_config())
    cfg["generator"]["test_set_size"] = 40
    world = generate(cfg, seed=seed, n_borrowers=n_borrowers)
    write_world(world, folder / "lending.db", folder / "ground_truth.db", folder / "dataset_manifest.json")
    config_path = write_config(cfg, folder / "config.yaml")
    with contextlib.redirect_stdout(io.StringIO()):
        assert classify_main(["--classifier", "local", "--config", str(config_path)]) == 0
    return load_config(config_path), config_path
