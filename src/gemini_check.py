"""A second opinion from Gemini on the demo's SYNTHETIC test split (Phase 3B).

    python -m src.gemini_check            # the active dataset, which must be the demo
    python -m src.gemini_check --dataset demo

An outside check of the local classifier. It is NOT used in the app, NOT used for training,
and NEVER run on real data. It only ever sends the demo's held-out TEST messages: never dev
or reserve messages, never anything from a real dataset.

Safeguards, in the order they are checked:
  1. the dataset must be the demo and its own meta table must say synthetic = 'true'
  2. only messages whose split is 'test' are selected (checked again after selection)
  3. the key is read from the environment variable GEMINI_API_KEY only. It is never printed,
     logged, written to a file or put in a URL, and errors never echo it or any request header
  4. lender names are masked (classifier.local.mask_lender_names) before anything is sent
  5. only DISTINCT texts are sent; answers are mapped back to every message
  6. every valid answer is cached in classifier.gemini.cache_file, keyed by
     sha256(prompt version + model + text), so a run can be stopped and resumed and a cached
     text is never sent again
  7. free-tier limits: batches of batch_size texts, a pause between calls (delay_seconds and
     requests_per_minute), exponential backoff on 429 and 5xx (max_retries), and a hard cap
     of max_calls API calls per run (retries count)
  8. a reply that is not valid JSON, or gives an unknown class, counts as "no answer" for
     those texts. It is never guessed and never cached, so a later run asks again

Output: classifier.gemini.report_file (one row per phrasing: truth vs local vs Gemini, with
one example text), classifier.gemini.summary_file (counts only, no text, for the About page)
and a printed summary. Message text appears only in the report file.

THIS IS A SECOND OPINION ON SYNTHETIC TEXT, NOT PROOF OF REAL-WORLD ACCURACY.

This is an evaluation module: like the evaluate_* modules it reads the answer labels, to
pick the test split and to score both classifiers. The dashboard never imports it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.classify_local import LenderNameMasker, brand_names
from src.config import MESSAGE_CLASSES, PROJECT_ROOT, load_config
from src.datasets import DEMO, DatasetError, DatasetPaths, paths_for
from src.overlap import connect_read_only
from src.predictions import read_predictions

KEY_VARIABLE = "GEMINI_API_KEY"
TEST_SPLIT = "test"
NO_ANSWER = "no answer"
SECOND_OPINION = ("This is a second opinion on SYNTHETIC text from a small set of templates. "
                  "It is not proof of accuracy on real messages.")
MISSING_KEY = (f"{KEY_VARIABLE} is not set in this PowerShell session, so nothing was sent. Set it for this "
               f"session only, without saving it anywhere:\n"
               f"    $env:{KEY_VARIABLE} = Read-Host \"Paste key (will not be saved)\"")

PROMPT = """You label debt-collection text messages (SMS) sent by digital lenders in Uganda.
Choose exactly ONE class for each message:

- normal: a neutral reminder about a payment, before or after the due date. Polite, no pressure beyond the reminder.
- firm_pressure: insistent but lawful: late fees, interest, effects on the credit record or borrowing limit,
  referral to a recovery team, contacting a reference person the borrower agreed to.
- threat: threatens harm or action the lender cannot lawfully take: violence, visits to the home or work,
  arrest or police, seizing property, making the borrower lose their job, harm to family. Veiled threats count.
- shaming_third_party: exposes the debt to other people, or contacts people in the borrower's phone contacts,
  family, colleagues or neighbours about the debt; calls the borrower a thief, cheat or defaulter to others.
  Messages sent straight to the borrower that threaten to shame them before others also count.

The word "lendername" stands for the lender's name. Amounts are in Ugandan shillings (UGX).

Reply with JSON only: a list with one object per message, {{"id": <the message number>, "label": "<class>"}}.

Messages:
{messages}
"""


class CheckRefused(RuntimeError):
    """The check will not run. The message says why in plain words (never anything secret)."""


class TransientError(RuntimeError):
    """A 429 or 5xx reply: worth retrying after a pause."""

    def __init__(self, status: int | None):
        super().__init__(f"temporary error from the service (status {status})")
        self.status = status


class PermanentError(RuntimeError):
    """Any other failure: stop the run (the cache keeps what was done)."""


@dataclass
class Settings:
    model: str
    batch_size: int
    temperature: float
    max_retries: int
    backoff_base_seconds: float
    pause_seconds: float
    max_calls: int
    prompt_version: str
    cache_file: Path
    report_file: Path
    summary_file: Path

    @classmethod
    def from_config(cls, cfg: dict) -> "Settings":
        g = cfg["classifier"]["gemini"]

        def path(key: str) -> Path:
            value = Path(g[key])
            return value if value.is_absolute() else PROJECT_ROOT / value

        return cls(model=str(g["model"]), batch_size=int(g["batch_size"]), temperature=float(g["temperature"]),
                   max_retries=int(g["max_retries"]), backoff_base_seconds=float(g["backoff_base_seconds"]),
                   pause_seconds=max(float(g["delay_seconds"]), 60.0 / float(g["requests_per_minute"])),
                   max_calls=int(g["max_calls"]), prompt_version=str(g["prompt_version"]),
                   cache_file=path("cache_file"), report_file=path("report_file"),
                   summary_file=path("summary_file"))


@dataclass
class RunStats:
    calls: int = 0
    retries: int = 0
    sent_texts: int = 0
    cached_texts: int = 0
    invalid_texts: int = 0
    stopped: str = ""  # why the run stopped early ("" = it finished)
    notes: list[str] = field(default_factory=list)


# --- Choosing what may be sent ------------------------------------------------------------------------------

def select_test_messages(cfg: dict, paths: DatasetPaths) -> pd.DataFrame:
    """The demo's TEST messages with masked text, true class, phrasing and local label.

    Columns: message_id, text (lender names masked), true_class, template_id, local_label.
    Raises CheckRefused for anything but the synthetic demo.
    """
    if paths.name != DEMO:
        raise CheckRefused(f"Refused: '{paths.name}' is not the demo. The Gemini check only ever runs on the "
                           "demo's synthetic test messages. Real data is never sent.")
    if not paths.lending_db.exists():
        raise CheckRefused("Refused: the demo dataset is missing. Rebuild it with: python -m src.build_all")
    lending = connect_read_only(paths.lending_db)
    try:
        meta = dict(lending.execute("SELECT key, value FROM meta"))
        if meta.get("synthetic") != "true":
            raise CheckRefused("Refused: this dataset's meta table does not say synthetic = 'true'. "
                               "Only synthetic data may be sent to Gemini.")
        texts = pd.read_sql_query("SELECT message_id, text FROM messages", lending)
        brands = brand_names([row[0] for row in lending.execute("SELECT name FROM lenders")])
    finally:
        lending.close()
    if paths.ground_truth_db is None or not paths.ground_truth_db.exists():
        raise CheckRefused("Refused: the demo's answer labels are missing, so the test split cannot be "
                           "identified. Rebuild the demo with: python -m src.build_all")
    labels = connect_read_only(paths.ground_truth_db)
    try:
        truth = pd.read_sql_query("SELECT message_id, true_class, template_id, split FROM gt_messages "
                                  "WHERE split = ?", labels, params=(TEST_SPLIT,))
    finally:
        labels.close()
    if truth.empty:
        raise CheckRefused("Refused: the demo has no test messages.")
    if (truth["split"] != TEST_SPLIT).any():  # belt and braces: never dev or reserve
        raise CheckRefused("Refused: a message outside the test split was selected.")
    frame = truth.merge(texts, on="message_id", how="inner", validate="one_to_one")
    if len(frame) != len(truth):
        raise CheckRefused("Refused: some test labels have no message. Rebuild the demo: python -m src.build_all")
    if cfg["classifier"]["local"]["mask_lender_names"]:
        frame["text"] = LenderNameMasker(brands).transform(frame["text"].tolist())
    local = pd.DataFrame(columns=["message_id", "predicted_class"])
    if paths.predictions_db.exists():
        conn = connect_read_only(paths.predictions_db)
        try:
            local = read_predictions(conn, "local")
        finally:
            conn.close()
    frame = frame.merge(local[["message_id", "predicted_class"]].rename(columns={"predicted_class": "local_label"}),
                        on="message_id", how="left")
    return frame[["message_id", "text", "true_class", "template_id", "local_label"]].sort_values(
        "message_id").reset_index(drop=True)


def read_key() -> str:
    """The API key from the environment. Raises CheckRefused (with no secret in it) if it is missing."""
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key:
        raise CheckRefused(MISSING_KEY)
    return key


# --- The cache ---------------------------------------------------------------------------------------------------

def cache_key(text: str, prompt_version: str, model: str) -> str:
    return hashlib.sha256(f"{prompt_version}\n{model}\n{text}".encode("utf-8")).hexdigest()


def load_cache(path: Path) -> dict[str, str]:
    """{cache key: label}. A missing or damaged file is an empty cache."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    answers = raw.get("answers", {}) if isinstance(raw, dict) else {}
    return {k: v for k, v in answers.items() if isinstance(k, str) and v in MESSAGE_CLASSES}


def save_cache(path: Path, answers: dict[str, str]) -> None:
    """Write the cache atomically (a stopped run never leaves a half-written file). Labels only, no text."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"note": "Gemini labels for synthetic demo test texts, keyed by "
                                             "sha256(prompt version + model + text). No text is stored.",
                                     "answers": dict(sorted(answers.items()))}, indent=1), encoding="utf-8")
    os.replace(temporary, path)


# --- Asking ------------------------------------------------------------------------------------------------------

def build_prompt(batch: list[tuple[int, str]]) -> str:
    lines = "\n".join(f"{number}. {json.dumps(text, ensure_ascii=False)}" for number, text in batch)
    return PROMPT.format(messages=lines)


def parse_reply(raw: str, numbers: list[int]) -> dict[int, str]:
    """{message number: class} for the valid entries of a reply. Anything invalid is simply left out."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if isinstance(data, dict):
        data = data.get("labels", data.get("results", []))
    if not isinstance(data, list):
        return {}
    wanted, found = set(numbers), {}
    for item in data:
        if not isinstance(item, dict):
            continue
        number, label = item.get("id"), item.get("label")
        if isinstance(number, bool) or not isinstance(number, int) or number not in wanted:
            continue
        if not isinstance(label, str) or label.strip() not in MESSAGE_CLASSES:
            continue
        if number in found and found[number] != label.strip():
            found[number] = None  # contradictory answers for one message: no answer
            continue
        found[number] = label.strip()
    return {n: label for n, label in found.items() if label is not None}


class GeminiClient:
    """The only code that talks to the network. It is built ONLY inside main(), never in tests."""

    def __init__(self, api_key: str, settings: Settings):
        from google import genai  # imported here: the dashboard and the tests never load the SDK
        from google.genai import types

        self._types = types
        self._settings = settings
        self._client = genai.Client(api_key=api_key)

    def classify(self, prompt: str) -> str:
        from google.genai import errors

        schema = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "id": {"type": "INTEGER"}, "label": {"type": "STRING", "enum": list(MESSAGE_CLASSES)}},
            "required": ["id", "label"]}}
        config = self._types.GenerateContentConfig(temperature=self._settings.temperature,
                                                   response_mime_type="application/json",
                                                   response_schema=schema)
        try:
            response = self._client.models.generate_content(model=self._settings.model, contents=prompt,
                                                            config=config)
        except errors.APIError as error:  # never echo str(error): it may carry request details
            status = getattr(error, "code", None)
            if status == 429 or (isinstance(status, int) and 500 <= status < 600):
                raise TransientError(status) from None
            raise PermanentError(f"the service refused the request (status {status})") from None
        except Exception as error:
            raise PermanentError(f"the request failed ({type(error).__name__})") from None
        return response.text or ""


def ask_all(texts: list[str], client, settings: Settings, cache: dict[str, str], sleep=time.sleep,
            save=None) -> tuple[dict[str, str], RunStats]:
    """Labels for every text: cached ones are not sent; the rest go in batches within the limits.

    Returns ({text: class} for the texts with a valid answer, statistics). The cache dict is updated
    in place and saved after every successful call, so a stopped run can resume.
    """
    stats = RunStats()
    answers: dict[str, str] = {}
    pending = []
    for text in sorted(set(texts)):
        key = cache_key(text, settings.prompt_version, settings.model)
        if key in cache:
            answers[text] = cache[key]
            stats.cached_texts += 1
        else:
            pending.append(text)
    batches = [pending[i:i + settings.batch_size] for i in range(0, len(pending), settings.batch_size)]
    first_call = True
    for batch in batches:
        numbered = list(enumerate(batch, start=1))
        reply = None
        for attempt in range(settings.max_retries + 1):
            if stats.calls >= settings.max_calls:
                stats.stopped = (f"stopped at the cap of {settings.max_calls} calls "
                                 "(classifier.gemini.max_calls); run again to continue from the cache")
                break
            if not first_call:
                sleep(settings.pause_seconds)
            first_call = False
            stats.calls += 1
            try:
                reply = client.classify(build_prompt(numbered))
                break
            except TransientError as error:
                stats.retries += 1
                if attempt == settings.max_retries:
                    stats.stopped = f"gave up after {settings.max_retries} retries ({error})"
                    break
                sleep(settings.backoff_base_seconds * (2 ** attempt))
            except PermanentError as error:
                stats.stopped = f"stopped: {error}"
                break
        if reply is None:
            break
        stats.sent_texts += len(batch)
        parsed = parse_reply(reply, [n for n, _ in numbered])
        for number, text in numbered:
            label = parsed.get(number)
            if label is None:
                stats.invalid_texts += 1
                continue
            answers[text] = label
            cache[cache_key(text, settings.prompt_version, settings.model)] = label
        if save is not None:
            save(cache)
    return answers, stats


# --- Reporting ---------------------------------------------------------------------------------------------------

def _rate(a: pd.Series, b: pd.Series) -> tuple[float | None, int]:
    both = a.notna() & b.notna() & (a != NO_ANSWER) & (b != NO_ANSWER)
    n = int(both.sum())
    return (float((a[both] == b[both]).mean()) if n else None), n


def _mode(values: pd.Series) -> str:
    values = values[values.notna() & (values != NO_ANSWER)]
    return values.value_counts().sort_index().idxmax() if not values.empty else NO_ANSWER


def build_report(frame: pd.DataFrame, answers: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """(one row per phrasing, a summary with agreement rates and confusion matrices; no text in the summary)."""
    data = frame.assign(gemini_label=frame["text"].map(answers).fillna(NO_ANSWER),
                        local_label=frame["local_label"].fillna(NO_ANSWER))
    rows = []
    for template, group in data.groupby("template_id", sort=True):
        rows.append({
            "template_id": template,
            "true_class": group["true_class"].iloc[0],
            "messages": len(group),
            "distinct_texts": group["text"].nunique(),
            "local_label_most_common": _mode(group["local_label"]),
            "local_right_share": round(float((group["local_label"] == group["true_class"]).mean()), 4),
            "gemini_label_most_common": _mode(group["gemini_label"]),
            "gemini_right_share": round(float((group["gemini_label"] == group["true_class"]).mean()), 4),
            "gemini_no_answer": int((group["gemini_label"] == NO_ANSWER).sum()),
            "local_gemini_agree_share": round(float((group["local_label"] == group["gemini_label"]).mean()), 4),
            "example_text": group["text"].iloc[0],
        })
    report = pd.DataFrame(rows)
    local_truth, n_local = _rate(data["local_label"], data["true_class"])
    gemini_truth, n_gemini = _rate(data["gemini_label"], data["true_class"])
    local_gemini, n_both = _rate(data["local_label"], data["gemini_label"])
    columns = list(MESSAGE_CLASSES) + [NO_ANSWER]

    def confusion(predicted: str) -> dict:
        table = pd.crosstab(data["true_class"], data[predicted]).reindex(
            index=list(MESSAGE_CLASSES), columns=columns, fill_value=0)
        return {row: {col: int(table.loc[row, col]) for col in columns} for row in MESSAGE_CLASSES}

    disagree = report[report["local_label_most_common"] != report["gemini_label_most_common"]]
    summary = {
        "messages": int(len(data)), "distinct_texts": int(data["text"].nunique()),
        "phrasings": int(len(report)),
        "gemini_answered": int((data["gemini_label"] != NO_ANSWER).sum()),
        "local_vs_truth": local_truth, "local_vs_truth_n": n_local,
        "gemini_vs_truth": gemini_truth, "gemini_vs_truth_n": n_gemini,
        "local_vs_gemini": local_gemini, "local_vs_gemini_n": n_both,
        "disagreeing_phrasings": [
            {"template_id": r.template_id, "true_class": r.true_class, "local": r.local_label_most_common,
             "gemini": r.gemini_label_most_common} for r in disagree.itertuples()],
        "confusion_local": confusion("local_label"),
        "confusion_gemini": confusion("gemini_label"),
        "note": SECOND_OPINION,
    }
    return report, summary


def write_outputs(report: pd.DataFrame, summary: dict, settings: Settings) -> None:
    settings.report_file.parent.mkdir(parents=True, exist_ok=True)
    with settings.report_file.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# SYNTHETIC demo test split only. {SECOND_OPINION} Model {settings.model}, "
                     f"prompt {settings.prompt_version}.\n")
        report.to_csv(handle, index=False)
    settings.summary_file.write_text(json.dumps(summary, indent=1), encoding="utf-8")


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def format_summary(summary: dict, stats: RunStats) -> str:
    lines = [SECOND_OPINION, "",
             f"Test messages: {summary['messages']} ({summary['distinct_texts']} distinct texts after masking lender "
             f"names, {summary['phrasings']} phrasings). Gemini answered for {summary['gemini_answered']}.",
             f"API calls this run: {stats.calls} (retries {stats.retries}); texts sent {stats.sent_texts}, "
             f"from cache {stats.cached_texts}, invalid answers {stats.invalid_texts}.",
             "",
             f"Local vs truth:  {_pct(summary['local_vs_truth'])} of {summary['local_vs_truth_n']} messages",
             f"Gemini vs truth: {_pct(summary['gemini_vs_truth'])} of {summary['gemini_vs_truth_n']} messages",
             f"Local vs Gemini: {_pct(summary['local_vs_gemini'])} of {summary['local_vs_gemini_n']} messages", ""]
    if summary["disagreeing_phrasings"]:
        lines.append("Phrasings where Gemini and the local model disagree (most common label):")
        for row in summary["disagreeing_phrasings"]:
            lines.append(f"  {row['template_id']:<24} truth {row['true_class']:<20} local {row['local']:<20} "
                         f"gemini {row['gemini']}")
    else:
        lines.append("Gemini and the local model agree on the most common label for every phrasing.")
    short = {"normal": "normal", "firm_pressure": "firm", "threat": "threat", "shaming_third_party": "shaming",
             NO_ANSWER: "no ans"}
    for title, key in (("Local", "confusion_local"), ("Gemini", "confusion_gemini")):
        lines += ["", f"{title} confusion (rows = truth, columns = predicted):",
                  " " * 22 + "".join(f"{short[c]:>9}" for c in short)]
        for row, counts in summary[key].items():
            lines.append(f"  {row:<20}" + "".join(f"{counts[c]:>9}" for c in short))
    if stats.stopped:
        lines += ["", f"NOTE: the run {stats.stopped}. The report covers the answers so far."]
    return "\n".join(lines)


def main(argv: list[str] | None = None, client=None, sleep=time.sleep) -> int:
    """client and sleep are for the tests only (a mocked client, no waiting). Real runs build GeminiClient."""
    parser = argparse.ArgumentParser(description="Gemini second opinion on the demo's synthetic test split.")
    parser.add_argument("--dataset", help="Dataset to check (default: the active one; must be the demo).")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    settings = Settings.from_config(cfg)
    try:
        paths = paths_for(cfg, args.dataset)
        frame = select_test_messages(cfg, paths)
        if client is None:
            client = GeminiClient(read_key(), settings)
    except (CheckRefused, DatasetError) as error:
        print(error)
        return 1
    except ImportError:
        print("The google-genai package is not installed. Install it with: pip install -r requirements.txt")
        return 1
    except Exception as error:  # building the client failed: name the type only, never the details
        print(f"Could not start the Gemini client ({type(error).__name__}). Nothing was sent.")
        return 1

    cache = load_cache(settings.cache_file)
    answers, stats = ask_all(frame["text"].tolist(), client, settings, cache, sleep=sleep,
                             save=lambda c: save_cache(settings.cache_file, c))
    save_cache(settings.cache_file, cache)
    report, summary = build_report(frame, answers)
    summary.update(model=settings.model, prompt_version=settings.prompt_version,
                   created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                   complete=not stats.stopped and summary["gemini_answered"] == summary["messages"])
    write_outputs(report, summary, settings)
    print(format_summary(summary, stats))
    print("")
    print(f"Wrote {settings.report_file} and {settings.summary_file}")
    return 0 if not stats.stopped else 2


if __name__ == "__main__":
    sys.exit(main())
