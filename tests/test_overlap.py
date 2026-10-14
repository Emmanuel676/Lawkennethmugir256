"""Checks on the overlap detector and borrower risk score (Phase 2).

Three kinds of test:

  Hand-built tiny databases, where the right answer is simple arithmetic.
  A code check that src/overlap.py never mentions the answer labels.
  A synthetic world (1,500 borrowers, seed 11) where the score must separate
  the profiles roughly as designed. These use the ground truth only to judge
  the score, never to compute it.
"""

from __future__ import annotations

import copy
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src import db
from src.config import ConfigError, load_config, validate_config
from src.evaluate_overlap import evaluate, load_truth
from src.generate_data import generate, write_world
from src.overlap import explain, score_borrowers

from leak_check import forbidden_mentions

AS_OF = date(2026, 10, 1)
OVERLAP_SOURCE = Path(__file__).resolve().parents[1] / "src" / "overlap.py"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# ---------------------------------------------------------------------------
# Hand-built tiny databases
# ---------------------------------------------------------------------------

def _day(days_ago: int) -> str:
    return (AS_OF - timedelta(days=days_ago)).isoformat()


class TinyWorld:
    """Builds a small lending.db by hand. Days are given as 'days before as_of'."""

    def __init__(self) -> None:
        self.borrowers: list[dict] = []
        self.loans: list[dict] = []
        self.transactions: list[dict] = []

    def borrower(self, borrower_id: str, income: int) -> "TinyWorld":
        self.borrowers.append({"borrower_id": borrower_id, "region": "Central",
                               "monthly_income": income, "joined_date": _day(400)})
        return self

    def loan(self, loan_id: str, borrower_id: str, lender: int, owed: int, issued_days_ago: int,
             status: str = "active") -> "TinyWorld":
        self.loans.append({
            "loan_id": loan_id, "borrower_id": borrower_id, "lender_id": f"L{lender:02d}",
            "principal": max(owed, 1000), "amount_outstanding": owed,
            "issue_date": _day(issued_days_ago), "due_date": _day(issued_days_ago - 30), "status": status,
        })
        return self

    def repay(self, borrower_id: str, loan_id: str, days_ago: int, amount: int = 1000) -> "TinyWorld":
        self.transactions.append({
            "txn_id": f"T{len(self.transactions) + 1:05d}", "borrower_id": borrower_id,
            "txn_date": _day(days_ago), "amount": amount, "direction": "out",
            "counterparty_type": "lender", "linked_loan_id": loan_id,
        })
        return self

    def score(self, tmp_path: Path, cfg: dict) -> pd.DataFrame:
        conn = db.create_database(tmp_path / "lending.db", db.LENDING_SCHEMA)
        db.insert_rows(conn, "meta", [{"key": "as_of_date", "value": AS_OF.isoformat()},
                                      {"key": "synthetic", "value": "true"}])
        db.insert_rows(conn, "lenders", [{"lender_id": f"L{i:02d}", "name": f"Lender {i} (Demo)",
                                          "size_category": "small"} for i in range(1, 11)])
        db.insert_rows(conn, "borrowers", self.borrowers)
        db.insert_rows(conn, "loans", self.loans)
        db.insert_rows(conn, "transactions", self.transactions)
        conn.commit()
        try:
            return score_borrowers(conn, cfg).set_index("borrower_id", drop=False)
        finally:
            conn.close()


def _cycling_chain(world: TinyWorld, borrower_id: str = "B1") -> TinyWorld:
    """Four loans, each issued the day the previous one is repaid: 3 cycling events, little debt."""
    world.borrower(borrower_id, 1_000_000)
    world.loan("C1", borrower_id, 1, 0, 120, "repaid").repay(borrower_id, "C1", 90)
    world.loan("C2", borrower_id, 2, 0, 90, "repaid").repay(borrower_id, "C2", 60)
    world.loan("C3", borrower_id, 3, 0, 60, "repaid").repay(borrower_id, "C3", 30)
    world.loan("C4", borrower_id, 4, 50_000, 30, "active")
    return world


def test_one_small_loan_is_low_with_no_lender_or_arrears_points(tmp_path, cfg):
    scores = TinyWorld().borrower("B1", 1_000_000).loan("A", "B1", 1, 100_000, 100).score(tmp_path, cfg)
    row = scores.loc["B1"]
    assert row["band"] == "low"
    assert row["pts_open_lenders"] == 0
    assert row["pts_arrears"] == 0
    assert row["debt_to_income"] == pytest.approx(0.1)
    assert row["pts_debt_to_income"] == pytest.approx(1.5)  # 0.1 / 2.0 * 30
    assert row["score"] == pytest.approx(1.5)


def test_five_lenders_owing_twice_income_get_full_lender_and_debt_points(tmp_path, cfg):
    world = TinyWorld().borrower("B1", 500_000)
    for lender in range(1, 6):
        world.loan(f"A{lender}", "B1", lender, 200_000, 100)
    row = world.score(tmp_path, cfg).loc["B1"]
    assert row["open_lenders"] == 5
    assert row["debt_to_income"] == pytest.approx(2.0)
    assert row["pts_open_lenders"] == cfg["risk"]["weights"]["open_lenders"]
    assert row["pts_debt_to_income"] == cfg["risk"]["weights"]["debt_to_income"]
    assert row["score"] == pytest.approx(55.0)
    assert row["band"] == "medium"


def test_repaid_loans_are_not_counted_as_owed(tmp_path, cfg):
    world = TinyWorld().borrower("B1", 300_000)
    for lender in range(1, 6):
        world.loan(f"A{lender}", "B1", lender, 0, 100 + lender * 10, "repaid")
    row = world.score(tmp_path, cfg).loc["B1"]
    assert row["open_lenders"] == 0
    assert row["total_owed"] == 0
    assert row["score"] == 0
    assert row["band"] == "low"


def test_arrears_share_is_arrears_amount_over_total_owed(tmp_path, cfg):
    world = (TinyWorld().borrower("B1", 10_000_000)
             .loan("A1", "B1", 1, 100_000, 100, "in_arrears")
             .loan("A2", "B1", 2, 300_000, 100, "active"))
    row = world.score(tmp_path, cfg).loc["B1"]
    assert row["arrears_share"] == pytest.approx(0.25)
    assert row["pts_arrears"] == pytest.approx(5.0)  # 0.25 / 1.0 * 20


def test_cycling_counted_when_a_loan_is_issued_the_day_another_is_repaid(tmp_path, cfg):
    world = (TinyWorld().borrower("B1", 1_000_000)
             .loan("A1", "B1", 1, 0, 100, "repaid").repay("B1", "A1", 70)
             .loan("A2", "B1", 2, 50_000, 70, "active"))
    row = world.score(tmp_path, cfg).loc["B1"]
    assert row["cycling_events"] == 1
    assert row["pts_cycling"] == pytest.approx(5.0)  # 1 / 3 * 15


def test_cycling_not_counted_for_same_loan_or_a_repayment_15_days_away(tmp_path, cfg):
    world = (TinyWorld()
             # Repays its own loan on the day it was issued: not borrowing to repay.
             .borrower("SAME", 1_000_000)
             .loan("S1", "SAME", 1, 0, 70, "repaid").repay("SAME", "S1", 70)
             # A different loan, but repaid 15 days before the new one: too far apart.
             .borrower("FAR", 1_000_000)
             .loan("F1", "FAR", 1, 0, 100, "repaid").repay("FAR", "F1", 85)
             .loan("F2", "FAR", 2, 50_000, 70, "active"))
    scores = world.score(tmp_path, cfg)
    assert scores.loc["SAME", "cycling_events"] == 0
    assert scores.loc["FAR", "cycling_events"] == 0


def test_cycling_outside_the_lookback_window_is_not_counted(tmp_path, cfg):
    lookback = cfg["risk"]["cycling"]["lookback_days"]
    world = (TinyWorld()
             .borrower("OLD", 1_000_000)
             .loan("O1", "OLD", 1, 0, lookback + 40, "repaid").repay("OLD", "O1", lookback + 20)
             .loan("O2", "OLD", 2, 0, lookback + 20, "repaid")
             # Control: the same pattern inside the window is counted.
             .borrower("NEW", 1_000_000)
             .loan("N1", "NEW", 1, 0, lookback - 20, "repaid").repay("NEW", "N1", lookback - 40)
             .loan("N2", "NEW", 2, 0, lookback - 40, "repaid"))
    scores = world.score(tmp_path, cfg)
    assert scores.loc["OLD", "cycling_events"] == 0
    assert scores.loc["NEW", "cycling_events"] == 1


def test_three_cycling_events_with_low_debt_are_forced_to_medium(tmp_path, cfg):
    row = _cycling_chain(TinyWorld()).score(tmp_path, cfg).loc["B1"]
    assert row["cycling_events"] == 3
    assert row["score"] < cfg["risk"]["bands"]["medium"]  # the score alone would be low
    assert row["band"] == "medium"
    assert bool(row["band_forced_by_cycling"]) is True


def test_cycling_chain_stays_low_when_the_forcing_rule_is_off(tmp_path, cfg):
    relaxed = copy.deepcopy(cfg)
    relaxed["risk"]["cycling_forces_minimum_band"] = False
    row = _cycling_chain(TinyWorld()).score(tmp_path, relaxed).loc["B1"]
    assert row["cycling_events"] == 3
    assert row["band"] == "low"
    assert bool(row["band_forced_by_cycling"]) is False


def test_explain_puts_biggest_contributor_first_and_mentions_forced_medium(tmp_path, cfg):
    forced = _cycling_chain(TinyWorld()).score(tmp_path, cfg).loc["B1"]
    lines = explain(forced, cfg)
    assert "repaying a different loan" in lines[0]  # cycling is worth the most points here
    assert "medium" in lines[-1] and "cycling" in lines[-1]
    assert not any("arrears" in line for line in lines)  # 0-point signals are skipped

    world = TinyWorld().borrower("B2", 500_000)
    for lender in range(1, 6):
        world.loan(f"A{lender}", "B2", lender, 200_000, 100)
    stacked = world.score(tmp_path / "second", cfg).loc["B2"]
    lines = explain(stacked, cfg)
    assert "times monthly income" in lines[0]  # 30 points beats 25 for lenders
    assert "5 different lenders" in lines[1]
    assert len(lines) == 2
    assert not any("medium band" in line for line in lines)


def test_score_never_exceeds_100_even_for_extreme_debt(tmp_path, cfg):
    world = TinyWorld().borrower("B1", 100_000)
    for number, days_ago in enumerate((50, 40, 30, 20, 10, 5), start=1):
        world.loan(f"X{number}", "B1", number, 50_000_000, days_ago, "in_arrears")
        if number > 1:
            world.repay("B1", f"X{number - 1}", days_ago)
    row = world.score(tmp_path, cfg).loc["B1"]
    assert row["debt_to_income"] > 1000
    assert row["score"] == pytest.approx(100.0)
    assert row["band"] == "high"
    for signal, weight in cfg["risk"]["weights"].items():
        assert row[f"pts_{signal}"] == weight


# ---------------------------------------------------------------------------
# Config checks
# ---------------------------------------------------------------------------

def test_weights_not_adding_up_to_100_are_rejected(cfg):
    broken = copy.deepcopy(cfg)
    broken["risk"]["weights"]["arrears"] = 25
    with pytest.raises(ConfigError, match="add up to 100"):
        validate_config(broken)


def test_negative_weight_is_rejected(cfg):
    broken = copy.deepcopy(cfg)
    broken["risk"]["weights"]["arrears"] = -5
    broken["risk"]["weights"]["cycling"] = 40
    with pytest.raises(ConfigError, match="negative"):
        validate_config(broken)


def test_bands_out_of_order_are_rejected(cfg):
    broken = copy.deepcopy(cfg)
    broken["risk"]["bands"] = {"medium": 70, "high": 60}
    with pytest.raises(ConfigError, match="0 < medium < high"):
        validate_config(broken)


def test_full_at_open_lenders_of_one_is_rejected(cfg):
    broken = copy.deepcopy(cfg)
    broken["risk"]["full_at"]["open_lenders"] = 1
    with pytest.raises(ConfigError, match="open_lenders"):
        validate_config(broken)


def test_unknown_evaluation_profile_is_rejected(cfg):
    broken = copy.deepcopy(cfg)
    broken["evaluation"]["positive_profiles"] = ["stacked", "gamblers"]
    with pytest.raises(ConfigError, match="unknown profile"):
        validate_config(broken)


def test_profile_in_both_evaluation_lists_is_rejected(cfg):
    broken = copy.deepcopy(cfg)
    broken["evaluation"]["negative_profiles"] = ["typical", "stacked"]
    with pytest.raises(ConfigError, match="both"):
        validate_config(broken)


# ---------------------------------------------------------------------------
# The detector never touches the answer labels
# ---------------------------------------------------------------------------

def test_overlap_module_never_mentions_the_answer_labels():
    assert forbidden_mentions(OVERLAP_SOURCE.read_text(encoding="utf-8")) == []


def test_label_check_catches_leaks_but_ignores_docstrings_and_comments():
    clean = '"""Never reads ground_truth.db."""\n# gt_borrowers is off limits\nx = 1\n'
    assert forbidden_mentions(clean) == []
    assert forbidden_mentions(clean + '_leak = "gt_borrowers"\n') == ["gt_borrowers"]
    assert forbidden_mentions(clean + "path = cfg['paths']['ground_truth_db']\n") == ["ground_truth_db"]
    assert forbidden_mentions(clean + "def f(profile_type):\n    return 1\n") == ["profile_type"]


# ---------------------------------------------------------------------------
# A synthetic world: does the score separate the profiles as designed?
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world(cfg, tmp_path_factory):
    small = copy.deepcopy(cfg)
    small["generator"]["test_set_size"] = 40
    folder = tmp_path_factory.mktemp("world")
    write_world(generate(small, seed=11, n_borrowers=1500), folder / "lending.db", folder / "ground_truth.db")
    conn = sqlite3.connect(str(folder / "lending.db"))
    scores = score_borrowers(conn, cfg)
    again = score_borrowers(conn, cfg)
    conn.close()
    truth = load_truth(folder / "ground_truth.db")
    labelled = scores.merge(truth, on="borrower_id")
    return {"scores": scores, "again": again, "truth": truth, "labelled": labelled}


def _profile(world, name):
    rows = world["labelled"][world["labelled"]["profile_type"] == name]
    assert len(rows) > 0
    return rows


def _flagged(rows):
    return rows["band"].isin(["medium", "high"]).mean()


def test_every_borrower_scored_once_within_0_to_100(world):
    scores = world["scores"]
    assert len(scores) == 1500
    assert scores["borrower_id"].is_unique
    assert set(scores["borrower_id"]) == set(world["truth"]["borrower_id"])
    assert scores["score"].between(0, 100).all()
    assert set(scores["band"]) <= {"low", "medium", "high"}


def test_scoring_twice_gives_identical_results(world):
    pd.testing.assert_frame_equal(world["scores"], world["again"])


def test_scores_are_sorted_highest_first(world):
    scores = world["scores"]
    assert scores["score"].is_monotonic_decreasing


def test_typical_borrowers_are_rarely_flagged(world):
    assert _flagged(_profile(world, "typical")) < 0.02


def test_lookalikes_hold_several_lenders_but_are_never_high(world):
    lookalikes = _profile(world, "look_alike")
    assert (lookalikes["open_lenders"] >= 3).mean() > 0.5
    assert (lookalikes["band"] == "high").sum() == 0


def test_stacked_borrowers_are_mostly_flagged_and_often_high(world):
    stacked = _profile(world, "stacked")
    assert _flagged(stacked) > 0.80
    assert (stacked["band"] == "high").mean() > 0.30


def test_stacked_score_well_above_lookalikes(world):
    assert _profile(world, "stacked")["score"].median() >= _profile(world, "look_alike")["score"].median() + 15


def test_cycling_events_pick_out_cycling_borrowers(world):
    labelled = world["labelled"]
    cycling = labelled["profile_type"] == "cycling"
    assert (labelled.loc[cycling, "cycling_events"] >= 3).mean() > 0.90
    assert (labelled.loc[~cycling, "cycling_events"] >= 3).mean() < 0.03


def test_evaluation_precision_and_recall(world, cfg):
    result = evaluate(world["scores"], world["truth"], cfg)
    assert result["precision"] > 0.7
    assert result["recall"] > 0.75
    assert result["true_positives"] + result["false_positives"] + result["missed"] + result["true_negatives"] == 1500


def test_evaluation_refuses_borrowers_without_a_label(world, cfg):
    truth = world["truth"].iloc[10:]
    with pytest.raises(ValueError, match="no ground-truth"):
        evaluate(world["scores"], truth, cfg)
