"""Checks on the dataset actually built into the data folder.

The other tests build fresh small worlds. These look at the real files you will
use (data/lending.db and data/ground_truth.db), so a broken or stale build is
caught. They are skipped until you have built the dataset:

    python -m src.generate_data
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from src import db
from src.config import MESSAGE_CLASSES, load_config, resolve_path
from src.generate_data import is_holdout_template


@pytest.fixture(scope="module")
def built():
    cfg = load_config()
    lending, truth, manifest = (resolve_path(cfg, key) for key in ("lending_db", "ground_truth_db", "manifest"))
    if not (lending.exists() and truth.exists() and manifest.exists()):
        pytest.skip("Dataset not built yet. Run: python -m src.generate_data")
    lending_conn = sqlite3.connect(str(lending))
    truth_conn = sqlite3.connect(str(truth))
    yield {
        "cfg": cfg,
        "lending": lending_conn,
        "truth": truth_conn,
        "manifest": json.loads(manifest.read_text(encoding="utf-8")),
    }
    lending_conn.close()
    truth_conn.close()


def test_fingerprints_match_the_manifest(built):
    assert db.content_hash(built["lending"]) == built["manifest"]["lending_db_content_hash"]
    assert db.content_hash(built["truth"]) == built["manifest"]["ground_truth_db_content_hash"]


def test_no_broken_references(built):
    built["lending"].execute("PRAGMA foreign_keys = ON")
    assert built["lending"].execute("PRAGMA foreign_key_check").fetchall() == []


def test_dataset_is_marked_synthetic(built):
    meta = dict(built["lending"].execute("SELECT key, value FROM meta"))
    assert meta["synthetic"] == "true"
    assert "SYNTHETIC" in meta["notice"]


def test_lending_db_has_no_answer_labels_in_any_table(built):
    forbidden = {"true_class", "profile_type", "behaviour", "split", "template_id"}
    for table in db.table_names(built["lending"]):
        assert not table.startswith("gt_")
        columns = {row[1] for row in built["lending"].execute(f"PRAGMA table_info({table})")}
        assert not (columns & forbidden)


def test_both_databases_describe_the_same_messages_and_borrowers(built):
    lending_messages = {r[0] for r in built["lending"].execute("SELECT message_id FROM messages")}
    truth_messages = {r[0] for r in built["truth"].execute("SELECT message_id FROM gt_messages")}
    assert lending_messages == truth_messages
    lending_borrowers = {r[0] for r in built["lending"].execute("SELECT borrower_id FROM borrowers")}
    truth_borrowers = {r[0] for r in built["truth"].execute("SELECT borrower_id FROM gt_borrowers")}
    assert lending_borrowers == truth_borrowers


def test_test_set_matches_the_manifest_and_uses_only_held_out_phrasings(built):
    rows = built["truth"].execute("SELECT true_class, template_id, split FROM gt_messages").fetchall()
    by_class = {c: sum(1 for cls, _, split in rows if split == "test" and cls == c) for c in MESSAGE_CLASSES}
    assert by_class == built["manifest"]["test_set_by_class"]
    for _, template_id, split in rows:
        assert is_holdout_template(template_id) == (split != "dev")


def test_default_build_has_a_full_balanced_test_set(built):
    cfg = built["cfg"]
    n_borrowers = built["lending"].execute("SELECT COUNT(*) FROM borrowers").fetchone()[0]
    if n_borrowers != cfg["generator"]["n_borrowers"]:
        pytest.skip("Dataset was built with a different number of borrowers than the config.")
    expected = cfg["generator"]["test_set_size"] // len(MESSAGE_CLASSES)
    assert built["manifest"]["test_set_by_class"] == {c: expected for c in MESSAGE_CLASSES}


def test_tiny_lender_has_too_few_messages_to_rank(built):
    minimum = built["cfg"]["generator"]["min_lender_messages"]
    rows = built["lending"].execute(
        """SELECT l.name, (SELECT COUNT(*) FROM messages m WHERE m.lender_id = l.lender_id)
           FROM lenders l WHERE l.size_category = 'micro'"""
    ).fetchall()
    assert rows
    for name, volume in rows:
        assert volume < minimum, f"{name} has {volume} messages"
