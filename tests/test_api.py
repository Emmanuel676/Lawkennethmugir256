"""Phase 12A: the read-only JSON API in api/ (FastAPI) that feeds the web interface in web/.

The number-parity tests load the real synthetic demo (the same files the Streamlit app reads) and check that
every endpoint's headline numbers equal (a) the values the brief quotes from the Streamlit pages and (b) the
values the Streamlit pages actually render, read from app.py and pages/7_Repayments.py with AppTest.
All data is synthetic. A flag is a prompt for a human to look, not a verdict.
"""

from __future__ import annotations

import io
import re
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from src import db
from src import repayments as rp
from src.bootstrap import demo_status
from src.dashboard_data import filter_borrowers, sort_borrowers
from src.datasets import DEMO, PRESENT_VARIABLE, get_dataset_paths
from src.overlap import explain

from api import views
from api.data_source import DataNotReady, DemoDataSource, presentation_config
from api.main import create_app
from api.settings import DEFAULT_ORIGIN, Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]
DEMO_FINGERPRINT = "3945277a047220916234197d5844183d2ae84313ad9ba5fced6246ffe5d3df9e"
ORIGIN = "http://localhost:3000"

# The Streamlit page values quoted in the Phase 12A brief.
OVERVIEW = {"borrowers": 5_000, "high": 280, "medium": 863, "low": 3_857, "owed_high": "UGX 251.9M"}
REPAYMENTS = {"on_time": "29.2%", "late_within_grace": "22.8%", "not_paying": "12.5%", "follow_up": 885}


@pytest.fixture(scope="module")
def demo_ready():
    cfg = presentation_config()
    status, reason = demo_status(cfg)
    if status != "fresh":
        pytest.skip(f"The demo is {status} ({reason}). Build it first: python -m api.prepare")
    return cfg


@pytest.fixture(scope="module")
def client(demo_ready):
    mp = pytest.MonkeyPatch()
    mp.setenv(PRESENT_VARIABLE, "1")
    source = DemoDataSource()
    source.load()
    app = create_app(source=source, settings=Settings(web_origins=[ORIGIN]), prepare=False)
    with TestClient(app) as test_client:
        yield test_client
    mp.undo()


def _get(client, path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- The demo itself -----------------------------------------------------------------------------------------

def test_the_api_serves_the_untouched_demo(client):
    snap = client.app.state.source.snapshot()
    lending = get_dataset_paths(snap.cfg, DEMO).lending_db
    conn = sqlite3.connect(f"{lending.resolve().as_uri()}?mode=ro", uri=True)
    try:
        assert db.content_hash(conn) == DEMO_FINGERPRINT
    finally:
        conn.close()
    health = _get(client, "/api/health")
    assert health["status"] == "ok" and health["presentation_mode"] is True and health["read_only"] is True
    assert _get(client, "/api/meta")["dataset"]["synthetic"] is True


# --- Number parity with the brief ----------------------------------------------------------------------------

def test_overview_matches_the_streamlit_values_in_the_brief(client):
    body = _get(client, "/api/overview")
    kpis = body["kpis"]
    assert kpis["borrowers_scored"] == OVERVIEW["borrowers"]
    assert kpis["band_counts"] == {"high": OVERVIEW["high"], "medium": OVERVIEW["medium"], "low": OVERVIEW["low"]}
    assert kpis["owed_by_high_band"]["compact"] == OVERVIEW["owed_high"]
    assert [(b["key"], b["label"], b["borrowers"]) for b in body["bands"]] == [
        ("high", "High", 280), ("medium", "Medium", 863), ("low", "Low", 3857)]
    assert len(body["top_borrowers"]) == 10
    scores = [row["score"] for row in body["top_borrowers"]]
    assert scores == sorted(scores, reverse=True)


def test_repayments_match_the_streamlit_values_in_the_brief(client):
    body = _get(client, "/api/repayments")
    shares = {s["key"]: f"{s['share']:.1%}" for s in body["statuses"]}
    for status in ("on_time", "late_within_grace", "not_paying"):
        assert shares[status] == REPAYMENTS[status]
    assert body["follow_up_borrowers"] == REPAYMENTS["follow_up"]
    assert _get(client, "/api/repayments/follow-up")["matching"] == REPAYMENTS["follow_up"]
    assert sum(s["loans"] for s in body["statuses"]) == body["loans"]
    assert body["owed_note"] == views.OWED_NOTE and "not yet due" in body["owed_note"]


def test_lenders_have_intervals_and_the_too_small_flag(client):
    body = _get(client, "/api/lenders")
    assert len(body["ranked"]) == 12 and len(body["unranked"]) == 1
    assert [r["rank"] for r in body["ranked"]] == list(range(1, 13))
    assert all(not r["too_small"] and r["interval_low"] <= r["abusive_share"] <= r["interval_high"]
               for r in body["ranked"])
    small = body["unranked"][0]
    assert small["too_small"] is True and small["rank"] is None and small["messages"] < body["min_messages"]
    overview = _get(client, "/api/overview")["kpis"]
    assert (overview["lenders_ranked"], overview["lenders_unranked"]) == (12, 1)


# --- Number parity with what the Streamlit pages render -------------------------------------------------------

def _streamlit_page(page: str, monkeypatch) -> AppTest:
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    monkeypatch.delenv("LENDING_MONITOR_CONFIG", raising=False)
    at = AppTest.from_file(str(ROOT / page), default_timeout=300).run()
    assert not at.exception, at.exception
    return at


def _metrics(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_overview_endpoint_equals_the_rendered_streamlit_overview(client, monkeypatch):
    shown = _metrics(_streamlit_page("app.py", monkeypatch))
    kpis = _get(client, "/api/overview")["kpis"]
    assert shown["Borrowers scored"] == f"{kpis['borrowers_scored']:,}" == "5,000"
    for band in ("high", "medium", "low"):
        assert shown[f"Band: {band}"] == f"{kpis['band_counts'][band]:,}"
    assert shown["Owed, high band"] == kpis["owed_by_high_band"]["compact"]
    assert shown["Messages classified"] == f"{kpis['messages_classified']:,}"
    assert shown["Flagged AND harassed"] == f"{kpis['flagged_and_harassed']:,}"


def test_repayments_endpoint_equals_the_rendered_streamlit_page(client, monkeypatch):
    at = _streamlit_page("pages/7_Repayments.py", monkeypatch)
    shown = _metrics(at)
    body = _get(client, "/api/repayments")
    for status in body["statuses"]:
        if status["label"] in shown:
            assert shown[status["label"]] == f"{status['share']:.1%}", status["label"]
    assert shown["Owed, unpaid loans"] == body["owed_unpaid"]["compact"]
    count = next(m.value for m in at.markdown if "borrowers in the follow-up list" in m.value)
    assert count == f"**{body['follow_up_borrowers']:,} borrowers in the follow-up list.**"


# --- Borrowers -----------------------------------------------------------------------------------------------

def test_borrower_list_uses_the_engine_filters_and_sort(client):
    snap = client.app.state.source.snapshot()
    body = _get(client, "/api/borrowers", bands="high,medium", min_abusive=3, sort="total_owed", order="desc")
    expected = sort_borrowers(filter_borrowers(snap.data.borrowers, bands=["high", "medium"],
                                               min_abusive_messages=3), "Total owed", False)
    assert body["matching"] == len(expected) == _get(client, "/api/overview")["kpis"]["flagged_and_harassed"]
    assert [r["borrower_id"] for r in body["items"]] == expected["borrower_id"].head(25).tolist()
    assert body["items"][0]["total_owed"]["exact"].startswith("UGX ")
    assert _get(client, "/api/borrowers")["matching"] == 5000


@pytest.mark.parametrize("params", [{"sort": "region"}, {"bands": "severe"}, {"order": "up"}])
def test_bad_borrower_queries_get_a_400(client, params):
    assert client.get("/api/borrowers", params=params).status_code == 400


def test_borrower_detail_has_the_explanation_and_redacted_messages(client):
    snap = client.app.state.source.snapshot()
    top = _get(client, "/api/overview")["top_borrowers"][0]["borrower_id"]
    body = _get(client, f"/api/borrowers/{top}")
    row = snap.data.borrowers[snap.data.borrowers["borrower_id"] == top].iloc[0]
    assert body["explanation"] == explain(row, snap.cfg) and body["explanation"]
    assert body["band"]["label"] in ("Low", "Medium", "High")
    assert sum(p["points"] for p in body["points"]) == pytest.approx(body["score"], abs=0.2)
    raw = snap.data.messages.set_index("message_id")["text"]
    for message in body["messages"]:
        assert message["text"] == snap.redact(raw[message["message_id"]])
        assert message["label"]["label"] in views.CLASS_LABELS.values()
    assert client.get("/api/borrowers/NOPE").status_code == 404


def test_redaction_is_applied_to_message_text(client):
    snap = client.app.state.source.snapshot()
    assert "[PHONE]" in snap.redact("Call 0772 123 456 today")
    assert "[EMAIL]" in snap.redact("write to someone@example.com")


# --- Repayments follow-up CSV --------------------------------------------------------------------------------

def test_follow_up_csv_carries_the_synthetic_notice_line(client):
    response = client.get("/api/repayments/follow-up.csv")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert "repayment_follow_up.csv" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    first = text.splitlines()[0]
    notice = client.app.state.source.snapshot().data.notice
    assert first.startswith("# ") and notice in first and rp.PROMPT in first
    frame = pd.read_csv(io.StringIO(text), comment="#")
    assert len(frame) == REPAYMENTS["follow_up"]
    assert "borrower_code" in frame.columns


def test_follow_up_filters(client):
    page = _get(client, "/api/repayments/follow-up", statuses="not_paying", bands="high", page_size=10)
    assert page["matching"] <= REPAYMENTS["follow_up"] and len(page["items"]) <= 10
    assert all(i["status"]["key"] == "not_paying" and i["band"]["key"] == "high" for i in page["items"])
    assert client.get("/api/repayments/follow-up", params={"statuses": "on_time"}).status_code == 400


# --- Read-only, CORS, start-up -------------------------------------------------------------------------------

# Phase 12B added sign-in, user management, dataset delete and import. Those are the ONLY routes that change
# anything; every data route stays GET-only, and nothing can write to the demo (tests/test_api_auth.py).
WRITE_ROUTES = {("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("POST", "/api/users"),
                ("PATCH", "/api/users/{user_id}"), ("POST", "/api/users/{user_id}/password"),
                ("DELETE", "/api/datasets/{slug}"), ("POST", "/api/imports/check"), ("POST", "/api/imports"),
                ("POST", "/api/review/batch"), ("POST", "/api/review/label")}  # Phase 12C: Review labels


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_data_endpoint_can_write(client, method):
    for path in ("/api/overview", "/api/borrowers", "/api/repayments/follow-up.csv"):
        assert getattr(client, method)(path).status_code == 405
    for path in ("/api/import", "/api/data"):
        assert getattr(client, method)(path).status_code in (404, 405)


def test_only_the_listed_routes_change_anything(client):
    for route in client.app.routes:
        methods = getattr(route, "methods", None)
        if methods and route.path.startswith("/api"):
            for method in methods - {"GET", "HEAD"}:
                assert (method, route.path) in WRITE_ROUTES, (method, route.path)


def test_cors_allows_only_the_configured_origin(client):
    good = client.get("/api/health", headers={"Origin": ORIGIN})
    assert good.headers.get("access-control-allow-origin") == ORIGIN
    bad = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
    preflight = client.options("/api/overview", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"})
    assert preflight.status_code == 400


def test_origins_come_from_a_setting():
    assert load_settings({}).web_origins == [DEFAULT_ORIGIN]
    assert load_settings({"FAIRLEND_WEB_ORIGINS": "https://a.example/, https://b.example"}).web_origins == [
        "https://a.example", "https://b.example"]


class _Unloaded:
    name = "unloaded"

    def load(self):
        raise DataNotReady("The dataset is still loading.")

    def snapshot(self):
        raise DataNotReady("The dataset is still loading.")

    def status(self):
        return {"state": "loading", "message": ""}


def test_data_endpoints_answer_503_until_the_data_is_loaded():
    with TestClient(create_app(source=_Unloaded(), settings=Settings(), prepare=False)) as c:
        assert c.get("/api/health").json()["status"] == "loading"
        response = c.get("/api/overview")
        assert response.status_code == 503 and "loading" in response.json()["detail"]


def test_data_is_loaded_at_start_up_not_on_first_request(monkeypatch):
    calls = []

    class Counting(_Unloaded):
        def load(self):
            calls.append("load")

    with TestClient(create_app(source=Counting(), settings=Settings(), prepare=False)):
        assert calls == ["load"]  # during start-up, before any request


def test_the_api_refuses_to_serve_anything_but_the_demo(monkeypatch, demo_ready):
    monkeypatch.setenv(PRESENT_VARIABLE, "0")
    source = DemoDataSource()
    with pytest.raises(DataNotReady, match="synthetic demo only"):
        source.load()


# --- Code and wording checks ---------------------------------------------------------------------------------

API_FILES = sorted((ROOT / "api").glob("*.py"))


def test_api_code_never_touches_answer_labels_secrets_or_the_network():
    forbidden = ("ground_truth", "gt_borrowers", "gt_messages", "profile_type", ".env", "dotenv", "requests",
                 "urllib", "genai", "GEMINI")
    for path in API_FILES:
        text = path.read_text(encoding="utf-8")
        for word in forbidden:
            assert not re.search(rf"(?<![\w.]){re.escape(word)}(?!\w)", text), f"{path.name} mentions {word}"


def test_api_wording_never_calls_anyone_guilty(client):
    words = re.compile(r"\b(guilty|culprit|offender|criminal|fraudster)\b", re.IGNORECASE)
    for path in API_FILES:
        assert not words.search(path.read_text(encoding="utf-8")), path.name
    for endpoint in ("/api/meta", "/api/overview", "/api/lenders", "/api/repayments"):
        assert not words.search(client.get(endpoint).text), endpoint
    assert views.TRUST_LINE == "Synthetic data. A flag is a prompt for a human to look, not a verdict."
