"""Phase 13: storage for hosts with no permanent disk (Postgres), and the unchanged SQLite path.

The Postgres tests run only when FAIRLEND_TEST_DATABASE_URL points at a test database. Each run uses its own fresh
schema and drops it afterwards. They check that users, sessions, the audit log, the dataset catalog and the dataset
files live in Postgres, so a new API with an EMPTY cache folder (a wiped disk) still sees everything. The SQLite
tests always run. All data is demonstration data; the URL is never printed.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.bootstrap import demo_status
from src.config import load_config
from src.datasets import DEMO, PRESENT_VARIABLE, get_dataset_paths
from src.import_data import TABLES
from src.make_sample_pack import build_scenario
from src import db as lending_db

from api.accounts import NOT_RECOGNISED, ROLES
from api.appdb import AppDatabase, DatabaseUnavailable, PostgresDatabase
from api.data_source import DemoDataSource, presentation_config
from api.main import create_app
from api.settings import Settings, SettingsError, load_settings
from api.store import LocalFolderFiles, PostgresBlobFiles

TEST_URL = os.environ.get("FAIRLEND_TEST_DATABASE_URL", "").strip()
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="Set FAIRLEND_TEST_DATABASE_URL to run the Postgres tests")
ORIGIN = "https://fairlend.example.org"
GOOD = {"Origin": ORIGIN}
PASSWORD = "correct horse 42"
DEMO_FINGERPRINT = "3945277a047220916234197d5844183d2ae84313ad9ba5fced6246ffe5d3df9e"


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


# --- The SQLite path is unchanged (always runs) ----------------------------------------------------------------------

def test_without_database_url_the_backend_is_sqlite_and_local_folders(demo_source, tmp_path):
    settings = Settings(web_origins=["http://localhost:3000"], data_dir=tmp_path / "web")
    assert settings.backend == "sqlite" and settings.secure_cookies is False
    app = create_app(source=demo_source, settings=settings, prepare=False)
    svc = app.state.services
    assert isinstance(svc.accounts.db, AppDatabase) and isinstance(svc.files, LocalFolderFiles)
    assert not isinstance(svc.files, PostgresBlobFiles)
    svc.accounts.create_user("admin@example.org", "admin", PASSWORD, created_by="test")
    response = TestClient(app).post("/api/auth/login", json={"email": "admin@example.org", "password": PASSWORD},
                                    headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200 and "Secure" not in response.headers["set-cookie"]
    assert (tmp_path / "web" / "app.db").exists()
    assert load_settings({}).database_url is None


def test_database_url_without_a_session_secret_refuses_to_start(demo_source):
    settings = Settings(database_url="postgresql://user@127.0.0.1:1/none")
    with pytest.raises(SettingsError, match="FAIRLEND_SESSION_SECRET"):
        create_app(source=demo_source, settings=settings, prepare=False)


def test_the_database_url_is_never_shown():
    settings = load_settings({"DATABASE_URL": "postgresql://someone:hunter2-not-real@db.example.org/x",
                              "FAIRLEND_SESSION_SECRET": "also-not-shown"})
    assert "hunter2" not in repr(settings) and "also-not-shown" not in repr(settings)
    assert settings.backend == "postgres" and settings.secure_cookies is True
    database = PostgresDatabase("postgresql://someone:hunter2-not-real@127.0.0.1:1/x")
    assert "hunter2" not in repr(database)
    with pytest.raises(DatabaseUnavailable) as caught:
        with database.connect():
            pass
    assert "hunter2" not in str(caught.value) and "127.0.0.1" not in str(caught.value)


# --- Postgres ------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def schema():
    if not TEST_URL:
        pytest.skip("Set FAIRLEND_TEST_DATABASE_URL to run the Postgres tests")
    name = f"fairlend_t_{uuid.uuid4().hex[:12]}"
    yield name
    import psycopg
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


def _settings(schema: str, cache: Path) -> Settings:
    return Settings(web_origins=[ORIGIN], database_url=TEST_URL, database_schema=schema,
                    session_secret="test-secret-not-real", cache_dir=cache)


def _client(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")  # Secure cookies are only sent over HTTPS


def _signed_in(app, role: str) -> TestClient:
    client = _client(app)
    response = client.post("/api/auth/login", json={"email": f"{role}@example.org", "password": PASSWORD},
                           headers=GOOD)
    assert response.status_code == 200, response.text
    return client


@pytest.fixture(scope="module")
def pg_app(demo_source, schema, tmp_path_factory):
    app = create_app(source=demo_source, settings=_settings(schema, tmp_path_factory.mktemp("cache_a")),
                     prepare=False)
    for role in ROLES:
        app.state.services.accounts.create_user(f"{role}@example.org", role, PASSWORD, created_by="test")
    return app


@pytest.fixture(scope="module")
def pack(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("pack")
    build_scenario(load_config(), "baseline", root)
    return root / "baseline" / "lender_D"


@pytest.fixture(scope="module")
def imported(pg_app, pack):
    files = [("files", (f"{t}.csv", (pack / f"{t}.csv").read_bytes(), "text/csv")) for t in TABLES]
    body = _signed_in(pg_app, "importer").post(
        "/api/imports", data={"file_type": "csv", "mode": "new", "name": "Lender D demo", "as_of": "2026-10-01",
                              "permission": "true"}, files=files, headers=GOOD).json()
    assert body["stage"] == "imported", body
    return body["dataset"]


@needs_postgres
def test_postgres_holds_users_sessions_and_secure_cookies(pg_app):
    svc = pg_app.state.services
    assert isinstance(svc.accounts.db, PostgresDatabase) and isinstance(svc.files, PostgresBlobFiles)
    client = _client(pg_app)
    response = client.post("/api/auth/login", json={"email": "admin@example.org", "password": PASSWORD}, headers=GOOD)
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert client.get("/api/users").status_code == 200
    with svc.accounts.db.connect() as conn:
        hashes = [r["password_hash"] for r in conn.execute("SELECT password_hash FROM users").fetchall()]
        sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    assert len(hashes) >= 3 and all(h.startswith("$argon2id$") for h in hashes) and sessions >= 1
    assert client.post("/api/auth/logout", headers=GOOD).status_code == 200
    assert client.get("/api/users").status_code == 401


@needs_postgres
def test_postgres_login_throttle(pg_app):
    pg_app.state.services.accounts.create_user("throttled@example.org", "viewer", PASSWORD, created_by="test")
    client = _client(pg_app)
    wrong = {"email": "throttled@example.org", "password": "not the password"}
    for _ in range(5):
        assert client.post("/api/auth/login", json=wrong, headers=GOOD).json() == {"detail": NOT_RECOGNISED}
    locked = client.post("/api/auth/login", json={"email": "throttled@example.org", "password": PASSWORD},
                         headers=GOOD)
    assert locked.status_code == 401
    entries = _signed_in(pg_app, "admin").get("/api/audit").json()["entries"]
    assert any(e["action"] == "login_locked" for e in entries)


@needs_postgres
def test_an_import_is_stored_in_postgres_and_survives_a_wiped_disk(pg_app, imported, demo_source, schema,
                                                                   tmp_path_factory):
    svc = pg_app.state.services
    assert set(svc.files.stored_names(imported)) >= {"lending.db", "predictions.db", "dataset.json"}
    before = _signed_in(pg_app, "viewer").get(f"/api/overview?dataset={imported}").json()["kpis"]
    # A new API process whose cache folder is empty, as after a host restart that wiped the disk.
    fresh_cache = tmp_path_factory.mktemp("cache_b")
    again = create_app(source=demo_source, settings=_settings(schema, fresh_cache), prepare=False)
    assert not any(fresh_cache.iterdir())
    viewer = _signed_in(again, "viewer")
    assert imported in [d["slug"] for d in viewer.get("/api/datasets").json()["datasets"]]
    after = viewer.get(f"/api/overview?dataset={imported}").json()["kpis"]
    assert after == before
    assert (fresh_cache / imported / "lending.db").exists()  # downloaded on first use


@needs_postgres
def test_a_saved_review_label_is_uploaded_again(pg_app, imported, demo_source, schema, tmp_path_factory):
    importer = _signed_in(pg_app, "importer")
    ids = importer.post("/api/review/batch", json={"dataset": imported, "kind": "random", "size": 2},
                        headers=GOOD).json()["ids"]
    saved = importer.post("/api/review/label", json={"dataset": imported, "message_id": ids[0], "label": "normal",
                                                     "kind": "random"}, headers=GOOD)
    assert saved.status_code == 200
    again = create_app(source=demo_source, settings=_settings(schema, tmp_path_factory.mktemp("cache_c")),
                       prepare=False)
    summary = _signed_in(again, "importer").get(f"/api/review?dataset={imported}").json()
    assert summary["reviewed"] == 1
    entries = _signed_in(again, "admin").get("/api/audit").json()["entries"]
    assert any(e["action"] == "review_label" for e in entries)
    assert any(e["action"] == "import_new" for e in entries)


@needs_postgres
def test_deleting_removes_the_blobs_and_the_catalog_entry(pg_app, pack):
    files = [("files", (f"{t}.csv", (pack / f"{t}.csv").read_bytes(), "text/csv")) for t in TABLES]
    made = _signed_in(pg_app, "importer").post(
        "/api/imports", data={"file_type": "csv", "mode": "new", "name": "To delete", "as_of": "2026-10-01",
                              "permission": "true"}, files=files, headers=GOOD).json()
    slug = made["dataset"]
    svc = pg_app.state.services
    assert svc.files.stored_names(slug)
    admin = _signed_in(pg_app, "admin")
    assert admin.request("DELETE", f"/api/datasets/{slug}", json={"confirm_name": "To delete"},
                         headers=GOOD).status_code == 200
    assert svc.files.stored_names(slug) == [] and svc.catalog.get(slug) is None
    assert not (svc.files.root / slug).exists()
    assert admin.get(f"/api/overview?dataset={slug}").status_code == 404


@needs_postgres
def test_the_demo_is_untouched_by_the_postgres_backend(pg_app, imported):
    paths = get_dataset_paths(load_config(), DEMO)
    conn = sqlite3.connect(f"{paths.lending_db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        assert lending_db.content_hash(conn) == DEMO_FINGERPRINT
    finally:
        conn.close()
    assert _client(pg_app).get("/api/overview").json()["kpis"]["borrowers_scored"] == 5000
