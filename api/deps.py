"""Access control for every endpoint (Phase 12B).

Every route declares exactly one access dependency, and tests/test_api_auth.py checks that none is missing:

  access_public     anyone, signed in or not (health, meta and data pages of the demo, sign-in, sign-out)
  dataset_reader    the demo: anyone; any other dataset: a signed-in Viewer or above
  access_viewer     a signed-in Viewer, Importer or Admin
  access_importer   a signed-in Importer or Admin
  access_admin      a signed-in Admin

Not signed in -> 401 "Sign in to see this."  Signed in without the role -> 403.

State-changing calls (POST, PATCH, DELETE) also depend on same_origin: the Origin header (or, if a browser
sent none, the Referer) must be one of the configured front-end origins, otherwise 403. Together with the
SameSite=Strict session cookie this blocks cross-site request forgery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query, Request

from src.datasets import DEMO

from api.accounts import AccountStore, User
from api.audit import AuditLog
from api.data_source import DataSources, Snapshot
from api.settings import Settings

COOKIE = "fairlend_session"
SIGN_IN = "Sign in to see this."
NO_ROLE = "Your role does not allow this. Ask an Admin if you need it."
CROSS_SITE = "Cross-site request refused."


@dataclass
class Services:
    settings: Settings
    sources: DataSources
    accounts: AccountStore
    audit: AuditLog

    @property
    def catalog(self):
        return self.sources.catalog

    @property
    def files(self):
        return self.sources.files


def services(request: Request) -> Services:
    return request.app.state.services


def current_user(request: Request) -> User | None:
    """The signed-in user, or None. Touches the database only when a session cookie was sent."""
    cookie = request.cookies.get(COOKIE)
    if not cookie:
        return None
    return services(request).accounts.session_user(cookie)


def _needs(role: str):
    def check(request: Request) -> User:
        user = current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail=SIGN_IN)
        if not user.can(role):
            raise HTTPException(status_code=403, detail=NO_ROLE)
        return user
    check.access_level = role
    check.__name__ = f"access_{role}"
    return check


def access_public(request: Request) -> User | None:
    return current_user(request)


access_public.access_level = "public"
access_viewer = _needs("viewer")
access_importer = _needs("importer")
access_admin = _needs("admin")


def dataset_reader(request: Request, dataset: str = Query(DEMO, max_length=80)) -> Snapshot:
    """The snapshot of the chosen dataset. The demo is public; every other dataset needs a signed-in Viewer."""
    if dataset != DEMO:
        access_viewer(request)
    return services(request).sources.snapshot(dataset)


dataset_reader.access_level = "dataset"


_ORIGIN = re.compile(r"^(https?://[^/?#\s]+)")


def _origin_of(value: str | None) -> str | None:
    """'http://localhost:3000/import?x=1' -> 'http://localhost:3000' (scheme and host only)."""
    match = _ORIGIN.match(value or "")
    return match.group(1).lower() if match else None


def same_origin(request: Request) -> None:
    allowed = set(services(request).settings.web_origins)
    origin = request.headers.get("origin")
    candidate = origin if origin and origin != "null" else _origin_of(request.headers.get("referer"))
    if candidate is None or candidate.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail=CROSS_SITE)


ACCESS_DEPENDENCIES = (access_public, access_viewer, access_importer, access_admin, dataset_reader)
Public = Depends(access_public)
Viewer = Depends(access_viewer)
Importer = Depends(access_importer)
Admin = Depends(access_admin)
SameOrigin = Depends(same_origin)
