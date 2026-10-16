"""Phase 10: the Repayments page (src/repayments.py, pages/7_Repayments.py).

Hand-built tiny databases, so every status and boundary is simple arithmetic. All data is synthetic.
"""

from __future__ import annotations

import copy
import io
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import db
from src import repayments as rp
from src.config import ConfigError, load_config, resolve_path, validate_config
from src.dashboard_ui import CONFIG_VARIABLE

from leak_check import forbidden_mentions
from worlds import build_classified_world

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 10, 1)
DEMO_FINGERPRINT = "3945277a047220916234197d5844183d2ae84313ad9ba5fced6246ffe5d3df9e"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _day(days_ago: int) -> str:
    return (AS_OF - timedelta(days=days_ago)).isoformat()


class Book:
    """Loans and repayments for a tiny lending.db. Days are 'days before the as-of date'; loans run 30 days."""

    def __init__(self):
        self.loans, self.txns = [], []

    def loan(self, loan_id, issued_ago, status, owed=0, borrower="B1", lender=1, term=30):
        self.loans.append({"loan_id": loan_id, "borrower_id": borrower, "lender_id": f"L{lender:02d}",
                           "principal": 100_000, "amount_outstanding": owed, "issue_date": _day(issued_ago),
                           "due_date": _day(issued_ago - term), "status": status})
        return self

    def pay(self, loan_id, days_ago, borrower="B1", linked=True):
        self.txns.append({"txn_id": f"T{len(self.txns) + 1:05d}", "borrower_id": borrower, "txn_date": _day(days_ago),
                          "amount": 5_000, "direction": "out", "counterparty_type": "lender",
                          "linked_loan_id": loan_id if linked else None})
        return self

    def write(self, path: Path) -> Path:
        conn = db.create_database(path, db.LENDING_SCHEMA)
        db.insert_rows(conn, "meta", [{"key": "as_of_date", "value": AS_OF.isoformat()},
                                      {"key": "synthetic", "value": "true"}])
        db.insert_rows(conn, "lenders", [{"lender_id": f"L{i:02d}", "name": f"Lender {i} (Demo)",
                                          "size_category": "small"} for i in range(1, 4)])
        borrowers = sorted({row["borrower_id"] for row in self.loans})
        db.insert_rows(conn, "borrowers", [{"borrower_id": b, "region": "Central", "monthly_income": 500_000,
                                            "joined_date": "2025-01-01"} for b in borrowers])
        db.insert_rows(conn, "loans", self.loans)
        db.insert_rows(conn, "transactions", self.txns)
        conn.commit()
        conn.close()
        return path

    def statuses(self, tmp_path: Path, cfg) -> pd.Series:
        conn = sqlite3.connect(str(self.write(tmp_path / "lending.db")))
        try:
            return rp.loan_statuses(conn, cfg).set_index("loan_id")["repayment_status"]
        finally:
            conn.close()


# --- Unpaid loans: current, grace, not paying, overdue but paying ------------------------------------------------

def test_current_in_grace_and_beyond_grace_boundaries(tmp_path, cfg):
    # due = issued - 30 days ago. Due today -> current; 1 and 3 days past due -> in grace; 4 -> beyond grace.
    book = (Book().loan("DUE_TOMORROW", 29, "active", 100).loan("DUE_TODAY", 30, "active", 100)
            .loan("PAST_1", 31, "active", 100).loan("PAST_3", 33, "in_arrears", 100)
            .loan("PAST_4", 34, "in_arrears", 100))
    s = book.statuses(tmp_path, cfg)
    assert s["DUE_TOMORROW"] == s["DUE_TODAY"] == "current"
    assert s["PAST_1"] == s["PAST_3"] == "in_grace"
    assert s["PAST_4"] == "not_paying"  # beyond grace and no repayment at all


def test_not_paying_versus_overdue_but_paying_at_the_window_edge(tmp_path, cfg):
    window = cfg["repayments"]["not_paying_after_days"]  # 30
    book = (Book().loan("PAID_29_DAYS_AGO", 100, "in_arrears", 100).pay("PAID_29_DAYS_AGO", window - 1)
            .loan("PAID_30_DAYS_AGO", 100, "in_arrears", 100).pay("PAID_30_DAYS_AGO", window)
            .loan("PAID_UNLINKED", 100, "in_arrears", 100).pay("PAID_UNLINKED", 1, linked=False)
            .loan("PAID_AFTER_AS_OF", 100, "in_arrears", 100).pay("PAID_AFTER_AS_OF", -2))
    s = book.statuses(tmp_path, cfg)
    assert s["PAID_29_DAYS_AGO"] == "overdue_paying"
    assert s["PAID_30_DAYS_AGO"] == "not_paying"
    assert s["PAID_UNLINKED"] == "not_paying"     # a repayment without a link cannot count (stated limit)
    assert s["PAID_AFTER_AS_OF"] == "not_paying"  # nothing after "today" counts


# --- Repaid loans: on time, late within / beyond grace (day 33), unknown --------------------------------------------

def test_repaid_boundaries_due_date_grace_and_day_33(tmp_path, cfg):
    # Issued 100 days ago, due 70 days ago (day 30 of the loan). Day 33 = due + grace.
    book = Book()
    for name, loan_day in (("DAY_30", 30), ("DAY_31", 31), ("DAY_33", 33), ("DAY_34", 34), ("DAY_10", 10)):
        book.loan(name, 100, "repaid").pay(name, 100 - 5).pay(name, 100 - loan_day)
    s = book.statuses(tmp_path, cfg)
    assert s["DAY_10"] == s["DAY_30"] == "on_time"
    assert s["DAY_31"] == s["DAY_33"] == "late_within_grace"
    assert s["DAY_34"] == "late_beyond_grace"


def test_a_repaid_loan_without_a_linked_repayment_is_unknown_never_guessed(tmp_path, cfg):
    book = (Book().loan("NO_REPAYMENTS", 100, "repaid")
            .loan("ONLY_UNLINKED", 100, "repaid").pay("ONLY_UNLINKED", 75, linked=False))
    s = book.statuses(tmp_path, cfg)
    assert s["NO_REPAYMENTS"] == s["ONLY_UNLINKED"] == "unknown"


def test_the_last_linked_repayment_decides_even_if_an_unlinked_one_is_later(tmp_path, cfg):
    book = Book().loan("A", 100, "repaid").pay("A", 72).pay("A", 60, linked=False)  # true last payment unlinked
    assert book.statuses(tmp_path, cfg)["A"] == "on_time"  # the stated limit: cleared looks earlier than it was


# --- Borrower roll-up, ageing, follow-up list ---------------------------------------------------------------------------

def _load(tmp_path, cfg, book):
    path = book.write(tmp_path / "lending.db")
    borrowers = sorted({row["borrower_id"] for row in book.loans})
    scores = pd.DataFrame({"borrower_id": borrowers, "band": "medium", "open_lenders": 2})
    lenders = pd.DataFrame({"lender_id": [f"L{i:02d}" for i in range(1, 4)],
                            "name": [f"Lender {i} (Demo)" for i in range(1, 4)]})
    return rp.load(cfg, scores, lenders, path)


def test_a_borrower_takes_the_worst_status_of_their_loans(tmp_path, cfg):
    book = (Book().loan("A1", 100, "repaid", borrower="BA").pay("A1", 70, borrower="BA")           # on time
            .loan("A2", 100, "repaid", borrower="BA", lender=2).pay("A2", 60, borrower="BA")      # late beyond grace
            .loan("A3", 100, "repaid", borrower="BA", lender=3)                                   # unknown
            .loan("C1", 100, "repaid", borrower="BC").pay("C1", 70, borrower="BC")                # on time
            .loan("C2", 100, "repaid", borrower="BC", lender=2)                                   # unknown
            .loan("D1", 100, "in_arrears", 50_000, borrower="BD").pay("D1", 5, borrower="BD")     # overdue paying
            .loan("D2", 120, "in_arrears", 70_000, borrower="BD", lender=2))                      # not paying
    rollup = _load(tmp_path, cfg, book)["rollup"].set_index("borrower_id")
    assert rollup.loc["BA", "worst_status"] == "late_beyond_grace"
    assert rollup.loc["BC", "worst_status"] == "unknown"  # missing information is never shown as a good record
    assert rollup.loc["BD", "worst_status"] == "not_paying"
    assert rollup.loc["BD", ["loans_overdue", "owed_overdue", "days_past_due"]].tolist() == [2, 120_000, 90]
    assert rollup.loc["BD", "overdue_lenders"] == "Lender 1 (Demo); Lender 2 (Demo)"
    assert rollup.loc["BA", "on_time"] == 1 and rollup.loc["BA", "unknown"] == 1


def test_ageing_buckets_and_their_edges(tmp_path, cfg):
    assert rp.bucket_labels([3, 30, 60, 90]) == ["current", "1-3 days (grace)", "4-30 days", "31-60 days",
                                                 "61-90 days", "over 90 days"]
    book = Book()
    for name, past_due in (("P0", 0), ("P3", 3), ("P4", 4), ("P30", 30), ("P31", 31), ("P90", 90), ("P91", 91)):
        book.loan(name, 30 + past_due, "in_arrears" if past_due else "active", 10_000)
    book.loan("PAID", 200, "repaid").pay("PAID", 170)  # repaid loans are not in the ageing table
    result = _load(tmp_path, cfg, book)
    buckets = dict(zip(result["statuses"]["loan_id"], result["statuses"]["bucket"]))
    assert [buckets[n] for n in ("P0", "P3", "P4", "P30", "P31", "P90", "P91", "PAID")] == [
        "current", "1-3 days (grace)", "4-30 days", "4-30 days", "31-60 days", "61-90 days", "over 90 days", ""]
    table = result["ageing"].set_index("bucket")
    assert table["loans"].tolist() == [1, 1, 2, 1, 1, 1] and table["owed"].sum() == 70_000


def test_follow_up_filters_sort_and_csv_notice(tmp_path, cfg):
    book = (Book().loan("X1", 100, "in_arrears", 10_000, borrower="BX")
            .loan("Y1", 60, "in_arrears", 90_000, borrower="BY", lender=2)
            .loan("Z1", 100, "repaid", borrower="BZ").pay("Z1", 70, borrower="BZ"))
    rollup = _load(tmp_path, cfg, book)["rollup"]
    rows = rp.follow_up(rollup)
    assert rows["borrower_id"].tolist() == ["BX", "BY"]  # most days past due first; BZ (on time) is not listed
    assert rp.follow_up(rollup, sort_label="Amount owed (overdue)")["borrower_id"].tolist() == ["BY", "BX"]
    assert rp.follow_up(rollup, lenders=["Lender 2 (Demo)"])["borrower_id"].tolist() == ["BY"]
    assert rp.follow_up(rollup, bands=["high"]).empty
    content = rp.follow_up_csv(rows, "SYNTHETIC DATA: test notice.").decode("utf-8")
    first = content.splitlines()[0]
    assert first.startswith("# SYNTHETIC DATA: test notice.") and rp.PROMPT in first
    frame = pd.read_csv(io.StringIO(content), comment="#")
    assert list(frame.columns) == list(rp.FOLLOW_UP_COLUMNS.values())
    assert frame["repayment_status"].tolist() == ["Not paying", "Not paying"]
    assert "name" not in " ".join(frame.columns)  # borrower codes only


def test_a_dataset_where_every_loan_has_one_repayment_is_recognised(tmp_path, cfg):
    lump = _load(tmp_path, cfg, Book().loan("A", 100, "repaid").pay("A", 70))
    daily = _load(tmp_path / "d", cfg, Book().loan("A", 100, "repaid").pay("A", 80).pay("A", 70))
    assert lump["lump"] is True and daily["lump"] is False


# --- Config ----------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("change, message", [
    (lambda c: c.pop("repayments"), "missing the 'repayments' section"),
    (lambda c: c["repayments"].__setitem__("grace_days", -1), "grace_days"),
    (lambda c: c["repayments"].__setitem__("not_paying_after_days", 0), "not_paying_after_days"),
    (lambda c: c["repayments"].__setitem__("ageing_bucket_edges", [3, 30, 20]), "keep rising"),
    (lambda c: c["repayments"].__setitem__("ageing_bucket_edges", [5, 30, 60]), "start at grace_days"),
    (lambda c: c["repayments"].__setitem__("min_loans_to_compare", True), "min_loans_to_compare"),
])
def test_bad_repayment_settings_give_a_plain_error(cfg, change, message):
    broken = copy.deepcopy(cfg)
    change(broken)
    with pytest.raises(ConfigError, match=message):
        validate_config(broken)


# --- The page, the answer key and the demo ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return build_classified_world(tmp_path_factory.mktemp("repayments_world"), n_borrowers=400)


@pytest.mark.parametrize("present", ["0", "1"])
def test_the_page_runs_headless_in_normal_and_presentation_mode(world, monkeypatch, present):
    _, config_path = world
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    monkeypatch.setenv("FAIRLEND_PRESENT", present)
    at = AppTest.from_file(str(ROOT / "pages" / "7_Repayments.py"), default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert [m.label for m in at.metric] == ["On time", "Late within grace", "Late beyond grace", "Not paying",
                                            "Unknown (no link)", "Owed, unpaid loans"]
    assert any(rp.PROMPT in i.value for i in at.info)
    assert any("follow-up list" in m.value for m in at.markdown)
    assert all(any(line in m.value for m in at.markdown) for line in rp.LIMITS)
    assert any("one payment" in c.value for c in at.caption)  # the demo-style data repays each loan in one go
    at.multiselect(key="rp_bands").set_value(["high"]).run()
    assert not at.exception


@pytest.mark.parametrize("module", ["src/repayments.py", "pages/7_Repayments.py"])
def test_repayment_code_never_reads_labels_answer_keys_secrets_or_network(module):
    names = ("ground_truth", "gt_borrowers", "gt_messages", "gt_lenders", "profile_type", "answer_key",
             "borrower_truth", "loan_truth", "sample_pack", ".env", "dotenv", "requests", "urllib", "genai")
    assert forbidden_mentions((ROOT / module).read_text(encoding="utf-8"), names) == []


def test_reading_repayments_leaves_the_demo_unchanged(cfg):
    lending = resolve_path(cfg, "lending_db")
    if not lending.exists():
        pytest.skip("Demo not built.")
    conn = sqlite3.connect(f"{lending.resolve().as_uri()}?mode=ro", uri=True)
    try:
        rp.loan_statuses(conn, cfg)
        assert db.content_hash(conn) == DEMO_FINGERPRINT
    finally:
        conn.close()
