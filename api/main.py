"""The FastAPI app (Phase 12A, extended in 12B with sign-in, roles, shared datasets and the Data import page).

Start it with `python -m api` (see docs/UI_V2.md). The demo is prepared and loaded during start-up (api.prepare,
then DemoDataSource.load), never on a visitor's first request.

  - The built-in demo is readable without signing in, and nothing can change or delete it.
  - Every other dataset needs a signed-in user; every endpoint names its access rule (api.deps).
  - Only these routes change anything: sign-in/out, users (Admin), dataset delete (Admin) and import (Importer).
    Each also requires the request to come from a configured front-end origin (cross-site protection).
    Any other method on any other route answers 405.
  - Uploads are kept in memory (never spooled to disk) and capped in size before they are read, so a refused
    upload is never written anywhere.
  - CORS allows only the configured front-end origins, GET only. The web app normally calls the API through its
    own proxy (same origin), which is what lets the SameSite=Strict session cookie work.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.formparsers import MultiPartParser

from src.config import load_config

from api import views
from api.accounts import AccountStore
from api.appdb import AppDatabase
from api.audit import AuditLog
from api.data_source import DataNotReady, DataSource, DataSources, DemoDataSource, Snapshot, UnknownDataset
from api.deps import Public, Services, dataset_reader
from api.routes import router as phase12b_router, unknown_dataset_handler
from api.security import load_secret
from api.settings import Settings, load_settings
from api.store import LocalFolderFiles, SqliteCatalog

UPLOAD_PATHS = ("/api/imports",)
UPLOAD_OVERHEAD = 1024 * 1024  # multipart headers and text fields on top of the files themselves


def build_services(settings: Settings, source: DataSource) -> Services:
    """Wire the stores. Nothing is created on disk until something is first read or written."""
    db = AppDatabase(settings.data_dir / "app.db")
    base_cfg = load_config(settings.config_path) if settings.config_path else load_config()
    sources = DataSources(source, catalog=SqliteCatalog(db), files=LocalFolderFiles(settings.data_dir / "datasets"),
                          base_cfg_loader=lambda: _copy(base_cfg))
    accounts = AccountStore(db, lambda: load_secret(settings.session_secret, settings.data_dir),
                            session_hours=settings.session_hours, max_attempts=settings.max_login_attempts,
                            lockout_minutes=settings.lockout_minutes,
                            password_min_length=settings.password_min_length)
    return Services(settings=settings, sources=sources, accounts=accounts, audit=AuditLog(db))


def _copy(cfg: dict) -> dict:
    import copy
    return copy.deepcopy(cfg)


def create_app(source: DataSource | None = None, settings: Settings | None = None, prepare: bool = True,
               classify_imports: bool = True) -> FastAPI:
    """prepare=True builds the demo if it is missing or stale (start-up only). Tests pass a loaded source."""
    settings = settings or load_settings()
    source = source or DemoDataSource(settings.config_path)
    svc = build_services(settings, source)
    upload_limit = int(float(svc.sources.base_config()["team_demo"]["max_upload_mb"]) * 1024 * 1024)
    # Keep uploaded files in memory up to the upload limit, so nothing is spooled to a temporary file on disk.
    MultiPartParser.spool_max_size = max(MultiPartParser.spool_max_size, upload_limit + UPLOAD_OVERHEAD)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if prepare:
            from api.prepare import prepare_demo
            prepare_demo(settings.config_path)
        try:
            if source.status()["state"] != "ready":
                source.load()
        except DataNotReady:
            pass  # /api/health reports the reason; data endpoints answer 503 with it
        yield

    app = FastAPI(title="FairLend Watch API", version="12B", lifespan=lifespan,
                  description="Synthetic data. A flag is a prompt for a human to look, not a verdict.")
    app.state.source = source          # the demo source (Phase 12A name, kept for tests)
    app.state.services = svc
    app.state.classify_imports = classify_imports
    app.add_middleware(CORSMiddleware, allow_origins=settings.web_origins, allow_methods=["GET"],
                       allow_headers=[], allow_credentials=False, expose_headers=["Content-Disposition"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith(UPLOAD_PATHS):
            length = request.headers.get("content-length")
            if length is None or not length.isdigit():
                return JSONResponse({"detail": "Upload refused: the request size is unknown."}, status_code=411)
            if int(length) > upload_limit + UPLOAD_OVERHEAD:
                return JSONResponse({"detail": f"Upload refused: at most {upload_limit // (1024 * 1024)} MB. "
                                               "Nothing was stored."}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(DataNotReady)
    async def not_ready(_: Request, error: DataNotReady):
        return JSONResponse({"detail": str(error)}, status_code=503)

    @app.exception_handler(views.BadRequest)
    async def bad_request(_: Request, error: views.BadRequest):
        return JSONResponse({"detail": str(error)}, status_code=400)

    app.add_exception_handler(UnknownDataset, unknown_dataset_handler)

    Dataset = Depends(dataset_reader)

    @app.get("/api/health")
    def health(_=Public):
        status = source.status()
        return {"status": "ok" if status["state"] == "ready" else status["state"], "source": source.name,
                "presentation_mode": True, "read_only": True, **{k: v for k, v in status.items() if k != "state"}}

    @app.get("/api/meta")
    def meta(snap: Snapshot = Dataset):
        return views.meta(snap)

    @app.get("/api/overview")
    def overview(snap: Snapshot = Dataset):
        return views.overview(snap)

    @app.get("/api/borrowers")
    def borrowers(bands: str | None = None, regions: str | None = None,
                  min_score: float = Query(0.0, ge=0, le=100), min_open_lenders: int = Query(0, ge=0),
                  min_abusive: int = Query(0, ge=0), q: str = Query("", max_length=40), sort: str = "score",
                  order: str = "desc", page: int = Query(1, ge=1), page_size: int | None = Query(None, ge=1, le=200),
                  snap: Snapshot = Dataset):
        return views.borrowers(snap, bands=bands, regions=regions, min_score=min_score,
                               min_open_lenders=min_open_lenders, min_abusive=min_abusive, q=q, sort=sort,
                               order=order, page=page, page_size=page_size)

    @app.get("/api/borrowers/{borrower_id}")
    def borrower(borrower_id: str, snap: Snapshot = Dataset):
        try:
            return views.borrower(snap, borrower_id)
        except KeyError:
            return JSONResponse({"detail": "No borrower with that code in this dataset."}, status_code=404)

    @app.get("/api/lenders")
    def lenders(snap: Snapshot = Dataset):
        return views.lenders(snap)

    @app.get("/api/lenders/{lender_id}")
    def lender(lender_id: str, snap: Snapshot = Dataset):
        try:
            return views.lender(snap, lender_id)
        except KeyError:
            return JSONResponse({"detail": "No lender with that id in this dataset."}, status_code=404)

    @app.get("/api/repayments")
    def repayments(snap: Snapshot = Dataset):
        return views.repayments(snap)

    @app.get("/api/repayments/follow-up")
    def follow_up(lenders: str | None = None, statuses: str | None = None, bands: str | None = None,
                  sort: str = "days_past_due", order: str = "desc", page: int = Query(1, ge=1),
                  page_size: int = Query(25, ge=1, le=200), snap: Snapshot = Dataset):
        return views.follow_up(snap, lenders=lenders, statuses=statuses, bands=bands, sort=sort, order=order,
                               page=page, page_size=page_size)

    @app.get("/api/repayments/follow-up.csv")
    def follow_up_csv(lenders: str | None = None, statuses: str | None = None, bands: str | None = None,
                      sort: str = "days_past_due", order: str = "desc", snap: Snapshot = Dataset):
        body = views.follow_up_csv(snap, lenders=lenders, statuses=statuses, bands=bands, sort=sort, order=order)
        return Response(body, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="repayment_follow_up.csv"'})

    app.include_router(phase12b_router)
    return app
