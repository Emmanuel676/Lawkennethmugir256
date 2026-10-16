"""Repayment performance (Phase 10, v1 of docs/REPAYMENT_PERFORMANCE_DESIGN.md). No Streamlit, no network.

A FOLLOW-UP PROMPT, NOT A VERDICT OR A CREDIT SCORE. It shows who paid on time, who paid late and who is not
paying, so a person knows whose file to open. It says nothing about anyone's creditworthiness, and a repayment
status is not proof of wrongdoing by a borrower or a lender.

Reads lending.db only (loans and the repayments linked to them), like src/overlap.py. "Today" is the dataset's
as_of_date. Settings: the 'repayments' section of config.yaml.

Status of each loan on the as-of date (grace = repayments.grace_days, window = repayments.not_paying_after_days):

  current             not yet due (due_date on or after the as-of date) and not repaid
  in_grace            not repaid, past the due date but still within grace (an extra status: the design's list
                      did not cover an unpaid loan inside the grace days)
  on_time             repaid; last linked repayment on or before due_date
  late_within_grace   repaid; last linked repayment after due_date, at most grace days after it
  late_beyond_grace   repaid; last linked repayment more than grace days after due_date
  overdue_paying      not repaid, past due + grace, with a linked repayment in the last `window` days
  not_paying          not repaid, past due + grace, with no linked repayment in the last `window` days
  unknown             repaid but no linked repayment, so the date it was cleared cannot be known. Never guessed.

The clearing date of a repaid loan is its LAST LINKED repayment (lending.db stores no amount due). If the true last
repayment carries no linked_loan_id, an earlier one is used, and repayments without a link cannot count as
"recent", so a loan that is still being paid without links shows as not paying. Both are stated on the page.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd

from src.datasets import get_active_paths
from src.overlap import as_of_date, connect_read_only

STATUSES = ("not_paying", "overdue_paying", "late_beyond_grace", "in_grace", "late_within_grace", "unknown",
            "on_time", "current")  # worst first: a borrower's status is the worst of their loans
LABELS = {
    "not_paying": "Not paying", "overdue_paying": "Overdue but paying", "late_beyond_grace": "Late beyond grace",
    "in_grace": "Past due, in grace", "late_within_grace": "Late within grace", "unknown": "Unknown (no link)",
    "on_time": "On time", "current": "Current (not yet due)",
}
FOLLOW_UP = ("not_paying", "overdue_paying")
PROMPT = "Follow-up prompt, not a verdict or a credit score."
LIMITS = (
    "Needs linked_loan_id on repayments: without it a repaid loan's clearing date is unknown, and a loan still "
    "being paid without links shows as not paying.",
    "Lenders differ on grace rules; the grace days here are one setting for every lender.",
    "A repayment status is not proof of wrongdoing by a borrower or a lender.",
    "The field facts behind the defaults (daily repayment, 3 grace days) come from one lender.",
)


def bucket_labels(edges: list[int]) -> list[str]:
    """['current', '1-3 days (grace)', '4-30 days', ..., 'over 90 days'] from upper edges [3, 30, 60, 90]."""
    labels, low = ["current"], 1
    for number, high in enumerate(edges):
        labels.append(f"{low}-{high} days" + (" (grace)" if number == 0 else ""))
        low = high + 1
    labels.append(f"over {edges[-1]} days")
    return labels


def _bucket(days: int, edges: list[int], labels: list[str]) -> str:
    if days <= 0:
        return labels[0]
    for number, high in enumerate(edges):
        if days <= high:
            return labels[number + 1]
    return labels[-1]


def classify(loans: pd.DataFrame, repayments: pd.DataFrame, as_of: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    """Add status, days_past_due and bucket to every loan.

    loans:      loan_id, borrower_id, lender_id, amount_outstanding, due_date, status (the database's status)
    repayments: linked_loan_id, txn_date (linked repayments only: direction out, counterparty lender)
    """
    settings = cfg["repayments"]
    grace, window = int(settings["grace_days"]), int(settings["not_paying_after_days"])
    edges = [int(e) for e in settings["ageing_bucket_edges"]]
    out = loans.copy()
    out["due_date"] = pd.to_datetime(out["due_date"])
    reps = repayments.copy()
    reps["txn_date"] = pd.to_datetime(reps["txn_date"])
    reps = reps[reps["txn_date"] <= as_of]  # nothing after "today" counts
    last = reps.groupby("linked_loan_id")["txn_date"].max().rename("last_repayment")
    recent_cut = as_of - timedelta(days=window)
    recent = (reps[reps["txn_date"] > recent_cut].groupby("linked_loan_id").size() > 0).rename("recent_repayment")
    count = reps.groupby("linked_loan_id").size().rename("linked_repayments")
    out = out.join(last, on="loan_id").join(recent, on="loan_id").join(count, on="loan_id")
    out["recent_repayment"] = out["recent_repayment"].fillna(False).astype(bool)
    out["linked_repayments"] = out["linked_repayments"].fillna(0).astype(int)

    repaid = out["status"] == "repaid"
    days_late = (out["last_repayment"] - out["due_date"]).dt.days
    days_past_due = (as_of - out["due_date"]).dt.days
    status = pd.Series("current", index=out.index, dtype=object)
    status[repaid & out["last_repayment"].isna()] = "unknown"
    status[repaid & (days_late <= 0)] = "on_time"
    status[repaid & (days_late > 0) & (days_late <= grace)] = "late_within_grace"
    status[repaid & (days_late > grace)] = "late_beyond_grace"
    unpaid = ~repaid
    status[unpaid & (days_past_due > 0) & (days_past_due <= grace)] = "in_grace"
    beyond = unpaid & (days_past_due > grace)
    status[beyond & out["recent_repayment"]] = "overdue_paying"
    status[beyond & ~out["recent_repayment"]] = "not_paying"
    out["repayment_status"] = status
    out["days_past_due"] = days_past_due.where(unpaid & (days_past_due > 0), 0).astype(int)
    labels = bucket_labels(edges)
    out["bucket"] = [(_bucket(d, edges, labels) if u else "") for d, u in zip(out["days_past_due"], unpaid)]
    out["owed"] = out["amount_outstanding"].where(unpaid, 0).astype("int64")
    return out


def loan_statuses(conn, cfg: dict) -> pd.DataFrame:
    """Every loan in lending.db with its repayment status on the as-of date."""
    as_of = as_of_date(conn)
    loans = pd.read_sql_query(
        "SELECT loan_id, borrower_id, lender_id, amount_outstanding, issue_date, due_date, status FROM loans", conn)
    repayments = pd.read_sql_query(
        """SELECT linked_loan_id, txn_date FROM transactions
           WHERE direction = 'out' AND counterparty_type = 'lender' AND linked_loan_id IS NOT NULL""", conn)
    return classify(loans, repayments, as_of, cfg)


def headline(statuses: pd.DataFrame) -> dict:
    """Loan counts and shares per status, and money still owed on unpaid loans."""
    n = len(statuses)
    counts = statuses["repayment_status"].value_counts()
    return {
        "loans": n,
        "counts": {s: int(counts.get(s, 0)) for s in STATUSES},
        "shares": {s: (int(counts.get(s, 0)) / n if n else 0.0) for s in STATUSES},
        "owed_unpaid": int(statuses["owed"].sum()),
        "owed_follow_up": int(statuses.loc[statuses["repayment_status"].isin(FOLLOW_UP), "owed"].sum()),
    }


def ageing(statuses: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Unpaid loans per ageing bucket: bucket, loans, owed (all buckets listed, in order)."""
    labels = bucket_labels([int(e) for e in cfg["repayments"]["ageing_bucket_edges"]])
    unpaid = statuses[statuses["bucket"] != ""]
    grouped = unpaid.groupby("bucket").agg(loans=("loan_id", "size"), owed=("owed", "sum"))
    return grouped.reindex(labels, fill_value=0).rename_axis("bucket").reset_index()


def lender_mix(statuses: pd.DataFrame, lenders: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Per lender: loans, the count and share of each status, and whether it has enough loans to compare."""
    minimum = int(cfg["repayments"]["min_loans_to_compare"])
    counts = pd.crosstab(statuses["lender_id"], statuses["repayment_status"]).reindex(columns=list(STATUSES),
                                                                                     fill_value=0)
    out = counts.reset_index().merge(lenders[["lender_id", "name"]], on="lender_id", how="left")
    out["loans"] = counts.sum(axis=1).to_numpy()
    out["comparable"] = out["loans"] >= minimum
    for s in STATUSES:
        out[f"share_{s}"] = out[s] / out["loans"]
    return out.sort_values(["comparable", "lender_id"], ascending=[False, True]).reset_index(drop=True)


def _joined_names(frame: pd.DataFrame) -> pd.Series:
    """Per borrower, its distinct lender names in A-Z order joined by '; ' (one pass, no per-borrower sets)."""
    pairs = (frame[["borrower_id", "lender_name"]].astype(object).dropna().drop_duplicates()
             .sort_values(["borrower_id", "lender_name"]))
    return pairs.groupby("borrower_id", sort=False)["lender_name"].agg("; ".join)


def borrower_rollup(statuses: pd.DataFrame, scores: pd.DataFrame, lenders: pd.DataFrame) -> pd.DataFrame:
    """Per borrower: worst status, loans per status, overdue loans, days past due, owed, lenders, band, open lenders.

    scores: borrower_id, band, open_lenders (from the existing risk score) for the cross-lender context.
    """
    rank = {s: i for i, s in enumerate(STATUSES)}
    data = statuses.assign(_rank=statuses["repayment_status"].map(rank),
                           lender_name=statuses["lender_id"].map(lenders.set_index("lender_id")["name"]))
    counts = pd.crosstab(data["borrower_id"], data["repayment_status"]).reindex(columns=list(STATUSES), fill_value=0)
    worst = data.groupby("borrower_id")["_rank"].min().map(dict(enumerate(STATUSES))).rename("worst_status")
    overdue = data[data["repayment_status"].isin(FOLLOW_UP)]
    out = pd.DataFrame(worst).join(counts)
    out["loans_overdue"] = overdue.groupby("borrower_id").size().reindex(out.index, fill_value=0)
    out["days_past_due"] = data.groupby("borrower_id")["days_past_due"].max().reindex(out.index, fill_value=0)
    out["owed"] = data.groupby("borrower_id")["owed"].sum().reindex(out.index, fill_value=0)
    out["owed_overdue"] = overdue.groupby("borrower_id")["owed"].sum().reindex(out.index, fill_value=0)
    out["overdue_lenders"] = _joined_names(overdue).reindex(out.index, fill_value="")
    out["lenders"] = _joined_names(data).reindex(out.index, fill_value="")
    out = out.reset_index().merge(scores[["borrower_id", "band", "open_lenders"]], on="borrower_id", how="left")
    return out.sort_values("borrower_id").reset_index(drop=True)


FOLLOW_UP_COLUMNS = {
    "borrower_id": "borrower_code", "overdue_lenders": "lenders_overdue", "worst_status": "repayment_status",
    "days_past_due": "days_past_due", "owed_overdue": "owed_overdue_ugx", "owed": "owed_all_loans_ugx",
    "loans_overdue": "loans_overdue", "band": "risk_band", "open_lenders": "open_lenders",
}
FOLLOW_UP_SORTS = {"Days past due": "days_past_due", "Amount owed (overdue)": "owed_overdue",
                   "Loans overdue": "loans_overdue", "Borrower code": "borrower_id"}


def follow_up(rollup: pd.DataFrame, lenders=None, statuses=None, bands=None, sort_label: str = "Days past due",
              ascending: bool = False) -> pd.DataFrame:
    """Borrowers with a loan not paying or overdue-but-paying, filtered and sorted. Empty filters mean 'any'."""
    rows = rollup[rollup["loans_overdue"] > 0]
    if lenders:
        wanted = set(lenders)
        rows = rows[rows["overdue_lenders"].map(lambda s: bool(wanted & set(s.split("; "))))]
    if statuses:
        rows = rows[rows["worst_status"].isin(list(statuses))]
    if bands:
        rows = rows[rows["band"].isin(list(bands))]
    column = FOLLOW_UP_SORTS[sort_label]
    return rows.sort_values([column, "borrower_id"], ascending=[ascending, True], kind="mergesort").reset_index(drop=True)


def follow_up_table(rows: pd.DataFrame) -> pd.DataFrame:
    """The follow-up list with plain column names (borrower codes only; statuses written as words)."""
    table = rows[list(FOLLOW_UP_COLUMNS)].rename(columns=FOLLOW_UP_COLUMNS)
    table["repayment_status"] = table["repayment_status"].map(LABELS)
    return table


def follow_up_csv(rows: pd.DataFrame, notice: str) -> bytes:
    """CSV bytes with the dataset notice and the follow-up wording as a first '#' line (read with comment='#')."""
    header = f"# {notice} {PROMPT} Flags prompt a human to look. They are not findings and not a verdict.\n"
    return (header + follow_up_table(rows).to_csv(index=False, lineterminator="\n")).encode("utf-8")


def looks_like_lump_repayments(statuses: pd.DataFrame) -> bool:
    """True when no loan has more than one linked repayment (as in the demo, which repays each loan in one go)."""
    return bool(len(statuses)) and int(statuses["linked_repayments"].max()) <= 1


def load(cfg: dict, scores: pd.DataFrame, lenders: pd.DataFrame, path: Path | None = None) -> dict:
    """Everything the Repayments page shows, for the active dataset (or the lending.db at path)."""
    lending = Path(path) if path else get_active_paths(cfg).lending_db
    conn = connect_read_only(lending)
    try:
        statuses = loan_statuses(conn, cfg)
    finally:
        conn.close()
    return {
        "statuses": statuses,
        "headline": headline(statuses),
        "ageing": ageing(statuses, cfg),
        "lender_mix": lender_mix(statuses, lenders, cfg),
        "rollup": borrower_rollup(statuses, scores, lenders),
        "lump": looks_like_lump_repayments(statuses),
    }
