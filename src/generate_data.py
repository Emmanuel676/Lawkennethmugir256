"""Seeded synthetic data generator.

Builds a made-up lending world: borrowers, lenders, loans, transactions and
collection messages. Nothing here describes a real person or company.

Run it from the project folder:

    python -m src.generate_data

The same seed and config always give exactly the same data. The answer labels
(which borrower is which kind, which class and template each message came from)
are written to a SEPARATE database, ground_truth.db. Detection code must never
read it. It exists only to measure how well the detectors work.

Borrower profiles (PRD section 8.2):
    typical     one or two loans, repaid on time, polite reminders
    stacked     three or more loans from different lenders in a short period
    cycling     a chain of loans, each repaying the one before, running up to today
    harassed    heavy arrears, frequent, late-night or threatening messages
    look_alike  several loans open at once, but high income and low debt (tests false alarms)

Test set: messages written from held-out phrasings (see templates.py) are the
only ones that can be test messages, so a classifier is tested on wording it
has never seen. The message split is 'dev', 'test' or 'reserve' (see db.py).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from src import db
from src.config import MESSAGE_CLASSES, PROFILES, load_config, resolve_path
from src.templates import TEMPLATE_POOLS

GENERATOR_VERSION = "2"
SYNTHETIC_NOTICE = "SYNTHETIC DATA: generated for a prototype. It describes no real people, loans, lenders or messages."
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_SMS_SHORTHAND = [
    (r"\bplease\b", "pls"),
    (r"\byour\b", "ur"),
    (r"\byou\b", "u"),
    (r"\btoday\b", "2day"),
    (r"\bwith\b", "wit"),
    (r"\band\b", "n"),
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _round_to(value: float, step: int) -> int:
    """Round a number to the nearest multiple of step, as a plain int."""
    return int(round(value / step) * step)


def _clip(value: int, low: int, high: int) -> int:
    return int(min(max(value, low), high))


def _fmt_date(day: date) -> str:
    """'12 Sep' style date, independent of the computer's language settings."""
    return f"{day.day} {MONTHS[day.month - 1]}"


def _days_text(days: int) -> str:
    """'1 day' or '5 days'."""
    return f"{days} day" if days == 1 else f"{days} days"


def _iso(day: date) -> str:
    return day.isoformat()


def late_night_hours(cfg: dict) -> list[int]:
    """The hours of the day counted as late night, from the config (default 21:00 to 05:59)."""
    window = cfg["generator"]["late_night"]
    return [h for h in range(24) if h >= window["start_hour"] or h < window["end_hour"]]


def is_holdout_template(template_id: str) -> bool:
    """True if a template id such as 'threat:H01' names a held-out phrasing."""
    return template_id.split(":")[1].startswith("H")


def _swap_letters(text: str, rng: np.random.Generator) -> str:
    """Swap two neighbouring letters inside one word, like a typing slip."""
    words = text.split(" ")
    candidates = [i for i, word in enumerate(words) if len(word) >= 5 and word.isalpha()]
    if not candidates:
        return text
    index = candidates[int(rng.integers(0, len(candidates)))]
    word = words[index]
    j = int(rng.integers(1, len(word) - 2))
    words[index] = word[:j] + word[j + 1] + word[j] + word[j + 2:]
    return " ".join(words)


def add_noise(text: str, rng: np.random.Generator) -> str:
    """Make a message look more like a real SMS: typos, shorthand, missing punctuation.

    Amounts are never altered (a comma may be dropped, so 250,000 can become 250000).
    """
    for _ in range(int(rng.integers(1, 3))):
        kind = int(rng.integers(0, 5))
        if kind == 0:
            text = text.lower()
        elif kind == 1:
            text = re.sub(r"[.,]", "", text)
        elif kind == 2:
            text = _swap_letters(text, rng)
        elif kind == 3:
            for pattern, replacement in _SMS_SHORTHAND:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        else:
            text = text.rstrip(".") + "!!"
    return text


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def _build_lenders(cfg: dict) -> tuple[list[dict], np.ndarray, list[str], list[str], list[int | None]]:
    """Lender rows, how likely each is to be picked, behaviours, short brand names and loan caps."""
    rows, weights, behaviours, brands, caps = [], [], [], [], []
    for number, spec in enumerate(cfg["lenders"], start=1):
        rows.append({
            "lender_id": f"L{number:02d}",
            "name": spec["name"],
            "size_category": spec["size"],
        })
        weights.append(float(cfg["lender_sizes"][spec["size"]]))
        behaviours.append(spec["behaviour"])
        brands.append(spec["name"].replace(" (Demo)", ""))
        caps.append(spec.get("max_loans"))
    return rows, np.array(weights), behaviours, brands, caps


def _assign_profiles(n_borrowers: int, mix: dict[str, float], rng: np.random.Generator) -> list[str]:
    """Give every borrower a profile, in exactly the configured proportions."""
    total = sum(mix.values())
    counts = {name: int(n_borrowers * share / total) for name, share in mix.items()}
    counts["typical"] += n_borrowers - sum(counts.values())  # leftovers become typical borrowers
    labels = [name for name in PROFILES for _ in range(counts[name])]
    order = rng.permutation(len(labels))
    return [labels[i] for i in order]


def _plan_loans(
    profile: str,
    spec: dict,
    as_of: date,
    lender_weights: np.ndarray,
    lender_behaviours: list[str],
    micro_lenders: np.ndarray,
    cfg: dict,
    rng: np.random.Generator,
) -> list[dict]:
    """Decide how many loans a borrower has, from which lenders, and when.

    lender_weights already has any lender that reached its max_loans set to zero.
    micro_lenders is True for the tiny lenders. Harassed borrowers never use them, because
    one harassed borrower in arrears produces about 19 messages and would push a tiny
    lender over the 'too small to rank' line.
    """
    cycling = profile == "cycling"
    # A cycling chain keeps going until it reaches today; n_loans[1] is only a safety cap.
    count = spec["n_loans"][1] if cycling else int(rng.integers(spec["n_loans"][0], spec["n_loans"][1] + 1))
    weights = lender_weights.copy()
    if profile == "harassed":
        bias = cfg["messages"]["harassed_lender_bias"]
        weights = weights * np.array([bias[b] for b in lender_behaviours])
        weights[micro_lenders] = 0.0
    probabilities = weights / weights.sum()
    distinct = bool(spec["distinct_lenders"])
    picked = rng.choice(len(weights), size=count, replace=not distinct, p=probabilities)

    term_low, term_high = spec["term_days"]
    ago_low, ago_high = spec["issue_days_ago"]
    plans: list[dict] = []

    if cycling:
        # A chain: each new loan is taken out about when the previous one falls due,
        # and its money is used to repay that previous loan. It stops once it reaches today.
        issue = as_of - timedelta(days=int(rng.integers(ago_low, ago_high + 1)))
        for lender_index in picked:
            term = int(rng.integers(term_low, term_high + 1))
            plans.append({"lender_idx": int(lender_index), "issue": issue, "term_days": term})
            issue = issue + timedelta(days=term + int(rng.integers(-2, 3)))
            if issue > as_of:
                break
        return plans

    for lender_index in picked:
        ago = int(rng.integers(ago_low, ago_high + 1))
        term = int(rng.integers(term_low, term_high + 1))
        plans.append({
            "lender_idx": int(lender_index),
            "issue": as_of - timedelta(days=ago),
            "term_days": term,
        })
    return plans


def _resolve_status(
    rng: np.random.Generator,
    arrears_prob: float,
    late_fee_range: list[float],
    as_of: date,
    issue: date,
    due: date,
    amount_due: int,
    force_repaid: bool,
) -> tuple[str, int]:
    """Work out whether a loan is active, repaid or in arrears, and what is still owed."""
    if force_repaid:
        return "repaid", 0
    if due >= as_of:
        if (as_of - issue).days >= 1 and rng.random() < 0.30:
            return "active", _round_to(amount_due * float(rng.uniform(0.4, 0.9)), 100)
        return "active", amount_due
    if rng.random() < arrears_prob:
        late = float(rng.uniform(late_fee_range[0], late_fee_range[1]))
        return "in_arrears", _round_to(amount_due * (1 + late), 100)
    return "repaid", 0


def _background_transactions(
    borrower_id: str, income: int, as_of: date, rng: np.random.Generator
) -> list[dict]:
    """Ordinary money in and out, so loan transactions are not the only thing in the data."""
    rows = []
    for month in range(3):
        if rng.random() < 0.80:
            day = as_of - timedelta(days=int(rng.integers(month * 30, month * 30 + 30)))
            counterparty = ("employer", "agent", "peer")[int(rng.choice(3, p=[0.60, 0.25, 0.15]))]
            rows.append({
                "borrower_id": borrower_id,
                "txn_date": day,
                "amount": max(1000, _round_to(income * float(rng.uniform(0.8, 1.1)), 1000)),
                "direction": "in",
                "counterparty_type": counterparty,
                "linked_loan_id": None,
            })
    for _ in range(int(rng.integers(4, 9))):
        day = as_of - timedelta(days=int(rng.integers(0, 90)))
        rows.append({
            "borrower_id": borrower_id,
            "txn_date": day,
            "amount": max(500, _round_to(income * float(rng.uniform(0.01, 0.12)), 500)),
            "direction": "out",
            "counterparty_type": "merchant",
            "linked_loan_id": None,
        })
    return rows


def _sent_at(rng: np.random.Generator, day: date, late_prob: float, late_hours: list[int]) -> datetime:
    """A time of day: office hours normally, late at night with the given probability."""
    if rng.random() < late_prob:
        hour = int(late_hours[int(rng.integers(0, len(late_hours)))])
    else:
        hour = int(rng.integers(8, 19))
    return datetime(day.year, day.month, day.day, hour, int(rng.integers(0, 60)), int(rng.integers(0, 60)))


def _render(
    rng: np.random.Generator, pool: str, noise_rate: float, holdout_prob: float, **values
) -> tuple[str, str]:
    """Fill in a template from the named pool and return (text, template_id).

    With probability holdout_prob the template comes from the held-out phrasings.
    Sometimes the text is then made to look like a messy real SMS.
    """
    development, holdout = TEMPLATE_POOLS[pool]
    use_holdout = bool(holdout) and rng.random() < holdout_prob
    templates = holdout if use_holdout else development
    index = int(rng.integers(0, len(templates)))
    text = templates[index].format(**values)
    if rng.random() < noise_rate:
        text = add_noise(text, rng)
    return text, f"{pool}:{'H' if use_holdout else 'D'}{index:02d}"


def _class_probabilities(cfg: dict, behaviour: str, harassed: bool) -> tuple[np.ndarray, float]:
    """How likely each message class is for this lender and borrower, and the late-night chance."""
    spec = cfg["lender_behaviour"][behaviour]
    probs = np.array([spec["class_probs"][c] for c in MESSAGE_CLASSES], dtype=float)
    late = float(spec["late_night_prob"])
    if harassed:
        abusive = np.array([cfg["lender_behaviour"]["abusive"]["class_probs"][c] for c in MESSAGE_CLASSES])
        shift = float(cfg["messages"]["harassed_class_shift"])
        probs = (1 - shift) * probs + shift * abusive
        late = min(1.0, late + float(cfg["messages"]["harassed_late_night_bonus"]))
    return probs / probs.sum(), late


def _loan_messages(
    rng: np.random.Generator,
    cfg: dict,
    *,
    profile: str,
    behaviour: str,
    brand: str,
    lender_id: str,
    borrower_id: str,
    issue: date,
    due: date,
    status: str,
    amount_due: int,
    outstanding: int,
    late_fee: int,
    as_of: date,
    late_hours: list[int],
) -> list[dict]:
    """Collection messages about one loan: reminders, and pressure if it is in arrears."""
    noise_rate = float(cfg["generator"]["noise_rate"])
    holdout_prob = float(cfg["generator"]["holdout_template_prob"])
    harassed = profile == "harassed"
    messages: list[dict] = []

    # Friendly reminders just before the due date. Always sent in office hours.
    reminder_count = int(rng.integers(1, 3))
    offsets = sorted(int(o) for o in rng.choice([3, 2, 1, 0], size=reminder_count, replace=False))
    for offset in offsets:
        day = due - timedelta(days=offset)
        if day > as_of or day <= issue:
            continue
        sent_at = _sent_at(rng, day, 0.0, late_hours)
        text, template_id = _render(
            rng, "normal_pre", noise_rate, holdout_prob,
            amount=f"{amount_due:,}", lender=brand, due_date=_fmt_date(due),
            days_text="0 days", fee="0",
        )
        messages.append({
            "lender_id": lender_id,
            "borrower_id": borrower_id,
            "recipient_type": "borrower",
            "sent_at": sent_at,
            "text": text,
            "true_class": "normal",
            "template_id": template_id,
        })

    if status != "in_arrears":
        return messages

    # Collection messages after a missed payment. Style depends on the lender and the borrower.
    probs, late_prob = _class_probabilities(cfg, behaviour, harassed)
    low, high = cfg["lender_behaviour"][behaviour]["overdue_messages"]
    count = int(rng.integers(low, high + 1))
    if harassed:
        count = max(1, int(round(count * float(cfg["messages"]["harassed_volume_multiplier"]))))
    days_overdue = (as_of - due).days  # at least 1, because an overdue loan is past its due date
    for _ in range(count):
        days_late_when_sent = int(rng.integers(1, days_overdue + 1))
        day = due + timedelta(days=days_late_when_sent)
        message_class = MESSAGE_CLASSES[int(rng.choice(len(MESSAGE_CLASSES), p=probs))]
        recipient = "borrower"
        if message_class == "normal":
            pool = "normal_post"
        elif message_class == "firm_pressure":
            pool = "firm"
        elif message_class == "threat":
            pool = "threat"
        elif rng.random() < float(cfg["messages"]["shaming_third_party_prob"]):
            recipient, pool = "third_party", "shaming_third"
        else:
            pool = "shaming_direct"
        sent_at = _sent_at(rng, day, late_prob, late_hours)
        text, template_id = _render(
            rng, pool, noise_rate, holdout_prob,
            amount=f"{outstanding:,}", lender=brand, due_date=_fmt_date(due),
            days_text=_days_text(days_late_when_sent), fee=f"{late_fee:,}",
        )
        messages.append({
            "lender_id": lender_id,
            "borrower_id": borrower_id,
            "recipient_type": recipient,
            "sent_at": sent_at,
            "text": text,
            "true_class": message_class,
            "template_id": template_id,
        })
    return messages


def _pick_test_set(
    holdout_ids_by_class: dict[str, list[str]], size: int, rng: np.random.Generator
) -> set[str]:
    """Choose the test set from held-out-phrasing messages, balanced across the classes where possible."""
    per_class = size // len(MESSAGE_CLASSES)
    chosen: set[str] = set()
    for message_class in MESSAGE_CLASSES:
        ids = holdout_ids_by_class[message_class]
        take = min(per_class, len(ids))
        if take:
            for index in rng.choice(len(ids), size=take, replace=False):
                chosen.add(ids[int(index)])
    return chosen


def _check_tiny_lenders(lender_rows: list[dict], messages: list[dict], minimum: int) -> None:
    """A 'micro' lender must have fewer messages than the minimum, so the 'too small to rank' case exists."""
    totals: dict[str, int] = {}
    for message in messages:
        totals[message["lender_id"]] = totals.get(message["lender_id"], 0) + 1
    for row in lender_rows:
        if row["size_category"] == "micro" and totals.get(row["lender_id"], 0) >= minimum:
            raise ValueError(
                f"The tiny lender {row['name']!r} got {totals[row['lender_id']]} messages, which is not below "
                f"the minimum of {minimum}. Lower its weight in 'lender_sizes' or its 'max_loans' in "
                "config.yaml, so there is still a lender that is too small to rank."
            )


# ---------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------

def generate(cfg: dict, seed: int | None = None, n_borrowers: int | None = None) -> dict:
    """Build the whole synthetic world in memory and return it as a dictionary of row lists.

    Keys: meta, lenders, borrowers, loans, transactions, messages (what detectors may see)
    and gt_borrowers, gt_messages, gt_lenders (answer labels, for evaluation only).
    """
    gen = cfg["generator"]
    seed = int(gen["seed"] if seed is None else seed)
    n_borrowers = int(gen["n_borrowers"] if n_borrowers is None else n_borrowers)
    rng = np.random.default_rng(seed)
    as_of = date.fromisoformat(str(cfg["project"]["as_of_date"]))
    late_hours = late_night_hours(cfg)
    loan_cfg = cfg["loans"]

    lender_rows, lender_weights, lender_behaviours, lender_brands, lender_caps = _build_lenders(cfg)
    loan_counts = [0] * len(lender_rows)
    micro_lenders = np.array([row["size_category"] == "micro" for row in lender_rows])
    regions = list(cfg["regions"])
    region_probs = np.array([cfg["regions"][r] for r in regions], dtype=float)
    region_probs = region_probs / region_probs.sum()

    profiles = _assign_profiles(n_borrowers, {name: cfg["profiles"][name]["mix"] for name in PROFILES}, rng)

    borrowers: list[dict] = []
    loans: list[dict] = []
    transactions: list[dict] = []
    raw_messages: list[dict] = []
    gt_borrowers: list[dict] = []
    loan_number = 0

    for number, profile in enumerate(profiles, start=1):
        borrower_id = f"B{number:05d}"
        spec = cfg["profiles"][profile]

        income = max(100_000, _round_to(
            spec["income_median"] * float(np.exp(rng.normal(0.0, spec["income_sigma"]))), 10_000))
        region = regions[int(rng.choice(len(regions), p=region_probs))]

        # A lender that has used up its loan cap cannot be picked any more.
        open_weights = lender_weights.copy()
        for index, cap in enumerate(lender_caps):
            if cap is not None and loan_counts[index] >= cap:
                open_weights[index] = 0.0
        plans = _plan_loans(profile, spec, as_of, open_weights, lender_behaviours, micro_lenders, cfg, rng)
        for plan in plans:
            loan_counts[plan["lender_idx"]] += 1

        earliest_issue = min(plan["issue"] for plan in plans)
        joined = earliest_issue - timedelta(days=int(rng.integers(5, 400)))

        borrowers.append({
            "borrower_id": borrower_id,
            "region": region,
            "monthly_income": int(income),
            "joined_date": _iso(joined),
        })
        gt_borrowers.append({"borrower_id": borrower_id, "profile_type": profile})

        for index, plan in enumerate(plans):
            loan_number += 1
            loan_id = f"TMP{loan_number:07d}"  # renumbered in time order once all loans exist
            lender_index = plan["lender_idx"]
            lender_id = lender_rows[lender_index]["lender_id"]
            issue = plan["issue"]
            due = issue + timedelta(days=plan["term_days"])

            principal = _clip(
                _round_to(income * spec["principal_ratio"] * float(np.exp(rng.normal(0.0, 0.4))), 5_000),
                loan_cfg["principal_min"], loan_cfg["principal_max"],
            )
            fee_rate = float(rng.uniform(loan_cfg["fee_rate_range"][0], loan_cfg["fee_rate_range"][1]))
            amount_due = _round_to(principal * (1 + fee_rate), 100)

            chain_funded = profile == "cycling" and index < len(plans) - 1
            status, outstanding = _resolve_status(
                rng, spec["arrears_prob"], loan_cfg["late_fee_range"],
                as_of, issue, due, amount_due, force_repaid=chain_funded,
            )

            # In arrears, the late fee is what is owed on top of the amount due.
            late_fee = max(0, outstanding - amount_due) if status == "in_arrears" else 0
            partial_paid = 0
            if status == "in_arrears" and rng.random() < float(loan_cfg["arrears_partial_payment_prob"]):
                partial_paid = max(100, _round_to(amount_due * float(rng.uniform(0.2, 0.6)), 100))
                outstanding = outstanding - partial_paid

            loans.append({
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "lender_id": lender_id,
                "principal": int(principal),
                "amount_outstanding": int(outstanding),
                "issue_date": _iso(issue),
                "due_date": _iso(due),
                "status": status,
            })

            # Money moves: the lender pays out, and the borrower repays (fully or partly).
            transactions.append({
                "borrower_id": borrower_id, "txn_date": issue, "amount": int(principal),
                "direction": "in", "counterparty_type": "lender", "linked_loan_id": loan_id,
            })
            if status == "repaid":
                if chain_funded:
                    # Cycling: repaid on the day the next loan arrives (or the day after).
                    repay_date = plans[index + 1]["issue"] + timedelta(days=int(rng.integers(0, 2)))
                else:
                    repay_date = due + timedelta(days=int(rng.integers(-3, 4)))
                repay_date = min(max(repay_date, issue + timedelta(days=1)), as_of)
                transactions.append({
                    "borrower_id": borrower_id, "txn_date": repay_date, "amount": int(amount_due),
                    "direction": "out", "counterparty_type": "lender", "linked_loan_id": loan_id,
                })
            elif status == "active" and outstanding < amount_due:
                span = max(1, min((as_of - issue).days, plan["term_days"]))
                pay_date = issue + timedelta(days=int(rng.integers(1, span + 1)))
                transactions.append({
                    "borrower_id": borrower_id, "txn_date": pay_date, "amount": int(amount_due - outstanding),
                    "direction": "out", "counterparty_type": "lender", "linked_loan_id": loan_id,
                })
            elif status == "in_arrears" and partial_paid:
                # Part of the loan was paid before it fell due; the rest was never paid.
                pay_date = issue + timedelta(days=int(rng.integers(1, plan["term_days"] + 1)))
                transactions.append({
                    "borrower_id": borrower_id, "txn_date": pay_date, "amount": int(partial_paid),
                    "direction": "out", "counterparty_type": "lender", "linked_loan_id": loan_id,
                })

            raw_messages.extend(_loan_messages(
                rng, cfg,
                profile=profile,
                behaviour=lender_behaviours[lender_index],
                brand=lender_brands[lender_index],
                lender_id=lender_id,
                borrower_id=borrower_id,
                issue=issue,
                due=due,
                status=status,
                amount_due=int(amount_due),
                outstanding=int(outstanding),
                late_fee=int(late_fee),
                as_of=as_of,
                late_hours=late_hours,
            ))

        transactions.extend(_background_transactions(borrower_id, int(income), as_of, rng))

    _check_tiny_lenders(lender_rows, raw_messages, int(gen["min_lender_messages"]))

    # Give loans, transactions and messages stable, readable IDs in time order.
    loans.sort(key=lambda r: (r["issue_date"], r["borrower_id"], r["lender_id"], r["principal"], r["due_date"]))
    loan_ids = {row["loan_id"]: f"LN{n:06d}" for n, row in enumerate(loans, start=1)}
    for row in loans:
        row["loan_id"] = loan_ids[row["loan_id"]]
    for txn in transactions:
        if txn["linked_loan_id"] is not None:
            txn["linked_loan_id"] = loan_ids[txn["linked_loan_id"]]

    transactions.sort(key=lambda t: (
        t["txn_date"], t["borrower_id"], t["direction"], t["amount"],
        t["counterparty_type"], t["linked_loan_id"] or "",
    ))
    transaction_rows = [{
        "txn_id": f"T{n:07d}",
        "borrower_id": t["borrower_id"],
        "txn_date": _iso(t["txn_date"]),
        "amount": int(t["amount"]),
        "direction": t["direction"],
        "counterparty_type": t["counterparty_type"],
        "linked_loan_id": t["linked_loan_id"],
    } for n, t in enumerate(transactions, start=1)]

    raw_messages.sort(key=lambda m: (m["sent_at"], m["borrower_id"], m["lender_id"], m["text"]))
    message_rows: list[dict] = []
    holdout_ids_by_class: dict[str, list[str]] = {c: [] for c in MESSAGE_CLASSES}
    truth: list[tuple[str, str, str]] = []
    for n, m in enumerate(raw_messages, start=1):
        message_id = f"M{n:06d}"
        message_rows.append({
            "message_id": message_id,
            "lender_id": m["lender_id"],
            "borrower_id": m["borrower_id"],
            "recipient_type": m["recipient_type"],
            "sent_at": m["sent_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "text": m["text"],
        })
        if is_holdout_template(m["template_id"]):
            holdout_ids_by_class[m["true_class"]].append(message_id)
        truth.append((message_id, m["true_class"], m["template_id"]))

    test_ids = _pick_test_set(holdout_ids_by_class, int(gen["test_set_size"]), rng)
    gt_messages = []
    for message_id, message_class, template_id in truth:
        if not is_holdout_template(template_id):
            split = "dev"
        elif message_id in test_ids:
            split = "test"
        else:
            split = "reserve"
        gt_messages.append({
            "message_id": message_id,
            "true_class": message_class,
            "template_id": template_id,
            "split": split,
        })
    gt_lenders = [
        {"lender_id": row["lender_id"], "behaviour": lender_behaviours[i]}
        for i, row in enumerate(lender_rows)
    ]
    meta = [
        {"key": "synthetic", "value": "true"},
        {"key": "notice", "value": SYNTHETIC_NOTICE},
        {"key": "seed", "value": str(seed)},
        {"key": "as_of_date", "value": _iso(as_of)},
        {"key": "currency", "value": str(cfg["currency"]["code"])},
        {"key": "generator_version", "value": GENERATOR_VERSION},
    ]

    return {
        "meta": meta,
        "lenders": lender_rows,
        "borrowers": borrowers,
        "loans": loans,
        "transactions": transaction_rows,
        "messages": message_rows,
        "gt_borrowers": gt_borrowers,
        "gt_messages": gt_messages,
        "gt_lenders": gt_lenders,
    }


# ---------------------------------------------------------------------------
# Writing to disk and reporting
# ---------------------------------------------------------------------------

def write_world(world: dict, lending_path: Path, ground_truth_path: Path, manifest_path: Path | None = None) -> dict:
    """Write both databases (and a small manifest) and return the manifest as a dictionary."""
    conn = db.create_database(lending_path, db.LENDING_SCHEMA)
    for table in ("meta", "lenders", "borrowers", "loans", "transactions", "messages"):
        db.insert_rows(conn, table, world[table])
    conn.commit()
    lending_counts = db.row_counts(conn)
    lending_hash = db.content_hash(conn)
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    if violations:
        raise RuntimeError(f"Foreign key problems found in the generated data: {violations[:5]}")

    truth_conn = db.create_database(ground_truth_path, db.GROUND_TRUTH_SCHEMA)
    for table in ("gt_borrowers", "gt_messages", "gt_lenders"):
        db.insert_rows(truth_conn, table, world[table])
    truth_conn.commit()
    truth_counts = db.row_counts(truth_conn)
    truth_hash = db.content_hash(truth_conn)
    truth_conn.close()

    meta = {row["key"]: row["value"] for row in world["meta"]}
    test_by_class = {c: 0 for c in MESSAGE_CLASSES}
    split_counts = {"dev": 0, "test": 0, "reserve": 0}
    for row in world["gt_messages"]:
        split_counts[row["split"]] += 1
        if row["split"] == "test":
            test_by_class[row["true_class"]] += 1

    manifest = {
        "seed": int(meta["seed"]),
        "as_of_date": meta["as_of_date"],
        "generator_version": meta["generator_version"],
        "synthetic": True,
        "lending_db_rows": lending_counts,
        "ground_truth_db_rows": truth_counts,
        "lending_db_content_hash": lending_hash,
        "ground_truth_db_content_hash": truth_hash,
        "message_split_counts": split_counts,
        "test_set_by_class": test_by_class,
    }
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def summarise(world: dict, late_hours: list[int]) -> str:
    """A plain-text report of what was generated, for the person running the command."""
    lines: list[str] = []
    meta = {row["key"]: row["value"] for row in world["meta"]}
    lines.append(f"Synthetic dataset, seed {meta['seed']}, as of {meta['as_of_date']}")
    lines.append("")
    lines.append("Rows written to lending.db:")
    for table in ("lenders", "borrowers", "loans", "transactions", "messages"):
        lines.append(f"  {table:<14}{len(world[table]):>9,}")

    profile_counts: dict[str, int] = {}
    for row in world["gt_borrowers"]:
        profile_counts[row["profile_type"]] = profile_counts.get(row["profile_type"], 0) + 1
    lines.append("")
    lines.append("Borrower profiles (answer labels):")
    for name in PROFILES:
        lines.append(f"  {name:<14}{profile_counts.get(name, 0):>9,}")

    class_by_message = {row["message_id"]: row["true_class"] for row in world["gt_messages"]}
    class_counts = {c: 0 for c in MESSAGE_CLASSES}
    for cls in class_by_message.values():
        class_counts[cls] += 1
    lines.append("")
    lines.append("Message classes (answer labels):")
    for cls in MESSAGE_CLASSES:
        lines.append(f"  {cls:<22}{class_counts[cls]:>9,}")

    split_counts = {"dev": 0, "test": 0, "reserve": 0}
    for row in world["gt_messages"]:
        split_counts[row["split"]] += 1
    lines.append("")
    lines.append("Message split (answer labels):")
    for name, note in (("dev", "free to use for tuning"), ("test", "held out, accuracy only"),
                       ("reserve", "held-out phrasing, keep out of tuning")):
        lines.append(f"  {name:<14}{split_counts[name]:>9,}   {note}")

    behaviour = {row["lender_id"]: row["behaviour"] for row in world["gt_lenders"]}
    names = {row["lender_id"]: row["name"] for row in world["lenders"]}
    late_set = set(late_hours)
    totals: dict[str, int] = {}
    abusive: dict[str, int] = {}
    late: dict[str, int] = {}
    for message in world["messages"]:
        lender_id = message["lender_id"]
        totals[lender_id] = totals.get(lender_id, 0) + 1
        if class_by_message[message["message_id"]] in ("threat", "shaming_third_party"):
            abusive[lender_id] = abusive.get(lender_id, 0) + 1
        if int(message["sent_at"][11:13]) in late_set:
            late[lender_id] = late.get(lender_id, 0) + 1
    lines.append("")
    lines.append("Messages per lender (abusive = threat or shaming; late = sent in the late-night hours from the config):")
    lines.append(f"  {'lender':<30}{'type':<12}{'messages':>9}{'abusive':>9}{'late':>8}")
    for lender_id in sorted(totals):
        total = totals[lender_id]
        lines.append(
            f"  {names[lender_id]:<30}{behaviour[lender_id]:<12}{total:>9,}"
            f"{abusive.get(lender_id, 0) / total:>9.1%}{late.get(lender_id, 0) / total:>8.1%}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic lending dataset.")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--seed", type=int, help="Random seed (default: from config).")
    parser.add_argument("--borrowers", type=int, help="Number of borrowers (default: from config).")
    parser.add_argument("--out-dir", help="Write the databases here instead of the paths in the config.")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    lending_path = resolve_path(cfg, "lending_db")
    truth_path = resolve_path(cfg, "ground_truth_db")
    manifest_path = resolve_path(cfg, "manifest")
    if args.out_dir:
        out_dir = Path(args.out_dir)
        lending_path = out_dir / lending_path.name
        truth_path = out_dir / truth_path.name
        manifest_path = out_dir / manifest_path.name

    world = generate(cfg, seed=args.seed, n_borrowers=args.borrowers)
    manifest = write_world(world, lending_path, truth_path, manifest_path)

    print(summarise(world, late_night_hours(cfg)))
    print("")
    requested = int(cfg["generator"]["test_set_size"])
    got = sum(manifest["test_set_by_class"].values())
    print(f"Test set (held-out phrasings, labelled): {got} messages {manifest['test_set_by_class']}")
    if got < requested:
        print(f"WARNING: asked for {requested} test messages but only {got} were possible. "
              "Use more borrowers or raise generator.holdout_template_prob.")
    print(f"Fingerprint of lending.db: {manifest['lending_db_content_hash'][:16]}")
    print(f"Wrote {lending_path}")
    print(f"Wrote {truth_path}  (answer labels: for evaluation only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
