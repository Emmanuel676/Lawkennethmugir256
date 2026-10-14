"""Compare lenders by how their collection messages read (Phase 3).

    python -m src.lender_comparison

Reads lending.db and predictions.db only, never the answer labels. The class of
each message comes from the classifier named in classifier.primary (config.yaml),
except where a person has reviewed the message (Phase 5.1): the human label wins.
Model labels are guesses, so a lender's figures are estimates.

Per lender:
  n_messages             messages it sent
  abusive_share          share labelled as one of lender_comparison.abusive_classes
  abusive_low/high       Wilson confidence interval around that share
  threat_share           share labelled threat
  shaming_share          share labelled shaming_third_party
  third_party_share      share sent to someone other than the borrower (recipient_type,
                         a fact of the message, not a classifier guess)
  late_night_share       share sent in the generator.late_night hours
  messages_per_borrower  messages per borrower it messaged

Lenders with fewer than generator.min_lender_messages messages are not ranked
("too few messages to rank"). The others are ranked by the LOWER end of the
abusive-share interval, highest first. A lender only reaches the top if there
is strong evidence that its share is high, not just a high share from a handful
of messages.

The ranking prompts a human to read a lender's messages. It is not a finding of
misconduct. All data is synthetic.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from pathlib import Path
from statistics import NormalDist

import pandas as pd

from src.config import load_config
from src.datasets import DatasetError, paths_for
from src.generate_data import late_night_hours
from src.overlap import DEFAULT_NOTICE, connect_read_only
from src.predictions import check_matches, human_share, read_effective_labels

COMPARISON_FILE_NAME = "lender_comparison.csv"
TOO_FEW = "too few messages to rank"
OUTPUT_COLUMNS = [
    "rank", "lender_id", "name", "n_messages", "abusive_share", "abusive_low", "abusive_high",
    "threat_share", "shaming_share", "third_party_share", "late_night_share", "messages_per_borrower", "reason",
]


def wilson_interval(successes: int, n: int, confidence: float) -> tuple[float, float]:
    """Wilson score interval for a proportion successes / n at the given confidence level."""
    if n <= 0:
        return 0.0, 1.0
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    # At 0 of n and n of n the exact bound is 0 or 1; set it so rounding error cannot creep in.
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return low, high


def _labelled_messages(messages: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    merged = messages.merge(labels[["message_id", "predicted_class"]], on="message_id", how="left")
    missing = merged["predicted_class"].isna()
    if missing.any():
        raise ValueError(
            f"{int(missing.sum()):,} messages have no label from the primary classifier. "
            "Run: python -m src.classify_messages")
    return merged


def is_late_night(sent_at: pd.Series, cfg: dict) -> pd.Series:
    """True for each sent_at timestamp whose hour is in the generator.late_night window."""
    # A message stored with a date only has no hour, so it can never count as late at night.
    hours = pd.to_numeric(sent_at.astype(str).str.slice(11, 13), errors="coerce")
    return hours.isin(late_night_hours(cfg))


def compare_lenders(messages: pd.DataFrame, labels: pd.DataFrame, lenders: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """One row per lender that sent messages: ranked lenders first (rank 1 = most concerning).

    messages: message_id, lender_id, borrower_id, recipient_type, sent_at
    labels:   message_id, predicted_class (from one classifier)
    lenders:  lender_id, name
    """
    comparison = cfg["lender_comparison"]
    abusive_classes = list(comparison["abusive_classes"])
    minimum = int(cfg["generator"]["min_lender_messages"])

    data = _labelled_messages(messages, labels)
    data["abusive"] = data["predicted_class"].isin(abusive_classes)
    data["threat"] = data["predicted_class"] == "threat"
    data["shaming"] = data["predicted_class"] == "shaming_third_party"
    data["third_party"] = data["recipient_type"] == "third_party"
    data["late"] = is_late_night(data["sent_at"], cfg)

    grouped = data.groupby("lender_id")
    out = pd.DataFrame({
        "n_messages": grouped.size(),
        "n_abusive": grouped["abusive"].sum(),
        "threat_share": grouped["threat"].mean(),
        "shaming_share": grouped["shaming"].mean(),
        "third_party_share": grouped["third_party"].mean(),
        "late_night_share": grouped["late"].mean(),
        "messages_per_borrower": grouped.size() / grouped["borrower_id"].nunique(),
    }).reset_index()
    out["abusive_share"] = out["n_abusive"] / out["n_messages"]
    bounds = [wilson_interval(int(k), int(n), float(comparison["confidence"]))
              for k, n in zip(out["n_abusive"], out["n_messages"])]
    out["abusive_low"] = [low for low, _ in bounds]
    out["abusive_high"] = [high for _, high in bounds]
    out = out.merge(lenders[["lender_id", "name"]], on="lender_id", how="left")

    eligible = out["n_messages"] >= minimum
    out["reason"] = ""
    out.loc[~eligible, "reason"] = TOO_FEW
    ranked = out[eligible].sort_values(
        ["abusive_low", "abusive_share", "lender_id"], ascending=[False, False, True], kind="mergesort")
    out["rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out.loc[ranked.index, "rank"] = range(1, len(ranked) + 1)

    unranked = out[~eligible].sort_values("lender_id")
    out = pd.concat([out.loc[ranked.index], unranked])
    return out[OUTPUT_COLUMNS].reset_index(drop=True)


def explain_lender(row, cfg: dict, classifier: str) -> str:
    """One plain sentence about a lender's row of compare_lenders()."""
    level = f"{cfg['lender_comparison']['confidence']:.0%}"
    n = int(row["n_messages"])
    abusive = (f"{row['abusive_share']:.0%} of its {n:,} messages were labelled abusive by the {classifier} "
               f"classifier")
    if pd.isna(row["rank"]):
        minimum = int(cfg["generator"]["min_lender_messages"])
        return (f"{row['name']}: not ranked, {TOO_FEW} ({n:,}, minimum {minimum:,}). {abusive}, "
                f"but with so few messages that share is unreliable "
                f"({level} interval {row['abusive_low']:.0%} to {row['abusive_high']:.0%}).")
    return (f"{row['name']}: rank {int(row['rank'])}. {abusive} ({level} interval {row['abusive_low']:.0%} to "
            f"{row['abusive_high']:.0%}); {row['threat_share']:.0%} threats, {row['shaming_share']:.0%} shaming; "
            f"{row['third_party_share']:.0%} sent to third parties; {row['late_night_share']:.0%} sent late at night; "
            f"{row['messages_per_borrower']:.1f} messages per borrower.")


def borrower_harassment_summary(messages: pd.DataFrame, labels: pd.DataFrame, cfg: dict,
                                borrower_ids: list[str] | None = None) -> pd.DataFrame:
    """Per borrower: abusive_messages, late_night_messages, third_party_messages.

    Borrowers in borrower_ids who received no messages get zeros.
    """
    data = _labelled_messages(messages, labels)
    data["abusive_messages"] = data["predicted_class"].isin(cfg["lender_comparison"]["abusive_classes"]).astype(int)
    data["late_night_messages"] = is_late_night(data["sent_at"], cfg).astype(int)
    data["third_party_messages"] = (data["recipient_type"] == "third_party").astype(int)
    columns = ["abusive_messages", "late_night_messages", "third_party_messages"]
    out = data.groupby("borrower_id")[columns].sum()
    if borrower_ids is not None:
        out = out.reindex(sorted(set(borrower_ids) | set(out.index)), fill_value=0)
    return out.astype(int).reset_index().sort_values("borrower_id").reset_index(drop=True)


def load_inputs(lending_conn: sqlite3.Connection, predictions_conn: sqlite3.Connection,
                classifier: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """messages, labels (one classifier, with human labels applied; column 'source') and lenders."""
    check_matches(predictions_conn, lending_conn)
    messages = pd.read_sql_query(
        "SELECT message_id, lender_id, borrower_id, recipient_type, sent_at FROM messages", lending_conn)
    lenders = pd.read_sql_query("SELECT lender_id, name FROM lenders", lending_conn)
    return messages, read_effective_labels(predictions_conn, classifier), lenders


def write_comparison_csv(table: pd.DataFrame, path: Path, notice: str) -> None:
    """Write the table with the synthetic-data notice as a first '#' line (read back with comment='#')."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {notice} The ranking prompts a human to look; it is not a finding of misconduct.\n")
        table.to_csv(handle, index=False)


def format_table(table: pd.DataFrame) -> str:
    lines = [f"{'rank':>4}  {'lender':<29}{'msgs':>7}{'abusive':>9}{'interval':>13}{'threat':>8}"
             f"{'shaming':>9}{'3rd pty':>9}{'late':>7}{'per brw':>8}"]
    for r in table.itertuples(index=False):
        rank = "-" if pd.isna(r.rank) else str(int(r.rank))
        lines.append(
            f"{rank:>4}  {r.name:<29}{r.n_messages:>7,}{r.abusive_share:>9.1%}"
            f"{f'{r.abusive_low:.0%}-{r.abusive_high:.0%}':>13}{r.threat_share:>8.1%}{r.shaming_share:>9.1%}"
            f"{r.third_party_share:>9.1%}{r.late_night_share:>7.1%}{r.messages_per_borrower:>8.1f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare lenders by how their collection messages read.")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--dataset", help="Dataset to compare (default: the active dataset).")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    classifier = cfg["classifier"]["primary"]
    try:
        active = paths_for(cfg, args.dataset)
    except DatasetError as error:
        print(error)
        return 1
    lending_path, predictions_path = active.lending_db, active.predictions_db
    for path in (lending_path, predictions_path):
        if not path.exists():
            print(f"{path} not found. For the demo run python -m src.build_all; for another dataset run "
                  f"python -m src.classify_messages --classifier {classifier} --dataset {active.name}")
            return 1

    lending_conn = connect_read_only(lending_path)
    predictions_conn = connect_read_only(predictions_path)
    try:
        notice = dict(lending_conn.execute("SELECT key, value FROM meta")).get("notice", DEFAULT_NOTICE)
        messages, labels, lenders = load_inputs(lending_conn, predictions_conn, classifier)
    finally:
        lending_conn.close()
        predictions_conn.close()

    table = compare_lenders(messages, labels, lenders, cfg)
    out_path = lending_path.parent / COMPARISON_FILE_NAME
    write_comparison_csv(table, out_path, notice)

    level = f"{cfg['lender_comparison']['confidence']:.0%}"
    print(notice)
    print("The ranking prompts a human to read a lender's messages. It is not a finding of misconduct.")
    print("")
    reviewed = human_share(labels)
    print(f"Message labels: {reviewed:.1%} checked by a person, {1 - reviewed:.1%} from the '{classifier}' "
          f"classifier (classifier.primary). Abusive = {cfg['lender_comparison']['abusive_classes']}.")
    print(f"Ranked by the lower end of the {level} Wilson interval of the abusive share. "
          f"Lenders under {cfg['generator']['min_lender_messages']} messages are not ranked.")
    print("")
    print(format_table(table))
    print("")
    for _, row in table.iterrows():
        print(f"- {explain_lender(row, cfg, classifier)}")
    print("")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
