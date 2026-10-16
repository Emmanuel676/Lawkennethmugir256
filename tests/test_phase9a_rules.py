"""Phase 9A (approved): the cycling rule needs a DIFFERENT lender, and late-night detection has its own window.

Hand-built tiny databases, so the right answer is simple arithmetic. All data is synthetic.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta

import pandas as pd
import pytest

from src import db
from src.config import ConfigError, load_config, validate_config
from src.generate_data import generate, late_night_hours, write_world
from src.lender_comparison import detect_late_night_hours, is_late_night
from src.overlap import explain, mark_clearing_repayments, score_borrowers

AS_OF = date(2026, 10, 1)
DEMO_FINGERPRINT = "3945277a047220916234197d5844183d2ae84313ad9ba5fced6246ffe5d3df9e"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _daily_world(tmp_path, cfg, lenders: list[int], gap_days: int = 0):
    """One borrower, one 30-day loan per entry in lenders, each repaid in 30 DAILY instalments linked to its
    own loan; the next loan starts gap_days after the last instalment (re-borrowing after clearing)."""
    loans, txns = [], []
    issue = AS_OF - timedelta(days=150)
    for number, lender in enumerate(lenders, start=1):
        loan_id = f"LN{number}"
        cleared = issue + timedelta(days=30)
        last = number == len(lenders)
        loans.append({"loan_id": loan_id, "borrower_id": "B1", "lender_id": f"L{lender:02d}", "principal": 150_000,
                      "amount_outstanding": 0 if not last else 180_000, "issue_date": issue.isoformat(),
                      "due_date": cleared.isoformat(), "status": "repaid" if not last else "active"})
        for day in range(1, 31):
            when = issue + timedelta(days=day)
            if when > AS_OF or last:
                break
            txns.append({"txn_id": f"T{len(txns) + 1:05d}", "borrower_id": "B1", "txn_date": when.isoformat(),
                         "amount": 6_000, "direction": "out", "counterparty_type": "lender", "linked_loan_id": loan_id})
        issue = cleared + timedelta(days=gap_days)
    conn = db.create_database(tmp_path / "lending.db", db.LENDING_SCHEMA)
    db.insert_rows(conn, "meta", [{"key": "as_of_date", "value": AS_OF.isoformat()}])
    db.insert_rows(conn, "lenders", [{"lender_id": f"L{i:02d}", "name": f"Lender {i} (Demo)", "size_category": "small"}
                                     for i in range(1, 6)])
    db.insert_rows(conn, "borrowers", [{"borrower_id": "B1", "region": "Central", "monthly_income": 1_000_000,
                                        "joined_date": "2025-01-01"}])
    db.insert_rows(conn, "loans", loans)
    db.insert_rows(conn, "transactions", txns)
    conn.commit()
    try:
        return score_borrowers(conn, cfg).set_index("borrower_id").loc["B1"]
    finally:
        conn.close()


@pytest.mark.parametrize("gap", [0, 1, 2])
def test_single_lender_daily_repayers_have_no_cycling_events(tmp_path, cfg, gap):
    row = _daily_world(tmp_path, cfg, [1, 1, 1, 1, 1], gap)
    assert row["cycling_events"] == 0
    assert not bool(row["band_forced_by_cycling"])


def test_genuine_cross_lender_cyclers_are_still_counted(tmp_path, cfg):
    row = _daily_world(tmp_path, cfg, [1, 2, 3, 4, 5])
    assert row["cycling_events"] == 4
    assert row["band"] == "medium" and bool(row["band_forced_by_cycling"])
    assert "from another lender" in explain(row, cfg)[0]


def test_switching_the_setting_off_brings_the_old_behaviour_back(tmp_path, cfg):
    old = copy.deepcopy(cfg)
    old["risk"]["cycling_require_different_lender"] = False
    row = _daily_world(tmp_path, old, [1, 1, 1, 1, 1])
    assert row["cycling_events"] == 4  # the old rule counted a same-lender re-borrow as cycling
    assert bool(row["band_forced_by_cycling"])
    assert "from another lender" not in explain(row, old)[0]


def test_a_missing_setting_means_the_new_rule(tmp_path, cfg):
    absent = copy.deepcopy(cfg)
    del absent["risk"]["cycling_require_different_lender"]
    assert _daily_world(tmp_path, absent, [1, 1, 1])["cycling_events"] == 0


def test_late_night_detection_uses_its_own_window(cfg):
    assert cfg["lender_comparison"]["late_night_detect"] == {"start_hour": 0, "end_hour": 5}
    assert detect_late_night_hours(cfg) == [0, 1, 2, 3, 4]
    stamps = pd.Series(["2026-09-01 21:30:00", "2026-09-01 23:59:00", "2026-09-02 00:00:00",
                        "2026-09-02 04:59:00", "2026-09-02 05:00:00", "2026-09-02"])
    assert is_late_night(stamps, cfg).tolist() == [False, False, True, True, False, False]
    # The demo generator keeps its own, unchanged window.
    assert late_night_hours(cfg) == [0, 1, 2, 3, 4, 5, 21, 22, 23]


def test_a_detection_window_may_wrap_past_midnight(cfg):
    wrapped = copy.deepcopy(cfg)
    wrapped["lender_comparison"]["late_night_detect"] = {"start_hour": 22, "end_hour": 2}
    assert detect_late_night_hours(wrapped) == [0, 1, 22, 23]


@pytest.mark.parametrize("change, message", [
    (lambda c: c["risk"].__setitem__("cycling_require_different_lender", "yes"), "cycling_require_different_lender"),
    (lambda c: c["lender_comparison"].pop("late_night_detect"), "late_night_detect"),
    (lambda c: c["lender_comparison"].__setitem__("late_night_detect", {"start_hour": 0, "end_hour": 24}),
     "late_night_detect"),
    (lambda c: c["lender_comparison"].__setitem__("late_night_detect", {"start_hour": 3, "end_hour": 3}), "differ"),
])
def test_bad_phase_9a_settings_are_rejected(cfg, change, message):
    broken = copy.deepcopy(cfg)
    change(broken)
    with pytest.raises(ConfigError, match=message):
        validate_config(broken)


def test_the_demo_fingerprint_is_unchanged(cfg, tmp_path):
    """The synthetic demo built from config.yaml and the seed is exactly the Phase 1 demo."""
    manifest = write_world(generate(cfg), tmp_path / "lending.db", tmp_path / "ground_truth.db")
    assert manifest["lending_db_content_hash"] == DEMO_FINGERPRINT


# --- Phase 9B: the repayment must CLEAR the old loan ---------------------------------------------------------------

def _score(tmp_path, cfg, loans: list[tuple], repayments: list[tuple]):
    """loans: (loan_id, lender, issued_days_ago, status, owed); repayments: (loan_id or None, days_ago, amount)."""
    conn = db.create_database(tmp_path / "lending.db", db.LENDING_SCHEMA)
    db.insert_rows(conn, "meta", [{"key": "as_of_date", "value": AS_OF.isoformat()}])
    db.insert_rows(conn, "lenders", [{"lender_id": f"L{i:02d}", "name": f"Lender {i} (Demo)", "size_category": "small"}
                                     for i in range(1, 6)])
    db.insert_rows(conn, "borrowers", [{"borrower_id": "B1", "region": "Central", "monthly_income": 1_000_000,
                                        "joined_date": "2025-01-01"}])
    db.insert_rows(conn, "loans", [{
        "loan_id": loan_id, "borrower_id": "B1", "lender_id": f"L{lender:02d}", "principal": 150_000,
        "amount_outstanding": owed, "issue_date": (AS_OF - timedelta(days=ago)).isoformat(),
        "due_date": (AS_OF - timedelta(days=ago - 30)).isoformat(), "status": status}
        for loan_id, lender, ago, status, owed in loans])
    db.insert_rows(conn, "transactions", [{
        "txn_id": f"T{n:05d}", "borrower_id": "B1", "txn_date": (AS_OF - timedelta(days=ago)).isoformat(),
        "amount": amount, "direction": "out", "counterparty_type": "lender", "linked_loan_id": loan_id}
        for n, (loan_id, ago, amount) in enumerate(repayments, start=1)])
    conn.commit()
    try:
        return score_borrowers(conn, cfg).set_index("borrower_id").loc["B1"]
    finally:
        conn.close()


def _parallel_daily(tmp_path, cfg):
    """Loan A (lender 1) repaid DAILY for 30 days and cleared; loans from lenders 2 and 3 start while A is still
    being paid. Nobody is borrowing to repay: A's clearing payment is far from both new loans."""
    loans = [("A", 1, 100, "repaid", 0), ("B", 2, 85, "active", 100_000), ("C", 3, 80, "active", 100_000)]
    repayments = [("A", 100 - day, 6_000) for day in range(1, 31)]
    return _score(tmp_path, cfg, loans, repayments)


def test_multi_lender_daily_repayers_get_no_cycling_events(tmp_path, cfg):
    row = _parallel_daily(tmp_path, cfg)
    assert row["cycling_events"] == 0 and not bool(row["band_forced_by_cycling"])


def test_switching_the_clearing_requirement_off_restores_the_9a_rule(tmp_path, cfg):
    old = copy.deepcopy(cfg)
    old["risk"]["cycling_require_clearing_repayment"] = False
    assert _parallel_daily(tmp_path, old)["cycling_events"] == 2  # a daily instalment to A sat near B's and C's start


def test_genuine_cyclers_who_clear_loan_a_on_the_day_loan_b_arrives_are_counted(tmp_path, cfg):
    """Pays each loan daily for 20 days, then a loan from the next lender arrives and pays the rest the same day."""
    loans, repayments = [], []
    for number, ago in enumerate((120, 100, 80, 60), start=1):
        loan_id = f"C{number}"
        last = number == 4
        loans.append((loan_id, number, ago, "active" if last else "repaid", 120_000 if last else 0))
        repayments += [(loan_id, ago - day, 6_000) for day in range(1, 20)]
        if not last:
            repayments.append((loan_id, ago - 20, 66_000))  # cleared on the day the next loan starts
    row = _score(tmp_path, cfg, loans, repayments)
    assert row["cycling_events"] == 3
    assert row["band"] == "medium" and bool(row["band_forced_by_cycling"])
    assert "clearing a loan from another lender" in explain(row, cfg)[0]


def test_a_loan_that_is_not_repaid_or_has_no_linked_repayment_never_clears(tmp_path, cfg):
    # In arrears: its last repayment, on the day a loan from another lender starts, does not clear it.
    arrears = _score(tmp_path, cfg, [("A", 1, 60, "in_arrears", 50_000), ("B", 2, 40, "active", 100_000)],
                     [("A", 41, 10_000), ("A", 40, 10_000)])
    assert arrears["cycling_events"] == 0
    # Repaid, but its clearing payment carries no linked_loan_id: no clearing information, so no event.
    unlinked = _score(tmp_path / "u", cfg, [("A", 1, 60, "repaid", 0), ("B", 2, 40, "active", 100_000)],
                      [("A", 50, 10_000), (None, 40, 170_000)])
    assert unlinked["cycling_events"] == 0
    # The same loan WITH the link on its clearing payment is counted.
    linked = _score(tmp_path / "l", cfg, [("A", 1, 60, "repaid", 0), ("B", 2, 40, "active", 100_000)],
                    [("A", 50, 10_000), ("A", 40, 170_000)])
    assert linked["cycling_events"] == 1


def test_only_the_last_linked_repayment_of_a_repaid_loan_clears_it():
    frame = pd.DataFrame({
        "linked_loan_id": ["A", "A", "A", "B", "B", "C"],
        "txn_date": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-02", "2026-09-01", "2026-09-05",
                                    "2026-09-03"]),
        "repaid_loan_status": ["repaid", "repaid", "repaid", "in_arrears", "in_arrears", None],
    })
    assert mark_clearing_repayments(frame).tolist() == [False, True, True, False, False, False]
