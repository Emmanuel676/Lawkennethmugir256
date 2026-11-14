"""JSON views: lay out what the existing engine computed. Pure functions of a Snapshot, no HTTP, no logic.

Every number comes from src/ (dashboard_data, repayments, money, overlap.explain), called the same way the
Streamlit pages call it, so the web interface shows the same figures. Money is sent as an exact integer
plus the strings the Streamlit app shows (format_money / format_money_compact). Message text is redacted.
"""

from __future__ import annotations

import json

import pandas as pd

from src import repayments as rp
from src.config import RISK_SIGNALS
from src.dashboard_data import (BANDS, CLASS_DESCRIPTIONS, REVIEW_LINE, SIGNAL_DESCRIPTIONS, SORT_OPTIONS,
                                band_distribution, borrower_detail, coverage_sentence, filter_borrowers,
                                lender_detail, overview_kpis, page_count, page_slice, ranked_lenders,
                                sort_borrowers, top_borrowers, unranked_lenders)
from src.money import currency_code, format_money, format_money_compact

from api.data_source import Snapshot

TRUST_LINE = "Synthetic data. A flag is a prompt for a human to look, not a verdict."
OWED_NOTE = "The total owed includes loans that are not yet due."
BAND_LABELS = {"high": "High", "medium": "Medium", "low": "Low"}
CLASS_LABELS = {"normal": "Normal", "firm_pressure": "Firm pressure", "threat": "Threat",
                "shaming_third_party": "Shaming or third party"}
GLOSSARY = {
    "overlap_score": ("Overlap score: 0 to 100 points from five signals (open lenders, debt to income, arrears, "
                      "cycling, loan velocity). A high score means a person should look; it is not proof of "
                      "over-indebtedness."),
    "band": "Band: the score grouped as Low, Medium or High using the thresholds in config.yaml.",
    "cycling": SIGNAL_DESCRIPTIONS["cycling"],
    "grace_period": None,  # filled in from the config in meta()
    "labelled_abusive": ("Labelled abusive: a model labelled the message a threat or shaming. Labels are a "
                         "model's guesses until a person checks them."),
    "confidence_interval": ("Confidence interval: the range the true share probably lies in. Lenders are ranked "
                            "by its lower end, so a small lender cannot top the list by luck."),
    "too_small": "Too small to rank: fewer messages than the minimum, so its share is too uncertain to compare.",
}
FOLLOW_UP_SORT_KEYS = {"days_past_due": "Days past due", "owed_overdue": "Amount owed (overdue)",
                       "loans_overdue": "Loans overdue", "borrower_id": "Borrower code"}
BORROWER_SORT_KEYS = {column: label for label, column in SORT_OPTIONS.items()}


class BadRequest(ValueError):
    """A query value the API does not accept. The message is safe to show."""


def records(frame: pd.DataFrame) -> list[dict]:
    """DataFrame rows as plain JSON values (numpy types become Python ones, NaN becomes null)."""
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=10))


def money(amount, cfg: dict) -> dict:
    return {"amount": None if pd.isna(amount) else int(round(float(amount))),
            "exact": format_money(amount, cfg), "compact": format_money_compact(amount, cfg)}


def _band(band: str) -> dict:
    return {"key": band, "label": BAND_LABELS.get(band, str(band).title())}


def dataset_info(snap: Snapshot) -> dict:
    """Which dataset this is. 'synthetic' is True for the built-in demo only: an imported dataset passed the
    synthetic-only check, which does not prove it is synthetic, so it is labelled as imported instead."""
    data = snap.data
    return {"name": snap.name, "slug": snap.slug, "kind": snap.kind, "label": snap.label,
            "synthetic": snap.kind == "demo" and bool(data.synthetic), "as_of_date": data.as_of_date,
            "notice": snap.notice, "trust_line": snap.trust_line, "classifier": data.classifier,
            "currency": currency_code(snap.cfg)}


# --- health and meta -------------------------------------------------------------------------------

def meta(snap: Snapshot) -> dict:
    cfg = snap.cfg
    glossary = dict(GLOSSARY)
    glossary["grace_period"] = (f"Grace period: {cfg['repayments']['grace_days']} days after the due date before a "
                                "late repayment counts as late beyond grace. One setting for every lender.")
    return {
        "product": {"name": cfg["project"]["name"], "tagline": cfg["project"]["tagline"]},
        "dataset": dataset_info(snap),
        "trust_line": snap.trust_line,
        "review_line": REVIEW_LINE,
        "presentation_mode": snap.kind == "demo",
        "read_only": True,
        "bands": [{**_band(b), "min_score": float(cfg["risk"]["bands"].get(b, 0))} for b in BANDS],
        "message_classes": [{"key": k, "label": CLASS_LABELS[k], "description": CLASS_DESCRIPTIONS[k],
                             "abusive": k in cfg["lender_comparison"]["abusive_classes"]} for k in CLASS_LABELS],
        "glossary": glossary,
    }


# --- overview --------------------------------------------------------------------------------------

def overview(snap: Snapshot) -> dict:
    data, cfg = snap.data, snap.cfg
    k = overview_kpis(data, cfg)
    top_n = int(cfg["dashboard"]["top_n"])
    top = top_borrowers(data, top_n)
    bands = band_distribution(data)
    return {
        "dataset": dataset_info(snap),
        "trust_line": snap.trust_line,
        "kpis": {
            "borrowers_scored": k["borrowers_scored"],
            "band_counts": k["band_counts"],
            "band_shares": k["band_shares"],
            "owed_by_high_band": money(k["owed_by_high_band"], cfg),
            "messages_classified": k["messages_classified"],
            "abusive_message_share": k["abusive_message_share"],
            "lenders_ranked": k["lenders_ranked"],
            "lenders_unranked": k["lenders_unranked"],
            "flagged_and_harassed": k["flagged_and_harassed"],
            "concern_min_abusive_messages": k["concern_min_abusive_messages"],
        },
        "bands": [{**_band(r.band), "borrowers": int(r.borrowers),
                   "share": k["band_shares"][r.band]} for r in bands.itertuples()],
        "top_n": top_n,
        "top_borrowers": [{"borrower_id": r.borrower_id, "score": float(r.score), "band": _band(r.band),
                           "open_lenders": int(r.open_lenders), "total_owed": money(r.total_owed, cfg),
                           "abusive_messages": int(r.abusive_messages)} for r in top.itertuples()],
        "coverage": coverage_sentence(data),
    }


# --- borrowers -------------------------------------------------------------------------------------

def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _borrower_row(r, cfg: dict) -> dict:
    return {"borrower_id": r.borrower_id, "score": float(r.score), "band": _band(r.band),
            "placed_in_medium_by_cycling": bool(r.band_forced_by_cycling), "region": r.region,
            "open_lenders": int(r.open_lenders), "total_owed": money(r.total_owed, cfg),
            "debt_to_income": float(r.debt_to_income), "abusive_messages": int(r.abusive_messages),
            "late_night_messages": int(r.late_night_messages), "third_party_messages": int(r.third_party_messages)}


def borrowers(snap: Snapshot, bands: str | None = None, regions: str | None = None, min_score: float = 0.0,
              min_open_lenders: int = 0, min_abusive: int = 0, q: str = "", sort: str = "score",
              order: str = "desc", page: int = 1, page_size: int | None = None) -> dict:
    data, cfg = snap.data, snap.cfg
    band_list = _split(bands)
    if any(b not in BANDS for b in band_list):
        raise BadRequest("bands must be a comma-separated list of high, medium, low.")
    if sort not in BORROWER_SORT_KEYS:
        raise BadRequest(f"sort must be one of: {', '.join(BORROWER_SORT_KEYS)}.")
    if order not in ("asc", "desc"):
        raise BadRequest("order must be asc or desc.")
    size = int(page_size or cfg["dashboard"]["table_page_size"])
    if not 1 <= size <= 200:
        raise BadRequest("page_size must be between 1 and 200.")
    all_rows = data.borrowers
    filtered = sort_borrowers(
        filter_borrowers(all_rows, bands=band_list, regions=_split(regions), min_score=min_score,
                         min_open_lenders=min_open_lenders, min_abusive_messages=min_abusive, id_search=q),
        BORROWER_SORT_KEYS[sort], order == "asc")
    pages = page_count(len(filtered), size)
    page = min(max(1, int(page)), pages)
    return {
        "total": int(len(all_rows)), "matching": int(len(filtered)), "page": page, "pages": pages,
        "page_size": size, "sort": sort, "order": order,
        "sortable": list(BORROWER_SORT_KEYS),
        "regions": sorted(all_rows["region"].dropna().unique().tolist()),
        "items": [_borrower_row(r, cfg) for r in page_slice(filtered, page, size).itertuples()],
    }


def borrower(snap: Snapshot, borrower_id: str) -> dict:
    data, cfg = snap.data, snap.cfg
    detail = borrower_detail(data, borrower_id, cfg)  # KeyError for an unknown id
    row = detail["row"]
    loans = detail["loans"]
    messages = detail["messages"]
    abusive = set(cfg["lender_comparison"]["abusive_classes"])
    return {
        "borrower_id": borrower_id,
        "score": float(row["score"]), "band": _band(row["band"]),
        "placed_in_medium_by_cycling": bool(row["band_forced_by_cycling"]),
        "region": row["region"], "open_lenders": int(row["open_lenders"]),
        "total_owed": money(row["total_owed"], cfg), "monthly_income": money(row["monthly_income"], cfg),
        "debt_to_income": float(row["debt_to_income"]), "arrears_share": float(row["arrears_share"]),
        "cycling_events": int(row["cycling_events"]), "recent_loans": int(row["loans_in_window"]),
        "abusive_messages": int(row["abusive_messages"]),
        "explanation": list(detail["explanation"]),
        "points": [{"key": s, "signal": p.signal, "points": float(p.points), "max_points": float(p.max_points),
                    "description": SIGNAL_DESCRIPTIONS[s]}
                   for s, p in zip(RISK_SIGNALS, detail["points"].itertuples())],
        "lenders_involved": detail["lenders_involved"],
        "loans": [{"loan_id": r.loan_id, "lender": r.lender, "principal": money(r.principal, cfg),
                   "owed": money(r.owed, cfg), "issue_date": r.issue_date, "due_date": r.due_date,
                   "status": r.status} for r in loans.itertuples()],
        "messages": [{"message_id": r.message_id, "sent_at": r.sent_at, "lender": r.lender,
                      "label": {"key": r.predicted_class, "label": CLASS_LABELS.get(r.predicted_class,
                                                                                    str(r.predicted_class)),
                                "abusive": r.predicted_class in abusive},
                      "label_from": r.label_from, "late_night": bool(r.late_night),
                      "third_party": bool(r.third_party), "recipient_type": r.recipient_type,
                      "text": snap.redact(r.text)} for r in messages.itertuples()],
        "classifier": data.classifier,
    }


# --- lenders ---------------------------------------------------------------------------------------

def _lender_row(r) -> dict:
    ranked = not pd.isna(r.rank)
    return {"rank": int(r.rank) if ranked else None, "lender_id": r.lender_id, "name": r.name,
            "size": r.size_category, "messages": int(r.n_messages), "too_small": not ranked,
            "reason": None if ranked or pd.isna(r.reason) else r.reason,
            "abusive_share": float(r.abusive_share), "interval_low": float(r.abusive_low),
            "interval_high": float(r.abusive_high), "threat_share": float(r.threat_share),
            "shaming_share": float(r.shaming_share), "third_party_share": float(r.third_party_share),
            "late_night_share": float(r.late_night_share),
            "messages_per_borrower": float(r.messages_per_borrower)}


def lenders(snap: Snapshot) -> dict:
    data, cfg = snap.data, snap.cfg
    return {
        "confidence": float(cfg["lender_comparison"]["confidence"]),
        "min_messages": int(cfg["generator"]["min_lender_messages"]),
        "coverage": coverage_sentence(data),
        "ranked": [_lender_row(r) for r in ranked_lenders(data).itertuples()],
        "unranked": [_lender_row(r) for r in unranked_lenders(data).itertuples()],
    }


def lender(snap: Snapshot, lender_id: str) -> dict:
    data, cfg = snap.data, snap.cfg
    detail = lender_detail(data, lender_id, cfg)  # KeyError for an unknown id
    return {
        **_lender_row(detail["row"]),
        "sentence": detail["sentence"],
        "examples": [{"class": {"key": name, "label": CLASS_LABELS.get(name, name)},
                      "messages": [{"message_id": m.message_id, "sent_at": m.sent_at,
                                    "recipient_type": m.recipient_type, "text": snap.redact(m.text)}
                                   for m in frame.itertuples()]}
                     for name, frame in detail["examples"].items()],
    }


# --- repayments ------------------------------------------------------------------------------------

def repayments(snap: Snapshot) -> dict:
    cfg, result = snap.cfg, snap.repayments
    head, settings = result["headline"], cfg["repayments"]
    mix = result["lender_mix"]
    worst = result["rollup"]["worst_status"].value_counts()
    return {
        "dataset": dataset_info(snap),
        "trust_line": snap.trust_line,
        "owed_note": OWED_NOTE,
        "prompt": rp.PROMPT,
        "lump": bool(result["lump"]),
        "loans": head["loans"],
        "statuses": [{"key": s, "label": rp.LABELS[s], "loans": head["counts"][s], "share": head["shares"][s],
                      "follow_up": s in rp.FOLLOW_UP} for s in rp.STATUSES],
        "owed_unpaid": money(head["owed_unpaid"], cfg),
        "owed_follow_up": money(head["owed_follow_up"], cfg),
        "grace_days": int(settings["grace_days"]),
        "not_paying_after_days": int(settings["not_paying_after_days"]),
        "min_loans_to_compare": int(settings["min_loans_to_compare"]),
        "ageing": [{"bucket": r.bucket, "loans": int(r.loans), "owed": money(r.owed, cfg)}
                   for r in result["ageing"].itertuples()],
        "lender_mix": [{"lender_id": r["lender_id"], "name": r["name"], "loans": int(r["loans"]),
                        "comparable": bool(r["comparable"]),
                        "shares": {s: float(r[f"share_{s}"]) for s in rp.STATUSES}}
                       for _, r in mix.iterrows()],
        "worst_status": [{"key": s, "label": rp.LABELS[s], "borrowers": int(worst.get(s, 0))} for s in rp.STATUSES],
        "follow_up_borrowers": int(len(rp.follow_up(result["rollup"]))),
        "limits": list(rp.LIMITS),
    }


def _follow_up_rows(snap: Snapshot, lenders: str | None, statuses: str | None, bands: str | None, sort: str,
                    order: str) -> pd.DataFrame:
    status_list, band_list = _split(statuses), _split(bands)
    if any(s not in rp.FOLLOW_UP for s in status_list):
        raise BadRequest(f"statuses must be a comma-separated list of {', '.join(rp.FOLLOW_UP)}.")
    if any(b not in BANDS for b in band_list):
        raise BadRequest("bands must be a comma-separated list of high, medium, low.")
    if sort not in FOLLOW_UP_SORT_KEYS:
        raise BadRequest(f"sort must be one of: {', '.join(FOLLOW_UP_SORT_KEYS)}.")
    if order not in ("asc", "desc"):
        raise BadRequest("order must be asc or desc.")
    lender_list = [part.strip() for part in (lenders or "").split("|") if part.strip()]
    return rp.follow_up(snap.repayments["rollup"], lenders=lender_list, statuses=status_list, bands=band_list,
                        sort_label=FOLLOW_UP_SORT_KEYS[sort], ascending=order == "asc")


def follow_up(snap: Snapshot, lenders: str | None = None, statuses: str | None = None, bands: str | None = None,
              sort: str = "days_past_due", order: str = "desc", page: int = 1, page_size: int = 25) -> dict:
    cfg = snap.cfg
    if not 1 <= int(page_size) <= 200:
        raise BadRequest("page_size must be between 1 and 200.")
    rows = _follow_up_rows(snap, lenders, statuses, bands, sort, order)
    rollup = snap.repayments["rollup"]
    pages = page_count(len(rows), int(page_size))
    page = min(max(1, int(page)), pages)
    return {
        "matching": int(len(rows)), "page": page, "pages": pages, "page_size": int(page_size),
        "sort": sort, "order": order, "sortable": list(FOLLOW_UP_SORT_KEYS),
        "options": {
            "lenders": sorted({n for s in rollup["overdue_lenders"] for n in s.split("; ") if n}),
            "statuses": [{"key": s, "label": rp.LABELS[s]} for s in rp.FOLLOW_UP],
            "bands": [_band(b) for b in BANDS],
        },
        "items": [{"borrower_id": r.borrower_id, "lenders_overdue": r.overdue_lenders,
                   "status": {"key": r.worst_status, "label": rp.LABELS[r.worst_status]},
                   "days_past_due": int(r.days_past_due), "owed_overdue": money(r.owed_overdue, cfg),
                   "owed_all_loans": money(r.owed, cfg), "loans_overdue": int(r.loans_overdue),
                   "band": _band(r.band) if isinstance(r.band, str) else None,
                   "open_lenders": None if pd.isna(r.open_lenders) else int(r.open_lenders)}
                  for r in page_slice(rows, page, int(page_size)).itertuples()],
    }


def follow_up_csv(snap: Snapshot, lenders: str | None = None, statuses: str | None = None, bands: str | None = None,
                  sort: str = "days_past_due", order: str = "desc") -> bytes:
    """The same CSV the Streamlit download gives: first line '#' with the dataset notice and the prompt wording."""
    rows = _follow_up_rows(snap, lenders, statuses, bands, sort, order)
    return rp.follow_up_csv(rows, snap.notice)
