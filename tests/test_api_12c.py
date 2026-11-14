"""Phase 12C: Guided Demo, About, Export, Review labels and the Repayments owed split in the API (api/).

The demo parts use the real synthetic demo (read-only). The import and review parts use the small lender D folder of
the baseline sample pack, built into a temporary folder and imported through the API. All data is synthetic.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import db
from src.bootstrap import demo_status
from src.config import load_config
from src.dashboard_data import featured_cases, filter_borrowers, flagged_borrowers_csv, lender_comparison_csv
from src.datasets import DEMO, PRESENT_VARIABLE, get_dataset_paths
from src.import_data import TABLES
from src.make_sample_pack import build_scenario

from api.accounts import ROLES
from api.data_source import DemoDataSource, presentation_config
from api.main import create_app
from api.settings import Settings

ORIGIN = "http://localhost:3000"
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


@pytest.fixture(scope="module")
def app(demo_source, tmp_path_factory):
    application = create_app(source=demo_source, prepare=False,
                             settings=Settings(web_origins=[ORIGIN], data_dir=tmp_path_factory.mktemp("web"),
                                               session_secret="test-secret-not-real"))
    for role in ROLES:
        application.state.services.accounts.create_user(f"{role}@example.org", role, PASSWORD, created_by="test")
    return application


@pytest.fixture(scope="module")
def anon(app):
    return TestClient(app)


def _signed_in(app, role: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"email": f"{role}@example.org", "password": PASSWORD},
                       headers=GOOD).status_code == 200
    return client


@pytest.fixture(scope="module")
def imported(app, tmp_path_factory):
    """The baseline pack's small lender D folder imported as a new dataset through the API."""
    root = tmp_path_factory.mktemp("pack")
    build_scenario(load_config(), "baseline", root)
    folder = root / "baseline" / "lender_D"
    files = [("files", (f"{t}.csv", (folder / f"{t}.csv").read_bytes(), "text/csv")) for t in TABLES]
    body = _signed_in(app, "importer").post(
        "/api/imports", data={"file_type": "csv", "mode": "new", "name": "SYNTHETIC lender D", "as_of": "2026-10-01",
                              "permission": "true"}, files=files, headers=GOOD).json()
    assert body["stage"] == "imported", body
    return body


def _demo_fingerprint() -> str:
    paths = get_dataset_paths(load_config(), DEMO)
    conn = sqlite3.connect(f"{paths.lending_db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return db.content_hash(conn)
    finally:
        conn.close()


# --- Guided Demo -----------------------------------------------------------------------------------------------------

def test_guided_demo_has_the_same_six_cases_as_streamlit(app, anon):
    body = anon.get("/api/guided-demo").json()
    snap = app.state.source.snapshot()
    expected = featured_cases(snap.data, snap.cfg)
    assert body["available"] is True and body["missing"] == expected["missing"] == []
    assert [(c["step"], c["key"], c["id"], c["title"]) for c in body["cases"]] == [
        (c["step"], c["key"], c["id"], c["title"]) for c in expected["cases"]]
    assert [c["id"] for c in body["cases"]] == ["B01767", "B00030", "B00550", "B02339", "L13", "L08"]
    for mine, theirs in zip(body["cases"], expected["cases"]):
        if mine["key"] != "harassed":
            assert mine["say"] == theirs["say"]  # the same wording as the Streamlit Guided Demo


def test_the_harassed_sentence_is_computed_and_cannot_be_misread(app, anon):
    case = next(c for c in anon.get("/api/guided-demo").json()["cases"] if c["key"] == "harassed")
    snap = app.state.source.snapshot()
    own = snap.data.messages[snap.data.messages["borrower_id"] == case["id"]]
    abusive = own["predicted_class"].isin(snap.cfg["lender_comparison"]["abusive_classes"])
    expected = {"messages": len(own), "abusive": int(abusive.sum()),
                "abusive_late_night": int((abusive & own["late_night"]).sum()),
                "abusive_third_party": int((abusive & own["third_party"]).sum())}
    assert case["counts"] == expected
    assert (expected["abusive"], expected["abusive_late_night"], expected["abusive_third_party"]) == (48, 11, 14)
    assert "48 of them were labelled abusive" in case["say"]
    assert "Of those 48, 11 were sent late at night and 14 were sent to other people" in case["say"]
    assert "20 late at night" not in case["say"]


def test_guided_demo_explains_itself_on_an_imported_dataset(app, imported):
    body = _signed_in(app, "viewer").get(f"/api/guided-demo?dataset={imported['dataset']}").json()
    assert body["available"] is False and "demo" in body["reason"] and body["cases"] == []


# --- About -----------------------------------------------------------------------------------------------------------

def test_about_has_the_five_signals_and_no_legal_judgement(anon):
    body = anon.get("/api/about").json()
    assert [s["key"] for s in body["signals"]] == ["open_lenders", "debt_to_income", "arrears", "cycling",
                                                   "loan_velocity"]
    assert sum(s["weight"] for s in body["signals"]) == 100
    assert body["review_line"] == "Flags prompt a human to look. They are not findings and not a verdict."
    for endpoint in ("/api/about", "/api/meta"):
        text = anon.get(endpoint).text.lower()
        assert "lawful" not in text and "illegal" not in text, endpoint
    threat = next(c for c in body["classes"] if c["key"] == "threat")
    assert threat["abusive"] is True and "wording" in threat["description"].lower()
    assert "not a legal finding" in body["label_note"]


# --- Export ----------------------------------------------------------------------------------------------------------

def test_exports_are_the_streamlit_files_with_the_notice_first(app, anon):
    snap = app.state.source.snapshot()
    flagged = anon.get("/api/export/flagged-borrowers.csv")
    assert flagged.status_code == 200 and "flagged_borrowers.csv" in flagged.headers["content-disposition"]
    expected = flagged_borrowers_csv(filter_borrowers(snap.data.borrowers, bands=["high", "medium"]), snap.data.notice)
    assert flagged.content == expected
    assert flagged.content.decode("utf-8").splitlines()[0].startswith(f"# {snap.data.notice}")
    assert len(pd.read_csv(io.BytesIO(flagged.content), comment="#")) == 280 + 863
    only_high = anon.get("/api/export/flagged-borrowers.csv?bands=high&min_abusive=3").content
    assert only_high == flagged_borrowers_csv(
        filter_borrowers(snap.data.borrowers, bands=["high"], min_abusive_messages=3), snap.data.notice)
    lenders = anon.get("/api/export/lender-comparison.csv")
    assert lenders.content == lender_comparison_csv(snap.data.lenders, snap.data.classifier, snap.data.notice,
                                                    snap.data.human_share)
    follow = anon.get("/api/repayments/follow-up.csv").content.decode("utf-8")
    assert follow.splitlines()[0].startswith(f"# {snap.data.notice}")
    summary = anon.get("/api/export").json()
    assert (summary["flagged_borrowers"], summary["lenders"], summary["follow_up_borrowers"]) == (1143, 13, 885)


def test_an_imported_datasets_exports_need_a_signed_in_viewer(app, anon, imported):
    slug = imported["dataset"]
    for path in ("/api/export", "/api/export/flagged-borrowers.csv", "/api/export/lender-comparison.csv",
                 "/api/repayments/follow-up.csv"):
        assert anon.get(f"{path}?dataset={slug}").status_code == 401, path
        response = _signed_in(app, "viewer").get(f"{path}?dataset={slug}")
        assert response.status_code == 200, path
    first = _signed_in(app, "viewer").get(f"/api/export/flagged-borrowers.csv?dataset={slug}").text.splitlines()[0]
    assert "Imported dataset. Passed the synthetic-only check." in first and "REAL DATA" not in first


# --- Repayments: owed split ------------------------------------------------------------------------------------------

def test_repayments_split_the_total_owed_so_it_is_not_read_as_arrears(anon):
    body = anon.get("/api/repayments").json()
    total, later, past = body["owed_unpaid"]["amount"], body["owed_not_yet_due"]["amount"], body["owed_past_due"]["amount"]
    assert later + past == total
    assert later == next(b["owed"]["amount"] for b in body["ageing"] if b["bucket"] == "current") == 849_085_700
    assert past == 359_405_000
    assert body["owed_follow_up"]["amount"] + body["owed_in_grace"]["amount"] == past


# --- Import message ----------------------------------------------------------------------------------------------------

def test_the_import_message_points_to_the_web_review_page(imported):
    assert "Review labels page" in imported["message"]
    assert "the Review page before" not in imported["message"]


# --- Review labels ---------------------------------------------------------------------------------------------------

def test_review_is_for_importers_on_imported_datasets_only(app, anon, imported):
    slug = imported["dataset"]
    assert anon.get(f"/api/review?dataset={slug}").status_code == 401
    assert _signed_in(app, "viewer").get(f"/api/review?dataset={slug}").status_code == 403
    demo = _signed_in(app, "importer").get("/api/review?dataset=demo").json()
    assert demo["available"] is False and "cannot be changed" in demo["reason"]
    refused = _signed_in(app, "admin").post("/api/review/batch", json={"dataset": "demo", "kind": "random", "size": 3},
                                           headers=GOOD)
    assert refused.status_code == 400
    assert _demo_fingerprint() == DEMO_FINGERPRINT


def test_a_person_checks_labels_and_they_are_stored_counted_and_audited(app, imported):
    slug = imported["dataset"]
    importer = _signed_in(app, "importer")
    before = importer.get(f"/api/review?dataset={slug}").json()
    assert before["available"] is True and before["reviewed"] == 0
    ids = importer.post("/api/review/batch", json={"dataset": slug, "kind": "random", "size": 3},
                        headers=GOOD).json()["ids"]
    assert len(ids) == 3
    item = importer.get(f"/api/review/message/{ids[0]}?dataset={slug}").json()
    assert item["text"].endswith("(SYNTHETIC)") and item["model_label"] in before["classes"]
    cross = importer.post("/api/review/label", json={"dataset": slug, "message_id": ids[0], "label": "normal",
                                                     "kind": "random"}, headers={"Origin": "http://evil.example"})
    assert cross.status_code == 403
    chosen = "threat" if item["model_label"] != "threat" else "normal"
    saved = importer.post("/api/review/label", json={"dataset": slug, "message_id": ids[0], "label": chosen,
                                                     "kind": "random", "reviewer": "AB"}, headers=GOOD).json()
    assert saved == {"saved": chosen, "model_label": item["model_label"], "agreed": False}
    bad = importer.post("/api/review/label", json={"dataset": slug, "message_id": ids[1], "label": "rude",
                                                   "kind": "random"}, headers=GOOD)
    assert bad.status_code == 400
    after = importer.get(f"/api/review?dataset={slug}").json()
    assert after["reviewed"] == 1 and after["per_batch"]["random"] == 1
    # stored with that dataset, in its own predictions file
    paths = get_dataset_paths(app.state.services.files.engine_config(app.state.services.sources.base_config(), slug),
                              slug)
    conn = sqlite3.connect(str(paths.predictions_db))
    try:
        assert conn.execute("SELECT label FROM human_labels WHERE message_id = ?", (ids[0],)).fetchone()[0] == chosen
    finally:
        conn.close()
    # the pages now use the person's label and count it as checked by a person
    overview = importer.get(f"/api/overview?dataset={slug}").json()
    assert "checked by a person" in overview["coverage"]
    entries = _signed_in(app, "admin").get("/api/audit").json()["entries"]
    review = next(e for e in entries if e["action"] == "review_label")
    assert review["actor"] == "importer@example.org" and review["detail"]["label"] == chosen
    assert "(SYNTHETIC)" not in json.dumps(entries)
    export = importer.get(f"/api/review/export.csv?dataset={slug}").text
    assert export.startswith("# Imported dataset. Passed the synthetic-only check.")
    assert _demo_fingerprint() == DEMO_FINGERPRINT


def test_new_routes_keep_explicit_access_rules(app):
    from api.deps import ACCESS_DEPENDENCIES

    def calls(dep):
        found = {dep.call} if dep.call else set()
        for child in dep.dependencies:
            found |= calls(child)
        return found

    for route in app.routes:
        path = getattr(route, "path", "")
        if re.match(r"^/api/(guided-demo|about|export|review)", path):
            assert len(calls(route.dependant) & set(ACCESS_DEPENDENCIES)) == 1, path
