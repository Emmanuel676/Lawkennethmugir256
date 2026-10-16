"""Data layer for the dashboard (Phase 4). Pure functions, no Streamlit.

Everything the pages show is computed here, so it can be unit-tested without a
browser. The pages (app.py and pages/) only lay it out.

Reads lending.db and predictions.db only, through the existing scoring and
lender-comparison code. It never opens the answer labels, never uses the
network and needs no API key.

FLAGS PROMPT A HUMAN TO LOOK. THEY ARE NOT FINDINGS AND NOT A VERDICT.
All data is synthetic.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.config import MESSAGE_CLASSES, RISK_SIGNALS
from src.datasets import DEMO, DatasetError, get_active_paths, get_dataset
from src.lender_comparison import (borrower_harassment_summary, compare_lenders, explain_lender,
                                   is_late_night)
from src.money import currency_code, money_column, money_label
from src.overlap import DEFAULT_NOTICE, connect_read_only, explain, score_borrowers
from src.predictions import StalePredictionsError, check_matches, human_share, read_effective_labels

REVIEW_LINE = "Flags prompt a human to look. They are not findings and not a verdict."
FLAGGED_BANDS = ("medium", "high")
BANDS = ("high", "medium", "low")
ACTIVATE = r".\.venv\Scripts\Activate.ps1"

SIGNAL_LABELS = {
    "open_lenders": "Open lenders",
    "debt_to_income": "Debt to income",
    "arrears": "Arrears",
    "cycling": "Cycling (borrowing to repay)",
    "loan_velocity": "Loan velocity",
}
SIGNAL_DESCRIPTIONS = {
    "open_lenders": "Distinct lenders among unpaid loans (one lender scores 0).",
    "debt_to_income": "Total owed on unpaid loans divided by monthly income.",
    "arrears": "Share of what is owed that sits in loans in arrears.",
    "cycling": ("Recent loans issued within a few days of clearing a loan from another lender (the old loan is "
                "repaid and this is its last linked repayment)."),
    "loan_velocity": "Loans of any status issued in the recent window.",
}
CLASS_DESCRIPTIONS = {
    "normal": "Neutral reminder, before or after the due date.",
    "firm_pressure": "Insistent but lawful: late fees, credit record, referral to a recovery team.",
    "threat": "Threatens harm or action the lender cannot lawfully take, including veiled threats.",
    "shaming_third_party": ("Exposes the debt to other people or contacts the borrower's contacts. "
                            "Also covers shaming sent straight to the borrower."),
}

# Export column names: plain English snake_case.
BORROWER_EXPORT_COLUMNS = {
    "borrower_id": "borrower_id",
    "region": "region",
    "score": "risk_score",
    "band": "band",
    "band_forced_by_cycling": "placed_in_medium_by_cycling_rule",
    "monthly_income": money_column("monthly_income"),  # monthly_income_ugx: the currency is in the name
    "open_lenders": "open_lenders",
    "total_owed": money_column("total_owed"),
    "debt_to_income": "debt_to_income",
    "arrears_share": "share_owed_in_arrears",
    "loans_in_window": "recent_loans",
    "cycling_events": "cycling_events",
    "abusive_messages": "abusive_messages",
    "late_night_messages": "late_night_messages",
    "third_party_messages": "third_party_messages",
    **{f"pts_{signal}": f"points_{signal}" for signal in RISK_SIGNALS},
}
LENDER_EXPORT_COLUMNS = {
    "rank": "rank",
    "lender_id": "lender_id",
    "name": "lender_name",
    "size_category": "lender_size",
    "n_messages": "messages",
    "abusive_share": "abusive_share",
    "abusive_low": "abusive_share_lower_bound",
    "abusive_high": "abusive_share_upper_bound",
    "threat_share": "threat_share",
    "shaming_share": "shaming_share",
    "third_party_share": "third_party_share",
    "late_night_share": "late_night_share",
    "messages_per_borrower": "messages_per_borrower",
    "reason": "not_ranked_reason",
}

SORT_OPTIONS = {
    "Score": "score",
    "Total owed": "total_owed",
    "Open lenders": "open_lenders",
    "Debt to income": "debt_to_income",
    "Abusive messages": "abusive_messages",
    "Borrower id": "borrower_id",
}


def _empty() -> pd.DataFrame:
    return pd.DataFrame()


@dataclass
class DashboardData:
    """Everything the pages need. status is 'ok', 'missing', 'stale' or 'incomplete'.

    dataset / dataset_name / kind say which dataset this is; synthetic is True only when
    the dataset's own meta table says so (a demo whose files are missing also counts as synthetic).
    """

    status: str
    message: str = ""
    commands: str = ""
    notice: str = DEFAULT_NOTICE
    dataset: str = ""
    dataset_name: str = ""
    kind: str = "demo"
    synthetic: bool = True
    as_of_date: str = ""
    currency: str = ""
    classifier: str = ""
    models: list[str] = field(default_factory=list)
    label_coverage: dict[str, float] = field(default_factory=dict)
    human_share: float = 0.0  # share of messages whose label a person gave (Review page)
    borrowers: pd.DataFrame = field(default_factory=_empty)
    lenders: pd.DataFrame = field(default_factory=_empty)
    messages: pd.DataFrame = field(default_factory=_empty)
    loans: pd.DataFrame = field(default_factory=_empty)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def real(self) -> bool:
        return self.kind == "real" or not self.synthetic


def data_signature(cfg: dict) -> tuple:
    """Changes when the active dataset or either of its database files changes, so cached data is reloaded."""
    active = get_active_paths(cfg)
    signature: list[tuple] = [(active.name,)]
    for path in (active.lending_db, active.predictions_db):
        if path.exists():
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        else:
            signature.append((str(path), None, None))
    return tuple(signature)


def _commands(*lines: str) -> str:
    return "\n".join((ACTIVATE,) + lines)


def load_all(cfg: dict) -> DashboardData:
    """Load and compute everything for the active dataset. Never raises for missing, stale, empty or
    unreadable (corrupt) data: the status and message say what is wrong and what to do."""
    try:
        return _load_all(cfg)
    except sqlite3.DatabaseError as error:
        active = get_active_paths(cfg)
        demo = active.name == DEMO
        return DashboardData(
            "unreadable", dataset=active.name, dataset_name=active.name, kind="demo" if demo else "real",
            synthetic=demo, classifier=cfg["classifier"]["primary"],
            message=(f"A database file of dataset '{active.name}' cannot be read ({type(error).__name__}): it is "
                     "damaged or empty. " + ("Rebuild the demo:" if demo else
                                             "Import the data again, or switch to another dataset on the Data page:")),
            commands=_commands("python -m src.build_all" if demo else "python -m src.datasets --list"))


def _load_all(cfg: dict) -> DashboardData:
    classifier = cfg["classifier"]["primary"]
    active = get_active_paths(cfg)
    lending_path, predictions_path = active.lending_db, active.predictions_db
    try:
        info = get_dataset(cfg, active.name)
        kind, display_name = info.kind, info.name
    except DatasetError:
        kind, display_name = ("demo" if active.name == DEMO else "real"), active.name
    ident = {"dataset": active.name, "dataset_name": display_name, "kind": kind, "classifier": classifier}
    classify_command = f"python -m src.classify_messages --classifier {classifier} --dataset {active.name}"

    if not lending_path.exists():
        if active.name == DEMO:
            return DashboardData(
                "missing", synthetic=True, **ident,
                message="No dataset found: the demo data is not there. Rebuild it with one command (15 to 35 seconds), "
                        "or use 'Restore demo' on the Data page:",
                commands=_commands("python -m src.build_all"))
        return DashboardData(
            "missing", synthetic=False, **ident,
            message=f"Dataset '{display_name}' has no data file. Import it again or switch dataset on the Data page.",
            commands=_commands("python -m src.datasets --list"))

    lending = connect_read_only(lending_path)
    try:
        meta = dict(lending.execute("SELECT key, value FROM meta"))
        notice = meta.get("notice", DEFAULT_NOTICE)
        ident.update(notice=notice, synthetic=meta.get("synthetic") == "true", as_of_date=meta.get("as_of_date", ""))
        if lending.execute("SELECT COUNT(*) FROM borrowers").fetchone()[0] == 0:
            return DashboardData(
                "empty", **ident,
                message=f"Dataset '{display_name}' has no borrowers yet, so there is nothing to show. Import data "
                        "into it on the Data page, or switch to another dataset:",
                commands=_commands("python -m src.datasets --list"))
        if not predictions_path.exists():
            return DashboardData(
                "missing", **ident,
                message="The messages of this dataset have not been classified yet. Run:",
                commands=_commands(classify_command))

        predictions = connect_read_only(predictions_path)
        try:
            try:
                check_matches(predictions, lending)
            except StalePredictionsError:
                return DashboardData(
                    "stale", **ident,
                    message=("The message labels were made from a different version of this dataset "
                             "(it has changed since). Classify the messages again:"),
                    commands=_commands(classify_command))
            labels = read_effective_labels(predictions, classifier)  # human labels win
        finally:
            predictions.close()

        messages = pd.read_sql_query(
            "SELECT message_id, lender_id, borrower_id, recipient_type, sent_at, text FROM messages", lending)
        # object dtype: pandas' Arrow-string isin between two large columns is about 30 times slower
        labelled = int(messages["message_id"].astype(object).isin(labels["message_id"].astype(object)).sum())
        if labelled < len(messages):
            return DashboardData(
                "incomplete", **ident,
                message=(f"Only {labelled:,} of {len(messages):,} messages have a label from the "
                         f"'{classifier}' classifier (classifier.primary). Classify them all:"),
                commands=_commands(classify_command))

        scores = score_borrowers(lending, cfg)
        borrower_info = pd.read_sql_query("SELECT borrower_id, region FROM borrowers", lending)
        lender_info = pd.read_sql_query("SELECT lender_id, name, size_category FROM lenders", lending)
        loans = pd.read_sql_query(
            """SELECT loan_id, borrower_id, lender_id, principal, amount_outstanding, issue_date, due_date, status
               FROM loans""", lending)
    finally:
        lending.close()

    harassment = borrower_harassment_summary(messages, labels, cfg, borrower_ids=scores["borrower_id"].tolist())
    borrowers = (scores.merge(borrower_info, on="borrower_id", how="left")
                 .merge(harassment, on="borrower_id", how="left")
                 .sort_values(["score", "borrower_id"], ascending=[False, True], kind="mergesort")
                 .reset_index(drop=True))

    lenders = compare_lenders(messages, labels, lender_info[["lender_id", "name"]], cfg).merge(
        lender_info[["lender_id", "size_category"]], on="lender_id", how="left")

    names = lender_info.set_index("lender_id")["name"]
    messages = messages.merge(labels[["message_id", "predicted_class", "confidence", "source"]],
                              on="message_id", how="left").rename(columns={"source": "label_source"})
    messages["lender_name"] = messages["lender_id"].map(names)
    messages["late_night"] = is_late_night(messages["sent_at"], cfg)
    messages["third_party"] = messages["recipient_type"] == "third_party"
    loans["lender_name"] = loans["lender_id"].map(names)

    return DashboardData(
        "ok", **ident, currency=currency_code(cfg),
        models=sorted(labels["model"].dropna().unique().tolist()),
        label_coverage={classifier: labelled / len(messages) if len(messages) else 1.0},
        human_share=human_share(labels),
        borrowers=borrowers, lenders=lenders, messages=messages, loans=loans,
    )


def data_health(cfg: dict) -> dict:
    """Checks on the active dataset's raw tables (needs no labels): per-lender coverage and cross-lender overlap."""
    active = get_active_paths(cfg)
    minimum = int(cfg["generator"]["min_lender_messages"])
    if not active.lending_db.exists():
        return {"available": False, "per_lender": pd.DataFrame(), "borrowers": 0, "shared_borrowers": 0,
                "minimum": minimum}
    conn = connect_read_only(active.lending_db)
    try:
        conn.execute("SELECT 1 FROM lenders LIMIT 1")
    except sqlite3.DatabaseError:
        conn.close()
        return {"available": False, "per_lender": pd.DataFrame(), "borrowers": 0, "shared_borrowers": 0,
                "minimum": minimum, "unreadable": True}
    try:
        lenders = pd.read_sql_query("SELECT lender_id, name FROM lenders", conn)
        loans = pd.read_sql_query("SELECT loan_id, borrower_id, lender_id, issue_date FROM loans", conn)
        messages = pd.read_sql_query("SELECT lender_id, borrower_id, sent_at FROM messages", conn)
        linked = {r[0] for r in conn.execute(
            "SELECT DISTINCT linked_loan_id FROM transactions WHERE linked_loan_id IS NOT NULL")}
        n_borrowers = conn.execute("SELECT COUNT(*) FROM borrowers").fetchone()[0]
    finally:
        conn.close()

    rows = []
    for lender in lenders.itertuples(index=False):
        own_loans = loans[loans["lender_id"] == lender.lender_id]
        own_messages = messages[messages["lender_id"] == lender.lender_id]
        dates = list(own_loans["issue_date"]) + [s[:10] for s in own_messages["sent_at"]]
        n_messages = len(own_messages)
        rows.append({
            "Lender": lender.name,
            "Loans": len(own_loans),
            "Messages": n_messages,
            "Borrowers": len(set(own_loans["borrower_id"]) | set(own_messages["borrower_id"])),
            "First date": min(dates) if dates else "",
            "Last date": max(dates) if dates else "",
            "Loans with transactions %": round(100 * own_loans["loan_id"].isin(linked).mean(), 1)
            if len(own_loans) else 0.0,
            "Can be ranked": "yes" if n_messages >= minimum else f"no: fewer than {minimum} messages",
        })
    per_borrower = loans.groupby("borrower_id")["lender_id"].nunique()
    return {
        "available": True,
        "per_lender": pd.DataFrame(rows),
        "borrowers": int(n_borrowers),
        "shared_borrowers": int((per_borrower >= 2).sum()),
        "minimum": minimum,
    }


def coverage_sentence(data: DashboardData) -> str:
    parts = [f"{share:.0%} from the '{name}' classifier" for name, share in data.label_coverage.items()]
    models = f" (model: {', '.join(data.models)})" if data.models else ""
    reviewed = (f" {data.human_share:.1%} of the labels were checked by a person and replace the model's label."
                if data.human_share else " None has been checked by a person yet.")
    return "Message labels: " + ", ".join(parts) + models + "." + reviewed + " Model labels are guesses."


def overview_kpis(data: DashboardData, cfg: dict) -> dict:
    """Headline numbers for the overview page."""
    borrowers, messages, lenders = data.borrowers, data.messages, data.lenders
    n = len(borrowers)
    counts = {band: int((borrowers["band"] == band).sum()) for band in BANDS}
    minimum = int(cfg["dashboard"]["concern_min_abusive_messages"])
    abusive = messages["predicted_class"].isin(cfg["lender_comparison"]["abusive_classes"])
    flagged = borrowers["band"].isin(FLAGGED_BANDS)
    return {
        "borrowers_scored": n,
        "band_counts": counts,
        "band_shares": {band: (count / n if n else 0.0) for band, count in counts.items()},
        "owed_by_high_band": int(borrowers.loc[borrowers["band"] == "high", "total_owed"].sum()),
        "messages_classified": int(messages["predicted_class"].notna().sum()),
        "abusive_message_share": float(abusive.mean()) if len(messages) else 0.0,
        "lenders_ranked": int(lenders["rank"].notna().sum()),
        "lenders_unranked": int(lenders["rank"].isna().sum()),
        "concern_min_abusive_messages": minimum,
        "flagged_and_harassed": int((flagged & (borrowers["abusive_messages"] >= minimum)).sum()),
    }


def band_distribution(data: DashboardData) -> pd.DataFrame:
    """band, borrowers: one row per band in the order high, medium, low."""
    counts = data.borrowers["band"].value_counts()
    return pd.DataFrame({"band": list(BANDS), "borrowers": [int(counts.get(b, 0)) for b in BANDS]})


def top_borrowers(data: DashboardData, n: int) -> pd.DataFrame:
    columns = ["borrower_id", "score", "band", "open_lenders", "total_owed", "abusive_messages"]
    return data.borrowers[columns].head(n).reset_index(drop=True)


def filter_borrowers(borrowers: pd.DataFrame, bands=None, regions=None, min_score: float = 0.0,
                     min_open_lenders: int = 0, min_abusive_messages: int = 0, id_search: str = "") -> pd.DataFrame:
    """Rows matching every filter. None or empty bands/regions means 'any'. id_search is a case-insensitive part of the id."""
    mask = pd.Series(True, index=borrowers.index)
    if bands:
        mask &= borrowers["band"].isin(list(bands))
    if regions:
        mask &= borrowers["region"].isin(list(regions))
    mask &= borrowers["score"] >= float(min_score)
    mask &= borrowers["open_lenders"] >= int(min_open_lenders)
    mask &= borrowers["abusive_messages"] >= int(min_abusive_messages)
    search = (id_search or "").strip()
    if search:
        mask &= borrowers["borrower_id"].str.contains(search, case=False, regex=False)
    return borrowers[mask].reset_index(drop=True)


def sort_borrowers(borrowers: pd.DataFrame, sort_label: str, ascending: bool = False) -> pd.DataFrame:
    column = SORT_OPTIONS[sort_label]
    return borrowers.sort_values([column, "borrower_id"], ascending=[ascending, True], kind="mergesort").reset_index(
        drop=True)


def page_count(n_rows: int, page_size: int) -> int:
    return max(1, math.ceil(n_rows / page_size))


def page_slice(frame: pd.DataFrame, page: int, page_size: int) -> pd.DataFrame:
    """Rows of a 1-based page; pages past the end are clamped to the last page."""
    page = min(max(1, int(page)), page_count(len(frame), page_size))
    start = (page - 1) * page_size
    return frame.iloc[start:start + page_size]


def borrower_table(borrowers: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """The borrower list as shown on screen (the band is always a word; money columns name the currency)."""
    return pd.DataFrame({
        "Borrower": borrowers["borrower_id"],
        "Score": borrowers["score"],
        "Band": borrowers["band"],
        "Cycling rule": borrowers["band_forced_by_cycling"].map({True: "placed in medium", False: ""}),
        "Region": borrowers["region"],
        "Open lenders": borrowers["open_lenders"],
        money_label("Total owed", cfg): borrowers["total_owed"],
        "Debt / income": borrowers["debt_to_income"],
        "Abusive msgs": borrowers["abusive_messages"],
        "Late-night msgs": borrowers["late_night_messages"],
        "Third-party msgs": borrowers["third_party_messages"],
    })


def borrower_detail(data: DashboardData, borrower_id: str, cfg: dict) -> dict:
    """Everything about one borrower: score row, reasons, points, loans across lenders, timeline, messages."""
    rows = data.borrowers[data.borrowers["borrower_id"] == borrower_id]
    if rows.empty:
        raise KeyError(f"Unknown borrower {borrower_id!r}")
    row = rows.iloc[0]
    weights = cfg["risk"]["weights"]
    points = pd.DataFrame({
        "signal": [SIGNAL_LABELS[s] for s in RISK_SIGNALS],
        "points": [float(row[f"pts_{s}"]) for s in RISK_SIGNALS],
        "max_points": [float(weights[s]) for s in RISK_SIGNALS],
    })

    loans = data.loans[data.loans["borrower_id"] == borrower_id].sort_values(["issue_date", "loan_id"])
    loan_table = pd.DataFrame({
        "loan_id": loans["loan_id"],
        "lender": loans["lender_name"],
        "principal": loans["principal"],
        "owed": loans["amount_outstanding"],
        "issue_date": loans["issue_date"],
        "due_date": loans["due_date"],
        "status": loans["status"],
    }).reset_index(drop=True)
    timeline = loan_table.assign(
        loan=loan_table["loan_id"] + " · " + loan_table["lender"] + " · " + loan_table["status"],
        issue_date=pd.to_datetime(loan_table["issue_date"]),
        due_date=pd.to_datetime(loan_table["due_date"]),
    )[["loan", "lender", "status", "issue_date", "due_date"]]

    messages = data.messages[data.messages["borrower_id"] == borrower_id].sort_values(["sent_at", "message_id"])
    message_table = pd.DataFrame({
        "message_id": messages["message_id"],
        "borrower_id": messages["borrower_id"],
        "sent_at": messages["sent_at"],
        "lender": messages["lender_name"],
        "predicted_class": messages["predicted_class"],
        "label_from": messages["label_source"],
        "late_night": messages["late_night"],
        "third_party": messages["third_party"],
        "recipient_type": messages["recipient_type"],
        "text": messages["text"],
    }).reset_index(drop=True)

    return {
        "row": row,
        "explanation": explain(row, cfg),
        "points": points,
        "loans": loan_table,
        "lenders_involved": int(loan_table["lender"].nunique()),
        "timeline": timeline,
        "messages": message_table,
    }


def lender_detail(data: DashboardData, lender_id: str, cfg: dict) -> dict:
    """One lender's comparison row, a plain sentence, and fixed example messages per abusive class."""
    rows = data.lenders[data.lenders["lender_id"] == lender_id]
    if rows.empty:
        raise KeyError(f"Unknown lender {lender_id!r}")
    row = rows.iloc[0]
    per_class = int(cfg["dashboard"]["example_messages_per_class"])
    seed = int(cfg["dashboard"]["example_seed"])
    own = data.messages[data.messages["lender_id"] == lender_id].sort_values("message_id")
    examples = {}
    for name in cfg["lender_comparison"]["abusive_classes"]:
        pool = own[own["predicted_class"] == name]
        picked = pool.sample(n=min(per_class, len(pool)), random_state=seed).sort_values("sent_at")
        examples[name] = picked[["message_id", "predicted_class", "sent_at", "recipient_type", "text"]].reset_index(
            drop=True)
    return {"row": row, "sentence": explain_lender(row, cfg, data.classifier), "examples": examples}


def ranked_lenders(data: DashboardData) -> pd.DataFrame:
    return data.lenders[data.lenders["rank"].notna()].reset_index(drop=True)


def unranked_lenders(data: DashboardData) -> pd.DataFrame:
    return data.lenders[data.lenders["rank"].isna()].reset_index(drop=True)


def lender_table(lenders: pd.DataFrame) -> pd.DataFrame:
    """The lender comparison as shown on screen. Shares are percentages (0-100)."""
    return pd.DataFrame({
        "Rank": lenders["rank"],
        "Lender": lenders["name"],
        "Size": lenders["size_category"],
        "Messages": lenders["n_messages"],
        "Abusive %": (lenders["abusive_share"] * 100).round(1),
        "Interval": [f"{low:.0%} to {high:.0%}" for low, high in zip(lenders["abusive_low"], lenders["abusive_high"])],
        "Threat %": (lenders["threat_share"] * 100).round(1),
        "Shaming %": (lenders["shaming_share"] * 100).round(1),
        "Third-party %": (lenders["third_party_share"] * 100).round(1),
        "Late-night %": (lenders["late_night_share"] * 100).round(1),
        "Msgs per borrower": lenders["messages_per_borrower"].round(1),
    })


def signal_weights(cfg: dict) -> pd.DataFrame:
    """The five score signals with their weights and full-points values, read from config.yaml."""
    risk = cfg["risk"]
    full_key = {"open_lenders": "open_lenders", "debt_to_income": "debt_to_income", "arrears": "arrears",
                "cycling": "cycling_events", "loan_velocity": "loans_in_window"}
    return pd.DataFrame({
        "Signal": [SIGNAL_LABELS[s] for s in RISK_SIGNALS],
        "What it measures": [SIGNAL_DESCRIPTIONS[s] for s in RISK_SIGNALS],
        "Full points at": [risk["full_at"][full_key[s]] for s in RISK_SIGNALS],
        "Weight": [risk["weights"][s] for s in RISK_SIGNALS],
    })


def class_table() -> pd.DataFrame:
    return pd.DataFrame({"Class": list(MESSAGE_CLASSES), "Meaning": [CLASS_DESCRIPTIONS[c] for c in MESSAGE_CLASSES]})


def _csv_bytes(frame: pd.DataFrame, notice: str) -> bytes:
    """CSV with the synthetic-data notice as a first '#' line. Read back with pandas.read_csv(..., comment='#')."""
    header = f"# {notice} {REVIEW_LINE}\n"
    return (header + frame.to_csv(index=False, lineterminator="\n")).encode("utf-8")


def flagged_borrowers_csv(borrowers: pd.DataFrame, notice: str = DEFAULT_NOTICE) -> bytes:
    """The given (already filtered) borrowers as CSV bytes, plain English column names."""
    return _csv_bytes(borrowers[list(BORROWER_EXPORT_COLUMNS)].rename(columns=BORROWER_EXPORT_COLUMNS), notice)


def lender_comparison_csv(lenders: pd.DataFrame, classifier: str, notice: str = DEFAULT_NOTICE,
                          human_share: float = 0.0) -> bytes:
    """The lender comparison as CSV bytes, with a column naming the classifier behind the labels."""
    frame = lenders[list(LENDER_EXPORT_COLUMNS)].rename(columns=LENDER_EXPORT_COLUMNS)
    frame["labels_from_classifier"] = classifier
    frame["share_of_labels_checked_by_a_person"] = round(float(human_share), 4)  # those labels replace the model's
    return _csv_bytes(frame, notice)


# --- Featured cases for the Guided Demo (Phase 5.2) ------------------------------------------------------

BORROWERS_PAGE = "pages/1_Borrowers.py"
LENDERS_PAGE = "pages/2_Lenders.py"


def _first(frame: pd.DataFrame, by: list[str], ascending: list[bool]) -> pd.Series | None:
    """The first row after a stable sort (ties go to the order of the last key, normally the id)."""
    if frame.empty:
        return None
    return frame.sort_values(by, ascending=ascending, kind="mergesort").iloc[0]


def featured_cases(data: DashboardData, cfg: dict) -> dict:
    """Example borrowers and lenders for the Guided Demo, chosen BY RULES FROM COMPUTED SIGNALS ONLY.

    Uses scores, bands, the cycling rule, message counts and the lender ranking (never answer labels).
    Thresholds come from the 'demo' section of config.yaml. Deterministic: ties go to the lowest id.
    Returns {"cases": [...], "missing": [plain sentences]}; a rule that finds nobody is left out and
    named in "missing". Each case has step, key, title, kind ('borrower' or 'lender'), id, page and say.
    """
    rules = cfg["demo"]
    borrowers = data.borrowers if data.ok else pd.DataFrame()
    lenders = data.lenders if data.ok else pd.DataFrame()
    level = f"{cfg['lender_comparison']['confidence']:.0%}"
    found, missing = [], []

    def add(key, title, kind, row, say):
        ident = row["borrower_id"] if kind == "borrower" else row["lender_id"]
        found.append({"key": key, "title": title, "kind": kind, "id": str(ident),
                      "page": BORROWERS_PAGE if kind == "borrower" else LENDERS_PAGE, "say": say})

    needed = {"band", "score", "band_forced_by_cycling", "open_lenders", "debt_to_income", "abusive_messages"}
    usable = not borrowers.empty and needed <= set(borrowers.columns)

    row = _first(borrowers[borrowers["band"] == "high"], ["score", "borrower_id"], [False, True]) if usable else None
    if row is None:
        missing.append("No borrower is in the high band, so there is no top-risk example.")
    else:
        add("top_high", "The highest-risk borrower", "borrower", row,
            f"Borrower {row['borrower_id']} scores {row['score']:.0f} of 100: {int(row['open_lenders'])} open lenders "
            f"and debt of {row['debt_to_income']:.1f} times monthly income. No single lender could see this.")

    pool = (borrowers[borrowers["band_forced_by_cycling"].astype(bool) & (borrowers["band"] == "medium")]
            if usable else pd.DataFrame())
    row = _first(pool, ["cycling_events", "borrower_id"], [False, True]) if not pool.empty else None
    if row is None:
        missing.append("No borrower was placed in medium by the cycling rule.")
    else:
        add("cycling", "Borrowing to repay (the cycling rule)", "borrower", row,
            f"Borrower {row['borrower_id']} scores only {row['score']:.0f}, but took {int(row['cycling_events'])} "
            "new loans within days of repaying others, so the rule lifts them to medium for a person to look at.")

    if usable:
        pool = borrowers[(borrowers["open_lenders"] >= int(rules["many_lenders_min_open"]))
                         & (borrowers["debt_to_income"] < float(rules["many_lenders_max_dti"]))
                         & (borrowers["band"] != "high")]
    row = _first(pool, ["open_lenders", "debt_to_income", "borrower_id"], [False, True, True]) if usable else None
    if row is None:
        missing.append(f"No borrower has {rules['many_lenders_min_open']}+ open lenders with debt under "
                       f"{rules['many_lenders_max_dti']} times income outside the high band.")
    else:
        add("many_lenders", "Many lenders, little debt", "borrower", row,
            f"Borrower {row['borrower_id']} has {int(row['open_lenders'])} open lenders but owes only "
            f"{row['debt_to_income']:.2f} times monthly income, and stays in the {row['band']} band: "
            "the score is not just a count of lenders.")

    if usable and {"late_night_messages", "third_party_messages"} <= set(borrowers.columns):
        pool = borrowers[(borrowers["abusive_messages"] >= int(rules["harassed_min_abusive"]))
                         & ((borrowers["late_night_messages"] > 0) | (borrowers["third_party_messages"] > 0))]
    else:
        pool = pd.DataFrame()
    row = _first(pool, ["abusive_messages", "borrower_id"], [False, True]) if not pool.empty else None
    if row is None:
        missing.append("No borrower received abusive messages together with late-night or third-party ones.")
    else:
        add("harassed", "The most harassed borrower", "borrower", row,
            f"Borrower {row['borrower_id']} received {int(row['abusive_messages'])} messages labelled abusive, "
            f"{int(row['late_night_messages'])} late at night and {int(row['third_party_messages'])} sent to "
            "other people. Read them on the borrower's page.")

    unranked = lenders[lenders["rank"].isna()] if not lenders.empty else pd.DataFrame()
    row = _first(unranked, ["n_messages", "lender_id"], [True, True]) if not unranked.empty else None
    if row is None:
        missing.append("Every lender has enough messages to be ranked, so there is no 'too few' example.")
    else:
        add("unranked", "A lender too small to rank", "lender", row,
            f"{row['name']} sent only {int(row['n_messages'])} messages: {row['reason']}. Its share is too "
            f"uncertain ({level} interval {row['abusive_low']:.0%} to {row['abusive_high']:.0%}) to compare fairly.")

    top = lenders[lenders["rank"] == 1] if not lenders.empty else pd.DataFrame()
    row = top.iloc[0] if not top.empty else None
    if row is None:
        missing.append("No lender has enough messages to be ranked.")
    else:
        add("top_lender", "The top-ranked lender", "lender", row,
            f"{row['name']} ranks first: {row['abusive_share']:.0%} of its {int(row['n_messages']):,} messages were "
            f"labelled abusive, and even the low end of the {level} interval is {row['abusive_low']:.0%}. "
            "That means read its messages, not that it broke the law.")

    for number, case in enumerate(found, start=1):
        case["step"] = number
    return {"cases": found, "missing": missing}


# --- Gemini second opinion, read only (Phase 3B) ---------------------------------------------------------------

def gemini_summary(cfg: dict) -> dict | None:
    """The last saved summary of `python -m src.gemini_check` (counts only, no text), or None.

    Read from classifier.gemini.summary_file. The dashboard never calls the network; this only reads a file.
    """
    import json

    path = Path(cfg["classifier"]["gemini"]["summary_file"])
    path = path if path.is_absolute() else Path(__file__).resolve().parents[1] / path
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    needed = {"messages", "local_vs_truth", "gemini_vs_truth", "local_vs_gemini", "disagreeing_phrasings"}
    return summary if isinstance(summary, dict) and needed <= set(summary) else None
