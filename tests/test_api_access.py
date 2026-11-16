"""Phase 14: request access with Admin approval, its abuse limits, and the in-place users migration.

A public request creates a PENDING account that cannot sign in until an Admin approves it (as Viewer or Importer) or
rejects it (which deletes it). The answer never reveals whether an email already has an account. The users table
gains the request fields and a status IN PLACE, on SQLite and on Postgres (the Postgres part runs only when
FAIRLEND_TEST_DATABASE_URL points at a test database). All data is demonstration data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from src.bootstrap import demo_status
from src.datasets import PRESENT_VARIABLE

from api import appdb
from api.access import RequestLimiter, client_address
from api.accounts import NOT_RECOGNISED, PENDING_MESSAGE, AccountStore
from api.appdb import AppDatabase, PostgresDatabase
from api.data_source import DemoDataSource, presentation_config
from api.main import create_app
from api.routes import REQUEST_RECEIVED, REQUESTS_PAUSED, TOO_MANY
from api.settings import Settings

ORIGIN = "http://localhost:3000"
GOOD = {"Origin": ORIGIN}
PASSWORD = "correct horse 42"
TEST_URL = os.environ.get("FAIRLEND_TEST_DATABASE_URL", "").strip()


@pytest.fixture(scope="module")
def demo_source():
    status, reason = demo_status(presentation_config())
    if status != "fresh":
        pytest.skip(f"The demo is {status} ({reason}). Build it first: python -m api.prepare")
    mp = pytest.MonkeyPatch()
    mp.setenv(PRESENT_VARIABLE, "1")
    source = DemoDataSource()
    source.load()
    yield source
    mp.undo()


def _app(demo_source, tmp_path, **settings):
    app = create_app(source=demo_source, prepare=False,
                     settings=Settings(web_origins=[ORIGIN], data_dir=tmp_path / "web",
                                       session_secret="test-secret-not-real", **settings))
    app.state.services.accounts.create_user("admin@example.org", "admin", PASSWORD, created_by="test")
    return app


@pytest.fixture
def app(demo_source, tmp_path):
    return _app(demo_source, tmp_path)


def _form(email="new.person@example.org", **changes) -> dict:
    form = {"full_name": "Ada Example", "email": email, "organisation": "Consumer Body Demo",
            "user_type": "regulator", "reason": "To review lending conduct for a demonstration.",
            "password": "a long new password", "password_again": "a long new password", "website": ""}
    form.update(changes)
    return form


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}, headers=GOOD)


def _admin(app) -> TestClient:
    client = TestClient(app)
    assert _login(client, "admin@example.org", PASSWORD).status_code == 200
    return client


def _count_users(app) -> int:
    with app.state.services.accounts.db.connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


# --- Requesting ----------------------------------------------------------------------------------------------------

def test_a_request_creates_a_pending_account_that_cannot_sign_in(app):
    client = TestClient(app)
    response = client.post("/api/access-requests", json=_form(), headers=GOOD)
    assert response.status_code == 200 and response.json() == {"message": REQUEST_RECEIVED}
    assert "no email is sent" in REQUEST_RECEIVED
    pending = app.state.services.accounts.list_pending()
    assert [p.email for p in pending] == ["new.person@example.org"]
    assert pending[0].status == "pending" and pending[0].organisation == "Consumer Body Demo"
    right = _login(client, "new.person@example.org", "a long new password")
    assert right.status_code == 403 and right.json()["detail"] == PENDING_MESSAGE
    wrong = _login(client, "new.person@example.org", "not the password")
    assert wrong.status_code == 401 and wrong.json() == {"detail": NOT_RECOGNISED}
    assert client.get("/api/datasets").status_code == 401
    assert all(u.email != "new.person@example.org" for u in app.state.services.accounts.list_users())


def test_a_known_email_gets_exactly_the_same_answer_and_nothing_changes(app):
    client = TestClient(app)
    first = client.post("/api/access-requests", json=_form(), headers=GOOD)
    before = _count_users(app)
    again = client.post("/api/access-requests", json=_form(full_name="Someone Else"), headers=GOOD)
    existing = client.post("/api/access-requests", json=_form(email="admin@example.org"), headers=GOOD)
    assert first.json() == again.json() == existing.json() == {"message": REQUEST_RECEIVED}
    assert first.status_code == again.status_code == existing.status_code == 200
    assert _count_users(app) == before
    assert _login(client, "admin@example.org", PASSWORD).status_code == 200  # the Admin's password is untouched


def test_the_honeypot_looks_accepted_but_stores_nothing(app):
    before = _count_users(app)
    response = TestClient(app).post("/api/access-requests", json=_form(website="http://spam.example"), headers=GOOD)
    assert response.json() == {"message": REQUEST_RECEIVED}
    assert _count_users(app) == before


@pytest.mark.parametrize("changes, words", [
    ({"password_again": "something different"}, "different"),
    ({"password": "short", "password_again": "short"}, "10 characters"),
    ({"reason": "x" * 501}, "500"),
    ({"full_name": "x" * 101}, "100"),
    ({"organisation": ""}, "organisation"),
    ({"user_type": "superuser"}, "type of user"),
    ({"email": "not-an-email"}, "email"),
])
def test_bad_requests_are_explained_and_store_nothing(app, changes, words):
    before = _count_users(app)
    response = TestClient(app).post("/api/access-requests", json=_form(**changes), headers=GOOD)
    assert response.status_code == 400 and words in response.json()["detail"]
    assert _count_users(app) == before


def test_requests_need_the_web_origin(app):
    client = TestClient(app)
    assert client.post("/api/access-requests", json=_form()).status_code == 403
    assert client.post("/api/access-requests", json=_form(), headers={"Origin": "http://evil.example"}).status_code == 403
    assert app.state.services.accounts.list_pending() == []


# --- Abuse limits --------------------------------------------------------------------------------------------------

def test_requests_are_limited_per_address_and_a_forged_header_does_not_help(demo_source, tmp_path):
    app = _app(demo_source, tmp_path, requests_per_hour=2)
    client = TestClient(app)
    for n in range(2):
        assert client.post("/api/access-requests", json=_form(email=f"p{n}@example.org"), headers=GOOD).status_code == 200
    forged = {**GOOD, "X-Forwarded-For": "203.0.113.9"}
    blocked = client.post("/api/access-requests", json=_form(email="p9@example.org"), headers=forged)
    assert blocked.status_code == 429 and blocked.json()["detail"] == TOO_MANY
    assert len(app.state.services.accounts.list_pending()) == 2


def test_behind_a_trusted_proxy_the_forwarded_address_is_used(demo_source, tmp_path):
    app = _app(demo_source, tmp_path, requests_per_hour=1, proxy_hops=1)
    client = TestClient(app)
    for n, address in enumerate(("198.51.100.1", "198.51.100.2")):
        headers = {**GOOD, "X-Forwarded-For": address}
        assert client.post("/api/access-requests", json=_form(email=f"q{n}@example.org"), headers=headers).status_code == 200
    again = client.post("/api/access-requests", json=_form(email="q9@example.org"),
                        headers={**GOOD, "X-Forwarded-For": "198.51.100.1"})
    assert again.status_code == 429


def test_client_address_rules():
    class Fake:
        def __init__(self, header, peer="10.0.0.5"):
            self.headers = {"x-forwarded-for": header} if header is not None else {}
            self.client = type("C", (), {"host": peer})()

    assert client_address(Fake("1.1.1.1, 2.2.2.2"), 0) == "10.0.0.5"          # no trusted proxy: the peer
    assert client_address(Fake("1.1.1.1, 2.2.2.2"), 1) == "2.2.2.2"
    assert client_address(Fake("9.9.9.9, 1.1.1.1, 2.2.2.2"), 2) == "1.1.1.1"  # Vercel + Render
    assert client_address(Fake("2.2.2.2"), 2) == "10.0.0.5"                   # too short: safe fallback
    assert client_address(Fake(None), 2) == "10.0.0.5"
    clock = {"t": 0.0}
    limiter = RequestLimiter(2, clock=lambda: clock["t"])
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a") and limiter.allow("b")
    clock["t"] = 3601
    assert limiter.allow("a")


def test_the_number_of_pending_requests_is_capped(demo_source, tmp_path):
    app = _app(demo_source, tmp_path, max_pending=2, requests_per_hour=10)
    client = TestClient(app)
    for n in range(2):
        assert client.post("/api/access-requests", json=_form(email=f"c{n}@example.org"), headers=GOOD).status_code == 200
    capped = client.post("/api/access-requests", json=_form(email="c9@example.org"), headers=GOOD)
    assert capped.status_code == 503 and capped.json()["detail"] == REQUESTS_PAUSED
    assert len(app.state.services.accounts.list_pending()) == 2


# --- Approval ------------------------------------------------------------------------------------------------------

def test_admin_sees_pending_requests_and_approves_as_viewer_or_importer(app):
    client = TestClient(app)
    for email in ("v@example.org", "i@example.org", "x@example.org"):
        client.post("/api/access-requests", json=_form(email=email), headers=GOOD)
    admin = _admin(app)
    listing = admin.get("/api/users").json()
    pending = {p["email"]: p for p in listing["pending"]}
    assert set(pending) == {"v@example.org", "i@example.org", "x@example.org"}
    one = pending["v@example.org"]
    assert one["full_name"] == "Ada Example" and one["user_type_label"] == "Regulator or consumer body"
    assert one["reason"].startswith("To review") and one["requested_at"] > 0
    assert "password" not in json.dumps(listing).lower().replace("password_min_length", "")
    assert "argon2" not in json.dumps(listing)
    assert all(u["email"] not in pending for u in listing["users"])
    as_admin = admin.post(f"/api/users/{pending['x@example.org']['id']}/approve", json={"role": "admin"}, headers=GOOD)
    assert as_admin.status_code == 400
    assert admin.post(f"/api/users/{one['id']}/approve", json={"role": "viewer"}, headers=GOOD).json()["role"] == "viewer"
    assert admin.post(f"/api/users/{pending['i@example.org']['id']}/approve", json={"role": "importer"},
                      headers=GOOD).json()["status"] == "active"
    viewer = TestClient(app)
    assert _login(viewer, "v@example.org", "a long new password").status_code == 200
    assert viewer.get("/api/datasets").status_code == 200 and viewer.get("/api/imports/info").status_code == 403
    importer = TestClient(app)
    assert _login(importer, "i@example.org", "a long new password").status_code == 200
    assert importer.get("/api/imports/info").status_code == 200
    again = admin.post(f"/api/users/{one['id']}/approve", json={"role": "viewer"}, headers=GOOD)
    assert again.status_code == 400  # not pending any more


def test_reject_deletes_the_request_and_both_are_audited_without_secrets(app):
    client = TestClient(app)
    client.post("/api/access-requests", json=_form(email="r@example.org"), headers=GOOD)
    client.post("/api/access-requests", json=_form(email="a@example.org"), headers=GOOD)
    admin = _admin(app)
    pending = {p["email"]: p["id"] for p in admin.get("/api/users").json()["pending"]}
    assert admin.post(f"/api/users/{pending['r@example.org']}/reject", headers=GOOD).status_code == 200
    admin.post(f"/api/users/{pending['a@example.org']}/approve", json={"role": "viewer"}, headers=GOOD)
    assert _login(TestClient(app), "r@example.org", "a long new password").json() == {"detail": NOT_RECOGNISED}
    assert "r@example.org" not in [p["email"] for p in admin.get("/api/users").json()["pending"]]
    entries = admin.get("/api/audit").json()["entries"]
    actions = {(e["action"], e["target"]) for e in entries}
    assert ("access_reject", "r@example.org") in actions and ("access_approve", "a@example.org") in actions
    text = json.dumps(entries)
    assert "a long new password" not in text and "argon2" not in text


def test_only_admins_can_approve_or_reject(app):
    TestClient(app).post("/api/access-requests", json=_form(email="z@example.org"), headers=GOOD)
    target = app.state.services.accounts.list_pending()[0].id
    app.state.services.accounts.create_user("imp@example.org", "importer", PASSWORD, created_by="test")
    importer = TestClient(app)
    assert _login(importer, "imp@example.org", PASSWORD).status_code == 200
    assert importer.post(f"/api/users/{target}/approve", json={"role": "viewer"}, headers=GOOD).status_code == 403
    assert importer.post(f"/api/users/{target}/reject", headers=GOOD).status_code == 403
    assert TestClient(app).post(f"/api/users/{target}/reject", headers=GOOD).status_code == 401
    assert app.state.services.accounts.list_pending()[0].id == target


# --- The in-place migration from the Phase 13 schema -------------------------------------------------------------

def test_sqlite_migrates_a_phase_13_database_in_place(tmp_path):
    path = tmp_path / "app.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(appdb.SCHEMA)  # exactly the Phase 13 tables, without the Phase 14 columns
    from api import security
    conn.execute("INSERT INTO users (email, role, password_hash, created_at, created_by) VALUES (?, 'admin', ?, 1, 'x')",
                 ("live.admin@example.org", security.hash_password(PASSWORD)))
    conn.execute("INSERT INTO audit (at, actor, action) VALUES (1, 'live.admin@example.org', 'user_create')")
    conn.commit()
    before = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    conn.close()
    assert "status" not in before
    store = AccountStore(AppDatabase(path), b"secret", session_hours=8, max_attempts=5, lockout_minutes=10,
                         password_min_length=10)
    user, event = store.authenticate("live.admin@example.org", PASSWORD)
    assert event == "ok" and user.status == "active" and user.can("admin")
    conn = sqlite3.connect(str(path))
    after = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    audit_rows = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    conn.close()
    assert {name for name, _ in appdb.USER_COLUMNS_V14} <= after and audit_rows == 1
    AccountStore(AppDatabase(path), b"secret", session_hours=8, max_attempts=5, lockout_minutes=10,
                 password_min_length=10).list_users()  # running it again changes nothing and does not fail


@pytest.mark.skipif(not TEST_URL, reason="Set FAIRLEND_TEST_DATABASE_URL to run the Postgres migration test")
def test_postgres_migrates_a_phase_13_database_in_place():
    import psycopg
    from api import security

    schema = f"fairlend_m_{uuid.uuid4().hex[:12]}"
    try:
        with psycopg.connect(TEST_URL, autocommit=True) as conn:
            conn.execute(f'CREATE SCHEMA "{schema}"')
            conn.execute(f'SET search_path TO "{schema}"')
            for statement in appdb.PG_SCHEMA:  # exactly the Phase 13 tables
                conn.execute(statement)
            conn.execute("INSERT INTO users (email, role, password_hash, created_at, created_by) "
                         "VALUES (%s, 'admin', %s, 1, 'x')", ("live.admin@example.org", security.hash_password(PASSWORD)))
            before = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'users'",
                (schema,))}
        assert "status" not in before
        store = AccountStore(PostgresDatabase(TEST_URL, schema=schema), b"secret", session_hours=8, max_attempts=5,
                             lockout_minutes=10, password_min_length=10)
        user, event = store.authenticate("live.admin@example.org", PASSWORD)
        assert event == "ok" and user.status == "active" and user.can("admin")
        assert store.request_access(full_name="P Q", email="p@example.org", organisation="Org", user_type="other",
                                    reason="Demonstration", password="a long new password",
                                    password_again="a long new password") == "created"
        assert [u.email for u in store.list_pending()] == ["p@example.org"]
        with psycopg.connect(TEST_URL) as conn:
            after = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'users'",
                (schema,))}
        assert {name for name, _ in appdb.USER_COLUMNS_V14} <= after
        # A second start on the migrated database is a no-op.
        AccountStore(PostgresDatabase(TEST_URL, schema=schema), b"secret", session_hours=8, max_attempts=5,
                     lockout_minutes=10, password_min_length=10).list_users()
    finally:
        with psycopg.connect(TEST_URL, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
