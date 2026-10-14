"""People check the classifier's labels on real data (Phase 5.1). No Streamlit, no network.

The local classifier is trained on synthetic text, so on real messages its labels are
unreliable until a person has checked a sample. This module is everything behind the
Review page (pages/6_Review.py):

  next_batch()        messages to review next. kind 'random' is a seeded, uniform random
                      sample of messages nobody has reviewed yet: the UNBIASED sample used
                      to measure accuracy. kind 'hard' is half the lowest-confidence messages
                      and half spread across lenders and predicted classes: chosen to help
                      training, so it says nothing fair about accuracy.
  save_label()        store one human label (a skipped message is simply not stored).
  progress()          how many messages are reviewed, per class and per batch.
  measured_accuracy() the current model's labels against the human labels of the RANDOM
                      batch only, with Wilson intervals and a plain sentence.
  effective_labels()  one label per message: the human label where there is one, else the model's.
  retrain()           train a model for THIS dataset on its human labels (plus, if configured,
                      the demo's dev messages at a lower weight), cross-validate it on the human
                      labels only, save it in the dataset's folder and re-label the dataset.

Reads lending.db and predictions.db of the dataset only (and, for retraining, the demo's
dev training examples through src/training_data.py, the one door for those).
Human labels are NOT answer labels: they live in the dataset's predictions.db.
Nothing here prints or logs message text. Real data is confidential.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold

from src.classify_local import build_pipeline, model_id
from src.classify_messages import (classify_dataset, dataset_model_info, dataset_model_path, lender_brands,
                                   save_dataset_model, saved_model_note)
from src.config import MESSAGE_CLASSES
from src.datasets import DEMO, DatasetPaths, get_dataset_paths
from src.lender_comparison import wilson_interval
from src.overlap import connect_read_only
from src.predictions import (BATCHES, HUMAN_COLUMNS, apply_human_labels, now_utc, open_predictions,
                             read_human_labels, read_predictions)
from src.training_data import labels_path, load_dev_examples, training_data_available

KINDS = BATCHES
MAX_REVIEWER_LENGTH = 20
MAX_NOTE_LENGTH = 300


class ReviewError(ValueError):
    """A review action was refused. The message says why in plain words (it never contains message text)."""


# --- Reading ------------------------------------------------------------------------------------

def _messages(paths: DatasetPaths) -> pd.DataFrame:
    conn = connect_read_only(paths.lending_db)
    try:
        return pd.read_sql_query("SELECT message_id, lender_id, text FROM messages ORDER BY message_id", conn)
    finally:
        conn.close()


def _read_predictions_db(paths: DatasetPaths, classifier: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(model labels of one classifier, human labels). Empty frames when predictions.db does not exist yet."""
    if not paths.predictions_db.exists():
        return (pd.DataFrame(columns=["message_id", "classifier", "model", "predicted_class", "confidence",
                                      "created_at"]),
                pd.DataFrame(columns=HUMAN_COLUMNS))
    conn = connect_read_only(paths.predictions_db)
    try:
        return read_predictions(conn, classifier), read_human_labels(conn)
    finally:
        conn.close()


def human_labels(paths: DatasetPaths) -> pd.DataFrame:
    return _read_predictions_db(paths, "local")[1]


def effective_labels(paths: DatasetPaths, classifier: str = "local") -> pd.DataFrame:
    """One row per labelled message: message_id, label, source ('human' or the classifier). Human labels win."""
    labels, human = _read_predictions_db(paths, classifier)
    merged = apply_human_labels(labels, human, classifier)
    return merged.rename(columns={"predicted_class": "label"})[["message_id", "label", "source"]]


# --- Choosing what to review ---------------------------------------------------------------------

def next_batch(paths: DatasetPaths, kind: str, n: int, seed: int, classifier: str = "local") -> list[str]:
    """Message ids to review next, never ones already reviewed. Same seed and same state = same batch."""
    if kind not in KINDS:
        raise ReviewError(f"Unknown batch kind: use one of {', '.join(KINDS)}.")
    n = int(n)
    if n < 1:
        raise ReviewError("The batch size must be 1 or more.")
    messages = _messages(paths)
    labels, human = _read_predictions_db(paths, classifier)
    pool = messages[~messages["message_id"].isin(set(human["message_id"]))].reset_index(drop=True)
    if pool.empty:
        return []
    rng = np.random.default_rng(int(seed))

    if kind == "random":
        picked = rng.choice(len(pool), size=min(n, len(pool)), replace=False)
        return pool["message_id"].iloc[picked].tolist()

    pool = pool.merge(labels[["message_id", "predicted_class", "confidence"]], on="message_id", how="inner")
    if pool.empty:
        raise ReviewError("The messages have no model labels yet, so hard cases cannot be chosen. "
                          "Label them first (Data page, or python -m src.classify_messages).")
    n = min(n, len(pool))
    n_low = (n + 1) // 2
    lowest = pool.sort_values(["confidence", "message_id"], kind="mergesort").head(n_low)
    rest = pool[~pool["message_id"].isin(set(lowest["message_id"]))]
    groups = [group["message_id"].tolist() for _, group in rest.groupby(["lender_id", "predicted_class"], sort=True)]
    for group in groups:
        rng.shuffle(group)
    order = rng.permutation(len(groups)).tolist()
    spread: list[str] = []
    while len(spread) < n - n_low and any(groups[i] for i in order):
        for i in order:
            if groups[i] and len(spread) < n - n_low:
                spread.append(groups[i].pop())
    batch = lowest["message_id"].tolist() + spread
    return [batch[i] for i in rng.permutation(len(batch))]


def message_for_review(paths: DatasetPaths, message_id: str, classifier: str = "local") -> dict:
    """The (already redacted) text of one message, its lender name and the model's label, for the Review page."""
    conn = connect_read_only(paths.lending_db)
    try:
        row = conn.execute(
            "SELECT m.message_id, m.text, m.sent_at, m.recipient_type, l.name FROM messages m "
            "JOIN lenders l ON l.lender_id = m.lender_id WHERE m.message_id = ?", (message_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ReviewError("That message is not in this dataset.")
    labels, _ = _read_predictions_db(paths, classifier)
    own = labels[labels["message_id"] == message_id]
    return {"message_id": row[0], "text": row[1], "sent_at": row[2], "recipient_type": row[3], "lender": row[4],
            "model_label": own["predicted_class"].iloc[0] if len(own) else None,
            "model_confidence": float(own["confidence"].iloc[0]) if len(own) and pd.notna(own["confidence"].iloc[0])
            else None}


# --- Saving ------------------------------------------------------------------------------------------

def clean_reviewer(reviewer: str | None) -> str | None:
    """Initials or a short code. Optional. Never needs to be a name."""
    value = (reviewer or "").strip()
    if not value:
        return None
    if len(value) > MAX_REVIEWER_LENGTH:
        raise ReviewError(f"Reviewer: use initials or a short code (at most {MAX_REVIEWER_LENGTH} characters).")
    return value


def save_label(paths: DatasetPaths, message_id: str, label: str, batch: str, reviewer: str | None = None,
               note: str | None = None, reviewed_at: str | None = None) -> None:
    """Store (or replace) one human label. A message the reviewer skips is never passed here."""
    if label not in MESSAGE_CLASSES:
        raise ReviewError(f"The label must be one of: {', '.join(MESSAGE_CLASSES)}.")
    if batch not in BATCHES:
        raise ReviewError(f"The batch must be one of: {', '.join(BATCHES)}.")
    reviewer = clean_reviewer(reviewer)
    note = (note or "").strip()[:MAX_NOTE_LENGTH] or None
    lending = connect_read_only(paths.lending_db)
    try:
        if lending.execute("SELECT 1 FROM messages WHERE message_id = ?", (message_id,)).fetchone() is None:
            raise ReviewError("That message is not in this dataset.")
        conn = open_predictions(paths.predictions_db, lending)  # creates the file or adds the table if needed
    finally:
        lending.close()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO human_labels (message_id, label, batch, reviewer, reviewed_at, note) "
                "VALUES (?, ?, ?, ?, ?, ?)", (message_id, label, batch, reviewer, reviewed_at or now_utc(), note))
    finally:
        conn.close()


def progress(paths: DatasetPaths) -> dict:
    """Counts: messages, reviewed, per class, per batch, and a batch-by-class table."""
    conn = connect_read_only(paths.lending_db)
    try:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    finally:
        conn.close()
    human = human_labels(paths)
    table = (pd.crosstab(human["batch"], human["label"]).reindex(index=list(BATCHES), columns=list(MESSAGE_CLASSES),
                                                                 fill_value=0)
             if len(human) else pd.DataFrame(0, index=list(BATCHES), columns=list(MESSAGE_CLASSES)))
    return {
        "messages": int(total),
        "reviewed": int(len(human)),
        "share_reviewed": len(human) / total if total else 0.0,
        "per_class": {c: int((human["label"] == c).sum()) for c in MESSAGE_CLASSES},
        "per_batch": {b: int((human["batch"] == b).sum()) for b in BATCHES},
        "table": table.astype(int),
    }


def reviewed_labels_frame(paths: DatasetPaths, classifier: str = "local") -> pd.DataFrame:
    """Every human label with the model's current label and the (already redacted) message text, for export."""
    labels, human = _read_predictions_db(paths, classifier)
    if human.empty:
        return pd.DataFrame(columns=HUMAN_COLUMNS + ["model_label", "text"])
    messages = _messages(paths)[["message_id", "text"]]
    out = (human.merge(labels[["message_id", "predicted_class"]], on="message_id", how="left")
           .rename(columns={"predicted_class": "model_label"})
           .merge(messages, on="message_id", how="left"))
    return out[HUMAN_COLUMNS + ["model_label", "text"]].sort_values("message_id").reset_index(drop=True)


def reviewed_labels_csv(paths: DatasetPaths, notice: str) -> bytes:
    """The export with the dataset notice as a first '#' line (read back with pandas.read_csv(..., comment='#'))."""
    header = (f"# {notice} Human review labels: a person's judgement, not answer labels. "
              "Message text is stored as imported (redacted if redaction was on).\n")
    return (header + reviewed_labels_frame(paths).to_csv(index=False, lineterminator="\n")).encode("utf-8")


# --- Measuring the current model ------------------------------------------------------------------------

def _recall_rows(truth: list[str], predicted: list[str], confidence: float) -> pd.DataFrame:
    rows = []
    for name in MESSAGE_CLASSES:
        support = sum(t == name for t in truth)
        hit = sum(t == name and p == name for t, p in zip(truth, predicted))
        low, high = wilson_interval(hit, support, confidence) if support else (math.nan, math.nan)
        rows.append({"class": name, "checked": support, "model_right": hit,
                     "recall": hit / support if support else math.nan, "low": low, "high": high})
    return pd.DataFrame(rows)


def measured_accuracy(paths: DatasetPaths, cfg: dict, classifier: str = "local") -> dict:
    """The CURRENT model labels against human labels from the RANDOM batch only.

    Returns ok, n, accuracy, low, high, macro_f1, per_class (recall with Wilson intervals),
    small (True below classifier.review.small_sample_warning) and a plain sentence.
    Refuses (ok False) below classifier.review.min_for_accuracy messages, and says why.
    """
    review = cfg["classifier"]["review"]
    confidence, minimum = float(review["confidence"]), int(review["min_for_accuracy"])
    level = f"{confidence:.0%}"
    labels, human = _read_predictions_db(paths, classifier)
    sample = human[human["batch"] == "random"].merge(labels[["message_id", "predicted_class"]], on="message_id",
                                                    how="inner")
    unlabelled = int((human["batch"] == "random").sum()) - len(sample)
    n = len(sample)
    out = {"ok": False, "n": n, "minimum": minimum, "unlabelled": unlabelled, "confidence": confidence}
    if n < minimum:
        low, high = wilson_interval(n // 2, n, confidence) if n else (0.0, 1.0)
        out["sentence"] = (
            f"Only {n} randomly checked message(s) so far. Accuracy is reported from {minimum} on: with fewer, "
            f"the {level} range is too wide to mean anything (for {n} messages and a model right half the time "
            f"it would run from {low:.0%} to {high:.0%}). Review a 'random check' batch to get there.")
        return out
    truth, predicted = sample["label"].tolist(), sample["predicted_class"].tolist()
    right = sum(t == p for t, p in zip(truth, predicted))
    accuracy = right / n
    low, high = wilson_interval(right, n, confidence)
    present = sorted(set(truth) | set(predicted), key=list(MESSAGE_CLASSES).index)
    macro = float(f1_score(truth, predicted, labels=present, average="macro", zero_division=0))
    small = n < int(review["small_sample_warning"])
    sentence = (f"On {n} randomly checked messages the model was right {accuracy:.0%} of the time, "
                f"{level} range {low * 100:.0f}-{high:.0%}. Macro-F1 {macro:.2f} over the {len(present)} class(es) seen "
                "(no simple interval exists for it).")
    if small:
        sentence += (f" This is a small sample (under {review['small_sample_warning']}); per-class figures rest on "
                     "very few messages.")
    out.update(ok=True, right=right, accuracy=accuracy, low=low, high=high, macro_f1=macro, classes_seen=present,
               per_class=_recall_rows(truth, predicted, confidence), small=small, sentence=sentence)
    return out


# --- Retraining ----------------------------------------------------------------------------------------------

@dataclass
class RetrainReport:
    ok: bool
    message: str
    lines: list[str] = field(default_factory=list)
    cv_macro_f1: float | None = None
    cv_per_class: pd.DataFrame | None = None
    n_human: int = 0
    n_demo: int = 0
    labels_changed: int = 0
    shares_before: dict[str, float] = field(default_factory=dict)
    shares_after: dict[str, float] = field(default_factory=dict)
    model_path: str = ""


def missing_for_retrain(human: pd.DataFrame, cfg: dict) -> list[str]:
    """Plain sentences saying what is still missing before retraining is allowed (empty = ready)."""
    review = cfg["classifier"]["review"]
    need_total, need_each = int(review["min_reviewed_to_retrain"]), int(review["min_per_class"])
    missing = []
    if len(human) < need_total:
        missing.append(f"{need_total - len(human)} more human label(s) overall (you have {len(human)}, "
                       f"{need_total} are needed)")
    for name in MESSAGE_CLASSES:
        have = int((human["label"] == name).sum())
        if have < need_each:
            missing.append(f"{need_each - have} more '{name}' label(s) (you have {have}, {need_each} are needed)")
    return missing


def _demo_examples(cfg: dict) -> tuple[pd.DataFrame, list[str]]:
    demo = get_dataset_paths(cfg, DEMO)
    conn = connect_read_only(demo.lending_db)
    try:
        return load_dev_examples(conn, labels_path(cfg)), lender_brands(conn)
    finally:
        conn.close()


def _fit(cfg: dict, brands: list[str], texts: list[str], labels: list[str], weights: list[float]):
    return build_pipeline(cfg, brands).fit(texts, labels, model__sample_weight=np.asarray(weights, dtype=float))


def _shares(labels: pd.DataFrame) -> dict[str, float]:
    n = len(labels)
    return {c: float((labels["predicted_class"] == c).sum() / n) if n else 0.0 for c in MESSAGE_CLASSES}


def retrain(cfg: dict, paths: DatasetPaths) -> RetrainReport:
    """Train this dataset's own model on its human labels; cross-validate; save; re-label the dataset."""
    review = cfg["classifier"]["review"]
    if paths.name == DEMO:
        return RetrainReport(False, "Retraining is for real datasets. The demo has answer labels elsewhere and keeps "
                                    "its demo-trained model, which is never overwritten.")
    labels_before, human = _read_predictions_db(paths, "local")
    missing = missing_for_retrain(human, cfg)
    if missing:
        return RetrainReport(False, "Not enough human labels to retrain yet. Still needed: " + "; ".join(missing) + ".",
                             n_human=len(human))

    texts = _messages(paths)[["message_id", "text"]]
    data = human.merge(texts, on="message_id", how="inner").sort_values("message_id").reset_index(drop=True)
    conn = connect_read_only(paths.lending_db)
    try:
        brands = lender_brands(conn)
    finally:
        conn.close()

    lines: list[str] = []
    demo_texts: list[str] = []
    demo_labels: list[str] = []
    weight = float(review["demo_weight"])
    if review["include_demo_in_retrain"] and weight > 0:
        if training_data_available(cfg):
            examples, demo_brands = _demo_examples(cfg)
            demo_texts, demo_labels = examples["text"].tolist(), examples["label"].tolist()
            brands = sorted(set(brands) | set(demo_brands))
            share = len(demo_texts) * weight / (len(demo_texts) * weight + len(data))
            lines.append(f"Also trained on {len(demo_texts):,} synthetic demo messages at weight {weight} each; "
                         f"together they carry {share:.0%} of the training weight.")
        else:
            note = saved_model_note(cfg)
            known = (f" The saved demo model was trained on {note['n_train']:,} demo messages; it is not changed."
                     if note.get("n_train") else "")
            lines.append("The demo data is not present, so the demo messages were left out and only your human "
                         "labels were used." + known)
    else:
        lines.append("Trained on your human labels only (classifier.review.include_demo_in_retrain is off).")

    # Cross-validation on the human labels only; the demo messages are added to every training fold.
    y = data["label"].to_numpy()
    folds = int(min(review["cv_folds"], pd.Series(y).value_counts().min()))
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=int(review["seed"]))
    predicted = np.empty(len(data), dtype=object)
    for train_index, test_index in splitter.split(data["text"], y):
        model = _fit(cfg, brands, data["text"].iloc[train_index].tolist() + demo_texts,
                     y[train_index].tolist() + demo_labels,
                     [1.0] * len(train_index) + [weight] * len(demo_texts))
        predicted[test_index] = model.predict(data["text"].iloc[test_index].tolist())
    truth = y.tolist()
    cv_macro = float(f1_score(truth, predicted.tolist(), labels=list(MESSAGE_CLASSES), average="macro",
                              zero_division=0))
    per_class = _recall_rows(truth, predicted.tolist(), float(review["confidence"]))
    lines.append(f"Cross-validation ({folds} folds, on your {len(data)} human labels only): macro-F1 {cv_macro:.2f}.")
    for row in per_class.to_dict("records"):
        lines.append(f"  {row['class']}: recall {row['recall']:.0%} on {row['checked']} labelled message(s)")
    if len(data) < int(review["small_sample_warning"]):
        lines.append(f"WARNING: only {len(data)} human labels (under {review['small_sample_warning']}). These figures "
                     "are rough; they can move a lot with a few more labels.")
    lines.append("Human labels include 'hard cases' picked on purpose, so these figures are not the fair accuracy "
                 "on all messages; the random-check box is.")

    final = _fit(cfg, brands, data["text"].tolist() + demo_texts, truth + demo_labels,
                 [1.0] * len(data) + [weight] * len(demo_texts))
    label = (f"dataset-retrained n_human={len(data)} n_demo={len(demo_texts)} demo_weight={weight} "
             f"{model_id(cfg)}")
    path = save_dataset_model(paths, final, {
        "model_id": label, "n_human": len(data), "n_demo": len(demo_texts), "demo_weight": weight,
        "trained_at": now_utc(), "cv_folds": folds, "cv_macro_f1": round(cv_macro, 4),
        "cv_recall": {r["class"]: (None if math.isnan(r["recall"]) else round(r["recall"], 4))
                      for r in per_class.to_dict("records")},
    })

    classify_dataset(cfg, paths, final, "retrained", label)
    labels_after, _ = _read_predictions_db(paths, "local")
    both = labels_before[["message_id", "predicted_class"]].merge(
        labels_after[["message_id", "predicted_class"]], on="message_id", suffixes=("_before", "_after"))
    changed = int((both["predicted_class_before"] != both["predicted_class_after"]).sum())
    before, after = _shares(labels_before), _shares(labels_after)
    lines.append(f"Re-labelled {len(labels_after):,} messages: {changed:,} model label(s) changed. Human labels "
                 "still win where they exist.")
    for name in MESSAGE_CLASSES:
        lines.append(f"  {name}: {before[name]:.1%} -> {after[name]:.1%} of model labels")
    return RetrainReport(True, f"Retrained on {len(data)} human labels and saved as {path.name} in this dataset's "
                               "folder.", lines, cv_macro, per_class, len(data), len(demo_texts), changed,
                         before, after, str(path))


def retrained_model_info(paths: DatasetPaths) -> dict:
    """The note saved with this dataset's own model (empty if it has none)."""
    path = dataset_model_path(paths)
    return dataset_model_info(paths) if path is not None and path.exists() else {}
