"""Phase 9A: the synthetic sample lender packs (src/make_sample_pack.py).

Packs are built into a temporary folder and imported with the REAL importer, then scored with the real
score_borrowers. The answer key is read here, in the tests, only to check the results. All data is synthetic.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src import db
from src.config import ConfigError, load_config, resolve_path, validate_config
from src.datasets import get_dataset_paths
from src.evaluate_sample_pack import import_folder, link_check, read_truth, sequential_import, temp_config
from src.import_data import COLUMNS, TABLES, _table_for_file
from src.make_sample_pack import ALL_LENDERS, ANSWER_DIR, _safe_remove, build_all, build_scenario
from src.overlap import connect_read_only, score_borrowers

from leak_check import forbidden_mentions

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("baseline", "high_overlap", "cycling", "repayment_mix", "clean_control")
ABUSIVE = ("threat", "shaming_third_party")
DEMO_FINGERPRINT = "3945277a047220916234197d5844183d2ae84313ad9ba5fced6246ffe5d3df9e"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def packs(cfg, tmp_path_factory):
    root = tmp_path_factory.mktemp("sample_pack")
    build_all(cfg, root)
    return root


@pytest.fixture(scope="module")
def imported(cfg, packs, tmp_path_factory):
    """Every scenario's all_lenders folder imported with the real importer, then scored."""
    work = tmp_path_factory.mktemp("imports")
    out = {}
    for scenario in SCENARIOS:
        tmp = temp_config(cfg, work / scenario)
        result, _ = import_folder(tmp, packs / scenario / ALL_LENDERS, f"pack {scenario}")
        paths = get_dataset_paths(tmp, result.dataset)
        conn = connect_read_only(paths.lending_db)
        try:
            scores = score_borrowers(conn, tmp)
        finally:
            conn.close()
        out[scenario] = {"result": result, "paths": paths,
                         "scores": scores.merge(read_truth(packs, scenario, "borrower_truth"), on="borrower_id")}
    return out


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _digests(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


# --- Format: the import format, per lender and combined ----------------------------------------------------------

def test_each_scenario_has_lender_folders_in_the_exact_import_format(cfg, packs):
    letters = [lender["letter"] for lender in cfg["sample_pack"]["lenders"]]
    for scenario in SCENARIOS:
        for folder in [f"lender_{x}" for x in letters] + [ALL_LENDERS]:
            for table in TABLES:
                path = packs / scenario / folder / f"{table}.csv"
                header = path.read_text(encoding="utf-8").splitlines()[0]
                assert header.split(",") == COLUMNS[table], path


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_pack_loads_through_the_real_importer(imported, packs, scenario):
    result = imported[scenario]["result"]
    assert result.ok and not result.report.errors
    for table in TABLES:
        assert result.rows_written[table] == len(_rows(packs / scenario / ALL_LENDERS / f"{table}.csv"))


def test_lenders_imported_one_after_another_match_across_lenders(cfg, packs, tmp_path):
    steps = sequential_import(cfg, packs, "baseline", tmp_path)
    assert [s["matched_2plus"] for s in steps] == [s["expected_2plus"] for s in steps]
    assert steps[0]["matched_2plus"] == 0 and steps[1]["matched_2plus"] > 0  # matches appear with lender B
    truth = read_truth(packs, "baseline", "borrower_truth")
    assert steps[-1]["matched_2plus"] == int(truth["high_overlap"].sum())
    assert steps[-1]["borrowers"] == len(truth)


def test_the_same_code_names_the_same_borrower_at_every_lender(cfg, packs):
    seen: dict[str, dict] = {}
    for lender in cfg["sample_pack"]["lenders"]:
        for row in _rows(packs / "high_overlap" / f"lender_{lender['letter']}" / "borrowers.csv"):
            assert re.fullmatch(r"B-[0-9a-f]{12}", row["borrower_id"])
            assert seen.setdefault(row["borrower_id"], row) == row  # identical row wherever it appears


# --- Reproducible, synthetic, no seed -----------------------------------------------------------------------------

def test_the_same_seed_reproduces_the_same_files(cfg, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for root in (first, second):
        build_scenario(cfg, "cycling", root)
    assert _digests(first) == _digests(second)
    other = copy.deepcopy(cfg)
    other["sample_pack"]["seed"] += 1
    build_scenario(other, "cycling", tmp_path / "c")
    assert _digests(first) != _digests(tmp_path / "c")


def test_no_seed_is_stored_in_the_pack_files(cfg, packs):
    seed = str(cfg["sample_pack"]["seed"])
    for path in packs.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "seed" not in text.lower(), path
            assert not re.search(rf"(?<!\d){seed}(?!\d)", text), path


def test_everything_is_marked_synthetic(cfg, packs):
    suffix = cfg["sample_pack"]["message_suffix"]
    for scenario in SCENARIOS:
        for row in _rows(packs / scenario / ALL_LENDERS / "lenders.csv"):
            assert row["name"].endswith("(Demo)")
        assert all(r["text"].endswith(suffix) for r in _rows(packs / scenario / ALL_LENDERS / "messages.csv"))
        assert "SYNTHETIC" in (packs / scenario / "ABOUT_THIS_PACK.txt").read_text(encoding="utf-8")
    assert "FAKE" in cfg["sample_pack"]["fake_salt"]


# --- Scenario expectations --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("scenario, share", [("baseline", 0.30), ("high_overlap", 0.90), ("clean_control", 0.0)])
def test_share_of_borrowers_at_two_or_more_lenders(imported, scenario, share):
    conn = connect_read_only(imported[scenario]["paths"].lending_db)
    try:
        per = pd.read_sql_query("SELECT borrower_id, COUNT(DISTINCT lender_id) n FROM loans GROUP BY borrower_id", conn)
    finally:
        conn.close()
    assert (per["n"] >= 2).mean() == pytest.approx(share, abs=0.02)


def test_clean_control_has_no_high_band_borrowers_and_no_abusive_messages(imported, packs):
    scores = imported["clean_control"]["scores"]
    assert (scores["band"] == "high").sum() == 0
    assert scores["cycling_events"].sum() == 0
    truth = read_truth(packs, "clean_control", "message_truth")
    assert not truth["true_class"].isin(ABUSIVE).any()


def test_the_defined_cyclers_are_caught(imported):
    scores = imported["cycling"]["scores"]
    cyclers = scores[scores["cycler"]]
    assert len(cyclers) == 60
    assert (cyclers["cycling_events"] >= 1).all() and cyclers["band"].isin(["medium", "high"]).all()


@pytest.mark.parametrize("scenario", ["baseline", "repayment_mix", "cycling"])
def test_single_lender_daily_repayers_never_get_a_cycling_event(imported, scenario):
    """The fixed rule, exercised by realistic repeat borrowing (re-borrow gap 0-14 days)."""
    scores = imported[scenario]["scores"]
    assert (scores.loc[scores["role"] == "single", "cycling_events"] == 0).all()


def test_repayment_mix_shows_the_payer_split(cfg, packs):
    truth = read_truth(packs, "repayment_mix", "borrower_truth")
    shares = truth["payer_type"].value_counts(normalize=True)
    for kind, share in cfg["sample_pack"]["repayment"]["payer_split"].items():
        assert shares[kind] == pytest.approx(share, abs=0.05)
    assert truth["bad_payer"].mean() == pytest.approx(cfg["sample_pack"]["repayment"]["payer_split"]["not_paid"], abs=0.05)


# --- Realism settings (a) to (f) ------------------------------------------------------------------------------------------

def test_a_abusive_messages_before_the_due_date_and_late_night_reminders(packs):
    truth = read_truth(packs, "baseline", "message_truth")
    early = truth[(truth["kind"] == "pre_due_pressure") & truth["sent_before_due"]]
    assert early["true_class"].isin(ABUSIVE).sum() > 0
    assert (truth["late_night"] & (truth["kind"] == "reminder")).sum() > 0


def test_b_messages_after_a_part_payment_quote_the_remaining_balance(packs):
    messages = read_truth(packs, "baseline", "message_truth")
    loans = read_truth(packs, "baseline", "loan_truth").set_index("loan_id")
    reminders = messages[messages["kind"] == "reminder"]
    part_paid = reminders[reminders["balance_at_send"] < reminders["loan_id"].map(loans["total_due"])]
    assert len(part_paid) > 0
    assert (part_paid["quoted_amount"] == part_paid["balance_at_send"]).all()


def test_c_post_due_messages_do_not_always_quote_the_exact_balance(cfg, packs):
    truth = read_truth(packs, "high_overlap", "message_truth")
    overdue = truth[truth["kind"].isin(["overdue", "overdue_after_clear"])]
    exact = overdue["quoted_exact"].mean()
    assert 0 < exact < 1
    assert exact == pytest.approx(cfg["sample_pack"]["messages"]["exact_balance_prob"], abs=0.1)


def test_d_late_but_cleared_borrowers_sometimes_get_overdue_messages(packs):
    messages = read_truth(packs, "baseline", "message_truth")
    loans = read_truth(packs, "baseline", "loan_truth").set_index("loan_id")
    after = messages[messages["kind"] == "overdue_after_clear"]
    assert len(after) > 0
    assert (after["loan_id"].map(loans["payer_kind"]) == "late_cleared").all()
    assert after["loan_id"].map(loans["cleared_date"]).astype(str).str.len().eq(10).all()


@pytest.mark.parametrize("scenario", ["baseline", "high_overlap", "cycling", "repayment_mix"])
def test_e_the_small_lender_is_too_small_to_rank_but_has_abusive_messages(cfg, packs, scenario):
    letter = cfg["sample_pack"]["small_lender"]["letter"]
    truth = read_truth(packs, scenario, "message_truth")
    mine = truth[truth["lender_letter"] == letter]
    assert len(mine) < cfg["generator"]["min_lender_messages"]
    assert mine["true_class"].isin(ABUSIVE).sum() >= cfg["sample_pack"]["small_lender"]["min_abusive_messages"]


def test_f_a_share_of_repayments_has_no_link_and_the_cycling_signal_needs_it(cfg, packs, tmp_path):
    rows = _rows(packs / "cycling" / ALL_LENDERS / "transactions.csv")
    repayments = [r for r in rows if r["direction"] == "out"]
    unlinked = sum(not r["linked_loan_id"] for r in repayments) / len(repayments)
    assert unlinked == pytest.approx(1 - cfg["sample_pack"]["repayment"]["link_share"], abs=0.02)
    assert all(r["linked_loan_id"] for r in rows if r["direction"] == "in")  # disbursements always linked
    default, none = link_check(cfg, "cycling", tmp_path, shares=(None, 0.0))
    assert default["with_event"] == default["cyclers"] > 0
    assert none["with_event"] == 0  # without the link the cycling signal is gone


# --- Separation: the answer key, the demo -------------------------------------------------------------------------------

def test_the_answer_key_is_outside_the_packs_and_cannot_be_imported(packs):
    keys = list((packs / ANSWER_DIR).rglob("*.csv"))
    assert len(keys) == 3 * len(SCENARIOS)
    assert all(_table_for_file(p.name) is None for p in keys)
    for scenario in SCENARIOS:
        assert not any("truth" in p.name for p in (packs / scenario).rglob("*"))


DETECTION_CODE = (["app.py"] + sorted(f"pages/{p.name}" for p in (ROOT / "pages").glob("*.py"))
                  + [f"src/{name}.py" for name in ("overlap", "lender_comparison", "dashboard_data", "dashboard_ui",
                                                   "classify_local", "classify_messages", "import_data", "datasets",
                                                   "predictions", "review", "bootstrap", "build_all", "repayments")])


@pytest.mark.parametrize("module", DETECTION_CODE)
def test_detection_and_dashboard_code_never_read_the_answer_key(module):
    names = ("answer_key", "borrower_truth", "loan_truth", "message_truth", "evaluate_sample_pack",
             "make_sample_pack", "sample_pack")
    assert forbidden_mentions((ROOT / module).read_text(encoding="utf-8"), names) == []


def test_building_packs_leaves_the_demo_untouched(cfg, packs):
    lending = resolve_path(cfg, "lending_db")
    if not lending.exists():
        pytest.skip("Demo not built.")
    conn = sqlite3.connect(f"{lending.resolve().as_uri()}?mode=ro", uri=True)
    try:
        assert db.content_hash(conn) == DEMO_FINGERPRINT
    finally:
        conn.close()
    manifest = json.loads(resolve_path(cfg, "manifest").read_text(encoding="utf-8"))
    assert manifest["lending_db_content_hash"] == DEMO_FINGERPRINT


def test_the_builder_only_removes_folders_inside_its_own_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="Refusing"):
        _safe_remove(tmp_path / "root", outside)
    assert outside.exists()


@pytest.mark.parametrize("change, message", [
    (lambda p: p["repayment"]["payer_split"].__setitem__("on_time", 0.5), "payer_split"),
    (lambda p: p["lenders"][0].__setitem__("name", "Real Bank"), "Demo"),
    (lambda p: p.__setitem__("fake_salt", "my-real-salt"), "FAKE"),
    (lambda p: p["repayment"].__setitem__("link_share", 1.5), "link_share"),
    (lambda p: p["scenarios"].__setitem__("party", {}), "unknown scenario"),
])
def test_bad_sample_pack_settings_are_rejected(cfg, change, message):
    broken = copy.deepcopy(cfg)
    change(broken["sample_pack"])
    with pytest.raises(ConfigError, match=message):
        validate_config(broken)
