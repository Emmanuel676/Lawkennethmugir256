"""Endpoints added in Phase 12C: Guided Demo, About, Export and Review labels.

Access rules (api.deps):
  Guided Demo, About, Export   dataset_reader: the demo's are public; an imported dataset's need a signed-in Viewer
  Review labels                access_importer (Importer and Admin), imported datasets only; saving a label also
                               needs same_origin and is recorded in the audit log
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from src.review import ReviewError

from api import review as reviewing
from api import views
from api.accounts import User
from api.data_source import Snapshot
from api.deps import Importer, SameOrigin, dataset_reader, services

router = APIRouter(prefix="/api")
Dataset = Depends(dataset_reader)


def _csv(body: bytes, name: str) -> Response:
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- Guided Demo, About ----------------------------------------------------------------------------------------------

@router.get("/guided-demo")
def guided_demo(snap: Snapshot = Dataset):
    return views.guided_demo(snap)


@router.get("/about")
def about(snap: Snapshot = Dataset):
    return views.about(snap)


# --- Export ----------------------------------------------------------------------------------------------------------

@router.get("/export")
def export_summary(bands: str | None = None, min_abusive: int = Query(0, ge=0), snap: Snapshot = Dataset):
    return views.export_summary(snap, bands=bands, min_abusive=min_abusive)


@router.get("/export/flagged-borrowers.csv")
def export_flagged(bands: str | None = None, min_abusive: int = Query(0, ge=0), snap: Snapshot = Dataset):
    return _csv(views.flagged_csv(snap, bands=bands, min_abusive=min_abusive), "flagged_borrowers.csv")


@router.get("/export/lender-comparison.csv")
def export_lenders(snap: Snapshot = Dataset):
    return _csv(views.lenders_csv(snap), "lender_comparison.csv")


# --- Review labels (Importer and Admin, imported datasets only) -------------------------------------------------------

def _unavailable(error: Exception) -> JSONResponse:
    return JSONResponse({"available": False, "reason": str(error)}, status_code=200)


@router.get("/review")
def review_summary(request: Request, dataset: str = Query("demo", max_length=80), _: User = Importer):
    try:
        return reviewing.summary(services(request), dataset)
    except reviewing.ReviewUnavailable as error:
        return _unavailable(error)


class BatchRequest(BaseModel):
    dataset: str = Field(max_length=80)
    kind: str
    size: int = 20


@router.post("/review/batch", dependencies=[SameOrigin])
def review_batch(body: BatchRequest, request: Request, _: User = Importer):
    try:
        return {"ids": reviewing.batch(services(request), body.dataset, body.kind, body.size)}
    except (reviewing.ReviewUnavailable, ReviewError) as error:
        return JSONResponse({"detail": str(error)}, status_code=400)


@router.get("/review/message/{message_id}")
def review_message(message_id: str, request: Request, dataset: str = Query(..., max_length=80), _: User = Importer):
    svc = services(request)
    try:
        snap = svc.sources.snapshot(dataset)
        return reviewing.message(svc, dataset, message_id, snap.redact)
    except (reviewing.ReviewUnavailable, ReviewError) as error:
        return JSONResponse({"detail": str(error)}, status_code=400)


class LabelRequest(BaseModel):
    dataset: str = Field(max_length=80)
    message_id: str = Field(max_length=80)
    label: str
    kind: str
    reviewer: str | None = Field(default=None, max_length=20)


@router.post("/review/label", dependencies=[SameOrigin])
def review_label(body: LabelRequest, request: Request, user: User = Importer):
    svc = services(request)
    try:
        result = reviewing.label(svc, body.dataset, body.message_id, body.label, body.kind, body.reviewer)
    except (reviewing.ReviewUnavailable, ReviewError) as error:
        return JSONResponse({"detail": str(error)}, status_code=400)
    record = svc.catalog.get(body.dataset)
    svc.audit.record(user.email, "review_label", record.name if record else body.dataset,
                     {"message_id": body.message_id, "label": body.label, "batch": body.kind,
                      "model_agreed": result["agreed"]})
    svc.files.save(svc.sources.base_config(), body.dataset)  # Postgres: re-upload the dataset's labels file
    svc.sources.forget(body.dataset)  # the pages reload with the person's label in place of the model's
    return result


@router.get("/review/export.csv")
def review_export(request: Request, dataset: str = Query(..., max_length=80), _: User = Importer):
    svc = services(request)
    try:
        snap = svc.sources.snapshot(dataset)
        return _csv(reviewing.export_csv(svc, dataset, snap.notice), f"reviewed_labels_{dataset}.csv")
    except reviewing.ReviewUnavailable as error:
        return JSONResponse({"detail": str(error)}, status_code=400)
