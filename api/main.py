"""The FastAPI app: GET-only JSON endpoints over the data-source layer (Phase 12A).

Start it with `python -m api` (see docs/UI_V2.md). The dataset is prepared and loaded during start-up
(api.prepare, then DataSource.load), never on a visitor's first request. Presentation mode: no endpoint can
write or import data, and any method other than GET, HEAD or OPTIONS is refused with 405. CORS allows only
the configured front-end origins (FAIRLEND_WEB_ORIGINS).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from api import views
from api.data_source import DataNotReady, DataSource, DemoDataSource
from api.settings import Settings, load_settings

READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_app(source: DataSource | None = None, settings: Settings | None = None, prepare: bool = True) -> FastAPI:
    """prepare=True builds the demo if it is missing or stale (start-up only). Tests pass a loaded source."""
    settings = settings or load_settings()
    source = source or DemoDataSource(settings.config_path)

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

    app = FastAPI(title="FairLend Watch API", version="12A", lifespan=lifespan,
                  description="Read-only. Synthetic data. A flag is a prompt for a human to look, not a verdict.")
    app.state.source = source
    app.add_middleware(CORSMiddleware, allow_origins=settings.web_origins, allow_methods=["GET"],
                       allow_headers=[], allow_credentials=False, expose_headers=["Content-Disposition"])

    @app.middleware("http")
    async def read_only(request: Request, call_next):
        if request.method not in READ_METHODS:
            return JSONResponse({"detail": "This API is read-only (presentation mode)."}, status_code=405)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(DataNotReady)
    async def not_ready(_: Request, error: DataNotReady):
        return JSONResponse({"detail": str(error)}, status_code=503)

    @app.exception_handler(views.BadRequest)
    async def bad_request(_: Request, error: views.BadRequest):
        return JSONResponse({"detail": str(error)}, status_code=400)

    def snap():
        return source.snapshot()

    @app.get("/api/health")
    def health():
        status = source.status()
        return {"status": "ok" if status["state"] == "ready" else status["state"], "source": source.name,
                "presentation_mode": True, "read_only": True, **{k: v for k, v in status.items() if k != "state"}}

    @app.get("/api/meta")
    def meta():
        return views.meta(snap())

    @app.get("/api/overview")
    def overview():
        return views.overview(snap())

    @app.get("/api/borrowers")
    def borrowers(bands: str | None = None, regions: str | None = None,
                  min_score: float = Query(0.0, ge=0, le=100), min_open_lenders: int = Query(0, ge=0),
                  min_abusive: int = Query(0, ge=0), q: str = Query("", max_length=40), sort: str = "score",
                  order: str = "desc", page: int = Query(1, ge=1), page_size: int | None = Query(None, ge=1, le=200)):
        return views.borrowers(snap(), bands=bands, regions=regions, min_score=min_score,
                               min_open_lenders=min_open_lenders, min_abusive=min_abusive, q=q, sort=sort,
                               order=order, page=page, page_size=page_size)

    @app.get("/api/borrowers/{borrower_id}")
    def borrower(borrower_id: str):
        try:
            return views.borrower(snap(), borrower_id)
        except KeyError:
            return JSONResponse({"detail": "No borrower with that code in this dataset."}, status_code=404)

    @app.get("/api/lenders")
    def lenders():
        return views.lenders(snap())

    @app.get("/api/lenders/{lender_id}")
    def lender(lender_id: str):
        try:
            return views.lender(snap(), lender_id)
        except KeyError:
            return JSONResponse({"detail": "No lender with that id in this dataset."}, status_code=404)

    @app.get("/api/repayments")
    def repayments():
        return views.repayments(snap())

    @app.get("/api/repayments/follow-up")
    def follow_up(lenders: str | None = None, statuses: str | None = None, bands: str | None = None,
                  sort: str = "days_past_due", order: str = "desc", page: int = Query(1, ge=1),
                  page_size: int = Query(25, ge=1, le=200)):
        return views.follow_up(snap(), lenders=lenders, statuses=statuses, bands=bands, sort=sort, order=order,
                               page=page, page_size=page_size)

    @app.get("/api/repayments/follow-up.csv")
    def follow_up_csv(lenders: str | None = None, statuses: str | None = None, bands: str | None = None,
                      sort: str = "days_past_due", order: str = "desc"):
        body = views.follow_up_csv(snap(), lenders=lenders, statuses=statuses, bands=bands, sort=sort, order=order)
        return Response(body, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="repayment_follow_up.csv"'})

    return app
