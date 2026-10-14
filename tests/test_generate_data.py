"""Checks that the synthetic data generator behaves as the PRD requires.

Most tests build a small world (800 borrowers) so they run in a few seconds.
They check the *design* of the data: reproducible, labels kept apart, profiles
behave as described, messages are honest about dates, and the test set cannot be
passed by memorising templates. Detector accuracy is tested in later phases.

A few tests build the full-size world on purpose, because some properties (like
the tiny lender staying tiny) only show up at full size.
"""

from __future__ import annotations

import copy
import re
import sqlite3
from collections import defaultdict
from datetime import date
from statistics import median

import numpy as np
import pytest

from src import db
from src.config import MESSAGE_CLASSES, PROFILES, ConfigError, load_config, validate_config
from src.generate_data import add_noise, generate, is_holdout_template, write_world

SEED = 7
N = 800
TEST_SET_SIZE = 40  # small worlds cannot supply 400 held-out messages, so tests ask for 40


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def small_cfg(cfg):
    small = copy.deepcopy(cfg)
    small["generator"]["test_set_size"] = TEST_SET_SIZE
    return small


@pytest.fixture(scope="module")
def world(small_cfg):
    return generate(small_cfg, seed=SEED, n_borrowers=N)


def _profile_by_borrower(world):
    return {row["borrower_id"]: row["profile_type"] for row in world["gt_borrowers"]}


def _loans_by_borrower(world):
    grouped: dict[str, list[dict]] = defaultdict(list)
    for loan in world["loans"]:
        grouped[loan["borrower_id"]].append(loan)
    return grouped


def _class_by_message(world):
    return {row["message_id"]: row["true_class"] for row in world["gt_messages"]}


def _normalise(text: str, brands: list[str]) -> str:
    """Strip everything that varies between messages from the same template (names, numbers, punctuation)."""
    text = text.lower()
    for brand in brands:
        text = text.replace(brand.lower(), "x")
    text = re.sub(r"\d[\d,]*", "0", text)
    text = re.sub(r"[^a-z0 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# --- Reproducibility (FR-D2) ------------------------------------------------

def test_same_seed_gives_identical_data(cfg):
    first = generate(cfg, seed=SEED, n_borrowers=300)
    second = generate(cfg, seed=SEED, n_borrowers=300)
    assert first == second


def test_different_seed_gives_different_data(cfg):
    first = generate(cfg, seed=1, n_borrowers=300)
    second = generate(cfg, seed=2, n_borrowers=300)
    assert first["loans"] != second["loans"]
    assert first["messages"] != second["messages"]


def test_two_builds_have_the_same_fingerprints(cfg, tmp_path):
    manifests = []
    for name in ("a", "b"):
        world = generate(cfg, seed=SEED, n_borrowers=300)
        manifests.append(write_world(world, tmp_path / name / "lending.db", tmp_path / name / "ground_truth.db"))
    assert manifests[0]["lending_db_content_hash"] == manifests[1]["lending_db_content_hash"]
    assert manifests[0]["ground_truth_db_content_hash"] == manifests[1]["ground_truth_db_content_hash"]


# --- Ground truth is kept apart (FR-D3) ------------------------------------

def test_lending_db_contains_no_answer_labels(small_cfg, tmp_path):
    world = generate(small_cfg, seed=SEED, n_borrowers=200)
    write_world(world, tmp_path / "lending.db", tmp_path / "ground_truth.db")

    conn = sqlite3.connect(str(tmp_path / "lending.db"))
    forbidden_columns = {"true_class", "profile_type", "behaviour", "split", "template_id"}
    for table in db.table_names(conn):
        assert not table.startswith("gt_"), f"{table} looks like a ground-truth table"
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        assert not (columns & forbidden_columns), f"{table} leaks labels: {columns & forbidden_columns}"
    conn.close()

    truth = sqlite3.connect(str(tmp_path / "ground_truth.db"))
    assert set(db.table_names(truth)) == {"gt_borrowers", "gt_messages", "gt_lenders"}
    truth.close()


def test_every_lending_row_has_exactly_the_expected_fields(world):
    """Checks every row of every table, not just the first."""
    for table in ("lenders", "borrowers", "loans", "transactions", "messages"):
        expected = set(db.COLUMNS[table])
        for row in world[table]:
            assert set(row) == expected, f"{table} row has unexpected fields: {set(row) ^ expected}"


def test_every_message_borrower_and_lender_has_a_label(world):
    assert {m["message_id"] for m in world["messages"]} == {g["message_id"] for g in world["gt_messages"]}
    assert {b["borrower_id"] for b in world["borrowers"]} == {g["borrower_id"] for g in world["gt_borrowers"]}
    assert {x["lender_id"] for x in world["lenders"]} == {g["lender_id"] for g in world["gt_lenders"]}


# --- Database integrity -----------------------------------------------------

def test_database_has_no_broken_references(world, tmp_path):
    write_world(world, tmp_path / "lending.db", tmp_path / "ground_truth.db")
    conn = sqlite3.connect(str(tmp_path / "lending.db"))
    conn.execute("PRAGMA foreign_keys = ON")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT value FROM meta WHERE key = 'synthetic'").fetchone()[0] == "true"
    conn.close()


def test_dates_and_amounts_are_consistent(world, cfg):
    as_of = date.fromisoformat(cfg["project"]["as_of_date"])
    joined = {b["borrower_id"]: date.fromisoformat(b["joined_date"]) for b in world["borrowers"]}
    for loan in world["loans"]:
        issue, due = date.fromisoformat(loan["issue_date"]), date.fromisoformat(loan["due_date"])
        assert issue < due
        assert issue <= as_of
        assert joined[loan["borrower_id"]] < issue
        assert loan["principal"] > 0
        if loan["status"] == "repaid":
            assert loan["amount_outstanding"] == 0
        else:
            assert loan["amount_outstanding"] > 0
        if loan["status"] == "in_arrears":
            assert due < as_of
        if loan["status"] == "active":
            assert due >= as_of
    for txn in world["transactions"]:
        assert date.fromisoformat(txn["txn_date"]) <= as_of
    for message in world["messages"]:
        assert message["sent_at"][:10] <= as_of.isoformat()


def test_loan_ids_follow_issue_date_order(world):
    ids = [loan["loan_id"] for loan in world["loans"]]
    assert ids == sorted(ids)
    issue_dates = [loan["issue_date"] for loan in world["loans"]]
    assert issue_dates == sorted(issue_dates)
    assert len(set(ids)) == len(ids)


# --- Profiles behave as the PRD describes (section 8.2) --------------------

def test_profile_counts_follow_the_configured_mix(world, cfg):
    counts = {name: 0 for name in PROFILES}
    for profile in _profile_by_borrower(world).values():
        counts[profile] += 1

    total_share = sum(cfg["profiles"][name]["mix"] for name in PROFILES)
    expected = {name: int(N * cfg["profiles"][name]["mix"] / total_share) for name in PROFILES}
    expected["typical"] += N - sum(expected.values())  # leftovers become typical borrowers
    assert counts == expected


def _open_lenders_and_dti(world, profile):
    profiles, loans = _profile_by_borrower(world), _loans_by_borrower(world)
    income = {b["borrower_id"]: b["monthly_income"] for b in world["borrowers"]}
    lenders, ratios = [], []
    for borrower_id, kind in profiles.items():
        if kind != profile:
            continue
        open_loans = [loan for loan in loans[borrower_id] if loan["status"] != "repaid"]
        lenders.append(len({loan["lender_id"] for loan in open_loans}))
        ratios.append(sum(loan["amount_outstanding"] for loan in open_loans) / income[borrower_id])
    return median(lenders), median(ratios)


def test_stacked_borrowers_have_three_or_more_distinct_lenders_in_a_short_window(world):
    profiles, loans = _profile_by_borrower(world), _loans_by_borrower(world)
    stacked = [b for b, p in profiles.items() if p == "stacked"]
    assert stacked
    for borrower_id in stacked:
        assert len({loan["lender_id"] for loan in loans[borrower_id]}) >= 3
        issues = sorted(date.fromisoformat(loan["issue_date"]) for loan in loans[borrower_id])
        assert (issues[-1] - issues[0]).days <= 50


def test_lookalikes_hold_as_many_open_loans_as_stacked_borrowers_but_owe_far_less(world):
    """Hard negatives: counting lenders alone must not be enough to tell the two groups apart."""
    stacked_lenders, stacked_dti = _open_lenders_and_dti(world, "stacked")
    lookalike_lenders, lookalike_dti = _open_lenders_and_dti(world, "look_alike")
    assert lookalike_lenders >= 3
    assert abs(stacked_lenders - lookalike_lenders) <= 1
    assert stacked_dti > 3 * lookalike_dti


def test_lookalikes_almost_never_fall_into_arrears(world):
    profiles, loans = _profile_by_borrower(world), _loans_by_borrower(world)
    flat = [loan for b, p in profiles.items() if p == "look_alike" for loan in loans[b]]
    arrears = sum(1 for loan in flat if loan["status"] == "in_arrears")
    assert arrears / len(flat) < 0.05


def test_cycling_loans_fund_the_repayment_of_the_previous_loan(world):
    profiles, loans = _profile_by_borrower(world), _loans_by_borrower(world)
    txns_by_loan: dict[str, list[dict]] = defaultdict(list)
    for txn in world["transactions"]:
        if txn["linked_loan_id"]:
            txns_by_loan[txn["linked_loan_id"]].append(txn)

    pairs = matched = 0
    for borrower_id, profile in profiles.items():
        if profile != "cycling":
            continue
        chain = sorted(loans[borrower_id], key=lambda loan: loan["issue_date"])
        assert len(chain) >= 3
        for earlier, later in zip(chain, chain[1:]):
            pairs += 1
            disbursed = date.fromisoformat(later["issue_date"])
            repayments = [t for t in txns_by_loan[earlier["loan_id"]] if t["direction"] == "out"]
            if any(abs((date.fromisoformat(t["txn_date"]) - disbursed).days) <= 1 for t in repayments):
                matched += 1
    assert pairs > 0
    assert matched / pairs >= 0.95


def test_cycling_borrowers_are_still_cycling_today(world, cfg):
    """The chain runs up to today, so most cycling borrowers have an open loan, not a clean slate."""
    profiles, loans = _profile_by_borrower(world), _loans_by_borrower(world)
    as_of = date.fromisoformat(cfg["project"]["as_of_date"])
    cycling = [b for b, p in profiles.items() if p == "cycling"]
    owing = [b for b in cycling if any(loan["amount_outstanding"] > 0 for loan in loans[b])]
    assert len(owing) / len(cycling) >= 0.7
    for borrower_id in cycling:
        latest_issue = max(date.fromisoformat(loan["issue_date"]) for loan in loans[borrower_id])
        assert (as_of - latest_issue).days <= 40  # the chain reaches (almost) to today


def test_some_arrears_loans_have_a_partial_repayment(world):
    arrears_ids = {loan["loan_id"] for loan in world["loans"] if loan["status"] == "in_arrears"}
    paid = {t["linked_loan_id"] for t in world["transactions"]
            if t["linked_loan_id"] in arrears_ids and t["direction"] == "out"}
    share = len(paid) / len(arrears_ids)
    assert 0.10 < share < 0.50  # configured at 0.25


# --- Messages ---------------------------------------------------------------

def test_all_four_message_classes_appear(world):
    assert set(_class_by_message(world).values()) == set(MESSAGE_CLASSES)


def test_abusive_lenders_send_more_abuse_than_borderline_and_clean(world):
    behaviour = {row["lender_id"]: row["behaviour"] for row in world["gt_lenders"]}
    classes = _class_by_message(world)
    totals = {"clean": 0, "borderline": 0, "abusive": 0}
    bad = {"clean": 0, "borderline": 0, "abusive": 0}
    for message in world["messages"]:
        kind = behaviour[message["lender_id"]]
        totals[kind] += 1
        if classes[message["message_id"]] in ("threat", "shaming_third_party"):
            bad[kind] += 1
    rate = {kind: bad[kind] / totals[kind] for kind in totals}
    assert rate["abusive"] > rate["borderline"] > rate["clean"]


def test_third_party_messages_are_all_shaming(world):
    classes = _class_by_message(world)
    third_party = [m for m in world["messages"] if m["recipient_type"] == "third_party"]
    assert third_party
    assert all(classes[m["message_id"]] == "shaming_third_party" for m in third_party)


def test_abusive_lenders_message_late_at_night_more_often(world):
    behaviour = {row["lender_id"]: row["behaviour"] for row in world["gt_lenders"]}
    late = {"clean": [0, 0], "abusive": [0, 0]}
    for message in world["messages"]:
        kind = behaviour[message["lender_id"]]
        if kind not in late:
            continue
        hour = int(message["sent_at"][11:13])
        late[kind][0] += 1 if (hour >= 21 or hour < 6) else 0
        late[kind][1] += 1
    assert late["abusive"][0] / late["abusive"][1] > 3 * (late["clean"][0] / late["clean"][1])


def test_days_overdue_in_message_text_matches_the_day_it_was_sent(world):
    """A message that says 'N days overdue' must be true on the day it was sent."""
    due_dates: dict[tuple[str, str], list[date]] = defaultdict(list)
    for loan in world["loans"]:
        if loan["status"] == "in_arrears":
            due_dates[(loan["borrower_id"], loan["lender_id"])].append(date.fromisoformat(loan["due_date"]))

    patterns = [
        re.compile(r"(\d+) days? (?:overdue|late|behind)"),
        re.compile(r"overdue by (\d+) days?"),
        re.compile(r"after (\d+) days?"),
    ]
    checked = 0
    for message in world["messages"]:
        match = next((p.search(message["text"]) for p in patterns if p.search(message["text"])), None)
        if match is None:
            continue
        checked += 1
        sent = date.fromisoformat(message["sent_at"][:10])
        claimed = int(match.group(1))
        assert any((sent - due).days == claimed for due in due_dates[(message["borrower_id"], message["lender_id"])]), (
            f"{message['message_id']} says {claimed} days but that is not true on {sent}: {message['text']}")
    assert checked > 50  # make sure the test really looked at messages


def test_no_message_says_one_days_or_due_tomorrow(world):
    for message in world["messages"]:
        lowered = message["text"].lower()
        assert " 1 days" not in lowered
        assert "due tomorrow" not in lowered


def test_micro_lender_stays_too_small_to_rank_at_full_size(cfg):
    """PRD FR-L2: a lender with fewer than 50 messages is 'insufficient data'. Checked across seeds at full size."""
    minimum = cfg["generator"]["min_lender_messages"]
    for seed in (7, 100, 2024):
        world = generate(cfg, seed=seed)  # generate() itself raises if the tiny lender is too big
        micro_ids = {row["lender_id"] for row in world["lenders"] if row["size_category"] == "micro"}
        assert micro_ids
        for lender_id in micro_ids:
            assert sum(1 for m in world["messages"] if m["lender_id"] == lender_id) < minimum


def test_generator_stops_loudly_if_the_tiny_lender_is_not_tiny(cfg):
    strict = copy.deepcopy(cfg)
    strict["generator"]["min_lender_messages"] = 1  # any message at all is now "too many"
    with pytest.raises(ValueError, match="tiny lender"):
        generate(strict, seed=42)


def test_lender_loan_cap_is_respected(small_cfg):
    capped = copy.deepcopy(small_cfg)
    capped["lender_sizes"]["micro"] = 3.0              # make the tiny lender popular...
    capped["generator"]["min_lender_messages"] = 10_000  # ...and switch off the size check for this test
    micro_name = next(spec["name"] for spec in capped["lenders"] if spec["size"] == "micro")
    for spec in capped["lenders"]:
        if spec["name"] == micro_name:
            spec["max_loans"] = 3
    world = generate(capped, seed=SEED, n_borrowers=N)
    micro_id = next(row["lender_id"] for row in world["lenders"] if row["name"] == micro_name)
    loans = sum(1 for loan in world["loans"] if loan["lender_id"] == micro_id)
    assert 0 < loans <= 4  # the cap, plus at most one overshoot when a borrower picks it twice


# --- The held-out test set (finding: test used to be answerable by memorising templates) ---

def test_test_set_has_the_requested_size_and_is_balanced(world):
    test = [g for g in world["gt_messages"] if g["split"] == "test"]
    per_class = {c: sum(1 for g in test if g["true_class"] == c) for c in MESSAGE_CLASSES}
    assert per_class == {c: TEST_SET_SIZE // len(MESSAGE_CLASSES) for c in MESSAGE_CLASSES}


def test_test_phrasings_never_appear_in_development_messages(world):
    for row in world["gt_messages"]:
        holdout = is_holdout_template(row["template_id"])
        if row["split"] == "dev":
            assert not holdout, f"{row['message_id']} is dev but uses held-out phrasing {row['template_id']}"
        else:
            assert holdout, f"{row['message_id']} is {row['split']} but uses development phrasing"
    assert {row["split"] for row in world["gt_messages"]} == {"dev", "test", "reserve"}


def test_no_test_message_has_an_identical_phrasing_twin_in_dev(world):
    """The check that exposed the original flaw: strip names, numbers and punctuation, then look for twins."""
    brands = [row["name"].replace(" (Demo)", "") for row in world["lenders"]]
    text = {m["message_id"]: m["text"] for m in world["messages"]}
    dev = {_normalise(text[g["message_id"]], brands) for g in world["gt_messages"] if g["split"] == "dev"}
    test = [_normalise(text[g["message_id"]], brands) for g in world["gt_messages"] if g["split"] == "test"]
    assert test
    assert sum(1 for t in test if t in dev) == 0


def test_noise_never_changes_amounts():
    rng = np.random.default_rng(3)
    original = "Please pay UGX 250,000 today. Your loan with Demo Lender is overdue, and fees apply."
    for _ in range(200):
        noisy = add_noise(original, rng)
        # Noise may drop the comma but must never alter the amount itself.
        assert "250000" in noisy.replace(",", "")


def test_some_messages_are_noisy(world):
    odd = sum(1 for m in world["messages"] if m["text"].islower() or m["text"].endswith("!!"))
    assert odd > 0


# --- Config checking --------------------------------------------------------

def test_bad_class_probabilities_give_a_clear_error(cfg):
    broken = copy.deepcopy(cfg)
    broken["lender_behaviour"]["clean"]["class_probs"] = {
        "normal": 0.5, "firm_pressure": 0.1, "threat": 0.1, "shaming_third_party": 0.1}
    with pytest.raises(ConfigError, match="add up to 1"):
        validate_config(broken)


def test_bad_loan_cap_gives_a_clear_error(cfg):
    broken = copy.deepcopy(cfg)
    broken["lenders"][-1]["max_loans"] = 0
    with pytest.raises(ConfigError, match="max_loans"):
        validate_config(broken)


def test_bad_holdout_probability_gives_a_clear_error(cfg):
    broken = copy.deepcopy(cfg)
    broken["generator"]["holdout_template_prob"] = 1.5
    with pytest.raises(ConfigError, match="holdout_template_prob"):
        validate_config(broken)
