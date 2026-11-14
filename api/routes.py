"""Endpoints added in Phase 12B: sign-in, users, audit, shared datasets and the Data import page.

Each route names its access rule (api.deps) explicitly; state-changing routes also require same_origin.
Nothing here logs or returns a password, a hash, a session token, a cell value or message text.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from src.dashboard_data import data_health
from src.datasets import DEMO, get_dataset_paths
from src.import_data import PERMISSION_TEXT

from api import imports as importing
from api import wording
from api.accounts import NOT_RECOGNISED, ROLES, AccountError, User
from api.audit import ACTIONS
from api.data_source import IMPORTED_LABEL, UnknownDataset
from api.deps import (COOKIE, Admin, Importer, Public, SameOrigin, Viewer, services)

router = APIRouter(prefix="/api")
MAX_FILES = 10


# --- Sign-in -------------------------------------------------------------------------------------------------------

class Credentials(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=500)


def _me(user: User | None) -> dict:
    return {"user": user.public() if user else None, "roles": list(ROLES)}


@router.get("/auth/me")
def me(user: User | None = Public):
    return _me(user)


@router.post("/auth/login", dependencies=[SameOrigin])
def login(body: Credentials, request: Request, _: User | None = Public):
    svc = services(request)
    user, event = svc.accounts.authenticate(body.email, body.password)
    if event == "locked_now":
        svc.audit.record(body.email.strip().lower()[:200], "login_locked",
                         detail={"minutes": svc.settings.lockout_minutes})
    if user is None:
        return JSONResponse({"detail": NOT_RECOGNISED}, status_code=401)
    response = JSONResponse(_me(user))
    response.set_cookie(COOKIE, svc.accounts.start_session(user), max_age=int(svc.accounts.session_seconds),
                        httponly=True, samesite="strict", secure=svc.settings.secure_cookies, path="/")
    return response


@router.post("/auth/logout", dependencies=[SameOrigin])
def logout(request: Request, _: User | None = Public):
    services(request).accounts.end_session(request.cookies.get(COOKIE))
    response = JSONResponse({"user": None, "roles": list(ROLES)})
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                           secure=services(request).settings.secure_cookies)
    return response


# --- Users (Admin) ---------------------------------------------------------------------------------------------------

class NewUser(BaseModel):
    email: str = Field(max_length=200)
    role: str
    password: str = Field(max_length=500)


class UserChange(BaseModel):
    role: str | None = None
    disabled: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(max_length=500)


def _account_error(error: AccountError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=400)


@router.get("/users")
def list_users(request: Request, _: User = Admin):
    return {"users": [u.public() for u in services(request).accounts.list_users()], "roles": list(ROLES),
            "password_min_length": services(request).settings.password_min_length}


@router.post("/users", dependencies=[SameOrigin])
def create_user(body: NewUser, request: Request, admin: User = Admin):
    svc = services(request)
    try:
        user = svc.accounts.create_user(body.email, body.role, body.password, created_by=admin.email)
    except AccountError as error:
        return _account_error(error)
    svc.audit.record(admin.email, "user_create", user.email, {"role": user.role})
    return user.public()


@router.patch("/users/{user_id}", dependencies=[SameOrigin])
def change_user(user_id: int, body: UserChange, request: Request, admin: User = Admin):
    svc = services(request)
    before = svc.accounts.get(user_id)
    try:
        user = svc.accounts.update_user(user_id, role=body.role, disabled=body.disabled, acting=admin)
    except AccountError as error:
        return _account_error(error)
    if before and body.role is not None and body.role != before.role:
        svc.audit.record(admin.email, "user_role", user.email, {"from": before.role, "to": user.role})
    if before and body.disabled is not None and body.disabled != before.disabled:
        svc.audit.record(admin.email, "user_disable" if body.disabled else "user_enable", user.email)
    return user.public()


@router.post("/users/{user_id}/password", dependencies=[SameOrigin])
def reset_password(user_id: int, body: PasswordReset, request: Request, admin: User = Admin):
    svc = services(request)
    try:
        user = svc.accounts.reset_password(user_id, body.password)
    except AccountError as error:
        return _account_error(error)
    svc.audit.record(admin.email, "password_reset", user.email)
    return user.public()


@router.get("/audit")
def audit(request: Request, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), _: User = Admin):
    total, entries = services(request).audit.entries(limit=page_size, offset=(page - 1) * page_size)
    return {"total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size)),
            "entries": entries, "actions": ACTIONS}


# --- Datasets --------------------------------------------------------------------------------------------------------

def _demo_entry(request: Request) -> dict:
    snap = services(request).sources.demo.snapshot()
    counts = {"lenders": int(len(snap.data.lenders)), "borrowers": int(len(snap.data.borrowers)),
              "loans": int(len(snap.data.loans)), "messages": int(len(snap.data.messages))}
    return {"slug": DEMO, "name": wording.DEMO_NAME, "kind": "demo", "label": wording.DEMO_LABEL,
            "notes": "Built from config.yaml and a fixed seed. Cannot be changed or deleted.", "source": "built in",
            "added_by": "built in", "added_at": None, "updated_at": None, "as_of_date": snap.data.as_of_date,
            "counts": counts, "imports": 0, "deletable": False}


@router.get("/datasets")
def list_datasets(request: Request, user: User = Viewer):
    svc = services(request)
    imported = [{**r.public(), "kind": "imported", "label": IMPORTED_LABEL, "deletable": user.can("admin")}
                for r in svc.catalog.list()]
    return {"datasets": [_demo_entry(request)] + imported, "can_import": user.can("importer"),
            "can_delete": user.can("admin")}


def _health(cfg: dict) -> dict:
    health = data_health(cfg)
    per_lender = health["per_lender"]
    return {"borrowers": health["borrowers"], "shared_borrowers": health["shared_borrowers"],
            "min_messages": health["minimum"],
            "per_lender": [] if per_lender.empty else per_lender.to_dict("records")}


@router.get("/datasets/{slug}")
def dataset_detail(slug: str, request: Request, user: User = Viewer):
    svc = services(request)
    if slug == DEMO:
        return {**_demo_entry(request), "health": _health(svc.sources.demo.snapshot().cfg)}
    record = svc.catalog.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail="No dataset with that name.")
    cfg = svc.files.engine_config(svc.sources.base_config(), slug)
    return {**record.public(), "kind": "imported", "label": IMPORTED_LABEL, "deletable": user.can("admin"),
            "health": _health(cfg)}


class DeleteConfirm(BaseModel):
    confirm_name: str = Field(max_length=200)


@router.delete("/datasets/{slug}", dependencies=[SameOrigin])
def delete_dataset(slug: str, body: DeleteConfirm, request: Request, admin: User = Admin):
    svc = services(request)
    if slug == DEMO:
        return JSONResponse({"detail": "The demo dataset cannot be deleted or changed."}, status_code=400)
    record = svc.catalog.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail="No dataset with that name.")
    if body.confirm_name.strip() != record.name:
        return JSONResponse({"detail": f"To delete it, type the dataset name exactly: {record.name}"}, status_code=400)
    svc.sources.forget(slug)
    svc.files.delete(svc.sources.base_config(), slug)
    svc.catalog.remove(slug)
    svc.audit.record(admin.email, "dataset_delete", record.name, {"slug": slug, "counts": record.counts})
    return {"deleted": slug, "message": f"Dataset '{record.name}' and all its files were deleted."}


# --- Data import (Importer and Admin) --------------------------------------------------------------------------------

def _limits(cfg: dict) -> dict:
    return {"max_upload_mb": float(cfg["team_demo"]["max_upload_mb"]),
            "max_rows_per_file": int(cfg["team_demo"]["max_rows_per_file"])}


@router.get("/imports/info")
def import_info(request: Request, _: User = Importer):
    svc = services(request)
    cfg = svc.sources.base_config()
    return {"permission_text": PERMISSION_TEXT, "limits": _limits(cfg),
            "day_first_default": bool(cfg["onboarding"]["day_first_default"]),
            "targets": [{"slug": r.slug, "name": r.name} for r in svc.catalog.list()],
            "label": IMPORTED_LABEL}


@router.get("/imports/template")
def import_template(request: Request, format: str = Query("xlsx", pattern="^(xlsx|csv)$"), _: User = Importer):
    cfg = services(request).sources.base_config()
    if format == "xlsx":
        return Response(importing.template_xlsx(cfg),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="fairlend_import_template.xlsx"'})
    return Response(importing.template_csv_zip(cfg), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="fairlend_import_templates_csv.zip"'})


async def _read_form(request: Request) -> tuple[dict[str, bytes], dict[str, str]]:
    """The uploaded files (kept in memory: see api.main) and the text fields of a multipart form."""
    form = await request.form(max_files=MAX_FILES, max_fields=20)
    files, fields = {}, {}
    for key, value in form.multi_items():
        if hasattr(value, "read"):
            if value.filename:
                files[value.filename.replace("\\", "/").rsplit("/", 1)[-1]] = await value.read()
        else:
            fields[key] = str(value)
    await form.close()
    return files, fields


def _flag(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _target_lending(svc, cfg: dict, mode: str, target: str):
    if mode != "add":
        return None
    if not target or target == DEMO or svc.catalog.get(target) is None:
        raise importing.ImportRequestError("Choose an imported dataset to add to. The demo cannot be changed.")
    return get_dataset_paths(cfg, target).lending_db


@router.post("/imports/check", dependencies=[SameOrigin])
async def import_check(request: Request, user: User = Importer):
    """Gate, then validate. Nothing is written, whatever the result."""
    svc = services(request)
    files, fields = await _read_form(request)
    cfg = svc.files.engine_config(svc.sources.base_config())
    mode = fields.get("mode", "new")
    try:
        target_lending = _target_lending(svc, cfg, mode, fields.get("target", ""))
        outcome = await run_in_threadpool(
            importing.check, files, fields.get("file_type", ""), engine_cfg=cfg, mode=mode,
            target_lending=target_lending, as_of=fields.get("as_of") or None,
            day_first=_flag(fields.get("day_first"), bool(cfg["onboarding"]["day_first_default"])))
    except importing.ImportRequestError as error:
        return JSONResponse({"detail": str(error)}, status_code=400)
    finally:
        files.clear()
    if outcome.stage == "refused":
        svc.audit.record(user.email, "import_refused", fields.get("name", "") or fields.get("target", ""),
                         {"reasons": len(outcome.reasons), "step": "check"})
    return outcome.public()


@router.post("/imports", dependencies=[SameOrigin])
async def import_run(request: Request, user: User = Importer):
    """Gate, then import with the existing importer. Nothing is saved unless the check finds no errors."""
    svc = services(request)
    files, fields = await _read_form(request)
    cfg = svc.files.engine_config(svc.sources.base_config())
    mode = fields.get("mode", "new")
    try:
        _target_lending(svc, cfg, mode, fields.get("target", ""))
        outcome = await run_in_threadpool(
            importing.run_import, files, fields.get("file_type", ""), engine_cfg=cfg, mode=mode,
            name=fields.get("name", ""), notes=fields.get("notes", ""), source=fields.get("source", ""),
            target=fields.get("target", ""), as_of=fields.get("as_of") or None,
            day_first=_flag(fields.get("day_first"), bool(cfg["onboarding"]["day_first_default"])),
            permission=_flag(fields.get("permission"), False), actor=user.email, catalog=svc.catalog,
            files_store=svc.files, classify=request.app.state.classify_imports)
    except importing.ImportRequestError as error:
        return JSONResponse({"detail": str(error)}, status_code=400)
    finally:
        files.clear()
    target = outcome.dataset or fields.get("name", "") or fields.get("target", "")
    if outcome.stage == "refused":
        svc.audit.record(user.email, "import_refused", target, {"reasons": len(outcome.reasons), "step": "import"})
    elif outcome.stage == "invalid":
        svc.audit.record(user.email, "import_failed", target, {"errors": len(outcome.report.errors)})
    elif outcome.stage == "imported":
        svc.sources.forget(outcome.dataset)
        record = svc.catalog.get(outcome.dataset)
        svc.audit.record(user.email, "import_new" if mode == "new" else "import_add",
                         record.name if record else outcome.dataset,
                         {"slug": outcome.dataset, "rows": outcome.report.counts,
                          "already_known": outcome.already_known})
        try:  # warm the cache so the pages open at once (a failure here only means a slower first page)
            await run_in_threadpool(svc.sources.snapshot, outcome.dataset)
        except Exception:
            pass
    body = outcome.public()
    if outcome.stage == "imported":
        record = svc.catalog.get(outcome.dataset)
        body["record"] = {**record.public(), "kind": "imported", "label": IMPORTED_LABEL} if record else None
    return body


def unknown_dataset_handler(_: Request, error: UnknownDataset):
    return JSONResponse({"detail": "No dataset with that name."}, status_code=404)
