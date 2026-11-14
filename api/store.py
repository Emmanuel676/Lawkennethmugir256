"""Shared datasets that persist (Phase 12B): metadata in a catalog, files in one folder per dataset.

Two small interfaces, so either part can be replaced later without touching the rest of the API:

  DatasetCatalog   metadata: name, notes, who added it, when, row counts.   SqliteCatalog (the app database).
  DatasetFiles     where each dataset's files live, and the engine config   LocalFolderFiles (a folder per dataset
                   that points the unchanged src/ engine at them.           under <data_dir>/datasets, git-ignored),
                                                                            or PostgresBlobFiles (Phase 13: files as
                                                                            blobs in Postgres, cached to a temporary
                                                                            folder on first use).

The catalog SQL works on both backends of api.appdb (SQLite locally, Postgres when DATABASE_URL is set).

A Postgres catalog or object storage (download a dataset's folder to a local cache before loading) would implement
the same methods. The built-in demo is NOT in the catalog: it is served by api.data_source.DemoDataSource from
its own files, which nothing here can write or delete.

The engine config for an imported dataset is a copy of config.yaml whose datasets_dir is this storage's folder and
whose active dataset is that one dataset, marked app.team_session (the Phase 11 mechanism) so presentation mode
does not force the demo. The engine marks every import with its own notice; the API labels every imported dataset
"Demonstration data" instead (api.wording).
"""

from __future__ import annotations

import copy
import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.datasets import DEMO, dataset_counts, get_dataset_paths, slugify

from api import security
from api.appdb import AppDatabase

ACTIVE_FILE = "active_dataset.txt"


@dataclass(frozen=True)
class DatasetRecord:
    slug: str
    name: str
    notes: str
    source: str
    added_by: str
    added_at: float
    updated_at: float
    as_of_date: str
    counts: dict = field(default_factory=dict)
    imports: int = 1

    def public(self) -> dict:
        return {"slug": self.slug, "name": self.name, "notes": self.notes, "source": self.source,
                "added_by": self.added_by, "added_at": self.added_at, "updated_at": self.updated_at,
                "as_of_date": self.as_of_date, "counts": self.counts, "imports": self.imports}


class DatasetCatalog(Protocol):
    def list(self) -> list[DatasetRecord]: ...
    def get(self, slug: str) -> DatasetRecord | None: ...
    def add(self, record: DatasetRecord) -> None: ...
    def touch(self, slug: str, counts: dict, as_of_date: str) -> None: ...
    def remove(self, slug: str) -> None: ...


class DatasetFiles(Protocol):
    def engine_config(self, base_cfg: dict, slug: str | None = None) -> dict: ...
    def counts(self, base_cfg: dict, slug: str) -> dict: ...
    def delete(self, base_cfg: dict, slug: str) -> None: ...
    def exists(self, base_cfg: dict, slug: str) -> bool: ...
    def save(self, base_cfg: dict, slug: str) -> None: ...  # after an import or a saved review label


def _record(row) -> DatasetRecord:
    return DatasetRecord(slug=row["slug"], name=row["name"], notes=row["notes"], source=row["source"],
                         added_by=row["added_by"], added_at=row["added_at"], updated_at=row["updated_at"],
                         as_of_date=row["as_of_date"], counts=json.loads(row["counts"] or "{}"),
                         imports=row["imports"])


class SqliteCatalog:
    def __init__(self, db: AppDatabase):
        self.db = db

    def list(self) -> list[DatasetRecord]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM datasets ORDER BY added_at DESC, slug").fetchall()
        return [_record(row) for row in rows]

    def get(self, slug: str) -> DatasetRecord | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE slug = ?", (slug,)).fetchone()
        return _record(row) if row else None

    def add(self, record: DatasetRecord) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO datasets (slug, name, notes, source, added_by, added_at, updated_at, as_of_date, counts,
                                         imports) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.slug, record.name, record.notes, record.source, record.added_by, record.added_at,
                 record.updated_at, record.as_of_date, json.dumps(record.counts, sort_keys=True), record.imports))

    def touch(self, slug: str, counts: dict, as_of_date: str) -> None:
        with self.db.connect() as conn:
            conn.execute("""UPDATE datasets SET counts = ?, as_of_date = ?, updated_at = ?, imports = imports + 1
                            WHERE slug = ?""", (json.dumps(counts, sort_keys=True), as_of_date, security.now(), slug))

    def remove(self, slug: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM datasets WHERE slug = ?", (slug,))


class LocalFolderFiles:
    """One folder per dataset under `root` (created by the existing importer, src.datasets.create_dataset)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def engine_config(self, base_cfg: dict, slug: str | None = None) -> dict:
        """The engine config for this storage (slug=None: for importing a new dataset)."""
        cfg = copy.deepcopy(base_cfg)
        cfg["paths"]["datasets_dir"] = str(self.root)
        cfg.setdefault("app", {})["team_session"] = True  # presentation mode off for THIS config only
        cfg["app"]["presentation_mode"] = False
        if slug is None:
            cfg["paths"]["active_dataset_file"] = str(self.root / ACTIVE_FILE)  # never written
        else:
            self._check_slug(slug)
            active = self.root / slug / ACTIVE_FILE
            if (self.root / slug).is_dir() and not active.exists():
                active.write_text(slug, encoding="utf-8")
            cfg["paths"]["active_dataset_file"] = str(active)
        return cfg

    def _check_slug(self, slug: str) -> None:
        if not slug or slug == DEMO or slugify(slug) != slug:
            raise ValueError("Not a dataset name this storage can hold.")

    def exists(self, base_cfg: dict, slug: str) -> bool:
        self._check_slug(slug)
        return (self.root / slug / "dataset.json").is_file()

    def counts(self, base_cfg: dict, slug: str) -> dict:
        return dataset_counts(get_dataset_paths(self.engine_config(base_cfg, slug), slug))

    def delete(self, base_cfg: dict, slug: str) -> None:
        self._remove_local(slug)

    def _remove_local(self, slug: str) -> None:
        self._check_slug(slug)
        folder = (self.root / slug).resolve()
        if folder.parent != self.root.resolve():
            raise ValueError("Refusing to delete outside the datasets folder.")
        if folder.exists():
            shutil.rmtree(folder)

    def save(self, base_cfg: dict, slug: str) -> None:
        """Nothing to do: the local folder IS the storage."""


SqlCatalog = SqliteCatalog  # the catalog SQL runs on SQLite and Postgres alike (api.appdb)

# Files that make up a dataset folder. Journal files are never stored; the active-dataset marker is rewritten locally.
STORED_SUFFIXES = (".db", ".json")


class PostgresBlobFiles(LocalFolderFiles):
    """Each dataset's files as blobs in Postgres (table dataset_files), for hosts with no permanent disk.

    The engine still reads ordinary files: on first use a dataset's blobs are written to a local cache folder (a
    temporary folder by default), and after an import or a saved review label the folder is uploaded again. If the
    host wipes its disk, the next request simply downloads the files again. One API instance at a time is assumed:
    a second instance would not notice another's changes until its cache is cleared.
    """

    def __init__(self, db, cache_root: Path):
        super().__init__(cache_root)
        self.db = db
        self._lock = threading.Lock()

    def _download(self, slug: str) -> bool:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT name, content FROM dataset_files WHERE slug = ?", (slug,)).fetchall()
        if not rows:
            return False
        folder = self.root / slug
        partial = self.root / f".{slug}.downloading"
        if partial.exists():
            shutil.rmtree(partial)
        partial.mkdir(parents=True)
        for row in rows:
            name = Path(row["name"]).name  # never a path from the database
            (partial / name).write_bytes(bytes(row["content"]))
        if folder.exists():
            shutil.rmtree(folder)
        partial.rename(folder)
        return True

    def _ensure(self, slug: str) -> bool:
        self._check_slug(slug)
        if (self.root / slug / "dataset.json").is_file():
            return True
        with self._lock:
            if (self.root / slug / "dataset.json").is_file():
                return True
            return self._download(slug)

    def exists(self, base_cfg: dict, slug: str) -> bool:
        return self._ensure(slug)

    def engine_config(self, base_cfg: dict, slug: str | None = None) -> dict:
        if slug is not None:
            self._ensure(slug)
        return super().engine_config(base_cfg, slug)

    def save(self, base_cfg: dict, slug: str) -> None:
        self._check_slug(slug)
        folder = self.root / slug
        files = [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix in STORED_SUFFIXES]
        at = security.now()
        with self.db.connect() as conn:
            conn.execute("DELETE FROM dataset_files WHERE slug = ?", (slug,))
            for path in files:
                conn.execute("INSERT INTO dataset_files (slug, name, content, updated_at) VALUES (?, ?, ?, ?)",
                             (slug, path.name, path.read_bytes(), at))

    def delete(self, base_cfg: dict, slug: str) -> None:
        self._check_slug(slug)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM dataset_files WHERE slug = ?", (slug,))
        self._remove_local(slug)

    def stored_names(self, slug: str) -> list[str]:
        with self.db.connect() as conn:
            return [r["name"] for r in conn.execute(
                "SELECT name FROM dataset_files WHERE slug = ? ORDER BY name", (slug,)).fetchall()]
