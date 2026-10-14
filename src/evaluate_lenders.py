"""Check the lender ranking against each lender's true behaviour (Phase 3).

    python -m src.evaluate_lenders

One of the evaluation modules allowed to read ground_truth.db. It runs the
lender comparison (which never sees the labels) and then compares the ranking
with gt_lenders.behaviour: abusive lenders should rank above borderline ones,
and borderline above clean. It also shows, per lender, the abusive share
according to the classifier next to the true abusive share of its messages,
so classifier error is visible.

All data is synthetic. The lenders were built to differ clearly, so a clean
ordering here is much easier than it would be with real lenders.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.datasets import DatasetError, evaluation_paths
from src.lender_comparison import compare_lenders, load_inputs
from src.overlap import DEFAULT_NOTICE, connect_read_only

BEHAVIOUR_ORDER = ("abusive", "borderline", "clean")


def load_lender_truth(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(lender behaviour, message true classes) from ground_truth.db."""
    conn = connect_read_only(path)
    try:
        behaviour = pd.read_sql_query("SELECT lender_id, behaviour FROM gt_lenders", conn)
        classes = pd.read_sql_query("SELECT message_id, true_class FROM gt_messages", conn)
    finally:
        conn.close()
    return behaviour, classes


def _all_above(table: pd.DataFrame, upper: str, lower: str) -> bool | None:
    """True if every ranked 'upper' lender ranks above every ranked 'lower' lender (None if either is absent)."""
    ranked = table.dropna(subset=["rank"])
    top = ranked.loc[ranked["behaviour"] == upper, "rank"]
    bottom = ranked.loc[ranked["behaviour"] == lower, "rank"]
    if top.empty or bottom.empty:
        return None
    return bool(top.max() < bottom.min())


def evaluate_ranking(table: pd.DataFrame, behaviour: pd.DataFrame, true_shares: pd.DataFrame | None = None) -> dict:
    """Compare a compare_lenders() table with the true lender behaviour."""
    merged = table.merge(behaviour, on="lender_id", how="left")
    if merged["behaviour"].isna().any():
        raise ValueError("no ground-truth behaviour for some lenders: "
                         f"{list(merged.loc[merged['behaviour'].isna(), 'lender_id'])}")
    if true_shares is not None:
        merged = merged.merge(true_shares, on="lender_id", how="left")
    unranked = merged[merged["rank"].isna()]
    return {
        "table": merged,
        "abusive_above_clean": _all_above(merged, "abusive", "clean"),
        "abusive_above_borderline": _all_above(merged, "abusive", "borderline"),
        "borderline_above_clean": _all_above(merged, "borderline", "clean"),
        "unranked": list(zip(unranked["name"], unranked["behaviour"], unranked["n_messages"])),
    }


def true_abusive_shares(messages: pd.DataFrame, classes: pd.DataFrame, abusive_classes: list[str]) -> pd.DataFrame:
    data = messages.merge(classes, on="message_id")
    data["truly_abusive"] = data["true_class"].isin(abusive_classes)
    return data.groupby("lender_id")["truly_abusive"].mean().rename("true_abusive_share").reset_index()


def format_report(result: dict, classifier: str) -> str:
    def verdict(value):
        return "n/a" if value is None else ("YES" if value else "NO")

    lines = [f"Lender ranking vs true behaviour (labels from the '{classifier}' classifier)", "",
             f"{'rank':>4}  {'lender':<29}{'behaviour':<12}{'msgs':>7}{'abusive (model)':>17}{'abusive (true)':>16}"]
    for r in result["table"].itertuples(index=False):
        rank = "-" if pd.isna(r.rank) else str(int(r.rank))
        true_share = getattr(r, "true_abusive_share", float("nan"))
        lines.append(f"{rank:>4}  {r.name:<29}{r.behaviour:<12}{r.n_messages:>7,}{r.abusive_share:>17.1%}"
                     f"{true_share:>16.1%}")
    lines += [
        "",
        f"Every ranked abusive lender above every ranked clean lender:      {verdict(result['abusive_above_clean'])}",
        f"Every ranked abusive lender above every ranked borderline lender: {verdict(result['abusive_above_borderline'])}",
        f"Every ranked borderline lender above every ranked clean lender:   {verdict(result['borderline_above_clean'])}",
    ]
    if result["unranked"]:
        lines.append("Unranked (too few messages): " + ", ".join(
            f"{name} ({behaviour}, {n} messages)" for name, behaviour, n in result["unranked"]))
    lines += ["", "The data is SYNTHETIC and the lenders were built to differ clearly, so this ordering is "
                  "optimistic; real lenders will overlap far more."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the lender ranking against the true lender behaviour.")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--dataset", help="Dataset to evaluate (default: the active dataset).")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    classifier = cfg["classifier"]["primary"]
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
                  f"python -m src.classify_messages --classifier {classifier}")
            return 1

    lending_conn = connect_read_only(paths["lending_db"])
    predictions_conn = connect_read_only(paths["predictions_db"])
    try:
        notice = dict(lending_conn.execute("SELECT key, value FROM meta")).get("notice", DEFAULT_NOTICE)
        messages, labels, lenders = load_inputs(lending_conn, predictions_conn, classifier)
    finally:
        lending_conn.close()
        predictions_conn.close()

    table = compare_lenders(messages, labels, lenders, cfg)
    behaviour, classes = load_lender_truth(paths["ground_truth_db"])
    shares = true_abusive_shares(messages, classes, list(cfg["lender_comparison"]["abusive_classes"]))
    print(notice)
    print(format_report(evaluate_ranking(table, behaviour, shares), classifier))
    return 0


if __name__ == "__main__":
    sys.exit(main())
