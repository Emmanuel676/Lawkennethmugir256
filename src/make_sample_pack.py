"""Synthetic sample lender packs for practising imports (Phase 9A). No network.

    python -m src.make_sample_pack                      # all five scenarios into sample_pack\
    python -m src.make_sample_pack --scenario cycling   # one scenario
    .\\dev.ps1 -SamplePack

Each scenario is written in the exact import format (CSV per table, the columns of src/import_data.py):

    sample_pack\\<scenario>\\lender_A\\lenders.csv, borrowers.csv, loans.csv, transactions.csv, messages.csv
    sample_pack\\<scenario>\\lender_B\\...          one folder per lender, to import one after the other
    sample_pack\\<scenario>\\all_lenders\\...       the same rows in one set, for a single import
    sample_pack\\_answer_keys\\<scenario>\\*_truth.csv   who was generated as what (tests and evaluation ONLY)

The answer key sits OUTSIDE the scenario folders and its file names do not end in a table name, so it can
never be picked up by an import. Detection and dashboard code never read it (a test checks this).

EVERYTHING IS SYNTHETIC: fictional "(Demo)" lenders; borrower codes made with the real borrower-code code
(src/make_borrower_codes.py) from invented phone numbers and a FAKE salt (the numbers are never written);
every message ends with the synthetic marker. The same seed gives byte-identical files, and the seed is not
written into any of them. Field facts and assumptions are settings in the sample_pack section of config.yaml.

This module is separate from the demo generator (src/generate_data.py), which it does not use or change.
"""

from __future__ import annotations

import argparse
import csv
import math
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from src.config import MESSAGE_CLASSES, PROJECT_ROOT, SAMPLE_PACK_SCENARIOS, ConfigError, load_config
from src.import_data import COLUMNS, TABLES
from src.make_borrower_codes import make_code
from src.sample_pack_templates import TEMPLATES

ALL_LENDERS = "all_lenders"
ANSWER_DIR = "_answer_keys"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
TRUTH_COLUMNS = {
    "borrower_truth": ["borrower_id", "role", "n_lenders", "lenders", "high_overlap", "cycler", "payer_scope",
                       "payer_type", "loans_not_paid", "bad_payer"],
    "loan_truth": ["loan_id", "lender_letter", "borrower_id", "payer_kind", "total_due", "late_charge",
                   "cleared_date", "status_at_as_of"],
    "message_truth": ["message_id", "lender_letter", "loan_id", "true_class", "kind", "sent_before_due",
                      "late_night", "quoted_amount", "balance_at_send", "quoted_exact", "language"],
}
NOTICE = ("SYNTHETIC SAMPLE PACK for practising imports. Fictional '(Demo)' lenders, borrower codes made with a "
          "FAKE salt from invented phone numbers, no real people or data. Never mix it with real data.")


def _r100(value: float) -> int:
    return int(round(value / 100.0) * 100)


def _fmt_day(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]}"


def _days_text(days: int) -> str:
    return f"{days} day" if days == 1 else f"{days} days"


def output_root(cfg: dict, out_dir: str | Path | None = None) -> Path:
    if out_dir:
        return Path(out_dir)
    path = Path(cfg["sample_pack"]["output_dir"])
    return path if path.is_absolute() else PROJECT_ROOT / path


class _Loan:
    """One simulated loan: its daily payments, what was due when, and its state on the as-of date."""

    def __init__(self, issue: date, principal: int, pack: dict, as_of: date):
        loans = pack["loans"]
        self.issue, self.principal, self.as_of = issue, principal, as_of
        self.term = int(loans["term_days"])
        self.due = issue + timedelta(days=self.term)
        self.total0 = _r100(principal * (1 + float(loans["interest_flat"])))
        self.charge_day = int(loans["late_charge_day"])
        self.charge_rate = float(loans["late_charge_rate"])
        self.late_charge = 0
        self.payments: list[tuple[date, int]] = []  # every payment, including any after as_of (cut later)
        self.cleared: date | None = None

    def plan_daily(self, clear_offset: int | None, stop_offset: int | None) -> None:
        """Pay every day. clear_offset: the day of the loan it is cleared; stop_offset: the day payments stop."""
        last = clear_offset or stop_offset
        per_day = self.total0 / (clear_offset or self.term)
        paid = 0
        for day in range(1, last + 1):
            if day == self.charge_day + 1:  # the late charge was added at the end of charge_day
                balance = self.total0 - paid
                if balance > 0:
                    self.late_charge = _r100(self.charge_rate * balance)
                    per_day = (balance + self.late_charge) / max(1, last - self.charge_day)
            if clear_offset and day == last:
                amount = self.total0 + self.late_charge - paid
            else:
                amount = max(100, _r100(per_day))
            if amount <= 0:
                break
            self.payments.append((self.issue + timedelta(days=day), amount))
            paid += amount
        if stop_offset and stop_offset < self.charge_day:  # a non-payer is still charged on day 33
            self.late_charge = _r100(self.charge_rate * (self.total0 - paid))
        if clear_offset:
            self.cleared = self.issue + timedelta(days=clear_offset)

    def plan_payoff(self, pay_days: int, payoff: date) -> None:
        """Cycler: daily payments for pay_days, then the rest in one payment on the payoff date."""
        per_day = max(100, _r100(self.total0 / self.term))
        paid = 0
        for day in range(1, pay_days + 1):
            self.payments.append((self.issue + timedelta(days=day), per_day))
            paid += per_day
        self.payments.append((payoff, self.total0 - paid))
        self.cleared = payoff

    def charge_applies(self, when: date) -> bool:
        return self.late_charge > 0 and (when - self.issue).days > self.charge_day

    def balance_on(self, when: date) -> int:
        """What is still owed at the start of a day (payments made earlier that day are not yet counted)."""
        due = self.total0 + (self.late_charge if self.charge_applies(when) else 0)
        return max(0, due - sum(a for d, a in self.payments if d < when))

    def state(self) -> tuple[str, int]:
        if self.cleared is not None and self.cleared <= self.as_of:
            return "repaid", 0
        owed = max(100, self.balance_on(self.as_of + timedelta(days=1)))
        return ("active" if self.due >= self.as_of else "in_arrears"), owed


class _ScenarioBuilder:
    def __init__(self, cfg: dict, scenario: str, overrides: dict | None = None):
        self.cfg, self.pack = cfg, cfg["sample_pack"]
        self.spec = dict(self.pack["scenarios"][scenario])
        self.scenario = scenario
        self.repay = dict(self.pack["repayment"])
        for key, value in (overrides or {}).items():  # evaluation only, e.g. {"link_share": 0.0}
            (self.repay if key in self.repay else self.spec)[key] = value
        self.rng = np.random.default_rng([int(self.pack["seed"]), SAMPLE_PACK_SCENARIOS.index(scenario)])
        self.as_of = date.fromisoformat(str(self.pack["as_of_date"]))
        self.lenders = {spec["letter"]: spec for spec in self.pack["lenders"]}
        self.letters = list(self.lenders)
        self.loan_counts = {x: 0 for x in self.letters}
        self.rows = {x: {t: [] for t in TABLES} for x in self.letters}
        self.counters = {x: {"loan": 0, "txn": 0, "msg": 0} for x in self.letters}
        self.borrower_rows: dict[str, dict] = {}
        self.borrower_letters: dict[str, set[str]] = {}
        self.truth = {name: [] for name in TRUTH_COLUMNS}

    # --- choices --------------------------------------------------------------------------------------------
    def _int(self, pair) -> int:
        return int(self.rng.integers(int(pair[0]), int(pair[1]) + 1))

    def _open(self, letter: str) -> bool:
        cap = self.lenders[letter].get("max_loans")
        return cap is None or self.loan_counts[letter] < int(cap)

    def _pick_lenders(self, count: int, exclude=()) -> list[str]:
        pool = [x for x in self.letters if x not in exclude and self._open(x)]
        count = min(count, len(pool))
        if not pool or count == 0:
            return []
        weights = np.array([float(self.lenders[x]["weight"]) for x in pool])
        picked = self.rng.choice(len(pool), size=count, replace=False, p=weights / weights.sum())
        return [pool[int(i)] for i in picked]

    def _payer_kind(self) -> str:
        split = self.repay["payer_split"]
        kinds = list(split)
        return kinds[int(self.rng.choice(len(kinds), p=np.array([split[k] for k in kinds], dtype=float)))]

    def _principal(self) -> int:
        loans = self.pack["loans"]
        value = float(loans["principal_typical"]) * math.exp(float(self.rng.normal(0, float(loans["principal_sigma"]))))
        step = int(loans["principal_round"])
        return int(min(max(round(value / step) * step, loans["principal_min"]), loans["principal_max"]))

    # --- rows -------------------------------------------------------------------------------------------------
    def _next(self, letter: str, kind: str) -> int:
        self.counters[letter][kind] += 1
        return self.counters[letter][kind]

    def _add_loan(self, borrower: str, letter: str, loan: _Loan, payer_kind: str) -> str:
        self.loan_counts[letter] += 1
        loan_id = f"{letter}-LN{self._next(letter, 'loan'):05d}"
        status, owed = loan.state()
        self.rows[letter]["loans"].append({
            "loan_id": loan_id, "borrower_id": borrower, "lender_id": f"L{letter}", "principal": loan.principal,
            "amount_outstanding": owed, "issue_date": loan.issue.isoformat(), "due_date": loan.due.isoformat(),
            "status": status})
        self._txn(borrower, letter, loan.issue, loan.principal, "in", loan_id)
        link_share = float(self.repay["link_share"])
        for day, amount in loan.payments:
            if day > self.as_of:
                break
            linked = loan_id if self.rng.random() < link_share else None
            self._txn(borrower, letter, day, amount, "out", linked)
        self.borrower_letters.setdefault(borrower, set()).add(letter)
        self.truth["loan_truth"].append({
            "loan_id": loan_id, "lender_letter": letter, "borrower_id": borrower, "payer_kind": payer_kind,
            "total_due": loan.total0, "late_charge": loan.late_charge,
            "cleared_date": loan.cleared.isoformat() if loan.cleared and loan.cleared <= self.as_of else "",
            "status_at_as_of": status})
        self._messages(borrower, letter, loan_id, loan, payer_kind)
        return loan_id

    def _txn(self, borrower, letter, day, amount, direction, loan_id) -> None:
        self.rows[letter]["transactions"].append({
            "txn_id": f"{letter}-T{self._next(letter, 'txn'):06d}", "borrower_id": borrower,
            "txn_date": day.isoformat(), "amount": int(amount), "direction": direction,
            "counterparty_type": "lender", "linked_loan_id": loan_id})

    # --- messages ---------------------------------------------------------------------------------------------
    def _class_probs(self, letter: str, pre_due_pressure: bool = False) -> dict[str, float]:
        probs = dict(self.pack["behaviour"][self.lenders[letter]["behaviour"]]["class_probs"])
        if not self.spec["abusive"]:
            probs["threat"] = probs["shaming_third_party"] = 0.0
        if pre_due_pressure:
            probs["normal"] = 0.0
        total = sum(probs.values())
        return {k: v / total for k, v in probs.items()}

    def _hour(self, late_prob: float) -> int:
        if self.rng.random() < late_prob:
            return int(self.rng.integers(0, 5))  # 00:00-04:59
        low, high = self.pack["messages"]["staff_hours"]
        return int(self.rng.integers(int(low), int(high) + 1))

    def _message(self, borrower, letter, loan_id, loan, day, message_class, kind, late_prob) -> None:
        msgs = self.pack["messages"]
        balance = loan.balance_on(day)
        if balance <= 0:
            return
        quoted = balance if msgs["quote_remaining_balance"] else loan.total0
        if kind in ("overdue", "overdue_after_clear") and self.rng.random() >= float(msgs["exact_balance_prob"]):
            quoted = (int(math.ceil(balance / 10_000.0) * 10_000) if self.rng.random() < 0.5
                      else loan.total0 + (loan.late_charge if loan.charge_applies(day) else 0))
        recipient, pool = "borrower", message_class
        if message_class == "shaming_third_party":
            if self.rng.random() < float(msgs["shaming_third_party_prob"]):
                recipient = "third_party"
            else:
                pool = "shaming_borrower"
        language = "mixed" if self.rng.random() < float(msgs["mixed_language_prob"]) else "english"
        options = TEMPLATES[pool][language]
        brand = self.lenders[letter]["name"].replace(" (Demo)", "")
        text = options[int(self.rng.integers(0, len(options)))].format(
            amount=f"{int(quoted):,}", lender=brand, due_date=_fmt_day(loan.due),
            days_text=_days_text(max(1, (day - loan.due).days)))
        hour = self._hour(late_prob)
        sent = datetime(day.year, day.month, day.day, hour, int(self.rng.integers(0, 60)), int(self.rng.integers(0, 60)))
        message_id = f"{letter}-M{self._next(letter, 'msg'):05d}"
        self.rows[letter]["messages"].append({
            "message_id": message_id, "lender_id": f"L{letter}", "borrower_id": borrower,
            "recipient_type": recipient, "sent_at": sent.strftime("%Y-%m-%d %H:%M:%S"),
            "text": text + str(self.pack["message_suffix"])})
        self.truth["message_truth"].append({
            "message_id": message_id, "lender_letter": letter, "loan_id": loan_id, "true_class": message_class,
            "kind": kind, "sent_before_due": day <= loan.due, "late_night": hour < 5, "quoted_amount": int(quoted),
            "balance_at_send": int(balance), "quoted_exact": int(quoted) == int(balance), "language": language})

    def _draw_class(self, probs: dict[str, float]) -> str:
        names = list(MESSAGE_CLASSES)
        return names[int(self.rng.choice(len(names), p=np.array([probs[c] for c in names])))]

    def _messages(self, borrower, letter, loan_id, loan: _Loan, payer_kind: str) -> None:
        msgs = self.pack["messages"]
        behaviour = self.pack["behaviour"][self.lenders[letter]["behaviour"]]
        reminders = self._int(msgs["reminders_per_loan"])
        for before in sorted(int(x) for x in self.rng.choice([3, 2, 1], size=min(3, reminders), replace=False)):
            day = loan.due - timedelta(days=before)
            if loan.issue < day <= self.as_of and (loan.cleared is None or day < loan.cleared):
                self._message(borrower, letter, loan_id, loan, day, "normal", "reminder",
                              float(msgs["late_night_reminder_prob"]))
        abusive_lender = self.lenders[letter]["behaviour"] == "abusive" and self.spec["abusive"]
        if abusive_lender and self.rng.random() < float(msgs["abusive_before_due_prob"]):
            day = loan.due - timedelta(days=self._int([1, 3]))
            if loan.issue < day <= self.as_of and (loan.cleared is None or day < loan.cleared):
                self._message(borrower, letter, loan_id, loan, day, self._draw_class(self._class_probs(letter, True)),
                              "pre_due_pressure", float(behaviour["late_night_prob"]))
        first_overdue = loan.due + timedelta(days=1)
        if first_overdue > self.as_of:
            return
        if loan.cleared is None or loan.cleared > self.as_of:
            kind, count = "overdue", self._int(msgs["overdue_messages"])
            last = min(self.as_of, loan.due + timedelta(days=int(msgs["overdue_window_days"])))
        elif loan.cleared > first_overdue and payer_kind == "late_cleared" \
                and self.rng.random() < float(msgs["late_cleared_overdue_prob"]):
            kind, count = "overdue_after_clear", self._int([1, 3])
            last = loan.cleared - timedelta(days=1)
        else:
            return
        span = (last - first_overdue).days
        probs = self._class_probs(letter)
        for _ in range(count):
            day = first_overdue + timedelta(days=int(self.rng.integers(0, span + 1)))
            self._message(borrower, letter, loan_id, loan, day, self._draw_class(probs), kind,
                          float(behaviour["late_night_prob"]))

    # --- borrowers ----------------------------------------------------------------------------------------------
    def _new_code(self) -> str:
        while True:  # an invented number, used only to make the code; it is never written anywhere
            phone = "07" + "".join(str(int(d)) for d in self.rng.integers(0, 10, size=8))
            code = make_code(phone, str(self.pack["fake_salt"]))
            if code not in self.borrower_rows:
                return code

    def _chain(self, borrower: str, letter: str, payer_type: str | None) -> int:
        """Loans from one lender: daily repayments, re-borrowing after clearing. Returns loans not paid."""
        not_paid = 0
        issue = self.as_of - timedelta(days=self._int(self.repay["history_days"]))
        while issue <= self.as_of and self._open(letter):
            kind = payer_type or self._payer_kind()
            loan = _Loan(issue, self._principal(), self.pack, self.as_of)
            if kind == "on_time":
                loan.plan_daily(loan.term, None)
            elif kind == "late_cleared":
                loan.plan_daily(loan.term + self._int(self.repay["late_clear_days"]), None)
            else:
                loan.plan_daily(None, self._int(self.repay["not_paid_stop_day"]))
            self._add_loan(borrower, letter, loan, kind)
            if kind == "not_paid":
                not_paid += 1
                break
            if loan.cleared is None or loan.cleared > self.as_of or self.rng.random() >= float(self.repay["reborrow_prob"]):
                break
            issue = loan.cleared + timedelta(days=self._int(self.repay["reborrow_gap_days"]))
        return not_paid

    def _cycler(self, borrower: str) -> list[str]:
        """Repays each loan with a new loan from ANOTHER lender, up to the as-of date."""
        cyc = self.pack["cyclers"]
        used: list[str] = []
        current = self._pick_lenders(1)
        if not current:
            return used
        letter = current[0]
        issue = self.as_of - timedelta(days=self._int(cyc["start_days_ago"]))
        while True:
            used.append(letter)
            loan = _Loan(issue, self._principal(), self.pack, self.as_of)
            pay_days = self._int(cyc["pay_days_before_switch"])
            switch = issue + timedelta(days=pay_days)
            nxt = self._pick_lenders(1, exclude=(letter,))
            if switch > self.as_of or not nxt:
                loan.plan_daily(loan.term, None)  # the last loan of the chain, paid daily as usual
                self._add_loan(borrower, letter, loan, "on_time")
                return used
            loan.plan_payoff(pay_days, switch + timedelta(days=self._int(cyc["payoff_delay_days"])))
            self._add_loan(borrower, letter, loan, "refinanced")
            letter, issue = nxt[0], switch

    def build(self) -> None:
        borrowers = self.pack["borrowers"]
        regions = list(borrowers["regions"])
        region_p = np.array([borrowers["regions"][r] for r in regions], dtype=float)
        counts = {int(k): float(v) for k, v in borrowers["multi_lender_count"].items()}
        count_keys = sorted(counts)
        # Exact shares, shuffled (a coin flip per borrower can miss "about 30%" by several points).
        n = int(self.spec["borrowers"])
        n_cyclers = int(round(n * float(self.spec["cycler_share"])))
        n_multi = int(round((n - n_cyclers) * float(self.spec["multi_lender_share"])))
        roles = ["cycler"] * n_cyclers + ["multi"] * n_multi + ["single"] * (n - n_cyclers - n_multi)
        roles = [roles[int(i)] for i in self.rng.permutation(len(roles))]
        for planned in roles:
            code = self._new_code()
            income = max(int(borrowers["income_min"]), int(round(float(borrowers["income_median"]) * math.exp(
                float(self.rng.normal(0, float(borrowers["income_sigma"])))), -4)))
            region = regions[int(self.rng.choice(len(regions), p=region_p / region_p.sum()))]
            self.borrower_rows[code] = {"borrower_id": code, "region": region, "monthly_income": income,
                                        "joined_date": ""}
            payer_type = self._payer_kind() if self.spec["payer_scope"] == "borrower" else None
            not_paid = 0
            if planned == "cycler":
                role, used = "cycler", self._cycler(code)
            else:
                k = count_keys[int(self.rng.choice(len(count_keys), p=np.array([counts[c] for c in count_keys])
                                                   / sum(counts.values())))] if planned == "multi" else 1
                role, used = planned, self._pick_lenders(k)
                for letter in used:
                    not_paid += self._chain(code, letter, payer_type)
            letters = sorted(self.borrower_letters.get(code, set()))
            if not letters:  # every lender it could use was full: drop the borrower
                del self.borrower_rows[code]
                continue
            first = min(r["issue_date"] for x in letters for r in self.rows[x]["loans"] if r["borrower_id"] == code)
            self.borrower_rows[code]["joined_date"] = (date.fromisoformat(first) - timedelta(
                days=self._int([5, 300]))).isoformat()
            self.truth["borrower_truth"].append({
                "borrower_id": code, "role": role, "n_lenders": len(letters), "lenders": ";".join(letters),
                "high_overlap": len(letters) >= 2, "cycler": role == "cycler", "payer_scope": self.spec["payer_scope"],
                "payer_type": payer_type or "", "loans_not_paid": not_paid, "bad_payer": not_paid > 0})
        for letter in self.letters:
            self.rows[letter]["lenders"] = [{"lender_id": f"L{letter}", "name": self.lenders[letter]["name"],
                                             "size_category": self.lenders[letter]["size"]}]
            mine = sorted(c for c, used in self.borrower_letters.items() if letter in used and c in self.borrower_rows)
            self.rows[letter]["borrowers"] = [self.borrower_rows[c] for c in mine]
        self._check_small_lender()

    def _check_small_lender(self) -> None:
        small = self.pack["small_lender"]
        letter = small["letter"]
        minimum = int(self.cfg["generator"]["min_lender_messages"])
        mine = [m for m in self.truth["message_truth"] if m["lender_letter"] == letter]
        abusive = sum(m["true_class"] in ("threat", "shaming_third_party") for m in mine)
        if len(mine) >= minimum:
            raise ValueError(f"Scenario {self.scenario}: the small lender {letter} got {len(mine)} messages, not "
                             f"below {minimum}. Lower its weight or max_loans in sample_pack.lenders.")
        if self.spec["abusive"] and abusive < int(small["min_abusive_messages"]):
            raise ValueError(f"Scenario {self.scenario}: the small lender {letter} got only {abusive} abusive "
                             f"messages (need {small['min_abusive_messages']}). Raise its max_loans or "
                             "messages.abusive_before_due_prob, or change sample_pack.seed.")


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if row[c] is None else row[c] for c in columns])


def _safe_remove(root: Path, folder: Path) -> None:
    """Remove a folder this module wrote earlier, and only if it sits inside the pack root."""
    root, folder = root.resolve(), folder.resolve()
    if folder.exists():
        if root not in folder.parents:
            raise ValueError(f"Refusing to remove {folder}: it is not inside {root}.")
        shutil.rmtree(folder)


def build_scenario(cfg: dict, scenario: str, out_root: Path, overrides: dict | None = None) -> dict:
    """Build one scenario and write its files. Returns counts for the printed summary."""
    if scenario not in cfg["sample_pack"]["scenarios"]:
        raise ConfigError(f"There is no sample_pack scenario called {scenario!r}.")
    builder = _ScenarioBuilder(cfg, scenario, overrides)
    builder.build()
    folder, keys = out_root / scenario, out_root / ANSWER_DIR / scenario
    _safe_remove(out_root, folder)
    _safe_remove(out_root, keys)
    combined = {t: [] for t in TABLES}
    for letter in builder.letters:
        for table in TABLES:
            rows = builder.rows[letter][table]
            _write_csv(folder / f"lender_{letter}" / f"{table}.csv", COLUMNS[table], rows)
            combined[table].extend(rows)
    unique_borrowers = {r["borrower_id"]: r for r in combined["borrowers"]}
    combined["borrowers"] = [unique_borrowers[c] for c in sorted(unique_borrowers)]
    for table in TABLES:
        _write_csv(folder / ALL_LENDERS / f"{table}.csv", COLUMNS[table], combined[table])
    for name, columns in TRUTH_COLUMNS.items():
        _write_csv(keys / f"{scenario}_{name}.csv", columns, builder.truth[name])
    (folder / "ABOUT_THIS_PACK.txt").write_text(
        f"{NOTICE}\n\nScenario: {scenario}. Import lender_A, lender_B, lender_C and lender_D one after the other "
        f"on the Data page (or all_lenders in one go). As-of date: {cfg['sample_pack']['as_of_date']}.\n"
        "See docs\\ONBOARDING_DEMO.md.\n", encoding="utf-8")
    truth = builder.truth["borrower_truth"]
    return {"scenario": scenario, "borrowers": len(unique_borrowers), "loans": len(combined["loans"]),
            "transactions": len(combined["transactions"]), "messages": len(combined["messages"]),
            "multi_lender": sum(t["high_overlap"] for t in truth), "cyclers": sum(t["cycler"] for t in truth),
            "bad_payers": sum(t["bad_payer"] for t in truth)}


def build_all(cfg: dict, out_root: Path, scenarios=None) -> list[dict]:
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "README.txt").write_text(NOTICE + "\n\nRebuild with: python -m src.make_sample_pack\n"
                                         "The _answer_keys folder is for tests and evaluation only: never import it.\n",
                                         encoding="utf-8")
    return [build_scenario(cfg, name, out_root) for name in (scenarios or list(cfg["sample_pack"]["scenarios"]))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the synthetic sample lender packs (CSV per table).")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--scenario", action="append", choices=SAMPLE_PACK_SCENARIOS,
                        help="Only this scenario (may be repeated). Default: all.")
    parser.add_argument("--out-dir", help="Write here instead of sample_pack.output_dir.")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if "sample_pack" not in cfg:
        print("config.yaml has no sample_pack section.")
        return 1
    root = output_root(cfg, args.out_dir)
    try:
        results = build_all(cfg, root, args.scenario)
    except ValueError as error:
        print(error)
        return 1
    print(NOTICE)
    print("")
    print(f"{'scenario':<15}{'borrowers':>10}{'2+ lenders':>11}{'cyclers':>9}{'bad payers':>11}{'loans':>8}"
          f"{'repayments':>12}{'messages':>10}")
    for r in results:
        print(f"{r['scenario']:<15}{r['borrowers']:>10,}{r['multi_lender']:>11,}{r['cyclers']:>9,}{r['bad_payers']:>11,}"
              f"{r['loans']:>8,}{r['transactions']:>12,}{r['messages']:>10,}")
    print("")
    print(f"Wrote {root} (git-ignored). Import a lender_<X> folder on the Data page; never import {ANSWER_DIR}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
