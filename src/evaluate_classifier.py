"""Measure a message classifier against the answer labels (Phase 3).

    python -m src.evaluate_classifier --classifier local

Besides src/evaluate_overlap.py and src/evaluate_lenders.py, this is the only
place that reads ground_truth.db. It reads stored labels from predictions.db
and compares them with the true classes.

  test split   held-out phrasings the classifier never saw. This is the number to report.
  dev split    the messages the local classifier was TRAINED on. Its score is
               in-sample, shown only to expose the gap: a large gap means the
               model memorised the templates instead of learning the classes.

The reserve split is never reported, so nobody is tempted to tune on it.

All data is synthetic, so accuracy is optimistic: real collection messages are
more varied than any set of templates, even held-out ones.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from src.config import MESSAGE_CLASSES, load_config
from src.datasets import DatasetError, evaluation_paths
from src.overlap import DEFAULT_NOTICE, connect_read_only
from src.predictions import check_matches, read_predictions

CAVEAT = ("The data is SYNTHETIC: even the held-out test phrasings come from a small set of templates, "
          "so these numbers are optimistic and accuracy on real messages will be lower.")


def load_message_labels(path: Path) -> pd.DataFrame:
    """message_id, true_class, template_id and split for every message."""
    conn = connect_read_only(path)
    try:
        return pd.read_sql_query("SELECT message_id, true_class, template_id, split FROM gt_messages", conn)
    finally:
        conn.close()


def classification_metrics(y_true: list[str], y_pred: list[str]) -> dict:
    """Per-class precision, recall, F1 and support, macro-F1, accuracy and the confusion matrix."""
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=list(MESSAGE_CLASSES), zero_division=0)
    per_class = pd.DataFrame(
        {"precision": precision, "recall": recall, "f1": f1, "support": support}, index=list(MESSAGE_CLASSES))
    matrix = pd.DataFrame(
        confusion_matrix(y_true, y_pred, labels=list(MESSAGE_CLASSES)),
        index=list(MESSAGE_CLASSES), columns=list(MESSAGE_CLASSES))
    correct = sum(t == p for t, p in zip(y_true, y_pred))
    return {
        "per_class": per_class,
        "macro_f1": float(f1.mean()),
        "accuracy": correct / len(y_true) if len(y_true) else 0.0,
        "confusion": matrix,
        "n": len(y_true),
    }


def joined(predictions: pd.DataFrame, truth: pd.DataFrame, texts: pd.DataFrame) -> pd.DataFrame:
    """Predictions with their true class, split, template and text."""
    return (truth.merge(predictions[["message_id", "predicted_class", "confidence"]], on="message_id", how="left")
            .merge(texts, on="message_id", how="left"))


def format_metrics(title: str, metrics: dict, missing: int) -> list[str]:
    short = {"normal": "normal", "firm_pressure": "firm", "threat": "threat", "shaming_third_party": "shaming"}
    lines = [title, f"  messages: {metrics['n']:,}" + (f"   (+{missing:,} with no label, left out)" if missing else "")]
    lines.append(f"  {'class':<22}{'precision':>10}{'recall':>8}{'F1':>8}{'support':>9}")
    for name, row in metrics["per_class"].iterrows():
        lines.append(f"  {name:<22}{row['precision']:>10.3f}{row['recall']:>8.3f}{row['f1']:>8.3f}"
                     f"{int(row['support']):>9,}")
    lines.append(f"  macro-F1 {metrics['macro_f1']:.3f}   accuracy {metrics['accuracy']:.3f}")
    lines.append("  confusion matrix (rows = true class, columns = predicted):")
    lines.append("  " + " " * 22 + "".join(f"{short[c]:>9}" for c in MESSAGE_CLASSES))
    for name, row in metrics["confusion"].iterrows():
        lines.append(f"  {name:<22}" + "".join(f"{int(v):>9,}" for v in row))
    return lines


def report(predictions: pd.DataFrame, truth: pd.DataFrame, texts: pd.DataFrame, classifier: str,
           n_confused: int = 10) -> str:
    data = joined(predictions, truth, texts)
    lines: list[str] = []
    results = {}
    for split, title in (("test", "TEST split (held-out phrasings, never trained on) - the number to report"),
                         ("dev", "DEV split (the local model was trained on these: in-sample, for the gap only)")):
        rows = data[data["split"] == split]
        labelled = rows.dropna(subset=["predicted_class"])
        metrics = classification_metrics(labelled["true_class"].tolist(), labelled["predicted_class"].tolist())
        results[split] = metrics
        lines += format_metrics(title, metrics, len(rows) - len(labelled)) + [""]

    if results["test"]["n"] and results["dev"]["n"]:
        gap = results["dev"]["macro_f1"] - results["test"]["macro_f1"]
        lines.append(f"Gap: dev macro-F1 minus test macro-F1 = {gap:+.3f}"
                     + ("  (large: the model leans on the training templates)" if gap > 0.10 else ""))
        lines.append("")

    test_rows = data[(data["split"] == "test") & data["predicted_class"].notna()]
    wrong = test_rows[test_rows["predicted_class"] != test_rows["true_class"]]
    wrong = wrong.sort_values(["confidence", "message_id"], ascending=[False, True]).head(n_confused)
    lines.append(f"Most confidently wrong test messages ({len(wrong)} shown, "
                 f"{int((test_rows['predicted_class'] != test_rows['true_class']).sum())} wrong in total):")
    for r in wrong.itertuples(index=False):
        confidence = "" if pd.isna(r.confidence) else f" ({r.confidence:.0%})"
        lines.append(f"  {r.message_id}  true {r.true_class}, predicted {r.predicted_class}{confidence}, "
                     f"template {r.template_id}")
        lines.append(f"    \"{r.text}\"")
    lines += ["", CAVEAT]
    return "\n".join([f"Classifier: {classifier}", ""] + lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a message classifier against the answer labels.")
    parser.add_argument("--classifier", choices=("local", "gemini"), default="local")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--dataset", help="Dataset to evaluate (default: the active dataset).")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    try:
        dataset, message = evaluation_paths(cfg, args.dataset)
    except DatasetError as error:
        print(error)
        return 1
    if dataset is None:
        print(message)
        return 0
    paths = {"lending_db": dataset.lending_db, "ground_truth_db": dataset.ground_truth_db,
             "predictions_db": dataset.predictions_db}
    for path in paths.values():
        if not path.exists():
            print(f"{path} not found. Run python -m src.generate_data, then "
                  f"python -m src.classify_messages --classifier {args.classifier}")
            return 1

    lending_conn = connect_read_only(paths["lending_db"])
    predictions_conn = connect_read_only(paths["predictions_db"])
    try:
        check_matches(predictions_conn, lending_conn)
        notice = dict(lending_conn.execute("SELECT key, value FROM meta")).get("notice", DEFAULT_NOTICE)
        texts = pd.read_sql_query("SELECT message_id, text FROM messages", lending_conn)
        predictions = read_predictions(predictions_conn, args.classifier)
    finally:
        lending_conn.close()
        predictions_conn.close()
    if predictions.empty:
        print(f"No '{args.classifier}' labels stored yet. "
              f"Run: python -m src.classify_messages --classifier {args.classifier}")
        return 1

    print(notice)
    print(report(predictions, load_message_labels(paths["ground_truth_db"]), texts, args.classifier))
    return 0


if __name__ == "__main__":
    sys.exit(main())
