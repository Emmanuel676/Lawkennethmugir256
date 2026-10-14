"""Bring your own data into FairLend Watch (Phase 4B, made robust for field files in Phase 5.1).

No Streamlit, no network.

Input: one .xlsx workbook with sheets lenders, borrowers, loans, transactions,
messages, or the same five tables as CSV files (named lenders.csv and so on).
Column names are exactly those of the lending database (see COLUMNS); extra
columns are ignored with a notice. transactions may be missing or empty;
cycling then cannot be detected.

Steps:
  1. read_xlsx() or read_csvs()  -> an Upload (every cell as text, with its row number)
  2. validate_upload()           -> an ImportReport: plain-language errors, warnings and
                                    notes with sheet or file name and row number, row counts,
                                    what redaction would remove, and the suggested as_of_date
  3. import_upload()             -> validates again, then writes everything in ONE
                                    SQLite transaction (nothing is written if anything
                                    is wrong), and labels the messages with the local classifier.

Accepted formats (field spreadsheets are messy):
  dates     YYYY-MM-DD, or day/month/year with '/', '-' or '.' between the parts
            (with day_first=False an ambiguous date such as 03/04/2026 is an error),
            and real Excel date cells. Timestamps may add HH:MM or HH:MM:SS.
  amounts   200000, 200,000, 200 000, UGX 200,000, Ush 200,000, 200,000/= ("200k" is refused)
  CSV       UTF-8 (with or without a BOM) or Windows-1252 text; comma, semicolon or tab
            between columns (detected from the header line)
  lists     extra spaces and letter case do not matter (" Active ", "IN_ARREARS", "in arrears")
  region    free text; a blank region is a warning, never an error

Errors block the import; warnings and notes do not. Modes: "new" creates a real
dataset; "add" appends to an existing REAL dataset (never to the demo). In "add"
mode a borrower code that already exists is expected (the same person borrows
from several lenders) and is kept as it is; any other repeated id is an error.

Privacy: the importer refuses to run without the permission confirmation, and
redacts message text (src/redaction.py) when asked. Errors, warnings and notes
NEVER repeat a cell's value: they give the sheet or file, the row number and the
column name only. With redaction on, the original text is never written anywhere.
Real data is confidential.
"""

from __future__ import annotations

import io
import re
from functools import lru_cache
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import openpyxl
import pandas as pd

from src import db
from src.config import SIZES
from src.datasets import (DEMO, REAL_NOTICE, DatasetError, create_dataset, dataset_exists, get_dataset,
                          get_dataset_paths, remove_dataset_folder, update_dataset_info)
from src.redaction import EMAIL_PATTERN, TOKENS, build_redactor, empty_counts, phone_pattern, preview  # noqa: F401

TABLES = ("lenders", "borrowers", "loans", "transactions", "messages")
REQUIRED_TABLES = ("lenders", "borrowers", "loans", "messages")
COLUMNS = {table: db.COLUMNS[table] for table in TABLES}
ID_COLUMN = {"lenders": "lender_id", "borrowers": "borrower_id", "loans": "loan_id",
             "transactions": "txn_id", "messages": "message_id"}

LOAN_STATUSES = ("active", "repaid", "in_arrears")
DIRECTIONS = ("in", "out")
COUNTERPARTY_TYPES = ("lender", "merchant", "employer", "agent", "peer")
RECIPIENT_TYPES = ("borrower", "third_party")
ENUMS = {
    ("lenders", "size_category"): SIZES,
    ("loans", "status"): LOAN_STATUSES,
    ("transactions", "direction"): DIRECTIONS,
    ("transactions", "counterparty_type"): COUNTERPARTY_TYPES,
    ("messages", "recipient_type"): RECIPIENT_TYPES,
}
# Whole-number money columns: True = must be more than 0, False = may be 0.
MONEY = {("borrowers", "monthly_income"): True, ("loans", "principal"): True,
         ("loans", "amount_outstanding"): False, ("transactions", "amount"): True}
DATES = {("borrowers", "joined_date"), ("loans", "issue_date"), ("loans", "due_date"), ("transactions", "txn_date")}
TIMESTAMPS = {("messages", "sent_at")}
OPTIONAL = {("transactions", "linked_loan_id")}
BLANK_WARNS = {("borrowers", "region")}  # free text: a blank is a warning, never an error
# Dates that record something that already happened (a due date in the future is normal).
EVENT_DATES = (("borrowers", "joined_date"), ("loans", "issue_date"), ("transactions", "txn_date"),
               ("messages", "sent_at"))

PERMISSION_TEXT = "I have permission to use this data and have removed names and ID numbers"
PERMISSION_REFUSAL = ("Import refused: the permission confirmation is missing. Confirm: "
                      f"\"{PERMISSION_TEXT}\".")
NO_TRANSACTIONS = "No transactions were supplied, so cycling (borrowing to repay) cannot be detected."
DATE_HELP = "write it as YYYY-MM-DD or day/month/year, for example 2026-08-31 or 31/08/2026"
AMOUNT_HELP = "Ugandan shillings, UGX, no decimals; for example 200000, 200,000, UGX 200,000 or 200,000/="
MAX_ROWS_LISTED = 20
DELIMITERS = {",": "commas", ";": "semicolons", "\t": "tabs"}
TOKEN_WORDS = {"PHONE": "phone number(s)", "EMAIL": "email address(es)", "ID": "ID number(s)", "NAME": "name(s)"}


# --- Data structures ------------------------------------------------------------------------

@dataclass
class Issue:
    level: str        # 'error', 'warning' or 'note'
    location: str     # e.g. "sheet 'loans', row 5"
    message: str      # never contains a cell's value

    def __str__(self) -> str:
        return f"{self.location}: {self.message}" if self.location else self.message


@dataclass
class Upload:
    """The tables as read from the files: every cell as text, plus '_row' (row number, header = row 1)."""

    kind: str                                   # 'xlsx' or 'csv'
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    problems: list[Issue] = field(default_factory=list)


@dataclass
class ImportReport:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    notes: list[Issue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    as_of_date: str = ""
    day_first: bool = True
    dates_converted: int = 0
    amounts_converted: int = 0
    cells_adjusted: int = 0
    found: dict[str, int] = field(default_factory=empty_counts)  # what redaction would replace
    clean: dict[str, pd.DataFrame] = field(default_factory=dict)  # typed rows ready to write (only if ok)
    skipped_existing_borrowers: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def phones_found(self) -> int:
        return self.found["PHONE"]

    @property
    def emails_found(self) -> int:
        return self.found["EMAIL"]


@dataclass
class ImportResult:
    ok: bool
    message: str
    report: ImportReport | None = None
    dataset: str = ""
    rows_written: dict[str, int] = field(default_factory=dict)
    labelled: int = 0
    redacted: dict[str, int] = field(default_factory=empty_counts)

    @property
    def phones_redacted(self) -> int:
        return self.redacted["PHONE"]

    @property
    def emails_redacted(self) -> int:
        return self.redacted["EMAIL"]


@dataclass
class Existing:
    """Ids already in the dataset being appended to."""

    ids: dict[str, set[str]] = field(default_factory=lambda: {t: set() for t in TABLES})
    as_of_date: str = ""


# --- Reading ------------------------------------------------------------------------------------

def _cell_text(value) -> str:
    """A cell as text. Text is NOT trimmed here, so the check can count the cells it adjusts."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, datetime):
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _frame(header: list[str], rows: list[tuple[int, list[str]]], source: str, problems: list[Issue]) -> pd.DataFrame:
    names = [h.strip().lower() for h in header]
    keep = [i for i, name in enumerate(names) if name]
    seen: set[str] = set()
    for i in keep:
        if names[i] in seen:
            problems.append(Issue("error", source, f"column '{names[i]}' appears twice"))
        seen.add(names[i])
    records = []
    width = len(names)
    for row_number, values in rows:
        values = list(values) + [""] * (width - len(values))
        if all(not str(v).strip() for v in values):
            continue  # skip empty rows but keep everyone else's row number
        record = {names[i]: values[i] for i in keep}
        record["_row"] = row_number
        records.append(record)
    columns = list(dict.fromkeys(names[i] for i in keep)) + ["_row"]
    return pd.DataFrame(records, columns=columns)


def read_xlsx(source: bytes | str | Path) -> Upload:
    """Read a workbook. Sheet names are matched without regard to case; other sheets are ignored."""
    upload = Upload(kind="xlsx")
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(source) if isinstance(source, bytes) else source,
                                          read_only=True, data_only=True)
    except Exception as error:  # a damaged or non-Excel file
        upload.problems.append(Issue("error", "workbook",
                                     f"cannot be opened as an Excel workbook ({type(error).__name__})"))
        return upload
    try:
        sheets = {ws.title.strip().lower(): ws for ws in workbook.worksheets}
        for table in TABLES:
            sheet = sheets.get(table)
            if sheet is None:
                if table in REQUIRED_TABLES:
                    upload.problems.append(Issue("error", "workbook", f"there is no sheet called '{table}'"))
                continue
            label = f"sheet '{table}'"
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                if table in REQUIRED_TABLES:
                    upload.problems.append(Issue("error", label, "is empty: it needs a header row"))
                continue
            header = [_cell_text(c) for c in rows[0]]
            body = [(number, [_cell_text(c) for c in row]) for number, row in enumerate(rows[1:], start=2)]
            upload.tables[table] = _frame(header, body, label, upload.problems)
            upload.sources[table] = label
    finally:
        workbook.close()
    return upload


def _table_for_file(file_name: str) -> str | None:
    stem = Path(file_name).stem.strip().lower()
    for table in TABLES:
        if stem == table or stem.endswith(("_" + table, "-" + table, " " + table)):
            return table
    return None


def decode_text(raw: bytes) -> tuple[str, str]:
    """(text, encoding name). UTF-8 with or without a byte-order mark, otherwise Windows-1252."""
    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "windows-1252"


def detect_delimiter(text: str) -> str:
    """The column separator, judged from the header line: comma, semicolon or tab (comma if unclear)."""
    header = next((line for line in text.splitlines() if line.strip()), "")
    counts = {d: header.count(d) for d in DELIMITERS}
    best = max(counts, key=lambda d: (counts[d], d == ","))
    return best if counts[best] > 0 else ","


def read_csvs(files: dict[str, bytes | str | Path]) -> Upload:
    """Read CSV files given as {file name: bytes or path}. Each file name must end in the table name."""
    upload = Upload(kind="csv")
    for file_name, content in files.items():
        table = _table_for_file(file_name)
        label = f"file '{Path(file_name).name}'"
        if table is None:
            upload.problems.append(Issue("warning", label,
                                         "ignored: its name does not end in lenders, borrowers, loans, "
                                         "transactions or messages"))
            continue
        if table in upload.tables:
            upload.problems.append(Issue("error", label, f"a second file for the '{table}' table"))
            continue
        try:
            raw = content if isinstance(content, bytes) else Path(content).read_bytes()
            text, encoding = decode_text(raw)
            delimiter = detect_delimiter(text)
            frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, sep=delimiter,
                                skip_blank_lines=False)
        except Exception as error:
            upload.problems.append(Issue("error", label, f"cannot be read as CSV ({type(error).__name__})"))
            continue
        if encoding != "utf-8":
            upload.problems.append(Issue("note", label, "was read as Windows-1252 text (it is not UTF-8)"))
        if delimiter != ",":
            upload.problems.append(Issue("note", label, f"columns are separated by {DELIMITERS[delimiter]}"))
        frame = frame.fillna("")
        body = [(number, [str(v) for v in row])
                for number, row in enumerate(frame.itertuples(index=False, name=None), start=2)]
        upload.tables[table] = _frame([str(c) for c in frame.columns], body, label, upload.problems)
        upload.sources[table] = label
    for table in REQUIRED_TABLES:
        if table not in upload.tables and not any(p.message.startswith("a second file") for p in upload.problems):
            upload.problems.append(Issue("error", "files", f"there is no file for the '{table}' table "
                                                           f"(for example {table}.csv)"))
    return upload


# --- Parsing single values -------------------------------------------------------------------------

_CURRENCY = r"(?:UGX|USHS?|SHS?)\.?"
_MONEY = re.compile(rf"^(?:{_CURRENCY}\s*)?(-?)\s*(\d{{1,3}}(?:[, ]\d{{3}})+|\d+)(?:\.0+)?\s*(?:/=|/-)?"
                    rf"\s*(?:{_CURRENCY})?$", re.IGNORECASE)


@lru_cache(maxsize=65536)  # field files repeat the same values many times
def parse_amount(text: str) -> tuple[int | None, bool]:
    """(whole shillings, was it written in another form than plain digits). None if not an amount."""
    text = text.strip()
    match = _MONEY.match(text)
    if not match:
        return None, False
    number = int(re.sub(r"[, ]", "", match.group(2)))
    if match.group(1):
        number = -number
    return number, not re.fullmatch(r"-?\d+", text)


def _parse_whole_number(text: str) -> int | None:
    return parse_amount(text)[0]


_ISO_DATE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_DMY_DATE = re.compile(r"(\d{1,2})([/.\-])(\d{1,2})\2(\d{4})")
_TIME = re.compile(r"(?:\s+|T)(\d{1,2}):(\d{2})(?::(\d{2}))?")


def _make_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


@lru_cache(maxsize=65536)
def parse_day(text: str, day_first: bool = True) -> tuple[date | None, str]:
    """(date, status). status: 'iso' (already YYYY-MM-DD), 'converted', 'ambiguous' or 'invalid'.

    Non-ISO dates are day/month/year when day_first is True. When it is False, a date
    is read either way round only if one part is above 12; otherwise it is 'ambiguous'.
    """
    text = text.strip()
    match = _ISO_DATE.fullmatch(text)
    if match:
        value = _make_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if value is None:
            return None, "invalid"
        return value, "iso" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else "converted"
    match = _DMY_DATE.fullmatch(text)
    if not match:
        return None, "invalid"
    first, second, year = int(match.group(1)), int(match.group(3)), int(match.group(4))
    if day_first:
        value = _make_date(year, second, first)
    elif first > 12 >= second:
        value = _make_date(year, second, first)
    elif second > 12 >= first:
        value = _make_date(year, first, second)
    elif first == second:
        value = _make_date(year, first, first)
    else:
        return None, "ambiguous"
    return (value, "converted") if value else (None, "invalid")


@lru_cache(maxsize=65536)
def parse_timestamp(text: str, day_first: bool = True) -> tuple[datetime | None, bool, str]:
    """(value, has_time, status) for 'date' or 'date HH:MM[:SS]'; status as in parse_day."""
    text = text.strip()
    time_match = _TIME.search(text)
    date_text, has_time, extra = text, False, False
    if time_match and time_match.end() == len(text):
        date_text = text[:time_match.start()]
        has_time = True
        hour, minute, second = int(time_match.group(1)), int(time_match.group(2)), int(time_match.group(3) or 0)
        if hour > 23 or minute > 59 or second > 59:
            return None, False, "invalid"
        extra = time_match.group(3) is None or len(time_match.group(1)) == 1 or time_match.group(0)[0] == "T"
    day, status = parse_day(date_text, day_first)
    if day is None:
        return None, False, status
    if has_time:
        value = datetime(day.year, day.month, day.day, hour, minute, second)
    else:
        value = datetime.combine(day, datetime.min.time())
    return value, has_time, "converted" if (status == "converted" or extra) else status


def _parse_date(text: str) -> date | None:
    """Strict YYYY-MM-DD (used for the as-of date typed by a person)."""
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def default_as_of(upload: Upload, day_first: bool = True) -> date | None:
    """The latest date of something that happened (joined, issued, transaction, message) in the files."""
    latest: date | None = None
    for table, column in EVENT_DATES:
        frame = upload.tables.get(table)
        if frame is None or column not in frame.columns:
            continue
        for text in frame[column]:
            if (table, column) in TIMESTAMPS:
                value = parse_timestamp(str(text), day_first)[0]
                day = value.date() if value else None
            else:
                day = parse_day(str(text), day_first)[0]
            if day and (latest is None or day > latest):
                latest = day
    return latest


def scan_text(texts, cfg: dict) -> dict[str, int]:
    """How many of each token ([PHONE], [EMAIL], [ID], [NAME]) redaction would put into the texts."""
    redactor = build_redactor(cfg)
    total = empty_counts()
    for text in texts:
        for token, n in redactor.redact(text)[1].items():
            total[token] += n
    return total


def redact_text(text: str, cfg: dict) -> tuple[str, dict[str, int]]:
    """Redact one text following config.yaml. Returns (text, counts per token)."""
    return build_redactor(cfg).redact(text)


def redaction_preview(upload: Upload, cfg: dict, limit: int = 20) -> tuple[pd.DataFrame, dict[str, int]]:
    """Up to `limit` messages, as uploaded and as they would be stored, plus counts for ALL messages.

    For showing on screen before an import only. Never logged.
    """
    frame = upload.tables.get("messages")
    if frame is None or "text" not in frame.columns:
        return pd.DataFrame(columns=["Row", "Original", "Redacted"]), empty_counts()
    redactor = build_redactor(cfg)
    total = empty_counts()
    for text in frame["text"]:
        for token, n in redactor.redact(str(text))[1].items():
            total[token] += n
    return preview(frame, redactor, limit), total


# --- Validation --------------------------------------------------------------------------------------

def read_existing(lending_path: Path) -> Existing:
    """Ids already stored in a dataset (for 'add' mode)."""
    existing = Existing()
    conn = sqlite3.connect(f"{Path(lending_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        for table in TABLES:
            existing.ids[table] = {r[0] for r in conn.execute(f"SELECT {ID_COLUMN[table]} FROM {table}")}
        row = conn.execute("SELECT value FROM meta WHERE key = 'as_of_date'").fetchone()
        existing.as_of_date = row[0] if row else ""
    finally:
        conn.close()
    return existing


def _row_list(rows: list[int]) -> str:
    shown = ", ".join(map(str, rows[:MAX_ROWS_LISTED]))
    return shown + (f" and {len(rows) - MAX_ROWS_LISTED} more" if len(rows) > MAX_ROWS_LISTED else "")


@lru_cache(maxsize=4096)
def _enum_value(text: str) -> str:
    """' In Arrears ' -> 'in_arrears'; 'Third-Party' -> 'third_party'."""
    return re.sub(r"[\s\-]+", "_", text.strip().lower())


def validate_upload(upload: Upload, cfg: dict, as_of: date | str | None = None,
                    existing: Existing | None = None, day_first: bool | None = None) -> ImportReport:
    """Check everything. Writes nothing. The report's 'clean' tables are only meant to be used if report.ok.

    day_first: "Dates in my files are day/month/year" (default: onboarding.day_first_default).
    """
    if day_first is None:
        day_first = bool(cfg["onboarding"]["day_first_default"])
    report = ImportReport(day_first=day_first)
    errors, warnings, notes = report.errors, report.warnings, report.notes

    def err(location, message):
        errors.append(Issue("error", location, message))

    def warn(location, message):
        warnings.append(Issue("warning", location, message))

    for problem in upload.problems:
        {"error": errors, "warning": warnings}.get(problem.level, notes).append(problem)
    adding = existing is not None
    existing = existing or Existing()
    prefix = str(cfg["onboarding"]["example_id_prefix"]).upper()
    blank_rows: dict[tuple[str, str], list[int]] = {}

    # 1. Columns, and turning text into typed values -------------------------------------------
    clean: dict[str, pd.DataFrame] = {}
    for table in TABLES:
        frame = upload.tables.get(table)
        source = upload.sources.get(table, table)
        if frame is None:
            clean[table] = pd.DataFrame(columns=COLUMNS[table] + ["_row"])
            continue
        missing = [c for c in COLUMNS[table] if c not in frame.columns]
        extra = [c for c in frame.columns if c not in COLUMNS[table] and c != "_row"]
        if missing:
            err(source, f"missing column(s): {', '.join(missing)}")
            clean[table] = pd.DataFrame(columns=COLUMNS[table] + ["_row"])
            continue
        if extra:
            warn(source, f"extra column(s) ignored: {', '.join(extra)}")
        columns = {column: frame[column].astype(str).tolist() for column in COLUMNS[table]}
        row_numbers = frame["_row"].tolist()
        rows = []
        for index, row_number in enumerate(row_numbers):
            where = f"{source}, row {row_number}"
            row = {"_row": row_number}
            for column in COLUMNS[table]:
                raw = columns[column][index]
                text = raw.strip()
                key = (table, column)
                if text != raw and key not in ENUMS:
                    report.cells_adjusted += 1
                if not text:
                    if key in OPTIONAL:
                        row[column] = None
                    elif key in BLANK_WARNS:
                        row[column] = ""
                        blank_rows.setdefault(key, []).append(row_number)
                    else:
                        err(where, f"'{column}' is empty")
                        row[column] = None
                    continue
                if key in MONEY:
                    number, converted = parse_amount(text)
                    if number is None:
                        err(where, f"'{column}' must be a whole number of shillings ({AMOUNT_HELP})")
                    elif MONEY[key] and number <= 0:
                        err(where, f"'{column}' must be more than 0")
                    elif number < 0:
                        err(where, f"'{column}' cannot be negative")
                    report.amounts_converted += int(converted and number is not None)
                    row[column] = number
                elif key in DATES:
                    parsed, status = parse_day(text, day_first)
                    if status == "ambiguous":
                        err(where, f"'{column}' could be day/month or month/day; tick \"Dates in my files are "
                                   "day/month/year\" or write it as YYYY-MM-DD")
                    elif parsed is None:
                        err(where, f"'{column}' is not a date ({DATE_HELP})")
                    report.dates_converted += int(status == "converted")
                    row[column] = parsed.isoformat() if parsed else None
                elif key in TIMESTAMPS:
                    parsed, has_time, status = parse_timestamp(text, day_first)
                    if status == "ambiguous":
                        err(where, f"'{column}' could be day/month or month/day; tick \"Dates in my files are "
                                   "day/month/year\" or write it as YYYY-MM-DD HH:MM:SS")
                        row[column] = None
                    elif parsed is None:
                        err(where, f"'{column}' is not a date and time ({DATE_HELP}, optionally followed by "
                                   "HH:MM or HH:MM:SS)")
                        row[column] = None
                    else:
                        report.dates_converted += int(status == "converted")
                        row[column] = parsed.strftime("%Y-%m-%d %H:%M:%S") if has_time else parsed.date().isoformat()
                elif key in ENUMS:
                    value = _enum_value(text)
                    if value != raw:
                        report.cells_adjusted += 1
                    if value not in ENUMS[key]:
                        err(where, f"'{column}' is not one of: {', '.join(ENUMS[key])}")
                    row[column] = value
                else:
                    row[column] = text
            id_value = row.get(ID_COLUMN[table]) or ""
            if str(id_value).upper().startswith(prefix):
                err(where, "this is the template's example row; delete it before importing")
            rows.append(row)
        clean[table] = pd.DataFrame(rows, columns=COLUMNS[table] + ["_row"])

    for (table, column), numbers in blank_rows.items():
        warn(f"{upload.sources.get(table, table)}, row(s) {_row_list(numbers)}",
             f"'{column}' is blank ({len(numbers)} row(s)); it is kept blank")

    # 2. Duplicate ids -------------------------------------------------------------------------------
    for table in TABLES:
        frame, source, id_col = clean[table], upload.sources.get(table, table), ID_COLUMN[table]
        repeated = frame[frame[id_col].notna() & frame[id_col].duplicated(keep=False)]
        for _, group in repeated.groupby(id_col, sort=False):
            err(f"{source}, rows {_row_list(group['_row'].tolist())}", f"the same '{id_col}' appears more than once")
        if adding and table != "borrowers":
            for row_number in frame.loc[frame[id_col].isin(existing.ids[table]), "_row"]:
                err(f"{source}, row {row_number}", f"this '{id_col}' already exists in this dataset")

    # Borrowers already in the dataset are the same person at another lender: keep the stored row.
    if adding:
        known = clean["borrowers"]["borrower_id"].isin(existing.ids["borrowers"])
        report.skipped_existing_borrowers = int(known.sum())
        clean["borrowers"] = clean["borrowers"][~known]

    if not adding:
        for table in ("lenders", "borrowers", "loans"):
            label = upload.sources.get(table, "")
            if table in upload.tables and clean[table].empty and not any(label in e.location for e in errors):
                err(upload.sources.get(table, table), "has no rows; at least one is needed")

    # 3. References between tables ----------------------------------------------------------------------
    lenders = set(clean["lenders"]["lender_id"].dropna()) | existing.ids["lenders"]
    borrowers = set(clean["borrowers"]["borrower_id"].dropna()) | existing.ids["borrowers"]
    loans = set(clean["loans"]["loan_id"].dropna()) | existing.ids["loans"]
    checks = [("loans", "borrower_id", borrowers, "borrower"), ("loans", "lender_id", lenders, "lender"),
              ("transactions", "borrower_id", borrowers, "borrower"),
              ("transactions", "linked_loan_id", loans, "loan"),
              ("messages", "borrower_id", borrowers, "borrower"), ("messages", "lender_id", lenders, "lender")]
    for table, column, known_ids, what in checks:
        frame, source = clean[table], upload.sources.get(table, table)
        known = frame[column].astype(object).isin(list(known_ids))
        for row_number in frame.loc[frame[column].notna() & ~known, "_row"]:
            err(f"{source}, row {row_number}", f"'{column}' is not a known {what}")

    # 4. Loans that do not add up --------------------------------------------------------------------------
    loans_frame, source = clean["loans"], upload.sources.get("loans", "loans")
    for record in loans_frame.to_dict("records"):
        where = f"{source}, row {record['_row']}"
        issue, due = record["issue_date"], record["due_date"]
        if isinstance(issue, str) and isinstance(due, str) and issue > due:  # invalid dates are already errors
            err(where, "issue_date is after due_date")
        owed = record["amount_outstanding"]
        if pd.notna(owed):
            owed = int(owed)
            if record["status"] == "repaid" and owed > 0:
                warn(where, "status is 'repaid' but money is still outstanding")
            if record["status"] in ("active", "in_arrears") and owed == 0:
                warn(where, f"status is '{record['status']}' but nothing is outstanding")

    # 5. The as-of date and dates after it -------------------------------------------------------------------
    if as_of is None:
        found = default_as_of(upload, day_first)
        candidates = [d for d in (found, _parse_date(existing.as_of_date or "")) if d]
        as_of_day = max(candidates) if candidates else None
    else:
        as_of_day = as_of if isinstance(as_of, date) else _parse_date(str(as_of))
        if as_of_day is None:
            err("as_of_date", "the as-of date is not a date written YYYY-MM-DD")
    report.as_of_date = as_of_day.isoformat() if as_of_day else ""
    if as_of_day is None and not errors:
        err("as_of_date", "no date found in the data; choose the as-of date yourself")
    if as_of_day is not None:
        limit = as_of_day.isoformat()
        for table, column in EVENT_DATES:
            frame, source = clean[table], upload.sources.get(table, table)
            later = frame[frame[column].notna() & (frame[column].astype(str).str.slice(0, 10) > limit)]
            for row_number in later["_row"]:
                warn(f"{source}, row {row_number}", f"'{column}' is after the as-of date {limit}")

    # 6. Notes on what the data allows --------------------------------------------------------------------------
    if clean["transactions"].empty:
        warn("transactions", NO_TRANSACTIONS)
    messages = clean["messages"]
    if not messages.empty:
        no_time = int(messages["sent_at"].dropna().astype(str).str.len().eq(10).sum())
        if no_time:
            warn("messages", f"{no_time} message(s) have a date but no time; they cannot count as late-night")
        report.found = scan_text(messages["text"].dropna().astype(str), cfg)
        if any(report.found.values()):
            found = ", ".join(f"{report.found[t]} {TOKEN_WORDS[t]}" for t in TOKENS if report.found[t])
            warn("messages", f"message text contains {found}; choose redaction to remove them")
    elif "messages" in upload.tables:
        warn("messages", "no messages were supplied, so lenders cannot be compared")

    style = "day/month/year" if day_first else "month/day/year where it is clear (ambiguous dates are errors)"
    if report.dates_converted:
        notes.append(Issue("note", "dates", f"{report.dates_converted} date(s) were converted to YYYY-MM-DD "
                                            f"(read as {style})"))
    if report.amounts_converted:
        notes.append(Issue("note", "amounts", f"{report.amounts_converted} amount(s) were written with commas, "
                                              "spaces, a currency or '/=' and were converted to whole shillings"))
    if report.cells_adjusted:
        notes.append(Issue("note", "cells", f"{report.cells_adjusted} cell(s) had extra spaces or a different "
                                            "letter case or spelling of a fixed value and were adjusted"))

    report.counts = {table: len(clean[table]) for table in TABLES}
    report.clean = clean
    return report


# --- Writing -----------------------------------------------------------------------------------------------

def _rows(frame: pd.DataFrame, table: str) -> list[dict]:
    rows = frame[COLUMNS[table]].astype(object).where(frame[COLUMNS[table]].notna(), None).to_dict("records")
    return rows


def _write(conn: sqlite3.Connection, report: ImportReport, meta: dict[str, str], redact: bool,
           cfg: dict) -> tuple[dict[str, int], dict[str, int]]:
    """Insert every table and the meta rows. The caller owns the transaction.

    With redact, message text is redacted BEFORE it reaches the database, and the report's
    copy of the text is replaced too, so the original is not kept in memory after the import.
    """
    redacted = empty_counts()
    written = {}
    redactor = build_redactor(cfg) if redact else None
    for table in TABLES:
        rows = _rows(report.clean[table], table)
        if table == "messages" and redactor is not None:
            for row in rows:
                row["text"], counts = redactor.redact(row["text"])
                for token, n in counts.items():
                    redacted[token] += n
            report.clean[table] = report.clean[table].assign(text=[row["text"] for row in rows])
        db.insert_rows(conn, table, rows)
        written[table] = len(rows)
    conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", list(meta.items()))
    return written, redacted


def import_upload(upload: Upload, cfg: dict, *, mode: str, permission_confirmed: bool, redact: bool,
                  as_of: date | str | None = None, dataset_name: str = "", source_description: str = "",
                  notes: str = "", target: str = "", classify: bool = True,
                  day_first: bool | None = None) -> ImportResult:
    """Validate and, only if there are no errors, write everything in one transaction. Then label the messages."""
    if not permission_confirmed:
        return ImportResult(False, PERMISSION_REFUSAL)
    if mode not in ("new", "add"):
        return ImportResult(False, "Unknown import mode: use 'new' or 'add'.")

    existing = None
    if mode == "add":
        if target == DEMO:
            return ImportResult(False, "Adding to the demo dataset is not allowed: it holds synthetic data only. "
                                       "Create a new dataset instead.")
        if not target or not dataset_exists(cfg, target) or get_dataset(cfg, target).kind != "real":
            return ImportResult(False, f"There is no real dataset called {target!r} to add to.")
        target_paths = get_dataset_paths(cfg, target)
        if not target_paths.lending_db.exists():
            return ImportResult(False, f"Dataset {target!r} has no data file to add to.")
        existing = read_existing(target_paths.lending_db)

    report = validate_upload(upload, cfg, as_of, existing, day_first)
    if not report.ok:
        return ImportResult(False, f"{len(report.errors)} error(s) found. Nothing was written.", report)

    imported_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    meta = {"synthetic": "false", "notice": REAL_NOTICE, "as_of_date": report.as_of_date,
            "currency": str(cfg["currency"]["code"]), "last_import_at": imported_at,
            "dates_day_first": "true" if report.day_first else "false",
            "text_redacted": "true" if redact else "false"}

    if mode == "new":
        try:
            info = create_dataset(cfg, dataset_name, source_description, report.as_of_date, notes)
        except DatasetError as error:
            return ImportResult(False, str(error), report)
        meta.update({"dataset_name": info.name, "source_description": info.source_description})
        conn = None
        try:
            conn = db.create_database(info.paths.lending_db, db.LENDING_SCHEMA)
            with conn:  # one transaction: committed only if every insert works
                written, redacted = _write(conn, report, meta, redact, cfg)
        except Exception as error:
            if conn is not None:
                conn.close()
                conn = None
            remove_dataset_folder(cfg, info.slug)
            return ImportResult(False, f"Writing failed, nothing was kept ({type(error).__name__}).", report)
        finally:
            if conn is not None:
                conn.close()
        slug, paths = info.slug, info.paths
    else:
        slug, paths = target, get_dataset_paths(cfg, target)
        conn = sqlite3.connect(str(paths.lending_db))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                written, redacted = _write(conn, report, meta, redact, cfg)
        except Exception as error:
            return ImportResult(False, f"Writing failed, nothing was changed ({type(error).__name__}).", report)
        finally:
            conn.close()
        update_dataset_info(cfg, slug, as_of_date=report.as_of_date)

    result = ImportResult(True, "", report, slug, written, 0, redacted)
    parts = [f"Imported into '{slug}': " + ", ".join(f"{n:,} {t}" for t, n in written.items()) + "."]
    if report.skipped_existing_borrowers:
        parts.append(f"{report.skipped_existing_borrowers} borrower code(s) were already in the dataset and kept.")
    if redact:
        parts.append("Redacted " + ", ".join(f"{redacted[t]} {TOKEN_WORDS[t]}" for t in TOKENS) + ".")
        parts.extend(build_redactor(cfg).notes)
    if classify:
        from src.classify_messages import NoModelError, classify_dataset  # heavy import, only when needed
        try:
            result.labelled = classify_dataset(cfg, paths)
            parts.append(f"Labelled {result.labelled:,} messages with the local classifier. Check a sample on "
                         "the Review page before relying on the labels.")
        except NoModelError as error:
            parts.append(f"Messages were NOT labelled: {error}")
    result.message = " ".join(parts)
    return result
