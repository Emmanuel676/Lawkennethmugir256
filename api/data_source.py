"""The single data-source layer: the only place the API gets a dataset from (Phase 12A, extended in 12B).

Every endpoint asks for a read-only Snapshot and never opens a database itself. Two kinds of source:

  DemoDataSource      the built-in demonstration dataset, loaded once at start-up through the existing engine
                      (src.dashboard_data.load_all and src.repayments.load), exactly as the Streamlit pages load it.
                      Readable without signing in. Nothing in the API can change or delete it.
  ImportedDataSource  one shared dataset imported through the Data import page (Phase 12B). Its files live in
                      api.store's storage; it is loaded with the same engine calls on first use after a restart,
                      and right after each import.

DataSources holds the demo and a cache of imported snapshots, keyed by slug, and forgets a snapshot when its
dataset changes or is deleted. Every dataset, built in or imported, is labelled "Demonstration data" (api.wording);
the engine's own notice lines are replaced by that neutral wording before they reach the web app.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from src import repayments as rp
from src.config import load_config
from src.dashboard_data import DashboardData, load_all
from src.datasets import DEMO, get_active_name, presentation_mode
from src.redaction import Redactor, build_redactor

from api import wording  # noqa: E402

DEMO_TRUST_LINE = wording.TRUST_LINE
IMPORTED_LABEL = wording.IMPORTED_LABEL
IMPORTED_TRUST_LINE = wording.TRUST_LINE
IMPORTED_NOTICE = wording.NOTICE


class DataNotReady(RuntimeError):
    """The dataset is not loaded (still starting, or it failed). The message is safe to show."""


class UnknownDataset(KeyError):
    """No dataset with that name. The message is safe to show."""


@dataclass(frozen=True)
class Snapshot:
    """One loaded dataset, never changed after it is built. Pages only read it."""

    cfg: dict
    data: DashboardData
    repayments: dict
    redactor: Redactor
    loaded_at: float
    load_seconds: float
    slug: str = DEMO
    name: str = wording.DEMO_NAME
    kind: str = "demo"               # 'demo' or 'imported'
    label: str = wording.DEMO_LABEL
    notice: str = ""                 # first line of CSV exports
    trust_line: str = DEMO_TRUST_LINE

    def redact(self, text) -> str:
        """Message text as it may be shown: personal details replaced by [PHONE], [EMAIL], [ID], [NAME]."""
        return self.redactor.redact(text)[0]


class DataSource(Protocol):
    name: str

    def load(self) -> None: ...

    def snapshot(self) -> Snapshot: ...

    def status(self) -> dict: ...


def presentation_config(config_path: str | None = None) -> dict:
    """The config with presentation mode switched on: only the demo can ever be the active dataset."""
    cfg = copy.deepcopy(load_config(config_path) if config_path else load_config())
    cfg.setdefault("app", {})["presentation_mode"] = True
    return cfg


def repayment_lenders(data: DashboardData) -> pd.DataFrame:
    """The lender list the Repayments page passes to src.repayments.load (same frame, same order)."""
    return (data.loans[["lender_id", "lender_name"]].drop_duplicates().rename(columns={"lender_name": "name"})
            .sort_values("lender_id"))


def _load_snapshot(cfg: dict, started: float, **identity) -> Snapshot:
    data = load_all(cfg)
    if not data.ok:
        raise DataNotReady(f"This dataset cannot be shown yet ({data.status}). {data.message}".strip())
    result = rp.load(cfg, data.borrowers, repayment_lenders(data))
    return Snapshot(cfg=cfg, data=data, repayments=result, redactor=build_redactor(cfg), loaded_at=time.time(),
                    load_seconds=round(time.time() - started, 2), **identity)


class DemoDataSource:
    """The built-in demonstration dataset, read-only. load() is called once, at start-up, never by a visitor."""

    name = "demo"

    def __init__(self, config_path: str | None = None):
        self._config_path = config_path
        self._snapshot: Snapshot | None = None
        self._error: str = ""
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            started = time.time()
            cfg = presentation_config(self._config_path)
            if not presentation_mode(cfg) or get_active_name(cfg) != DEMO:
                # FAIRLEND_PRESENT=0 would let a stored real dataset become active; the API never serves one as demo.
                self._error = ("The API serves only the built-in demonstration dataset as its demo. Unset "
                               "FAIRLEND_PRESENT and start it again.")
                raise DataNotReady(self._error)
            data = load_all(cfg)
            if not data.ok:
                self._error = f"The demo data is not ready ({data.status}). Run: python -m api.prepare"
                raise DataNotReady(self._error)
            if data.real:
                self._error = "The active dataset is not the built-in demonstration dataset, so the API will not serve it."
                raise DataNotReady(self._error)
            result = rp.load(cfg, data.borrowers, repayment_lenders(data))
            self._snapshot = Snapshot(cfg=cfg, data=data, repayments=result, redactor=build_redactor(cfg),
                                      loaded_at=time.time(), load_seconds=round(time.time() - started, 2),
                                      notice=wording.NOTICE)
            self._error = ""

    def snapshot(self) -> Snapshot:
        if self._snapshot is None:
            raise DataNotReady(self._error or "The dataset is still loading. Try again in a few seconds.")
        return self._snapshot

    def status(self) -> dict:
        if self._snapshot is not None:
            return {"state": "ready", "load_seconds": self._snapshot.load_seconds}
        return {"state": "error" if self._error else "loading", "message": self._error}


class DataSources:
    """The demo plus the shared imported datasets (catalog + files from api.store)."""

    def __init__(self, demo: DataSource, catalog=None, files=None, base_cfg_loader=None):
        self.demo = demo
        self.catalog = catalog
        self.files = files
        self._base_cfg_loader = base_cfg_loader or (lambda: copy.deepcopy(load_config()))
        self._cache: dict[str, Snapshot] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def base_config(self) -> dict:
        return self._base_cfg_loader()

    def snapshot(self, slug: str | None = None) -> Snapshot:
        slug = slug or DEMO
        if slug == DEMO:
            return self.demo.snapshot()
        if self.catalog is None or self.files is None:
            raise UnknownDataset("No dataset with that name.")
        cached = self._cache.get(slug)
        if cached is not None:
            return cached
        with self._guard:
            lock = self._locks.setdefault(slug, threading.Lock())
        with lock:
            cached = self._cache.get(slug)
            if cached is not None:
                return cached
            record = self.catalog.get(slug)
            if record is None or not self.files.exists(self.base_config(), slug):
                raise UnknownDataset("No dataset with that name.")
            started = time.time()
            cfg = self.files.engine_config(self.base_config(), slug)
            snap = _load_snapshot(cfg, started, slug=slug, name=record.name, kind="imported", label=IMPORTED_LABEL,
                                  notice=IMPORTED_NOTICE, trust_line=IMPORTED_TRUST_LINE)
            self._cache[slug] = snap
            return snap

    def forget(self, slug: str) -> None:
        self._cache.pop(slug, None)
