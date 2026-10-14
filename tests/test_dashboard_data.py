"""Checks on the dashboard data layer, src/dashboard_data.py (Phase 4).

Uses a small classified world (800 borrowers, seed 11), built the same way
`python -m src.build_all` builds the real one.
"""

from __future__ import annotations

import copy
import io
import os
import shutil
import sqlite3

import pandas as pd
import pytest

from src.config import MESSAGE_CLASSES, ConfigError, load_config, validate_config
from src.dashboard_data import (BORROWER_EXPORT_COLUMNS, LENDER_EXPORT_COLUMNS, REVIEW_LINE, borrower_detail,
                                data_signature, filter_borrowers, flagged_borrowers_csv, lender_comparison_csv,
                                lender_detail, load_all, overview_kpis, page_count, page_slice, signal_weights)

from worlds import build_classified_world, config_for


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    folder = tmp_path_factory.mktemp("dashboard_world")
    cfg, _ = build_classified_world(folder)
    data = load_all(cfg)
    assert data.ok, data.message
    return {"folder": folder, "cfg": cfg, "data": data}


# --- load_all -----------------------------------------------------------------------

def test_load_all_returns_everything(world):
    data = world["data"]
    assert len(data.borrowers) == 800
    assert data.borrowers["borrower_id"].is_unique
    assert data.borrowers["score"].is_monotonic_decreasing
    assert data.label_coverage == {"local": 1.0}
    assert data.classifier == "local"
    assert data.as_of_date == "2026-10-01"
    assert "SYNTHETIC" in data.notice
    assert data.messages["predicted_class"].notna().all()
    for column in ("region", "abusive_messages", "late_night_messages", "third_party_messages"):
        assert column in data.borrowers.columns


def test_missing_dataset_gives_a_friendly_status(world, tmp_path):
    data = load_all(config_for(tmp_path / "empty", world["cfg"]))
    assert data.status == "missing"
    assert "python -m src.build_all" in data.commands
    assert data.borrowers.empty


def test_missing_predictions_gives_a_friendly_status(world, tmp_path):
    cfg = config_for(tmp_path, world["cfg"])
    shutil.copy(world["folder"] / "lending.db", tmp_path / "lending.db")
    data = load_all(cfg)
    assert data.status == "missing"
    assert "python -m src.classify_messages --classifier local" in data.commands
    assert "SYNTHETIC" in data.notice


def test_stale_predictions_give_a_friendly_status(world, tmp_path):
    cfg = config_for(tmp_path, world["cfg"])
    shutil.copy(world["folder"] / "lending.db", tmp_path / "lending.db")
    shutil.copy(world["folder"] / "predictions.db", tmp_path / "predictions.db")
    assert load_all(cfg).ok  # an exact copy still matches
    conn = sqlite3.connect(str(tmp_path / "lending.db"))
    conn.execute("UPDATE messages SET text = text || ' (edited)' WHERE message_id = "
                 "(SELECT MIN(message_id) FROM messages)")
    conn.commit()
    conn.close()
    data = load_all(cfg)
    assert data.status == "stale"
    assert "classify_messages" in data.commands


def test_incomplete_labels_give_a_friendly_status(world, tmp_path):
    cfg = config_for(tmp_path, world["cfg"])
    shutil.copy(world["folder"] / "lending.db", tmp_path / "lending.db")
    shutil.copy(world["folder"] / "predictions.db", tmp_path / "predictions.db")
    conn = sqlite3.connect(str(tmp_path / "predictions.db"))
    conn.execute("DELETE FROM message_predictions WHERE message_id = (SELECT MIN(message_id) FROM message_predictions)")
    conn.commit()
    conn.close()
    data = load_all(cfg)
    assert data.status == "incomplete"
    assert "classify_messages" in data.commands


def test_signature_changes_when_a_database_changes(world, tmp_path):
    cfg = config_for(tmp_path, world["cfg"])
    shutil.copy(world["folder"] / "lending.db", tmp_path / "lending.db")
    before = data_signature(cfg)
    stat = (tmp_path / "lending.db").stat()
    os.utime(tmp_path / "lending.db", ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000_000))
    assert data_signature(cfg) != before


# --- Overview numbers ----------------------------------------------------------------

def test_overview_kpis_add_up(world):
    data, cfg = world["data"], world["cfg"]
    kpis = overview_kpis(data, cfg)
    borrowers = data.borrowers
    assert kpis["borrowers_scored"] == 800
    assert sum(kpis["band_counts"].values()) == 800
    assert kpis["band_counts"]["high"] == (borrowers["band"] == "high").sum()
    assert sum(kpis["band_shares"].values()) == pytest.approx(1.0)
    assert kpis["owed_by_high_band"] == borrowers.loc[borrowers["band"] == "high", "total_owed"].sum()
    assert kpis["messages_classified"] == len(data.messages)
    assert kpis["lenders_ranked"] + kpis["lenders_unranked"] == len(data.lenders)
    assert kpis["lenders_unranked"] >= 1  # the tiny lender
    expected_abusive = data.messages["predicted_class"].isin(["threat", "shaming_third_party"]).mean()
    assert kpis["abusive_message_share"] == pytest.approx(expected_abusive)
    minimum = cfg["dashboard"]["concern_min_abusive_messages"]
    both = borrowers["band"].isin(["medium", "high"]) & (borrowers["abusive_messages"] >= minimum)
    assert kpis["flagged_and_harassed"] == both.sum()
    assert 0 < kpis["flagged_and_harassed"] < 800


# --- Filters ---------------------------------------------------------------------------

def test_filters_return_only_matching_rows(world):
    borrowers = world["data"].borrowers
    assert len(filter_borrowers(borrowers)) == len(borrowers)

    high = filter_borrowers(borrowers, bands=["high"])
    assert len(high) > 0 and set(high["band"]) == {"high"}
    assert len(high) == (borrowers["band"] == "high").sum()

    region = borrowers["region"].iloc[0]
    in_region = filter_borrowers(borrowers, regions=[region])
    assert set(in_region["region"]) == {region}
    assert len(in_region) == (borrowers["region"] == region).sum()

    combined = filter_borrowers(borrowers, bands=["medium", "high"], min_score=40, min_open_lenders=3,
                                min_abusive_messages=1)
    assert len(combined) > 0
    assert combined["band"].isin(["medium", "high"]).all()
    assert (combined["score"] >= 40).all()
    assert (combined["open_lenders"] >= 3).all()
    assert (combined["abusive_messages"] >= 1).all()
    expected = borrowers[borrowers["band"].isin(["medium", "high"]) & (borrowers["score"] >= 40)
                         & (borrowers["open_lenders"] >= 3) & (borrowers["abusive_messages"] >= 1)]
    assert len(combined) == len(expected)


def test_id_search_is_a_case_insensitive_part_of_the_id(world):
    borrowers = world["data"].borrowers
    found = filter_borrowers(borrowers, id_search="b0001")
    assert len(found) == borrowers["borrower_id"].str.startswith("B0001").sum()
    assert found["borrower_id"].str.contains("B0001").all()
    assert len(filter_borrowers(borrowers, id_search="  B00007 ")) == 1
    assert filter_borrowers(borrowers, id_search="nobody").empty


def test_paging(world):
    borrowers = world["data"].borrowers
    assert page_count(0, 25) == 1
    assert page_count(51, 25) == 3
    assert list(page_slice(borrowers, 2, 25)["borrower_id"]) == list(borrowers["borrower_id"].iloc[25:50])
    assert len(page_slice(borrowers, 999, 25)) == len(borrowers) - 25 * (page_count(len(borrowers), 25) - 1)


# --- Borrower detail --------------------------------------------------------------------

def test_borrower_detail_loans_sum_to_the_scored_total_owed(world):
    data, cfg = world["data"], world["cfg"]
    for borrower_id in data.borrowers["borrower_id"].head(30):
        detail = borrower_detail(data, borrower_id, cfg)
        assert detail["loans"]["owed"].sum() == detail["row"]["total_owed"]
        assert detail["points"]["points"].sum() == pytest.approx(detail["row"]["score"], abs=0.11)
        assert len(detail["timeline"]) == len(detail["loans"])
        assert detail["explanation"]


def test_borrower_detail_messages_belong_to_the_borrower_and_carry_classes(world):
    data, cfg = world["data"], world["cfg"]
    busiest = data.messages["borrower_id"].value_counts().index[0]
    messages = borrower_detail(data, busiest, cfg)["messages"]
    assert len(messages) == (data.messages["borrower_id"] == busiest).sum()
    assert (messages["borrower_id"] == busiest).all()
    assert messages["predicted_class"].isin(MESSAGE_CLASSES).all()
    assert messages["sent_at"].is_monotonic_increasing


def test_unknown_borrower_raises(world):
    with pytest.raises(KeyError):
        borrower_detail(world["data"], "B99999", world["cfg"])


def test_late_night_and_third_party_flags_follow_config_and_recipient(world):
    messages = world["data"].messages
    window = world["cfg"]["generator"]["late_night"]
    hours = messages["sent_at"].str.slice(11, 13).astype(int)
    expected_late = (hours >= window["start_hour"]) | (hours < window["end_hour"])
    assert (messages["late_night"] == expected_late).all()
    assert messages["late_night"].any() and not messages["late_night"].all()
    assert (messages["third_party"] == (messages["recipient_type"] == "third_party")).all()
    assert messages["third_party"].any()

    borrower = messages.loc[messages["third_party"], "borrower_id"].iloc[0]
    detail = borrower_detail(world["data"], borrower, world["cfg"])["messages"]
    assert (detail["third_party"] == (detail["recipient_type"] == "third_party")).all()


# --- Lender detail -----------------------------------------------------------------------

def test_lender_detail_examples_are_deterministic_and_from_the_right_classes(world):
    data, cfg = world["data"], world["cfg"]
    busiest = data.lenders.sort_values("n_messages", ascending=False)["lender_id"].iloc[0]
    first = lender_detail(data, busiest, cfg)
    second = lender_detail(data, busiest, cfg)
    assert set(first["examples"]) == {"threat", "shaming_third_party"}
    limit = cfg["dashboard"]["example_messages_per_class"]
    own_ids = set(data.messages.loc[data.messages["lender_id"] == busiest, "message_id"])
    for name, examples in first["examples"].items():
        pd.testing.assert_frame_equal(examples, second["examples"][name])
        assert 0 < len(examples) <= limit
        assert (examples["predicted_class"] == name).all()
        assert set(examples["message_id"]) <= own_ids
    assert first["sentence"].startswith(first["row"]["name"])


def test_lender_examples_change_with_the_seed(world):
    data, cfg = world["data"], copy.deepcopy(world["cfg"])
    busiest = data.lenders.sort_values("n_messages", ascending=False)["lender_id"].iloc[0]
    before = lender_detail(data, busiest, cfg)["examples"]["threat"]["message_id"].tolist()
    cfg["dashboard"]["example_seed"] += 1
    after = lender_detail(data, busiest, cfg)["examples"]["threat"]["message_id"].tolist()
    assert before != after  # the seed really drives the choice


# --- Exports ---------------------------------------------------------------------------------

def _read_export(content: bytes) -> tuple[str, pd.DataFrame]:
    text = content.decode("utf-8")
    return text.splitlines()[0], pd.read_csv(io.StringIO(text), comment="#")


def test_flagged_borrowers_csv(world):
    data = world["data"]
    flagged = filter_borrowers(data.borrowers, bands=["medium", "high"])
    first_line, frame = _read_export(flagged_borrowers_csv(flagged, data.notice))
    assert first_line.startswith("# SYNTHETIC DATA")
    assert REVIEW_LINE in first_line
    assert list(frame.columns) == list(BORROWER_EXPORT_COLUMNS.values())
    assert len(frame) == len(flagged)
    assert set(frame["band"]) <= {"medium", "high"}
    assert all(c == c.lower() and " " not in c for c in frame.columns)


def test_lender_comparison_csv(world):
    data = world["data"]
    first_line, frame = _read_export(lender_comparison_csv(data.lenders, data.classifier, data.notice))
    assert first_line.startswith("# SYNTHETIC DATA")
    assert list(frame.columns) == list(LENDER_EXPORT_COLUMNS.values()) + ["labels_from_classifier",
                                                                          "share_of_labels_checked_by_a_person"]
    assert (frame["share_of_labels_checked_by_a_person"] == 0).all()
    assert len(frame) == len(data.lenders)
    assert (frame["labels_from_classifier"] == "local").all()
    assert frame["rank"].isna().sum() == data.lenders["rank"].isna().sum()


# --- About page data and config ----------------------------------------------------------------

def test_signal_weights_come_from_the_config(world):
    cfg = copy.deepcopy(world["cfg"])
    cfg["risk"]["weights"]["arrears"] = 21
    cfg["risk"]["weights"]["cycling"] = 14
    table = signal_weights(cfg).set_index("Signal")
    assert table.loc["Arrears", "Weight"] == 21
    assert table["Weight"].sum() == 100


@pytest.mark.parametrize("key, value", [
    ("top_n", 0), ("example_messages_per_class", -1), ("table_page_size", 2.5),
    ("concern_min_abusive_messages", "3"), ("top_n", True), ("example_seed", -1),
])
def test_bad_dashboard_settings_are_rejected(key, value):
    broken = copy.deepcopy(load_config())
    broken["dashboard"][key] = value
    with pytest.raises(ConfigError, match=f"dashboard.{key}"):
        validate_config(broken)
