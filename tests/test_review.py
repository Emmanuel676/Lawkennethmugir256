"""People checking labels on real data (Phase 5.1): batches, measured accuracy, human labels winning, retraining.

The 'real' dataset here is a small synthetic world imported through the normal import
(so it behaves like field data). Its answer labels are read in THIS test file only, to
play the part of a careful human reviewer; the code under test never sees them.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.classify_messages import DATASET_MODEL_FILE, classify_dataset, dataset_model_path
from src.config import MESSAGE_CLASSES
from src.dashboard_data import load_all
from src.datasets import DEMO, get_dataset_paths, set_active
from src.import_data import TABLES, Upload, import_upload
from src.lender_comparison import load_inputs
from src.predictions import read_human_labels, read_predictions, upsert_predictions, now_utc
from src.review import (ReviewError, effective_labels, measured_accuracy, missing_for_retrain, next_batch, progress,
                        retrain, reviewed_labels_csv, save_label)

from tiny_data import COLUMNS
from worlds import build_classified_world

SLUG = "field-b"


def _upload_from(lending_db: Path) -> Upload:
    """The tables of a lending.db as an Upload, exactly as if they came from five CSV files."""
    conn = sqlite3.connect(str(lending_db))
    try:
        tables = {}
        for table in TABLES:
            frame = pd.read_sql_query(f"SELECT {', '.join(COLUMNS[table])} FROM {table}", conn)
            frame = frame.astype(object).where(frame.notna(), "").astype(str)
            frame["_row"] = range(2, len(frame) + 2)
            tables[table] = frame
    finally:
        conn.close()
    return Upload(kind="csv", tables=tables, sources={t: f"file '{t}.csv'" for t in TABLES})


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """A classified demo (300 borrowers, saved model) and a copy of it imported as a REAL dataset."""
    cfg, _ = build_classified_world(tmp_path_factory.mktemp("review_world"), n_borrowers=300)
    result = import_upload(_upload_from(Path(cfg["paths"]["lending_db"])), cfg, mode="new",
                           permission_confirmed=True, redact=True, dataset_name="Field B", source_description="t")
    assert result.ok, result.message
    conn = sqlite3.connect(cfg["paths"]["ground_truth_db"])
    truth = dict(conn.execute("SELECT message_id, true_class FROM gt_messages"))
    conn.close()
    return cfg, truth


@pytest.fixture
def world(built, tmp_path):
    """A fresh copy of the datasets folder for every test, so tests never see each other's labels."""
    cfg, truth = built
    custom = copy.deepcopy(cfg)
    shutil.copytree(cfg["paths"]["datasets_dir"], tmp_path / "datasets")
    custom["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    custom["paths"]["active_dataset_file"] = str(tmp_path / "active.txt")
    return custom, get_dataset_paths(custom, SLUG), truth


def _model_labels(paths) -> pd.DataFrame:
    conn = sqlite3.connect(str(paths.predictions_db))
    try:
        return read_predictions(conn, "local")
    finally:
        conn.close()


def _label_like_a_reviewer(paths, truth, ids, batch):
    for message_id in ids:
        save_label(paths, message_id, truth[message_id], batch, "AB")


# --- Batches ------------------------------------------------------------------------------------------------

def test_random_batch_is_deterministic_and_seed_dependent(world):
    _, paths, _ = world
    first = next_batch(paths, "random", 30, seed=5)
    assert len(first) == 30 == len(set(first))
    assert next_batch(paths, "random", 30, seed=5) == first
    assert next_batch(paths, "random", 30, seed=6) != first


def test_random_batch_never_includes_reviewed_messages(world):
    _, paths, truth = world
    reviewed = next_batch(paths, "random", 40, seed=1)
    _label_like_a_reviewer(paths, truth, reviewed[:25], "random")
    _label_like_a_reviewer(paths, truth, reviewed[25:], "hard")
    for seed in range(5):
        assert set(next_batch(paths, "random", 200, seed=seed)).isdisjoint(reviewed)
        assert set(next_batch(paths, "hard", 50, seed=seed)).isdisjoint(reviewed)


def test_random_batch_is_a_uniform_sample(world):
    """Over many seeds every message is drawn about equally often (no message or lender is favoured)."""
    _, paths, _ = world
    total = len(_model_labels(paths))
    counts = pd.Series(0, index=_model_labels(paths)["message_id"])
    seeds = 400
    for seed in range(seeds):
        counts[next_batch(paths, "random", 20, seed=seed)] += 1
    expected = seeds * 20 / total
    assert abs(counts.mean() - expected) < 1e-9
    # Lowest-confidence messages are NOT over-drawn by the random batch (the hard batch does that).
    low = _model_labels(paths).nsmallest(total // 10, "confidence")["message_id"]
    assert counts[low].mean() == pytest.approx(expected, rel=0.25)


def test_hard_batch_is_half_lowest_confidence_and_spread_across_lenders(world):
    _, paths, _ = world
    labels = _model_labels(paths)
    batch = next_batch(paths, "hard", 40, seed=3)
    assert batch == next_batch(paths, "hard", 40, seed=3)
    assert len(batch) == 40 == len(set(batch))
    lowest = labels.sort_values(["confidence", "message_id"]).head(20)["message_id"]
    assert set(lowest) <= set(batch)
    messages = sqlite3.connect(str(paths.lending_db))
    lenders = dict(messages.execute("SELECT message_id, lender_id FROM messages"))
    messages.close()
    rest = [m for m in batch if m not in set(lowest)]
    assert len({lenders[m] for m in rest}) >= 5
    assert len(set(labels.set_index("message_id").loc[rest, "predicted_class"])) >= 3


def test_bad_batch_requests_are_refused(world):
    _, paths, _ = world
    with pytest.raises(ReviewError, match="Unknown batch kind"):
        next_batch(paths, "easy", 5, seed=1)
    with pytest.raises(ReviewError, match="1 or more"):
        next_batch(paths, "random", 0, seed=1)


# --- Saving and progress -------------------------------------------------------------------------------------

def test_save_label_progress_and_checks(world):
    _, paths, _ = world
    ids = next_batch(paths, "random", 3, seed=2)
    save_label(paths, ids[0], "threat", "random", " ab ")
    save_label(paths, ids[1], "normal", "hard", None)
    state = progress(paths)
    assert state["reviewed"] == 2
    assert state["per_class"] == {"normal": 1, "firm_pressure": 0, "threat": 1, "shaming_third_party": 0}
    assert state["per_batch"] == {"random": 1, "hard": 1}
    assert int(state["table"].loc["random", "threat"]) == 1
    save_label(paths, ids[0], "firm_pressure", "random", "AB")  # a second look replaces the first
    assert progress(paths)["per_class"]["firm_pressure"] == 1 and progress(paths)["reviewed"] == 2
    with pytest.raises(ReviewError, match="must be one of"):
        save_label(paths, ids[2], "rude", "random")
    with pytest.raises(ReviewError, match="initials or a short code"):
        save_label(paths, ids[2], "normal", "random", "A very long full name of somebody")
    with pytest.raises(ReviewError, match="not in this dataset"):
        save_label(paths, "M-nope", "normal", "random")
    conn = sqlite3.connect(str(paths.predictions_db))
    stored = read_human_labels(conn)
    conn.close()
    assert stored.set_index("message_id").loc[ids[0], "reviewer"] == "AB"


def test_an_old_predictions_file_gets_the_table_added(world):
    _, paths, _ = world
    conn = sqlite3.connect(str(paths.predictions_db))
    conn.execute("DROP TABLE human_labels")
    conn.commit()
    assert read_human_labels(conn).empty  # no table: an empty frame, not an error
    conn.close()
    assert progress(paths)["reviewed"] == 0
    message = next_batch(paths, "random", 1, seed=1)[0]
    save_label(paths, message, "normal", "random")
    assert progress(paths)["reviewed"] == 1
    assert len(_model_labels(paths)) > 0  # the model labels survived the migration


def test_export_has_the_notice_line_and_the_labels(world):
    _, paths, truth = world
    ids = next_batch(paths, "random", 4, seed=9)
    _label_like_a_reviewer(paths, truth, ids, "random")
    raw = reviewed_labels_csv(paths, "REAL DATA notice.").decode("utf-8")
    assert raw.startswith("# REAL DATA notice. Human review labels")
    frame = pd.read_csv(__import__("io").StringIO(raw), comment="#")
    assert sorted(frame["message_id"]) == sorted(ids)
    assert {"label", "batch", "reviewer", "model_label", "text"} <= set(frame.columns)


# --- Measured accuracy -------------------------------------------------------------------------------------------

HAND = [  # (true label given by the person, model label): 7 of 10 right
    ("normal", "normal"), ("normal", "normal"), ("normal", "normal"), ("normal", "normal"),
    ("threat", "threat"), ("threat", "threat"), ("firm_pressure", "firm_pressure"),
    ("normal", "threat"), ("threat", "normal"), ("firm_pressure", "normal"),
]


def _hand_built(paths, cfg):
    ids = sorted(_model_labels(paths)["message_id"])[:len(HAND) + 1]
    conn = sqlite3.connect(str(paths.predictions_db))
    upsert_predictions(conn, [{"message_id": m, "classifier": "local", "model": "hand", "predicted_class": p,
                               "confidence": 0.9, "created_at": now_utc()} for m, (_, p) in zip(ids, HAND)])
    conn.close()
    for message_id, (truth, _) in zip(ids, HAND):
        save_label(paths, message_id, truth, "random")
    # A hard-case label the model got wrong must NOT count toward accuracy.
    save_label(paths, ids[-1], "shaming_third_party", "hard")
    small = copy.deepcopy(cfg)
    small["classifier"]["review"]["min_for_accuracy"] = 10
    return small


def test_measured_accuracy_matches_a_hand_built_case(world):
    cfg, paths, _ = world
    small = _hand_built(paths, cfg)
    result = measured_accuracy(paths, small)
    assert result["ok"] and result["n"] == 10 and result["right"] == 7
    assert result["accuracy"] == pytest.approx(0.7)
    assert (result["low"], result["high"]) == (pytest.approx(0.3968, abs=1e-4), pytest.approx(0.8922, abs=1e-4))
    # Macro-F1 over the three classes seen: normal 8/11, threat 2/3, firm_pressure 2/3.
    assert result["macro_f1"] == pytest.approx((8 / 11 + 2 / 3 + 2 / 3) / 3)
    assert result["sentence"].startswith(
        "On 10 randomly checked messages the model was right 70% of the time, 95% range 40-89%.")
    assert result["small"] and "small sample" in result["sentence"]
    recall = result["per_class"].set_index("class")
    assert recall.loc["normal", "checked"] == 5 and recall.loc["normal", "recall"] == pytest.approx(0.8)
    assert recall.loc["firm_pressure", "recall"] == pytest.approx(0.5)
    assert pd.isna(recall.loc["shaming_third_party", "recall"])  # never checked in the random batch


def test_measured_accuracy_refuses_below_the_minimum(world):
    cfg, paths, _ = world
    _hand_built(paths, cfg)
    result = measured_accuracy(paths, cfg)  # the real config asks for 20
    assert result["ok"] is False and result["n"] == 10
    assert "Only 10 randomly checked message(s) so far" in result["sentence"]
    assert "from 20 on" in result["sentence"] and "too wide" in result["sentence"]
    assert "accuracy" not in result


# --- Human labels win ------------------------------------------------------------------------------------------

def test_effective_labels_prefer_human_labels(world):
    cfg, paths, _ = world
    labels = _model_labels(paths)
    target = labels.iloc[0]
    other = "normal" if target["predicted_class"] != "normal" else "threat"
    save_label(paths, target["message_id"], other, "hard")
    effective = effective_labels(paths).set_index("message_id")
    assert len(effective) == len(labels)
    assert effective.loc[target["message_id"], "label"] == other
    assert effective.loc[target["message_id"], "source"] == "human"
    assert (effective.drop(index=target["message_id"])["source"] == "local").all()


def test_lender_comparison_and_dashboard_use_the_human_labels(world):
    cfg, paths, _ = world
    labels = _model_labels(paths)
    normal = labels[labels["predicted_class"] == "normal"]["message_id"].head(30).tolist()
    for message_id in normal:
        save_label(paths, message_id, "threat", "hard")
    lending, preds = sqlite3.connect(str(paths.lending_db)), sqlite3.connect(str(paths.predictions_db))
    _, used, _ = load_inputs(lending, preds, "local")
    lending.close()
    preds.close()
    assert (used.set_index("message_id").loc[normal, "predicted_class"] == "threat").all()
    set_active(cfg, SLUG)
    data = load_all(cfg)
    assert data.ok
    assert data.human_share == pytest.approx(30 / len(labels))
    abusive = data.messages["predicted_class"].isin(cfg["lender_comparison"]["abusive_classes"]).sum()
    model_abusive = labels["predicted_class"].isin(cfg["lender_comparison"]["abusive_classes"]).sum()
    assert abusive == model_abusive + 30
    assert data.borrowers["abusive_messages"].sum() == abusive  # the harassment summary follows too
    from src.dashboard_data import coverage_sentence
    assert f"{30 / len(labels):.1%} of the labels were checked by a person" in coverage_sentence(data)


# --- Retraining --------------------------------------------------------------------------------------------------

def _enough_labels(paths, truth, per_class=15):
    """Labels for per_class messages of every class, as a careful reviewer would give them."""
    chosen = []
    for name in MESSAGE_CLASSES:
        chosen += sorted(m for m, c in truth.items() if c == name)[:per_class]
    _label_like_a_reviewer(paths, truth, chosen, "hard")
    return chosen


def test_retrain_refuses_with_a_clear_reason_when_too_few(world):
    cfg, paths, truth = world
    some = sorted(m for m, c in truth.items() if c == "normal")[:40]
    some += sorted(m for m, c in truth.items() if c == "threat")[:3]
    _label_like_a_reviewer(paths, truth, some, "random")
    report = retrain(cfg, paths)
    assert not report.ok
    assert report.message.startswith("Not enough human labels to retrain yet.")
    assert "17 more human label(s) overall (you have 43, 60 are needed)" in report.message
    assert "2 more 'threat' label(s) (you have 3, 5 are needed)" in report.message
    assert "5 more 'firm_pressure' label(s)" in report.message
    assert "5 more 'shaming_third_party' label(s)" in report.message
    assert "'normal'" not in report.message
    assert not dataset_model_path(paths).exists()


def test_retrain_on_the_demo_is_refused(world):
    cfg, _, _ = world
    report = retrain(cfg, get_dataset_paths(cfg, DEMO))
    assert not report.ok and "never overwritten" in report.message


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_retrain_saves_a_dataset_model_relabels_and_never_touches_the_demo(world):
    cfg, paths, truth = world
    demo_model = Path(cfg["paths"]["local_model"])
    before_digest, before_mtime = _digest(demo_model), demo_model.stat().st_mtime_ns
    demo_labels_before = _model_labels(get_dataset_paths(cfg, DEMO))
    labels_before = _model_labels(paths)
    _enough_labels(paths, truth)
    assert missing_for_retrain(pd.DataFrame({"label": [truth[m] for m in _enough_labels(paths, truth)]}), cfg) == []

    report = retrain(cfg, paths)
    assert report.ok, report.message
    assert report.n_human == 60 and report.n_demo > 0
    assert Path(report.model_path) == paths.lending_db.parent / DATASET_MODEL_FILE
    assert Path(report.model_path).exists()
    assert _digest(demo_model) == before_digest and demo_model.stat().st_mtime_ns == before_mtime
    pd.testing.assert_frame_equal(_model_labels(get_dataset_paths(cfg, DEMO)), demo_labels_before)

    # Cross-validation is on the human labels only, with the sample size and a small-sample warning.
    assert int(report.cv_per_class["checked"].sum()) == 60
    assert 0 <= report.cv_macro_f1 <= 1
    assert any(line.startswith("WARNING: only 60 human labels") for line in report.lines)
    assert any("carry" in line and "training weight" in line for line in report.lines)
    # Re-labelled: the change count and the class shares are reported and add up.
    after = _model_labels(paths)
    both = labels_before.merge(after, on="message_id", suffixes=("_b", "_a"))
    assert report.labels_changed == int((both["predicted_class_b"] != both["predicted_class_a"]).sum())
    assert sum(report.shares_after.values()) == pytest.approx(1.0)
    assert after["model"].str.startswith("dataset-retrained n_human=60").all()


def test_classify_uses_the_dataset_model_when_it_exists(world):
    cfg, paths, truth = world
    _enough_labels(paths, truth)
    assert retrain(cfg, paths).ok
    conn = sqlite3.connect(str(paths.predictions_db))
    conn.execute("UPDATE message_predictions SET model = 'old'")
    conn.commit()
    conn.close()
    classify_dataset(cfg, paths)
    assert _model_labels(paths)["model"].str.startswith("dataset-retrained").all()
    classify_dataset(cfg, get_dataset_paths(cfg, DEMO))  # the demo keeps the demo-trained model
    assert not _model_labels(get_dataset_paths(cfg, DEMO))["model"].str.startswith("dataset-retrained").any()
    dataset_model_path(paths).unlink()
    classify_dataset(cfg, paths)  # without its own model, the dataset goes back to the demo-trained one
    assert not _model_labels(paths)["model"].str.startswith("dataset-retrained").any()


def test_retrain_without_the_demo_uses_human_labels_only_and_says_so(world):
    cfg, paths, truth = world
    _enough_labels(paths, truth)
    gone = copy.deepcopy(cfg)
    gone["paths"]["ground_truth_db"] = str(Path(cfg["paths"]["ground_truth_db"]).with_name("missing.db"))
    report = retrain(gone, paths)
    assert report.ok, report.message
    assert report.n_demo == 0
    assert any("The demo data is not present" in line and "demo messages; it is not changed" in line
               for line in report.lines)
