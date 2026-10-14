"""Datasets: the demo data and any real data you import, and which one is active.

A dataset is a set of files the app and the commands work on:

  demo   the synthetic data built by `python -m src.build_all`. Its files stay
         where they have always been (the 'paths' section of config.yaml).
  real   data you imported (src/import_data.py). Each lives in its own folder,
         paths.datasets_dir/<slug>/, holding lending.db, predictions.db and
         dataset.json (name, slug, kind, created_at, source_description,
         as_of_date, notes). Real data has no answer labels.

The active dataset's slug is kept in paths.active_dataset_file (default: demo).
get_active_paths() is THE place the dashboard and the commands get their
database paths from.

Guards: the active dataset cannot be deleted; deleting needs the dataset's
name typed in; deleting the demo also needs an extra confirmation and a saved
classifier model, because the classifier is trained on the demo's synthetic
text. restore_demo() rebuilds the demo with the existing generator and classifier.

Presentation mode (Phase 5.2, app.presentation_mode or the FAIRLEND_PRESENT environment
variable, which wins): the active dataset is ALWAYS the demo and list_datasets() returns only
the demo. In that mode this module never reads active_dataset.txt and never lists or opens a
real dataset folder, so real data cannot appear on a projector by accident.

This module never reads the answer-label tables. Real data is confidential.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.config import resolve_path

DEMO = "demo"
DEFAULT_DATASET = DEMO
KINDS = ("demo", "real")
INFO_FILE = "dataset.json"
REAL_NOTICE = ("REAL DATA: collected under permission. Handle as confidential. "
               "Flags prompt a human to look; they are not findings.")
DEMO_EXTRA_FILES = ("manifest",)  # config 'paths' keys besides the databases that belong to the demo
DEMO_OUTPUT_FILES = ("borrower_scores.csv", "lender_comparison.csv")
PRESENT_VARIABLE = "FAIRLEND_PRESENT"
_ON, _OFF = ("1", "true", "yes", "on"), ("0", "false", "no", "off")


class DatasetError(ValueError):
    """A dataset action was refused. The message says why in plain words."""


@dataclass(frozen=True)
class DatasetPaths:
    """Files of one dataset. ground_truth_db is optional (real data has no answer labels)
    and is for the evaluation modules only; the dashboard never uses it."""

    name: str
    lending_db: Path
    predictions_db: Path
    ground_truth_db: Path | None = None


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    slug: str
    kind: str
    created_at: str
    source_description: str
    as_of_date: str
    notes: str
    paths: DatasetPaths

    @property
    def exists(self) -> bool:
        return self.paths.lending_db.exists()


# --- Locations ----------------------------------------------------------------------------

def datasets_root(cfg: dict) -> Path:
    return resolve_path(cfg, "datasets_dir")


def _active_file(cfg: dict) -> Path:
    return resolve_path(cfg, "active_dataset_file")


def slugify(name: str) -> str:
    """'Field data, Gulu (May)' -> 'field-data-gulu-may'."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    return slug[:60].strip("-")


def get_dataset_paths(cfg: dict, slug: str) -> DatasetPaths:
    """Paths of a dataset by slug. The demo uses the 'paths' section of config.yaml."""
    if slug == DEMO:
        paths = cfg["paths"]
        return DatasetPaths(
            name=DEMO,
            lending_db=resolve_path(cfg, "lending_db"),
            predictions_db=resolve_path(cfg, "predictions_db"),
            ground_truth_db=resolve_path(cfg, "ground_truth_db") if paths.get("ground_truth_db") else None,
        )
    folder = datasets_root(cfg) / slug
    return DatasetPaths(name=slug, lending_db=folder / "lending.db", predictions_db=folder / "predictions.db")


def _real_exists(cfg: dict, slug: str) -> bool:
    return bool(slug) and slug != DEMO and (datasets_root(cfg) / slug / INFO_FILE).is_file()


def dataset_exists(cfg: dict, slug: str) -> bool:
    if slug == DEMO:
        return get_dataset_paths(cfg, DEMO).lending_db.exists()
    return _real_exists(cfg, slug)


# --- Presentation mode -------------------------------------------------------------------------

def presentation_mode(cfg: dict) -> bool:
    """True when the app must show the demo only. FAIRLEND_PRESENT (1/0, true/false...) wins over the config."""
    value = os.environ.get(PRESENT_VARIABLE, "").strip().lower()
    if value in _ON:
        return True
    if value in _OFF:
        return False
    return bool(cfg.get("app", {}).get("presentation_mode", False))


# --- The active dataset ----------------------------------------------------------------------

def get_active_name(cfg: dict) -> str:
    """Slug of the active dataset. Falls back to 'demo' if the stored choice is missing or gone.

    In presentation mode it is always 'demo', and the stored choice is not even read.
    """
    if presentation_mode(cfg):
        return DEMO
    path = _active_file(cfg)
    try:
        slug = path.read_text(encoding="utf-8").strip()
    except OSError:
        return DEMO
    return slug if _real_exists(cfg, slug) else DEMO


def get_active_paths(cfg: dict) -> DatasetPaths:
    """Paths of the active dataset (demo unless another one was chosen)."""
    return get_dataset_paths(cfg, get_active_name(cfg))


def paths_for(cfg: dict, slug: str | None = None) -> DatasetPaths:
    """Paths of the named dataset, or of the active one when no name is given (for --dataset options)."""
    if slug is None:
        return get_active_paths(cfg)
    if slug != DEMO and not _real_exists(cfg, slug):
        raise DatasetError(f"There is no dataset called {slug!r}. Run: python -m src.datasets --list")
    return get_dataset_paths(cfg, slug)


NO_LABELS = "No answer labels for this dataset"


def evaluation_paths(cfg: dict, slug: str | None = None) -> tuple[DatasetPaths | None, str]:
    """(paths, '') for a dataset that has answer labels, or (None, a plain message) for one that has none.

    Only the evaluation modules use this. Real datasets never have answer labels.
    """
    paths = paths_for(cfg, slug)
    if paths.ground_truth_db is None or not paths.ground_truth_db.exists():
        return None, (f"{NO_LABELS} ('{paths.name}'). Accuracy can only be measured on data with known answers, "
                      "such as the demo. Switch with: python -m src.datasets --use demo")
    return paths, ""


def set_active(cfg: dict, slug: str) -> None:
    """Make a dataset the active one for the app and the commands. Refused in presentation mode."""
    if presentation_mode(cfg):
        raise DatasetError("Presentation mode is on: only the demo can be used. Turn it off to switch datasets.")
    if slug != DEMO and not _real_exists(cfg, slug):
        raise DatasetError(f"There is no dataset called {slug!r}.")
    path = _active_file(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(slug + "\n", encoding="utf-8")


# --- Reading datasets ----------------------------------------------------------------------------

def _read_meta(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            return dict(conn.execute("SELECT key, value FROM meta"))
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def is_synthetic(paths: DatasetPaths) -> bool:
    """True only if the dataset's own meta table says synthetic = 'true'."""
    return _read_meta(paths.lending_db).get("synthetic") == "true"


def dataset_meta(paths: DatasetPaths) -> dict[str, str]:
    return _read_meta(paths.lending_db)


def _demo_info(cfg: dict) -> DatasetInfo:
    paths = get_dataset_paths(cfg, DEMO)
    meta = _read_meta(paths.lending_db)
    created = ""
    if paths.lending_db.exists():
        created = datetime.fromtimestamp(paths.lending_db.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M")
    return DatasetInfo(
        name=DEMO, slug=DEMO, kind="demo", created_at=created,
        source_description=f"Synthetic data from src.generate_data (seed {meta.get('seed', '?')})",
        as_of_date=meta.get("as_of_date", ""), notes="All data is synthetic.", paths=paths)


def _real_info(cfg: dict, slug: str) -> DatasetInfo:
    raw = json.loads((datasets_root(cfg) / slug / INFO_FILE).read_text(encoding="utf-8"))
    return DatasetInfo(
        name=raw.get("name", slug), slug=slug, kind=raw.get("kind", "real"), created_at=raw.get("created_at", ""),
        source_description=raw.get("source_description", ""), as_of_date=raw.get("as_of_date", ""),
        notes=raw.get("notes", ""), paths=get_dataset_paths(cfg, slug))


def get_dataset(cfg: dict, slug: str) -> DatasetInfo:
    if slug == DEMO:
        return _demo_info(cfg)
    if not _real_exists(cfg, slug):
        raise DatasetError(f"There is no dataset called {slug!r}.")
    return _real_info(cfg, slug)


def list_datasets(cfg: dict) -> list[DatasetInfo]:
    """The demo (if its files exist) followed by every real dataset, oldest first. Presentation mode: demo only."""
    found = [_demo_info(cfg)] if dataset_exists(cfg, DEMO) else []
    if presentation_mode(cfg):
        return found
    root = datasets_root(cfg)
    if root.is_dir():
        real = [_real_info(cfg, p.name) for p in sorted(root.iterdir()) if (p / INFO_FILE).is_file()]
        found += sorted(real, key=lambda info: (info.created_at, info.slug))
    return found


def dataset_counts(paths: DatasetPaths) -> dict[str, int]:
    """Rows per table in a dataset's lending.db (zeros if it has none yet)."""
    tables = ("lenders", "borrowers", "loans", "transactions", "messages")
    if not paths.lending_db.exists():
        return {t: 0 for t in tables}
    try:
        conn = sqlite3.connect(f"{paths.lending_db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
        finally:
            conn.close()
    except sqlite3.DatabaseError:  # a damaged or empty file: show zeros, the pages explain the problem
        return {t: 0 for t in tables}


# --- Creating, updating and deleting -----------------------------------------------------------

def _write_info(folder: Path, info: dict) -> None:
    (folder / INFO_FILE).write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_dataset(cfg: dict, name: str, source_description: str, as_of_date: str = "",
                   notes: str = "") -> DatasetInfo:
    """Create an empty real dataset folder with its dataset.json. The import fills it."""
    slug = slugify(name)
    if not slug:
        raise DatasetError("Give the dataset a name with at least one letter or number.")
    if slug == DEMO:
        raise DatasetError("'demo' is reserved for the synthetic data. Choose another name.")
    folder = datasets_root(cfg) / slug
    if folder.exists():
        raise DatasetError(f"A dataset called {slug!r} already exists. Choose another name.")
    folder.mkdir(parents=True)
    _write_info(folder, {
        "name": str(name).strip(), "slug": slug, "kind": "real",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "source_description": str(source_description).strip(), "as_of_date": as_of_date, "notes": str(notes).strip(),
    })
    return get_dataset(cfg, slug)


def update_dataset_info(cfg: dict, slug: str, **changes: str) -> None:
    if not _real_exists(cfg, slug):
        raise DatasetError(f"There is no real dataset called {slug!r}.")
    folder = datasets_root(cfg) / slug
    info = json.loads((folder / INFO_FILE).read_text(encoding="utf-8"))
    info.update(changes)
    _write_info(folder, info)


def remove_dataset_folder(cfg: dict, slug: str) -> None:
    """Remove a real dataset's folder (used to undo a failed import). Only ever inside datasets_dir."""
    root = datasets_root(cfg).resolve()
    folder = (root / slug).resolve()
    if slug in ("", DEMO) or folder.parent != root:
        raise DatasetError(f"Refusing to remove {folder}.")
    if folder.exists():
        shutil.rmtree(folder)


def saved_model_exists(cfg: dict) -> bool:
    """True when the trained message classifier has been saved (needed before the demo may be deleted)."""
    return resolve_path(cfg, "local_model").exists()


def delete_dataset(cfg: dict, slug: str, typed_name: str, confirm_demo: bool = False) -> str:
    """Delete a dataset after the guards pass. Returns a plain sentence saying what was removed."""
    if not dataset_exists(cfg, slug):
        raise DatasetError(f"There is no dataset called {slug!r}.")
    info = get_dataset(cfg, slug)
    if slug == get_active_name(cfg):
        raise DatasetError(f"'{info.name}' is the active dataset. Switch to another dataset first.")
    if str(typed_name).strip() not in (slug, info.name):
        raise DatasetError(f"To delete it, type the dataset name exactly: {slug}")

    if slug == DEMO:
        if not confirm_demo:
            raise DatasetError("Deleting the demo needs the extra confirmation box ticked.")
        if not saved_model_exists(cfg):
            raise DatasetError(
                "The demo cannot be deleted yet: the message classifier is trained on its synthetic text and no "
                "saved model exists. Train and save the classifier first, then try again.")
        paths = get_dataset_paths(cfg, DEMO)
        files = [paths.lending_db, paths.predictions_db] + ([paths.ground_truth_db] if paths.ground_truth_db else [])
        files += [resolve_path(cfg, key) for key in DEMO_EXTRA_FILES if key in cfg["paths"]]
        files += [paths.lending_db.parent / name for name in DEMO_OUTPUT_FILES]
        for path in files:
            path.unlink(missing_ok=True)
        return "The demo dataset was deleted. The saved classifier was kept. Use 'Restore demo' to rebuild it."

    remove_dataset_folder(cfg, slug)
    return f"Dataset '{info.name}' and all its files were deleted."


def restore_demo(cfg: dict) -> str:
    """Rebuild the demo with the generator and label it with the local classifier. No network."""
    from src.classify_messages import classify_dataset  # imported here to avoid a circular import
    from src.generate_data import generate, write_world

    paths = get_dataset_paths(cfg, DEMO)
    if paths.ground_truth_db is None:
        raise DatasetError("config.yaml has no paths.ground_truth_db, so the demo cannot be rebuilt.")
    manifest = resolve_path(cfg, "manifest") if "manifest" in cfg["paths"] else None
    write_world(generate(cfg), paths.lending_db, paths.ground_truth_db, manifest)
    labelled = classify_dataset(cfg, paths)
    return f"The demo dataset was rebuilt and {labelled:,} messages were labelled."


def main(argv: list[str] | None = None) -> int:
    import argparse

    from src.config import load_config

    parser = argparse.ArgumentParser(description="List datasets or choose the active one.")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="List datasets (the default).")
    group.add_argument("--use", metavar="NAME", help="Make this dataset the active one.")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if args.use:
        try:
            set_active(cfg, args.use)
        except DatasetError as error:
            print(error)
            return 1
        print(f"Active dataset is now '{args.use}'.")
        return 0
    active = get_active_name(cfg)
    for info in list_datasets(cfg):
        counts = dataset_counts(info.paths)
        marker = "*" if info.slug == active else " "
        print(f"{marker} {info.slug:<24}{info.kind:<6}as of {info.as_of_date or '?':<12}"
              f"{counts['borrowers']:>7,} borrowers{counts['messages']:>8,} messages")
    print("(* = active)")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
