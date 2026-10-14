"""Checks on the lender comparison and the borrower harassment summary (Phase 3).

All cases are tiny hand-made tables, so the right answer is arithmetic.
"""

from __future__ import annotations

import copy

import pandas as pd
import pytest

from src.config import load_config
from src.evaluate_lenders import evaluate_ranking
from src.lender_comparison import (TOO_FEW, borrower_harassment_summary, compare_lenders, explain_lender,
                                   wilson_interval)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class Messages:
    """Builds messages, labels and lenders for compare_lenders()."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.labels: list[dict] = []
        self.names: dict[str, str] = {}

    def add(self, lender_id: str, label: str, count: int = 1, borrower_id: str = "B1",
            recipient_type: str = "borrower", sent_at: str = "2026-09-01 10:00:00") -> "Messages":
        self.names.setdefault(lender_id, f"{lender_id} Loans (Demo)")
        for _ in range(count):
            message_id = f"M{len(self.messages) + 1:06d}"
            self.messages.append({"message_id": message_id, "lender_id": lender_id, "borrower_id": borrower_id,
                                  "recipient_type": recipient_type, "sent_at": sent_at})
            self.labels.append({"message_id": message_id, "predicted_class": label})
        return self

    def lender(self, lender_id: str, n: int, n_abusive: int) -> "Messages":
        return self.add(lender_id, "threat", n_abusive).add(lender_id, "normal", n - n_abusive)

    def frames(self):
        lenders = pd.DataFrame([{"lender_id": k, "name": v} for k, v in self.names.items()])
        return pd.DataFrame(self.messages), pd.DataFrame(self.labels), lenders

    def compare(self, cfg) -> pd.DataFrame:
        return compare_lenders(*self.frames(), cfg).set_index("lender_id", drop=False)


def _with_minimum(cfg, minimum):
    changed = copy.deepcopy(cfg)
    changed["generator"]["min_lender_messages"] = minimum
    return changed


# --- Wilson interval -----------------------------------------------------------

def test_wilson_interval_matches_hand_computed_values():
    low, high = wilson_interval(5, 10, 0.95)
    assert low == pytest.approx(0.2366, abs=1e-3)
    assert high == pytest.approx(0.7634, abs=1e-3)


def test_wilson_interval_edge_cases():
    low, high = wilson_interval(0, 10, 0.95)
    assert low == 0.0
    assert high == pytest.approx(0.2775, abs=1e-3)
    low, high = wilson_interval(10, 10, 0.95)
    assert low == pytest.approx(0.7225, abs=1e-3)
    assert high == 1.0
    assert wilson_interval(0, 0, 0.95) == (0.0, 1.0)


def test_lower_confidence_gives_a_narrower_interval():
    low95, high95 = wilson_interval(30, 100, 0.95)
    low90, high90 = wilson_interval(30, 100, 0.90)
    assert low95 < low90 < 0.30 < high90 < high95


# --- Ranking ---------------------------------------------------------------------

def test_lender_below_minimum_is_unranked_even_at_100_percent_abusive(cfg):
    table = Messages().lender("TINY", 10, 10).lender("BIG", 60, 6).compare(cfg)
    assert table.loc["TINY", "abusive_share"] == 1.0
    assert pd.isna(table.loc["TINY", "rank"])
    assert table.loc["TINY", "reason"] == TOO_FEW
    assert table.loc["BIG", "rank"] == 1
    assert table.loc["BIG", "reason"] == ""


def test_three_of_three_beats_a_large_lender_only_when_it_is_allowed_to_rank(cfg):
    world = Messages().lender("LARGE", 1000, 400).lender("TINY", 3, 3)

    default = world.compare(cfg)  # minimum 50: three messages are too few
    assert default.loc["LARGE", "rank"] == 1
    assert pd.isna(default.loc["TINY", "rank"])

    lenient = world.compare(_with_minimum(cfg, 3))  # now three messages are enough
    assert lenient.loc["TINY", "abusive_low"] == pytest.approx(0.4385, abs=1e-3)
    assert lenient.loc["LARGE", "abusive_low"] < lenient.loc["TINY", "abusive_low"]
    assert lenient.loc["TINY", "rank"] == 1
    assert lenient.loc["LARGE", "rank"] == 2


def test_ranking_uses_the_lower_bound_not_the_raw_share(cfg):
    # SMALL has the higher share (55%) but far less evidence than BIG (50% of 2,000).
    table = Messages().lender("SMALL", 55, 30).lender("BIG", 2000, 1000).compare(cfg)
    assert table.loc["SMALL", "abusive_share"] > table.loc["BIG", "abusive_share"]
    assert table.loc["BIG", "rank"] == 1
    assert table.loc["SMALL", "rank"] == 2


def test_abusive_classes_come_from_the_config(cfg):
    world = Messages().add("A", "threat", 30).add("A", "shaming_third_party", 20).add("A", "firm_pressure", 50)
    assert world.compare(cfg).loc["A", "abusive_share"] == pytest.approx(0.5)
    only_threats = copy.deepcopy(cfg)
    only_threats["lender_comparison"]["abusive_classes"] = ["threat"]
    assert world.compare(only_threats).loc["A", "abusive_share"] == pytest.approx(0.3)


# --- Late night and third party ------------------------------------------------------

def test_late_night_share_uses_the_configured_hours(cfg):
    world = Messages()
    for time in ("21:00:00", "05:59:00", "06:00:00", "20:59:00", "23:30:00"):
        world.add("A", "normal", sent_at=f"2026-09-01 {time}")
    assert world.compare(cfg).loc["A", "late_night_share"] == pytest.approx(3 / 5)  # 21:00 to 05:59

    narrow = copy.deepcopy(cfg)
    narrow["generator"]["late_night"] = {"start_hour": 23, "end_hour": 5}
    assert world.compare(narrow).loc["A", "late_night_share"] == pytest.approx(1 / 5)  # only 23:30


def test_third_party_share_uses_recipient_type_not_the_label(cfg):
    world = (Messages()
             .add("A", "normal", 2, recipient_type="third_party")
             .add("A", "normal", 2, recipient_type="borrower"))
    row = world.compare(cfg).loc["A"]
    assert row["third_party_share"] == pytest.approx(0.5)
    assert row["shaming_share"] == 0


def test_messages_per_borrower(cfg):
    world = Messages().add("A", "normal", 6, borrower_id="B1").add("A", "normal", 2, borrower_id="B2")
    assert world.compare(cfg).loc["A", "messages_per_borrower"] == pytest.approx(4.0)


def test_a_message_without_a_label_is_an_error(cfg):
    messages, labels, lenders = Messages().add("A", "normal", 3).frames()
    with pytest.raises(ValueError, match="no label"):
        compare_lenders(messages, labels.iloc[1:], lenders, cfg)


def test_explanations_say_why_a_lender_is_unranked(cfg):
    table = Messages().lender("TINY", 10, 10).lender("BIG", 60, 6).compare(cfg)
    assert "too few messages to rank" in explain_lender(table.loc["TINY"], cfg, "local")
    sentence = explain_lender(table.loc["BIG"], cfg, "local")
    assert sentence.startswith("BIG Loans (Demo): rank 1.")
    assert "10% of its 60 messages" in sentence


# --- Borrower harassment summary --------------------------------------------------------

def test_borrower_harassment_summary_counts(cfg):
    world = (Messages()
             .add("A", "threat", 2, borrower_id="B1", sent_at="2026-09-01 22:00:00")
             .add("A", "shaming_third_party", 1, borrower_id="B1", recipient_type="third_party")
             .add("A", "normal", 3, borrower_id="B1")
             .add("A", "firm_pressure", 1, borrower_id="B2", sent_at="2026-09-01 02:00:00"))
    messages, labels, _ = world.frames()
    summary = borrower_harassment_summary(messages, labels, cfg, borrower_ids=["B1", "B2", "B3"])
    summary = summary.set_index("borrower_id")
    assert summary.loc["B1"].to_dict() == {"abusive_messages": 3, "late_night_messages": 2, "third_party_messages": 1}
    assert summary.loc["B2"].to_dict() == {"abusive_messages": 0, "late_night_messages": 1, "third_party_messages": 0}
    assert summary.loc["B3"].to_dict() == {"abusive_messages": 0, "late_night_messages": 0, "third_party_messages": 0}


# --- Evaluation of the ranking ------------------------------------------------------------

def test_evaluate_ranking_detects_order_and_unranked(cfg):
    table = (Messages().lender("ABU", 100, 50).lender("MID", 100, 20).lender("OK", 100, 2)
             .lender("TINY", 5, 5).compare(cfg).reset_index(drop=True))
    behaviour = pd.DataFrame({"lender_id": ["ABU", "MID", "OK", "TINY"],
                              "behaviour": ["abusive", "borderline", "clean", "abusive"]})
    result = evaluate_ranking(table, behaviour)
    assert result["abusive_above_clean"] and result["abusive_above_borderline"] and result["borderline_above_clean"]
    assert result["unranked"] == [("TINY Loans (Demo)", "abusive", 5)]

    swapped = behaviour.assign(behaviour=["clean", "borderline", "abusive", "abusive"])
    assert evaluate_ranking(table, swapped)["abusive_above_clean"] is False
