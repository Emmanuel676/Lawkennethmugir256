"""The single data-source layer: the only place the API gets a dataset from (Phase 12A).

Every endpoint asks a DataSource for a read-only Snapshot and never opens a database itself. Phase 12A has one
source, DemoDataSource: the synthetic demo, loaded once at start-up through the existing engine
(src.dashboard_data.load_all and src.repayments.load), exactly as the Streamlit pages load it.

Later phases (login with Viewer / Importer / Admin roles, shared datasets that persist, a Data import page with
the synthetic-only gate) add other sources behind this same interface. Nothing here can write or import data.
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


class DataNotReady(RuntimeError):
    """The dataset is not loaded (still starting, or it failed). The message is safe to show."""


@dataclass(frozen=True)
class Snapshot:
    """One loaded dataset, never changed after it is built. Pages only read it."""

    cfg: dict
    data: DashboardData
    repayments: dict
    redactor: Redactor
    loaded_at: float
    load_seconds: float

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


class DemoDataSource:
    """The synthetic demo, read-only. load() is called once, by the start-up script, never by a visitor."""

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
                # FAIRLEND_PRESENT=0 would let a stored real dataset become active; the API never serves one.
                self._error = "The API serves the synthetic demo only. Unset FAIRLEND_PRESENT and start it again."
                raise DataNotReady(self._error)
            data = load_all(cfg)
            if not data.ok:
                self._error = f"The demo data is not ready ({data.status}). Run: python -m api.prepare"
                raise DataNotReady(self._error)
            if data.real:
                self._error = "The active dataset is not synthetic, so the API will not serve it."
                raise DataNotReady(self._error)
            result = rp.load(cfg, data.borrowers, repayment_lenders(data))
            self._snapshot = Snapshot(cfg=cfg, data=data, repayments=result, redactor=build_redactor(cfg),
                                      loaded_at=time.time(), load_seconds=round(time.time() - started, 2))
            self._error = ""

    def snapshot(self) -> Snapshot:
        if self._snapshot is None:
            raise DataNotReady(self._error or "The dataset is still loading. Try again in a few seconds.")
        return self._snapshot

    def status(self) -> dict:
        if self._snapshot is not None:
            return {"state": "ready", "load_seconds": self._snapshot.load_seconds}
        return {"state": "error" if self._error else "loading", "message": self._error}
