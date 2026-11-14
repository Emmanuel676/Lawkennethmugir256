"""Phase 13: neutral wording in everything a user sees in the web app.

Every dataset is "Demonstration data". The web app must never call a dataset synthetic or mock, and never describe
it as real, verified, collected or field data. This test fails if any of those words reaches:

  - the web app's own text (web/app, web/components, web/lib; code comments are not shown and are left out),
  - the API's answers for the built-in dataset and for an imported one (every text value except dataset content:
    message text is what was uploaded and is shown as stored),
  - the first line of every export, the import messages and the audit log labels.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.bootstrap import demo_status
from src.config import load_config
from src.datasets import PRESENT_VARIABLE
from src.import_data import TABLES
from src.make_sample_pack import build_scenario

from api.accounts import ROLES
from api.audit import ACTIONS
from api.data_source import DemoDataSource, presentation_config
from api.main import create_app
from api.settings import Settings
from api.wording import BANNED, TRUST_LINE

ROOT = Path(__file__).resolve().parents[1]
WEB_SOURCES = [p for folder in ("app", "components", "lib") for p in (ROOT / "web" / folder).rglob("*")
               if p.suffix in (".ts", ".tsx")]
ORIGIN = "http://localhost:3000"
GOOD = {"Origin": ORIGIN}
PASSWORD = "correct horse 42"
CONTENT_KEYS = {"text"}  # dataset content (uploaded message text), shown as stored


def _without_comments(source: str) -> str:
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)   # JSX comments
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)       # block comments
    return re.sub(r"(?m)(^|[^:\"'`])//.*$", r"\1", source)            # line comments (not http:// in strings)


def test_the_trust_line_is_neutral():
    assert TRUST_LINE == "Demonstration data. A flag is a prompt for a human to look, not a verdict."


def test_web_app_text_never_uses_the_banned_words():
    assert WEB_SOURCES, "no web sources found"
    offenders = []
    for path in WEB_SOURCES:
        for number, line in enumerate(_without_comments(path.read_text(encoding="utf-8")).splitlines(), start=1):
            if BANNED.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}")
    assert offenders == []


def test_the_banned_word_check_itself_works():
    for bad in ("Synthetic data", "mock lenders", "REAL DATA", "a real dataset", "verified records", "collected data",
                "field data from Gulu"):
        assert BANNED.search(bad), bad
    for fine in ("Demonstration data", "really", "realistic", "recollected", "unrealised"):
        assert not BANNED.search(fine), fine


# --- The API's answers ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app(tmp_path_factory):
    status, reason = demo_status(presentation_config())
    if status != "fresh":
        pytest.skip(f"The demo is {status} ({reason}). Build it first: python -m api.prepare")
    mp = pytest.MonkeyPatch()
    mp.setenv(PRESENT_VARIABLE, "1")
    source = DemoDataSource()
    source.load()
    application = create_app(source=source, prepare=False,
                             settings=Settings(web_origins=[ORIGIN], data_dir=tmp_path_factory.mktemp("web"),
                                               session_secret="test-secret-not-real"))
    for role in ROLES:
        application.state.services.accounts.create_user(f"{role}@example.org", role, PASSWORD, created_by="test")
    yield application
    mp.undo()


@pytest.fixture(scope="module")
def admin(app):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"email": "admin@example.org", "password": PASSWORD},
                       headers=GOOD).status_code == 200
    return client


@pytest.fixture(scope="module")
def imported(admin, tmp_path_factory):
    root = tmp_path_factory.mktemp("pack")
    build_scenario(load_config(), "baseline", root)
    folder = root / "baseline" / "lender_D"
    files = [("files", (f"{t}.csv", (folder / f"{t}.csv").read_bytes(), "text/csv")) for t in TABLES]
    body = admin.post("/api/imports", data={"file_type": "csv", "mode": "new", "name": "Lender D", "as_of": "2026-10-01",
                                            "permission": "true"}, files=files, headers=GOOD).json()
    assert body["stage"] == "imported", body
    return body


def _texts(value, where=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            if key not in CONTENT_KEYS:
                yield from _texts(inner, f"{where}.{key}")
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from _texts(inner, f"{where}[{index}]")
    elif isinstance(value, str):
        yield where, value


ENDPOINTS = ["/api/meta", "/api/overview", "/api/borrowers", "/api/lenders", "/api/repayments",
             "/api/repayments/follow-up", "/api/guided-demo", "/api/about", "/api/export"]


def _assert_clean(label: str, body) -> None:
    found = [f"{where}: {text[:120]}" for where, text in _texts(body) if BANNED.search(text)]
    assert found == [], label


def test_api_answers_for_the_built_in_dataset_are_neutral(admin):
    for path in ENDPOINTS + ["/api/borrowers/B02339", "/api/lenders/L08", "/api/lenders/L13", "/api/datasets",
                             "/api/imports/info", "/api/review?dataset=demo"]:
        response = admin.get(path)
        assert response.status_code == 200, path
        _assert_clean(path, response.json())


def test_api_answers_for_an_imported_dataset_are_neutral(admin, imported):
    slug = imported["dataset"]
    _assert_clean("import answer", {k: v for k, v in imported.items() if k != "report"})
    for path in ENDPOINTS + ["/api/datasets", f"/api/datasets/{slug}", "/api/review"]:
        response = admin.get(path, params={"dataset": slug})
        assert response.status_code == 200, path
        _assert_clean(f"{path} ({slug})", response.json())
    listing = admin.get("/api/datasets").json()["datasets"]
    assert next(d for d in listing if d["slug"] == slug)["label"] == "Demonstration data"
    assert admin.get(f"/api/meta?dataset={slug}").json()["trust_line"] == TRUST_LINE


def test_export_first_lines_say_demonstration_data(admin, imported):
    for dataset in ("demo", imported["dataset"]):
        for path in ("/api/export/flagged-borrowers.csv", "/api/export/lender-comparison.csv",
                     "/api/repayments/follow-up.csv"):
            first = admin.get(path, params={"dataset": dataset}).text.splitlines()[0]
            assert first.startswith("# Demonstration data."), (dataset, path, first)
            assert not BANNED.search(first), (dataset, path, first)


def test_audit_labels_and_audit_entries_are_neutral(admin, imported):
    assert not any(BANNED.search(label) for label in ACTIONS.values())
    _assert_clean("audit", admin.get("/api/audit").json())
    assert "REAL DATA" not in json.dumps(admin.get("/api/datasets").json())
