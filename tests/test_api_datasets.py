"""Phase 12B: shared datasets that persist, and the Data import page of the API (api/).

The baseline sample pack is built into a temporary folder with the existing builder (src.make_sample_pack) and
imported through the API exactly as a person would: lender A as a new dataset, then lender B added to it.
The numbers must match the documented Streamlit import of the same pack (docs/ONBOARDING_DEMO.md:
85 codes already known; 85 of 387 borrowers at two lenders; 0 high, 7 medium, 380 low) and a direct import
with the same engine. All data is synthetic.
"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser

from src import db
from src.bootstrap import demo_status
from src.classify_messages import classify_dataset
from src.config import load_config
from src.dashboard_data import load_all, overview_kpis
from src.datasets import DEMO, PRESENT_VARIABLE, get_dataset_paths
from src.evaluate_sample_pack import import_folder, temp_config
from src.import_data import TABLES
from src.make_sample_pack import build_scenario

from api.accounts import ROLES
from api.data_source import IMPORTED_LABEL, IMPORTED_TRUST_LINE, DemoDataSource, presentation_config
from api.main import create_app
from api.settings import Settings

ORIGIN = "http://localhost:3000"
GOOD = {"Origin": ORIGIN}
PASSWORD = "correct horse 42"
DEMO_FINGERPRINT = "3945277a047220916234197d5844183d2ae84313ad9ba5fced6246ffe5d3df9e"
BASELINE_NAME = "SYNTHETIC sample baseline"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


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


@pytest.fixture(scope="module")
def pack(cfg, tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("sample_pack")
    build_scenario(cfg, "baseline", root)
    return root / "baseline"


@pytest.fixture(scope="module")
def app(demo_source, tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("web")
    application = create_app(source=demo_source, prepare=False,
                             settings=Settings(web_origins=[ORIGIN], data_dir=data_dir,
                                               session_secret="test-secret-not-real"))
    for role in ROLES:
        application.state.services.accounts.create_user(f"{role}@example.org", role, PASSWORD, created_by="test")
    return application


def _signed_in(app, role: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"email": f"{role}@example.org", "password": PASSWORD},
                       headers=GOOD).status_code == 200
    return client


def _csv_files(folder: Path, change=None) -> list:
    files = []
    for table in TABLES:
        content = (folder / f"{table}.csv").read_bytes()
        if change:
            content = change(table, content)
        files.append(("files", (f"{table}.csv", content, "text/csv")))
    return files


def _form(**fields) -> dict:
    base = {"file_type": "csv", "mode": "new", "as_of": "2026-10-01", "permission": "true"}
    base.update({k: v for k, v in fields.items() if v is not None})
    return base


def _datasets_tree(app) -> list[str]:
    root = app.state.services.files.root
    if not root.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _demo_fingerprint() -> str:
    paths = get_dataset_paths(load_config(), DEMO)
    conn = sqlite3.connect(f"{paths.lending_db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return db.content_hash(conn)
    finally:
        conn.close()


# --- Templates -----------------------------------------------------------------------------------------------------

def test_templates_come_from_the_existing_builder(app):
    client = _signed_in(app, "importer")
    xlsx = client.get("/api/imports/template?format=xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert "fairlend_import_template.xlsx" in xlsx.headers["content-disposition"]
    import openpyxl
    sheets = openpyxl.load_workbook(io.BytesIO(xlsx.content)).sheetnames
    assert set(TABLES) <= set(sheets)
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(client.get("/api/imports/template?format=csv").content)).namelist()
    assert sorted(names) == sorted(f"{t}.csv" for t in TABLES)


# --- The upload check (Phase 13: no "(Demo)" / "(SYNTHETIC)" endings needed) ----------------------------------------

def _no_demo_suffix(table, content):
    return content.replace(b" (Demo)", b"") if table == "lenders" else content


def _no_markers(table, content):
    """Lender names without "(Demo)" and messages without "(SYNTHETIC)": ordinary files."""
    if table == "lenders":
        return content.replace(b" (Demo)", b"")
    if table == "messages":
        return content.replace(b" (SYNTHETIC)", b"")
    return content


def _phone_in_message(table, content):
    if table != "messages":
        return content
    lines = content.decode("utf-8").splitlines()
    lines[1] = lines[1].replace("(SYNTHETIC)", "call 0772 123 456 (SYNTHETIC)", 1)
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_ordinary_files_without_markers_pass_the_upload_check(app, pack):
    client = _signed_in(app, "importer")
    before = _datasets_tree(app)
    body = client.post("/api/imports/check", data=_form(name="Plain files"), files=_csv_files(pack / "lender_A", _no_markers),
                       headers=GOOD).json()
    assert body["stage"] == "valid", body
    assert body["report"]["counts"]["messages"] == 1291
    assert _datasets_tree(app) == before  # a check writes nothing


@pytest.mark.parametrize("change, words", [(_phone_in_message, "phone number")])
def test_a_refused_upload_writes_nothing(app, pack, change, words):
    client = _signed_in(app, "importer")
    before_tree, before_list = _datasets_tree(app), client.get("/api/datasets").json()["datasets"]
    for path in ("/api/imports/check", "/api/imports"):
        response = client.post(path, data=_form(name="Should not exist"), files=_csv_files(pack / "lender_A", change),
                               headers=GOOD)
        body = response.json()
        assert response.status_code == 200 and body["stage"] == "refused", body
        assert any(words in reason for reason in body["reasons"]) and "Nothing was stored" in body["message"]
        assert body["report"] is None  # never even validated
    assert _datasets_tree(app) == before_tree
    assert client.get("/api/datasets").json()["datasets"] == before_list
    entries = _signed_in(app, "admin").get("/api/audit").json()["entries"]
    refused = [e for e in entries if e["action"] == "import_refused"]
    assert refused and "0772" not in json.dumps(entries)


def test_uploads_stay_in_memory_and_are_capped_before_reading(app, cfg):
    limit = float(cfg["team_demo"]["max_upload_mb"]) * 1024 * 1024
    assert MultiPartParser.spool_max_size >= limit  # never spooled to a temporary file on disk
    client = _signed_in(app, "importer")
    too_big = client.post("/api/imports", headers={**GOOD, "Content-Length": str(int(limit) * 2),
                                                   "Content-Type": "multipart/form-data; boundary=x"}, content=b"--x--")
    assert too_big.status_code == 413


def test_validation_errors_are_plain_words_with_row_numbers_and_nothing_is_saved(app, pack):
    def bad_date(table, content):
        if table != "loans":
            return content
        lines = content.decode("utf-8").splitlines()
        cells = lines[3].split(",")
        cells[5] = "31/02/2026"  # issue_date: a day that does not exist
        lines[3] = ",".join(cells)
        return ("\n".join(lines) + "\n").encode("utf-8")

    client = _signed_in(app, "importer")
    before = _datasets_tree(app)
    for path in ("/api/imports/check", "/api/imports"):
        body = client.post(path, data=_form(name="Broken pack"), files=_csv_files(pack / "lender_A", bad_date),
                           headers=GOOD).json()
        assert body["stage"] == "invalid", body
        assert body["report"]["errors_total"] >= 1
        assert any("row 4" in e["location"] for e in body["report"]["errors"])
        assert "31/02/2026" not in json.dumps(body)  # cell values are never repeated
    assert _datasets_tree(app) == before


def test_a_viewer_cannot_import_and_the_demo_cannot_be_changed(app, pack):
    viewer = _signed_in(app, "viewer")
    assert viewer.post("/api/imports", data=_form(name="x"), files=_csv_files(pack / "lender_A"),
                       headers=GOOD).status_code == 403
    importer = _signed_in(app, "importer")
    add_to_demo = importer.post("/api/imports", data=_form(mode="add", target=DEMO),
                                files=_csv_files(pack / "lender_B"), headers=GOOD)
    assert add_to_demo.status_code == 400 and "demo" in add_to_demo.json()["detail"].lower()
    admin = _signed_in(app, "admin")
    delete_demo = admin.request("DELETE", "/api/datasets/demo", json={"confirm_name": "Demonstration data (built in)"},
                                headers=GOOD)
    assert delete_demo.status_code == 400
    assert _demo_fingerprint() == DEMO_FINGERPRINT


# --- The sample pack, lender A then lender B -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def baseline(app, pack):
    """Lender A imported as a new dataset, then lender B added to it, through the API."""
    client = _signed_in(app, "importer")
    check = client.post("/api/imports/check", data=_form(name=BASELINE_NAME), files=_csv_files(pack / "lender_A"),
                        headers=GOOD).json()
    first = client.post("/api/imports", data=_form(name=BASELINE_NAME, source="synthetic sample pack"),
                        files=_csv_files(pack / "lender_A"), headers=GOOD).json()
    slug = first["dataset"]
    after_a = client.get(f"/api/datasets/{slug}").json()
    second = client.post("/api/imports", data=_form(mode="add", target=slug), files=_csv_files(pack / "lender_B"),
                         headers=GOOD).json()
    return {"check": check, "first": first, "second": second, "slug": slug, "after_a": after_a}


def test_lender_a_checks_clean_and_imports(baseline):
    check = baseline["check"]
    assert check["stage"] == "valid" and check["report"]["errors_total"] == 0
    assert check["report"]["counts"] == {"lenders": 1, "borrowers": 244, "loans": 666, "transactions": 20144,
                                         "messages": 1291}
    assert baseline["first"]["stage"] == "imported", baseline["first"]
    assert baseline["after_a"]["health"]["shared_borrowers"] == 0
    assert baseline["after_a"]["health"]["borrowers"] == 244


def test_lender_b_matches_the_streamlit_import(app, baseline):
    second = baseline["second"]
    assert second["stage"] == "imported", second
    assert second["already_known"] == 85                       # "85 borrower code(s) were already in the dataset"
    client = _signed_in(app, "viewer")
    health = client.get(f"/api/datasets/{baseline['slug']}").json()["health"]
    assert (health["shared_borrowers"], health["borrowers"]) == (85, 387)   # "85 of 387"
    overview = client.get(f"/api/overview?dataset={baseline['slug']}").json()
    assert overview["kpis"]["band_counts"] == {"high": 0, "medium": 7, "low": 380}
    assert overview["kpis"]["borrowers_scored"] == 387


def test_api_numbers_equal_a_direct_engine_import_of_the_same_pack(app, baseline, pack, cfg, tmp_path):
    """The same two folders imported with the engine directly (what the Streamlit Data page calls)."""
    work = temp_config(cfg, tmp_path)
    first, _ = import_folder(work, pack / "lender_A", "direct")
    second, _ = import_folder(work, pack / "lender_B", "", mode="add", target=first.dataset)
    paths = get_dataset_paths(work, first.dataset)
    classify_dataset(work, paths)
    work["paths"]["active_dataset_file"] = str(tmp_path / "active.txt")
    (tmp_path / "active.txt").write_text(first.dataset, encoding="utf-8")
    work.setdefault("app", {})["team_session"] = True
    direct = overview_kpis(load_all(work), work)
    api = _signed_in(app, "viewer").get(f"/api/overview?dataset={baseline['slug']}").json()["kpis"]
    assert second.report.skipped_existing_borrowers == baseline["second"]["already_known"] == 85
    assert api["borrowers_scored"] == direct["borrowers_scored"]
    assert api["band_counts"] == direct["band_counts"]
    assert api["owed_by_high_band"]["amount"] == direct["owed_by_high_band"]
    assert api["messages_classified"] == direct["messages_classified"]
    assert api["flagged_and_harassed"] == direct["flagged_and_harassed"]


def test_imported_datasets_are_labelled_demonstration_data(app, baseline):
    client = _signed_in(app, "viewer")
    slug = baseline["slug"]
    meta = client.get(f"/api/meta?dataset={slug}").json()
    assert meta["dataset"]["label"] == IMPORTED_LABEL == "Demonstration data"
    assert meta["dataset"]["demonstration"] is True and meta["dataset"]["kind"] == "imported"
    assert meta["trust_line"] == IMPORTED_TRUST_LINE
    assert "A flag is a prompt for a human to look, not a verdict." in meta["trust_line"]
    csv = client.get(f"/api/repayments/follow-up.csv?dataset={slug}").content.decode("utf-8")
    first_line = csv.splitlines()[0]
    assert first_line.startswith("# Demonstration data.")
    for endpoint in ("meta", "overview", "repayments", "lenders"):
        text = client.get(f"/api/{endpoint}?dataset={slug}").text
        assert "REAL DATA" not in text and "Confidential" not in text, endpoint
    listing = client.get("/api/datasets").json()["datasets"]
    assert listing[0]["slug"] == DEMO and listing[0]["deletable"] is False
    mine = next(d for d in listing if d["slug"] == slug)
    assert mine["label"] == IMPORTED_LABEL and mine["added_by"] == "importer@example.org"
    assert mine["counts"]["borrowers"] == 387 and mine["counts"]["lenders"] == 2 and mine["imports"] == 2


def test_imported_datasets_need_a_signed_in_user(app, baseline):
    anonymous = TestClient(app)
    slug = baseline["slug"]
    for path in (f"/api/overview?dataset={slug}", f"/api/borrowers?dataset={slug}", "/api/datasets",
                 f"/api/repayments/follow-up.csv?dataset={slug}"):
        assert anonymous.get(path).status_code == 401, path
    assert anonymous.get("/api/overview").json()["kpis"]["borrowers_scored"] == 5000  # the demo stays public


def test_datasets_are_shared_between_users(app, baseline):
    for role in ROLES:
        slugs = [d["slug"] for d in _signed_in(app, role).get("/api/datasets").json()["datasets"]]
        assert slugs[0] == DEMO and baseline["slug"] in slugs


def test_two_datasets_do_not_leak_into_each_other(app, baseline, pack):
    importer = _signed_in(app, "importer")
    other = importer.post("/api/imports", data=_form(name="SYNTHETIC lender C only"),
                          files=_csv_files(pack / "lender_C"), headers=GOOD).json()
    assert other["stage"] == "imported", other
    viewer = _signed_in(app, "viewer")
    a_b = viewer.get(f"/api/lenders?dataset={baseline['slug']}").json()
    c = viewer.get(f"/api/lenders?dataset={other['dataset']}").json()
    names_ab = {r["name"] for r in a_b["ranked"] + a_b["unranked"]}
    names_c = {r["name"] for r in c["ranked"] + c["unranked"]}
    assert names_ab == {"Mango Tree Daily Cash (Demo)", "Riverstone Credit (Demo)"}
    assert names_c == {"Bright Day Loans (Demo)"}
    ab_ids = {r["borrower_id"] for r in viewer.get(f"/api/borrowers?dataset={baseline['slug']}&page_size=200"
                                                    "&sort=borrower_id&order=asc").json()["items"]}
    c_all = viewer.get(f"/api/borrowers?dataset={other['dataset']}&page_size=200").json()
    c_ids = set()
    for page in range(1, c_all["pages"] + 1):
        c_ids |= {r["borrower_id"] for r in viewer.get(
            f"/api/borrowers?dataset={other['dataset']}&page_size=200&page={page}").json()["items"]}
    only_ab = sorted(ab_ids - c_ids)
    assert only_ab
    assert viewer.get(f"/api/borrowers/{only_ab[0]}?dataset={other['dataset']}").status_code == 404
    assert viewer.get(f"/api/borrowers/{only_ab[0]}?dataset={baseline['slug']}").status_code == 200
    assert viewer.get("/api/overview").json()["kpis"]["borrowers_scored"] == 5000  # the demo is untouched
    assert viewer.get(f"/api/overview?dataset={baseline['slug']}").json()["kpis"]["borrowers_scored"] == 387


# --- Delete (Admin) and the audit log --------------------------------------------------------------------------------

def test_admin_deletes_a_dataset_after_typing_its_name(app, pack):
    importer = _signed_in(app, "importer")
    made = importer.post("/api/imports", data=_form(name="SYNTHETIC to delete"), files=_csv_files(pack / "lender_D"),
                         headers=GOOD).json()
    assert made["stage"] == "imported", made
    slug = made["dataset"]
    assert importer.request("DELETE", f"/api/datasets/{slug}", json={"confirm_name": "SYNTHETIC to delete"},
                            headers=GOOD).status_code == 403
    admin = _signed_in(app, "admin")
    wrong = admin.request("DELETE", f"/api/datasets/{slug}", json={"confirm_name": "synthetic to delete"},
                          headers=GOOD)
    assert wrong.status_code == 400 and "type the dataset name exactly" in wrong.json()["detail"]
    assert admin.get(f"/api/overview?dataset={slug}").status_code == 200
    done = admin.request("DELETE", f"/api/datasets/{slug}", json={"confirm_name": "SYNTHETIC to delete"},
                         headers=GOOD)
    assert done.status_code == 200
    assert not (app.state.services.files.root / slug).exists()
    assert admin.get(f"/api/datasets/{slug}").status_code == 404
    assert admin.get(f"/api/overview?dataset={slug}").status_code == 404
    actions = [(e["action"], e["actor"]) for e in admin.get("/api/audit").json()["entries"]]
    assert ("dataset_delete", "admin@example.org") in actions
    assert ("import_new", "importer@example.org") in actions and ("import_add", "importer@example.org") in actions
    assert _demo_fingerprint() == DEMO_FINGERPRINT


def test_the_audit_log_is_for_admins_only_and_holds_no_values(app, baseline):
    assert _signed_in(app, "importer").get("/api/audit").status_code == 403
    entries = _signed_in(app, "admin").get("/api/audit").json()["entries"]
    imported = next(e for e in entries if e["action"] == "import_add")
    assert imported["detail"]["already_known"] == 85 and imported["target"] == BASELINE_NAME
    assert "(SYNTHETIC)" not in json.dumps(entries)  # no message text


def test_datasets_persist_across_a_restart(app, baseline, demo_source):
    """A new app on the same data folder sees the same datasets (nothing is kept only in memory)."""
    settings = app.state.services.settings
    again = create_app(source=demo_source, settings=settings, prepare=False)
    client = TestClient(again)
    assert client.post("/api/auth/login", json={"email": "viewer@example.org", "password": PASSWORD},
                       headers=GOOD).status_code == 200
    assert baseline["slug"] in [d["slug"] for d in client.get("/api/datasets").json()["datasets"]]
    assert client.get(f"/api/overview?dataset={baseline['slug']}").json()["kpis"]["band_counts"] == {
        "high": 0, "medium": 7, "low": 380}


def test_the_demo_is_unchanged_after_imports_and_deletes(app, baseline):
    assert _demo_fingerprint() == DEMO_FINGERPRINT
    overview = TestClient(app).get("/api/overview").json()["kpis"]
    assert overview["band_counts"] == {"high": 280, "medium": 863, "low": 3857}
