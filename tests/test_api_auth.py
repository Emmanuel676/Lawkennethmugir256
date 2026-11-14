"""Phase 12B: sign-in, roles, sessions, the login throttle and cross-site protection of the API (api/).

Uses a temporary data folder for users and sessions; the demo is the real synthetic demo (loaded read-only).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import create_admin, security
from api.accounts import NOT_RECOGNISED, RANK, ROLES
from api.data_source import DemoDataSource, presentation_config
from api.deps import ACCESS_DEPENDENCIES, COOKIE
from api.main import create_app
from api.settings import Settings
from src.bootstrap import demo_status
from src.datasets import PRESENT_VARIABLE

ORIGIN = "http://localhost:3000"
GOOD = {"Origin": ORIGIN}
PASSWORD = "correct horse 42"


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


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock for sessions and lockouts."""
    state = {"t": 1_800_000_000.0}
    monkeypatch.setattr(security, "now", lambda: state["t"])
    return state


@pytest.fixture
def app(demo_source, tmp_path, clock):
    settings = Settings(web_origins=[ORIGIN], data_dir=tmp_path / "web", session_secret="test-secret-not-real",
                        session_hours=8)
    application = create_app(source=demo_source, settings=settings, prepare=False, classify_imports=False)
    accounts = application.state.services.accounts
    for role in ROLES:
        accounts.create_user(f"{role}@example.org", role, PASSWORD, created_by="test")
    return application


def _client(app) -> TestClient:
    return TestClient(app)


def _signed_in(app, role: str) -> TestClient:
    client = _client(app)
    response = client.post("/api/auth/login", json={"email": f"{role}@example.org", "password": PASSWORD},
                           headers=GOOD)
    assert response.status_code == 200, response.text
    return client


# --- Every endpoint names its access rule ----------------------------------------------------------------------------

def _calls(dependant) -> set:
    found = {dependant.call} if dependant.call else set()
    for child in dependant.dependencies:
        found |= _calls(child)
    return found


def test_every_endpoint_has_an_explicit_access_rule(app):
    routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api")]
    assert routes
    for route in routes:
        rules = _calls(route.dependant) & set(ACCESS_DEPENDENCIES)
        assert len(rules) == 1, f"{route.path} must declare exactly one access rule, found {len(rules)}"


# --- The role matrix -----------------------------------------------------------------------------------------------

# (method, path, json body, the least role allowed). 'public' = anyone; 'viewer' etc. = that role or above.
MATRIX = [
    ("GET", "/api/health", None, "public"),
    ("GET", "/api/meta", None, "public"),
    ("GET", "/api/overview", None, "public"),
    ("GET", "/api/borrowers", None, "public"),
    ("GET", "/api/lenders", None, "public"),
    ("GET", "/api/repayments", None, "public"),
    ("GET", "/api/repayments/follow-up.csv", None, "public"),
    ("GET", "/api/auth/me", None, "public"),
    ("GET", "/api/overview?dataset=someone-elses", None, "viewer"),
    ("GET", "/api/borrowers?dataset=someone-elses", None, "viewer"),
    ("GET", "/api/datasets", None, "viewer"),
    ("GET", "/api/datasets/demo", None, "viewer"),
    ("GET", "/api/imports/info", None, "importer"),
    ("GET", "/api/imports/template?format=xlsx", None, "importer"),
    ("GET", "/api/imports/template?format=csv", None, "importer"),
    ("POST", "/api/imports/check", None, "importer"),
    ("POST", "/api/imports", None, "importer"),
    ("GET", "/api/users", None, "admin"),
    ("POST", "/api/users", {"email": "new@example.org", "role": "viewer", "password": "short"}, "admin"),
    ("PATCH", "/api/users/999999", {"role": "viewer"}, "admin"),
    ("POST", "/api/users/999999/password", {"password": "another long one"}, "admin"),
    ("DELETE", "/api/datasets/not-there", {"confirm_name": "x"}, "admin"),
    ("GET", "/api/audit", None, "admin"),
]
WHO = ("anonymous",) + ROLES


def _call(client, method, path, body):
    if method == "POST" and path.startswith("/api/imports"):
        return client.post(path, data={"file_type": "csv", "mode": "new"}, headers=GOOD)
    return client.request(method, path, json=body, headers=GOOD)


@pytest.mark.parametrize("who", WHO)
def test_each_role_can_do_exactly_what_it_should(app, who):
    client = _client(app) if who == "anonymous" else _signed_in(app, who)
    for method, path, body, least in MATRIX:
        response = _call(client, method, path, body)
        allowed = least == "public" or (who != "anonymous" and RANK[who] >= RANK[least])
        if allowed:
            assert response.status_code not in (401, 403), (who, method, path, response.status_code)
        else:
            expected = 401 if who == "anonymous" else 403
            assert response.status_code == expected, (who, method, path, response.status_code, response.text)


# --- Sign-in, sessions, sign-out -----------------------------------------------------------------------------------

def test_sign_in_sets_a_strict_httponly_cookie_and_never_returns_a_hash(app):
    client = _client(app)
    response = client.post("/api/auth/login", json={"email": "Viewer@Example.org ", "password": PASSWORD},
                           headers=GOOD)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Max-Age=28800" in cookie
    assert response.json()["user"]["role"] == "viewer"
    assert "argon2" not in response.text and "password" not in response.json()["user"]
    assert client.get("/api/auth/me").json()["user"]["email"] == "viewer@example.org"


def test_passwords_are_stored_only_as_argon2_hashes(app):
    db = app.state.services.accounts.db
    with db.connect() as conn:
        rows = conn.execute("SELECT password_hash FROM users").fetchall()
        tokens = conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert rows and all(r["password_hash"].startswith("$argon2id$") for r in rows)
    assert all(PASSWORD not in r["password_hash"] for r in rows)
    _signed_in(app, "viewer")
    with db.connect() as conn:
        tokens = conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert tokens and all(re.fullmatch(r"[0-9a-f]{64}", t["token_hash"]) for t in tokens)


def test_every_failure_shows_the_same_message(app):
    app.state.services.accounts.update_user(
        app.state.services.accounts.list_users()[-1].id, disabled=True,
        acting=app.state.services.accounts.list_users()[0])  # viewer@ (last alphabetically) disabled by admin@
    client = _client(app)
    attempts = [{"email": "nobody@example.org", "password": PASSWORD},
                {"email": "importer@example.org", "password": "wrong password!"},
                {"email": "viewer@example.org", "password": PASSWORD},   # disabled
                {"email": "not an email", "password": PASSWORD}]
    for body in attempts:
        response = client.post("/api/auth/login", json=body, headers=GOOD)
        assert response.status_code == 401
        assert response.json() == {"detail": NOT_RECOGNISED}


def test_five_wrong_passwords_lock_the_account_for_ten_minutes(app, clock):
    client = _client(app)
    wrong = {"email": "importer@example.org", "password": "not the password"}
    right = {"email": "importer@example.org", "password": PASSWORD}
    for _ in range(5):
        assert client.post("/api/auth/login", json=wrong, headers=GOOD).status_code == 401
    locked = client.post("/api/auth/login", json=right, headers=GOOD)
    assert locked.status_code == 401 and locked.json() == {"detail": NOT_RECOGNISED}
    _, entries = app.state.services.audit.entries()
    assert any(e["action"] == "login_locked" and e["actor"] == "importer@example.org" for e in entries)
    assert "not the password" not in json.dumps(entries)
    clock["t"] += 9 * 60
    assert client.post("/api/auth/login", json=right, headers=GOOD).status_code == 401
    clock["t"] += 61
    assert client.post("/api/auth/login", json=right, headers=GOOD).status_code == 200
    # other accounts were never affected
    assert _client(app).post("/api/auth/login", json={"email": "admin@example.org", "password": PASSWORD},
                             headers=GOOD).status_code == 200


def test_four_wrong_passwords_then_the_right_one_resets_the_count(app):
    client = _client(app)
    wrong = {"email": "viewer@example.org", "password": "nope nope nope"}
    for _ in range(4):
        client.post("/api/auth/login", json=wrong, headers=GOOD)
    assert client.post("/api/auth/login", json={"email": "viewer@example.org", "password": PASSWORD},
                       headers=GOOD).status_code == 200
    for _ in range(4):
        client.post("/api/auth/login", json=wrong, headers=GOOD)
    assert client.post("/api/auth/login", json={"email": "viewer@example.org", "password": PASSWORD},
                       headers=GOOD).status_code == 200


def test_sessions_expire(app, clock):
    client = _signed_in(app, "viewer")
    assert client.get("/api/datasets").status_code == 200
    clock["t"] += 8 * 3600 - 5
    assert client.get("/api/datasets").status_code == 200
    clock["t"] += 10
    assert client.get("/api/datasets").status_code == 401
    assert client.get("/api/auth/me").json()["user"] is None


def test_sign_out_ends_the_session_even_for_a_copied_cookie(app):
    client = _signed_in(app, "admin")
    stolen = client.cookies.get(COOKIE)
    assert client.post("/api/auth/logout", headers=GOOD).status_code == 200
    replay = _client(app)
    replay.cookies.set(COOKIE, stolen)
    assert replay.get("/api/users").status_code == 401


def test_a_forged_cookie_is_refused(app):
    client = _signed_in(app, "viewer")
    token, _, mac = client.cookies.get(COOKIE).rpartition(".")
    forged = _client(app)
    forged.cookies.set(COOKIE, f"{token}.{'0' * len(mac)}")
    assert forged.get("/api/datasets").status_code == 401
    forged.cookies.set(COOKIE, "admin")
    assert forged.get("/api/users").status_code == 401


# --- Cross-site protection -----------------------------------------------------------------------------------------

def test_state_changing_requests_need_the_web_origin(app):
    client = _client(app)
    body = {"email": "admin@example.org", "password": PASSWORD}
    assert client.post("/api/auth/login", json=body).status_code == 403
    assert client.post("/api/auth/login", json=body, headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/auth/login", json=body, headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/auth/login", json=body,
                       headers={"Referer": "http://evil.example/http://localhost:3000"}).status_code == 403
    assert client.post("/api/auth/login", json=body,
                       headers={"Referer": f"{ORIGIN}/signin"}).status_code == 200
    # signed in as Admin, a cross-site request still cannot change anything
    for method, path, payload in (("POST", "/api/users", {"email": "x@example.org", "role": "admin",
                                                          "password": "long enough pw"}),
                                  ("DELETE", "/api/datasets/anything", {"confirm_name": "anything"}),
                                  ("POST", "/api/auth/logout", None)):
        response = client.request(method, path, json=payload, headers={"Origin": "http://evil.example"})
        assert response.status_code == 403, path
    assert all(u.email != "x@example.org" for u in app.state.services.accounts.list_users())
    assert client.get("/api/auth/me").json()["user"]["role"] == "admin"  # the cross-site logout did nothing


# --- Users (Admin) -------------------------------------------------------------------------------------------------

def test_admin_creates_users_sets_roles_resets_and_disables(app):
    admin = _signed_in(app, "admin")
    short = admin.post("/api/users", json={"email": "new@example.org", "role": "viewer", "password": "123456789"},
                       headers=GOOD)
    assert short.status_code == 400 and "10 characters" in short.json()["detail"]
    created = admin.post("/api/users", json={"email": "New@Example.org", "role": "viewer",
                                             "password": "a long password"}, headers=GOOD)
    assert created.status_code == 200 and created.json()["email"] == "new@example.org"
    assert admin.post("/api/users", json={"email": "new@example.org", "role": "viewer",
                                          "password": "a long password"}, headers=GOOD).status_code == 400
    uid = created.json()["id"]
    user = _client(app)
    assert user.post("/api/auth/login", json={"email": "new@example.org", "password": "a long password"},
                     headers=GOOD).status_code == 200
    assert user.get("/api/imports/info").status_code == 403
    assert admin.patch(f"/api/users/{uid}", json={"role": "importer"}, headers=GOOD).json()["role"] == "importer"
    assert user.get("/api/imports/info").status_code == 401  # a role change ends the old session
    assert user.post("/api/auth/login", json={"email": "new@example.org", "password": "a long password"},
                     headers=GOOD).status_code == 200
    assert user.get("/api/imports/info").status_code == 200
    assert admin.post(f"/api/users/{uid}/password", json={"password": "a brand new password"},
                      headers=GOOD).status_code == 200
    assert user.get("/api/imports/info").status_code == 401  # a reset ends sessions too
    assert user.post("/api/auth/login", json={"email": "new@example.org", "password": "a long password"},
                     headers=GOOD).status_code == 401
    assert user.post("/api/auth/login", json={"email": "new@example.org", "password": "a brand new password"},
                     headers=GOOD).status_code == 200
    assert admin.patch(f"/api/users/{uid}", json={"disabled": True}, headers=GOOD).json()["disabled"] is True
    assert user.get("/api/datasets").status_code == 401
    listing = admin.get("/api/users").json()
    assert "argon2" not in json.dumps(listing) and "password_hash" not in json.dumps(listing)
    actions = [e["action"] for e in admin.get("/api/audit").json()["entries"]]
    for action in ("user_create", "user_role", "password_reset", "user_disable"):
        assert action in actions
    assert "a brand new password" not in json.dumps(admin.get("/api/audit").json())


def test_the_last_admin_cannot_lock_everyone_out(app):
    admin = _signed_in(app, "admin")
    me = admin.get("/api/auth/me").json()["user"]["id"]
    refused = admin.patch(f"/api/users/{me}", json={"role": "viewer"}, headers=GOOD)
    assert refused.status_code == 400
    assert admin.patch(f"/api/users/{me}", json={"disabled": True}, headers=GOOD).status_code == 400


def test_there_is_no_public_sign_up(app):
    assert _client(app).post("/api/users", json={"email": "me@example.org", "role": "admin",
                                                 "password": "let me in please"}, headers=GOOD).status_code == 401
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any(word in path for path in paths for word in ("signup", "register", "forgot", "reset-email"))


# --- The first Admin -----------------------------------------------------------------------------------------------

def test_create_admin_asks_for_the_password_at_a_hidden_prompt(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FAIRLEND_WEB_DATA", str(tmp_path / "web"))
    asked = []

    def hidden(prompt):
        asked.append(prompt)
        return "first admin password"

    assert create_admin.main(["--email", "boss@example.org"], prompt=hidden, ask=lambda _: "") == 0
    assert asked == ["Password: ", "Password again: "]
    out = capsys.readouterr().out
    assert "first admin password" not in out and "argon2" not in out
    with pytest.raises(SystemExit):
        create_admin.main(["--email", "x@example.org", "--password", "on the command line"])
    db_bytes = (tmp_path / "web" / "app.db").read_bytes()
    assert b"first admin password" not in db_bytes and b"$argon2id$" in db_bytes
    source = Path(create_admin.__file__).read_text(encoding="utf-8")
    assert "getpass" in source and '"--password"' not in source


def test_create_admin_refuses_a_short_password(tmp_path, monkeypatch):
    monkeypatch.setenv("FAIRLEND_WEB_DATA", str(tmp_path / "web"))
    assert create_admin.main(["--email", "boss@example.org"], prompt=lambda _: "short", ask=lambda _: "") == 1


def test_the_session_secret_file_is_created_once_and_is_git_ignored(tmp_path):
    first = security.load_secret(None, tmp_path)
    assert security.load_secret(None, tmp_path) == first and len(first) == 64
    assert security.load_secret("from-env", tmp_path) == b"from-env"
    gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "data/*" in gitignore  # data/web/session_secret.txt and app.db are never committed
