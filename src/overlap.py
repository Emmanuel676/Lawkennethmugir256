"""Overlap detector and borrower risk score (Phase 2).

THE SCORE PROMPTS A HUMAN TO LOOK AT A BORROWER. IT IS NEVER A VERDICT.
A high score means "an analyst should read this file", not "this borrower is
over-indebted" and not "a lender did something wrong". Every score comes with a
plain-language breakdown (explain) so the analyst can see why it is high.

This module reads lending.db only: the data a regulator could actually hold.
It must never open the answer labels; only src/evaluate_overlap.py may do that,
and a test checks this file's code for any mention of them.

"Today" is the as_of_date stored in lending.db's meta table, never the real date,
so the same database always gives the same scores.

Signals per borrower (unpaid = any loan whose status is not 'repaid'):

  open_lenders     distinct lenders among unpaid loans
  total_owed       sum of amount_outstanding over unpaid loans
  debt_to_income   total_owed / monthly_income
  arrears_share    share of total_owed sitting in loans that are in arrears
  loans_in_window  loans of any status issued in the last velocity_window_days
  cycling_events   distinct loans, issued in the last lookback_days, that were
                   issued within match_days (either side) of the borrower repaying
                   a DIFFERENT loan, i.e. borrowing to repay

Each signal becomes a strength from 0 to 1 (1 once it reaches its full_at value
in config.yaml), times its weight. The weights add up to 100, so the score runs
from 0 to 100. Bands: low, medium (score >= bands.medium), high (score >= bands.high).
Optionally, repeated cycling lifts a borrower out of "low" into "medium".

All data in this project is synthetic.

Run it:  python -m src.overlap
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import RISK_SIGNALS, load_config
from src.datasets import DatasetError, paths_for
from src.money import format_money

# Which full_at value scales each weighted signal.
FULL_AT_KEY = {
    "open_lenders": "open_lenders",
    "debt_to_income": "debt_to_income",
    "arrears": "arrears",
    "cycling": "cycling_events",
    "loan_velocity": "loans_in_window",
}

RAW_SIGNALS = ["open_lenders", "total_owed", "debt_to_income", "arrears_share", "loans_in_window", "cycling_events"]
POINT_COLUMNS = [f"pts_{signal}" for signal in RISK_SIGNALS]
OUTPUT_COLUMNS = (
    ["borrower_id", "monthly_income"] + RAW_SIGNALS + POINT_COLUMNS
    + ["score", "band", "band_forced_by_cycling"]
)

SCORES_FILE_NAME = "borrower_scores.csv"
DEFAULT_NOTICE = "SYNTHETIC DATA: generated for a prototype. It describes no real people, loans, lenders or messages."


def connect_read_only(path: Path) -> sqlite3.Connection:
    """Open a database for reading only, so scoring can never change it."""
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


def _meta_value(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else row[0]


def as_of_date(conn: sqlite3.Connection) -> pd.Timestamp:
    """The fixed "today" of the dataset, from the meta table."""
    value = _meta_value(conn, "as_of_date")
    if value is None:
        raise ValueError("lending.db has no 'as_of_date' in its meta table, so 'today' is unknown.")
    return pd.Timestamp(value)


def _cycling_events(
    loans: pd.DataFrame, repayments: pd.DataFrame, as_of: pd.Timestamp, match_days: int, lookback_days: int
) -> pd.Series:
    """Per borrower, how many recent loans were issued around the repayment of a different loan."""
    days_ago = (as_of - loans["issue_date"]).dt.days
    recent = loans.loc[(days_ago >= 0) & (days_ago <= lookback_days), ["loan_id", "borrower_id", "issue_date"]]
    pairs = recent.merge(repayments, on="borrower_id")
    gap = (pairs["txn_date"] - pairs["issue_date"]).dt.days.abs()
    matched = pairs[(pairs["linked_loan_id"] != pairs["loan_id"]) & (gap <= match_days)]
    return matched.groupby("borrower_id")["loan_id"].nunique()


def score_borrowers(conn: sqlite3.Connection, cfg: dict) -> pd.DataFrame:
    """Score every borrower in lending.db. One row per borrower, highest score first.

    The score prompts a human to look; it is never a verdict.
    """
    risk = cfg["risk"]
    weights, full_at = risk["weights"], risk["full_at"]
    as_of = as_of_date(conn)

    borrowers = pd.read_sql_query("SELECT borrower_id, monthly_income FROM borrowers", conn)
    loans = pd.read_sql_query(
        "SELECT loan_id, borrower_id, lender_id, amount_outstanding, issue_date, status FROM loans", conn)
    loans["issue_date"] = pd.to_datetime(loans["issue_date"])
    repayments = pd.read_sql_query(
        """SELECT borrower_id, txn_date, linked_loan_id FROM transactions
           WHERE direction = 'out' AND counterparty_type = 'lender' AND linked_loan_id IS NOT NULL""",
        conn,
    )
    repayments["txn_date"] = pd.to_datetime(repayments["txn_date"])

    unpaid = loans[loans["status"] != "repaid"]
    owed = unpaid.groupby("borrower_id").agg(
        open_lenders=("lender_id", "nunique"), total_owed=("amount_outstanding", "sum"))
    arrears_owed = (unpaid[unpaid["status"] == "in_arrears"]
                    .groupby("borrower_id")["amount_outstanding"].sum().rename("arrears_owed"))
    days_ago = (as_of - loans["issue_date"]).dt.days
    in_window = (loans[(days_ago >= 0) & (days_ago <= risk["velocity_window_days"])]
                 .groupby("borrower_id").size().rename("loans_in_window"))
    cycling = _cycling_events(
        loans, repayments, as_of, risk["cycling"]["match_days"], risk["cycling"]["lookback_days"]
    ).rename("cycling_events")

    out = borrowers.set_index("borrower_id")
    for part in (owed, arrears_owed, in_window, cycling):
        out = out.join(part)
    for column in ("open_lenders", "total_owed", "arrears_owed", "loans_in_window", "cycling_events"):
        out[column] = out[column].fillna(0).astype("int64")

    out["debt_to_income"] = out["total_owed"] / out["monthly_income"]
    out["arrears_share"] = np.where(
        out["total_owed"] > 0, out["arrears_owed"] / out["total_owed"].where(out["total_owed"] > 0, 1), 0.0)

    strength = {
        "open_lenders": (out["open_lenders"] - 1) / (full_at["open_lenders"] - 1),
        "debt_to_income": out["debt_to_income"] / full_at["debt_to_income"],
        "arrears": out["arrears_share"] / full_at["arrears"],
        "cycling": out["cycling_events"] / full_at["cycling_events"],
        "loan_velocity": out["loans_in_window"] / full_at["loans_in_window"],
    }
    for signal in RISK_SIGNALS:
        out[f"pts_{signal}"] = (strength[signal].clip(0, 1) * weights[signal]).round(1)
    out["score"] = out[POINT_COLUMNS].sum(axis=1).round(1)

    bands = risk["bands"]
    band = np.select([out["score"] >= bands["high"], out["score"] >= bands["medium"]], ["high", "medium"], "low")
    forced = np.zeros(len(out), dtype=bool)
    if risk["cycling_forces_minimum_band"]:
        forced = (out["cycling_events"].to_numpy() >= risk["cycling_minimum_events"]) & (band == "low")
        band = np.where(forced, "medium", band)
    out["band"] = band
    out["band_forced_by_cycling"] = forced

    # Rounded only for display; the points above were computed from the exact values.
    out["debt_to_income"] = out["debt_to_income"].round(3)
    out["arrears_share"] = out["arrears_share"].round(3)

    out = out.reset_index().sort_values(["score", "borrower_id"], ascending=[False, True], kind="mergesort")
    return out[OUTPUT_COLUMNS].reset_index(drop=True)


def explain(row, cfg: dict) -> list[str]:
    """Plain-language reasons for a borrower's score, biggest contributor first.

    row is one row of score_borrowers() (a pandas Series or a dict). Signals worth
    0 points are left out. Remember: this explains why a human should look, not a verdict.
    """
    risk = cfg["risk"]
    weights = risk["weights"]

    def plural(count: int, word: str) -> str:
        return f"{count} {word}" if count == 1 else f"{count} {word}s"

    reasons = {
        "open_lenders": f"Has unpaid loans with {int(row['open_lenders'])} different lenders at the same time",
        "debt_to_income": (f"Owes {format_money(row['total_owed'], cfg)}, which is "
                           f"{float(row['debt_to_income']):.1f} times monthly income"),
        "arrears": f"{float(row['arrears_share']):.0%} of what is owed is in arrears",
        "cycling": (f"{plural(int(row['cycling_events']), 'new loan')} taken within "
                    f"{risk['cycling']['match_days']} days of repaying a different loan (borrowing to repay)"),
        "loan_velocity": (f"Took {plural(int(row['loans_in_window']), 'loan')} in the last "
                          f"{risk['velocity_window_days']} days"),
    }
    ranked = sorted(
        ((float(row[f"pts_{signal}"]), order, signal) for order, signal in enumerate(RISK_SIGNALS)),
        key=lambda item: (-item[0], item[1]),
    )
    lines = [f"{reasons[signal]} ({points:.1f} of {weights[signal]} points)."
             for points, _, signal in ranked if points > 0]
    if bool(row["band_forced_by_cycling"]):
        lines.append(
            f"Placed in the medium band because of repeated cycling ({int(row['cycling_events'])} events, "
            f"rule applies from {risk['cycling_minimum_events']}), although the score of "
            f"{float(row['score']):.1f} is below {risk['bands']['medium']}."
        )
    if not lines:
        lines.append("No warning signs found (score 0).")
    return lines


def write_scores_csv(scores: pd.DataFrame, path: Path, notice: str) -> None:
    """Write the scores with the synthetic-data notice as a first '#' line (read back with comment='#')."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {notice} The score prompts a human to look; it is never a verdict.\n")
        scores.to_csv(handle, index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score every borrower for overlapping-loan risk.")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--dataset", help="Dataset to score (default: the active dataset).")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    try:
        lending_path = paths_for(cfg, args.dataset).lending_db
    except DatasetError as error:
        print(error)
        return 1
    if not lending_path.exists():
        print(f"{lending_path} not found. For the demo run: python -m src.build_all")
        return 1

    conn = connect_read_only(lending_path)
    try:
        notice = _meta_value(conn, "notice") or DEFAULT_NOTICE
        as_of = as_of_date(conn)
        scores = score_borrowers(conn, cfg)
    finally:
        conn.close()

    out_path = lending_path.parent / SCORES_FILE_NAME
    write_scores_csv(scores, out_path, notice)

    print(notice)
    print("The score prompts a human to look at a borrower. It is never a verdict.")
    print("")
    print(f"Scored {len(scores):,} borrowers as of {as_of.date().isoformat()}.")
    counts = scores["band"].value_counts()
    forced = int(scores["band_forced_by_cycling"].sum())
    for band in ("high", "medium", "low"):
        extra = f"   ({forced:,} placed here by the cycling rule)" if band == "medium" and forced else ""
        print(f"  {band:<8}{int(counts.get(band, 0)):>7,}{extra}")
    print("")
    print("Top 3 borrowers and why:")
    for _, row in scores.head(3).iterrows():
        print(f"  {row['borrower_id']}  score {row['score']:.1f}  band {row['band']}")
        for line in explain(row, cfg):
            print(f"    - {line}")
    print("")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
