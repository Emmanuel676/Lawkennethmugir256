"""Measure how well the risk score finds the borrowers it should (Phase 2).

This is the ONLY module allowed to read data/ground_truth.db. The scoring code
(src/overlap.py) never sees the answer labels; here they are used only to count
hits and misses after scoring is done. Thresholds must not be tuned on these
results.

A borrower counts as "flagged" when their band is medium or high, and "should be
flagged" when their true profile is one of evaluation.positive_profiles in
config.yaml.

All data is synthetic, so these numbers are optimistic: the profiles were
generated to be separable, and real borrowers will be messier.

Run it:  python -m src.evaluate_overlap
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.config import PROFILES, load_config
from src.datasets import DatasetError, evaluation_paths
from src.overlap import connect_read_only, score_borrowers

FLAGGED_BANDS = ("medium", "high")


def load_truth(path: Path) -> pd.DataFrame:
    """Read the borrower profile labels from ground_truth.db."""
    conn = connect_read_only(path)
    try:
        return pd.read_sql_query("SELECT borrower_id, profile_type FROM gt_borrowers", conn)
    finally:
        conn.close()


def evaluate(scores: pd.DataFrame, truth: pd.DataFrame, cfg: dict) -> dict:
    """Compare bands with the true profiles.

    Returns precision, recall, true_positives, false_positives, missed,
    true_negatives, n_scored and per_profile (a DataFrame: n, share in each band,
    share flagged, share placed in medium by the cycling rule, median score).
    """
    positives = set(cfg["evaluation"]["positive_profiles"])
    columns = ["borrower_id", "score", "band", "band_forced_by_cycling"]
    merged = scores[columns].merge(
        truth[["borrower_id", "profile_type"]], on="borrower_id", how="left", validate="one_to_one")
    unlabelled = merged.loc[merged["profile_type"].isna(), "borrower_id"]
    if len(unlabelled):
        raise ValueError(
            f"no ground-truth label for {len(unlabelled)} scored borrower(s), e.g. {list(unlabelled[:5])}")

    flagged = merged["band"].isin(FLAGGED_BANDS)
    should_flag = merged["profile_type"].isin(positives)
    tp = int((flagged & should_flag).sum())
    fp = int((flagged & ~should_flag).sum())
    missed = int((~flagged & should_flag).sum())
    tn = int((~flagged & ~should_flag).sum())

    rows = []
    present = list(merged["profile_type"].unique())
    order = [p for p in PROFILES if p in present] + sorted(p for p in present if p not in PROFILES)
    for profile in order:
        group = merged[merged["profile_type"] == profile]
        rows.append({
            "profile": profile,
            "should_flag": profile in positives,
            "n": len(group),
            "share_high": float((group["band"] == "high").mean()),
            "share_medium": float((group["band"] == "medium").mean()),
            "share_low": float((group["band"] == "low").mean()),
            "share_flagged": float(group["band"].isin(FLAGGED_BANDS).mean()),
            "share_forced_by_cycling": float(group["band_forced_by_cycling"].mean()),
            "median_score": float(group["score"].median()),
        })

    return {
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + missed) if tp + missed else 0.0,
        "true_positives": tp,
        "false_positives": fp,
        "missed": missed,
        "true_negatives": tn,
        "n_scored": len(merged),
        "per_profile": pd.DataFrame(rows),
    }


def format_report(result: dict, cfg: dict) -> str:
    """The evaluation as a plain-text table."""
    lines = [
        f"Borrowers scored: {result['n_scored']:,}",
        f"Flagged = band medium or high. Should be flagged = profile in {cfg['evaluation']['positive_profiles']}.",
        "",
        f"{'profile':<12}{'role':<10}{'n':>6}{'high':>8}{'medium':>8}{'low':>8}"
        f"{'flagged':>9}{'forced*':>9}{'median':>8}",
    ]
    for row in result["per_profile"].itertuples(index=False):
        role = "positive" if row.should_flag else "negative"
        lines.append(
            f"{row.profile:<12}{role:<10}{row.n:>6,}{row.share_high:>8.0%}{row.share_medium:>8.0%}"
            f"{row.share_low:>8.0%}{row.share_flagged:>9.0%}{row.share_forced_by_cycling:>9.0%}"
            f"{row.median_score:>8.1f}"
        )
    lines += [
        "* forced = placed in medium only because of the repeated-cycling rule.",
        "",
        f"True positives  {result['true_positives']:>6,}   (flagged, should be)",
        f"False positives {result['false_positives']:>6,}   (flagged, should not be)",
        f"Missed          {result['missed']:>6,}   (not flagged, should be)",
        f"True negatives  {result['true_negatives']:>6,}",
        f"Precision {result['precision']:.1%}   Recall {result['recall']:.1%}",
        "",
        "The data is SYNTHETIC: the profiles were generated to be separable, so these numbers are "
        "optimistic and real-world accuracy will be lower.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the borrower risk score against the answer labels.")
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
    lending_path, truth_path = dataset.lending_db, dataset.ground_truth_db
    for path in (lending_path, truth_path):
        if not path.exists():
            print(f"{path} not found. Build the dataset first: python -m src.generate_data")
            return 1

    conn = connect_read_only(lending_path)
    try:
        scores = score_borrowers(conn, cfg)
    finally:
        conn.close()
    print(format_report(evaluate(scores, load_truth(truth_path), cfg), cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
