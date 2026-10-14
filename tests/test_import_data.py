"""Checks on importing your own data (Phase 4B): validation, all-or-nothing writing, privacy, templates, codes."""

from __future__ import annotations

import copy
import csv
import io
import sqlite3
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from src.datasets import DEMO, get_dataset, get_dataset_paths, is_synthetic, list_datasets
from src.import_data import (COLUMNS, NO_TRANSACTIONS, PERMISSION_REFUSAL, TABLES, import_upload, read_csvs,
                             read_existing, read_xlsx, redact_text, validate_upload)
from src.import_templates import build_csv_templates, build_xlsx_template
from src.make_borrower_codes import convert_file, make_code

from leak_check import forbidden_mentions
from tiny_data import DEFAULT_AS_OF, EMAILS, PHONES, SHARED_BORROWER, csv_bytes, tiny_rows, write_csvs, write_xlsx
from worlds import build_classified_world

ROOT = Path(__file__).resolve().parents[1]
NETWORK_AND_SECRETS = (".env", "dotenv", "requests", "urllib", "genai", "http.client", "socket")
LABEL_TABLES = ("gt_borrowers", "gt_messages", "gt_lenders", "profile_type")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """A small classified demo world with a saved model, shared by the tests in this file."""
    cfg, _ = build_classified_world(tmp_path_factory.mktemp("import_demo"), n_borrowers=300)
    return cfg


@pytest.fixture
def cfg(demo, tmp_path):
    """The demo's config, but with its own empty datasets folder and active-dataset file."""
    custom = copy.deepcopy(demo)
    custom["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    custom["paths"]["active_dataset_file"] = str(tmp_path / "active_dataset.txt")
    return custom


def upload_of(rows, kind="csv", tmp_path=None):
    if kind == "csv":
        return read_csvs(csv_bytes(rows))
    path = write_xlsx(rows, tmp_path / "tiny.xlsx")
    return read_xlsx(path.read_bytes())


def check(rows, cfg, **kwargs):
    return validate_upload(upload_of(rows), cfg, **kwargs)


def messages_of(report):
    return [str(issue) for issue in report.errors]


def warnings_of(report):
    return [str(issue) for issue in report.warnings]


def do_import(rows, cfg, **kwargs):
    options = {"mode": "new", "permission_confirmed": True, "redact": True, "dataset_name": "Field A",
               "source_description": "test", "classify": False}
    options.update(kwargs)
    return import_upload(upload_of(rows), cfg, **options)


# --- The tiny workbook passes ----------------------------------------------------------------------

def test_the_tiny_dataset_is_valid(cfg):
    report = check(tiny_rows(), cfg)
    assert report.ok, messages_of(report)
    assert report.counts == {"lenders": 2, "borrowers": 6, "loans": 8, "transactions": 3, "messages": 12}
    assert report.as_of_date == DEFAULT_AS_OF
    assert report.phones_found == PHONES and report.emails_found == EMAILS
    assert any("date but no time" in w for w in warnings_of(report))  # M12 has a date only


def test_xlsx_and_csv_give_identical_results(cfg, tmp_path):
    rows = tiny_rows()
    rows["loans"][2][4] = 500  # a warning, so the comparison covers warnings too
    from_csv = validate_upload(upload_of(rows, "csv"), cfg)
    from_xlsx = validate_upload(upload_of(rows, "xlsx", tmp_path), cfg)
    assert from_csv.counts == from_xlsx.counts
    assert from_csv.as_of_date == from_xlsx.as_of_date
    assert (from_csv.phones_found, from_csv.emails_found) == (from_xlsx.phones_found, from_xlsx.emails_found)
    for table in TABLES:
        pd.testing.assert_frame_equal(from_csv.clean[table].reset_index(drop=True),
                                      from_xlsx.clean[table].reset_index(drop=True), check_dtype=False)
    strip = lambda items: [s.replace("file 'loans.csv'", "LOANS").replace("sheet 'loans'", "LOANS") for s in items]
    assert strip(warnings_of(from_csv)) == strip(warnings_of(from_xlsx))


def test_xlsx_and_csv_report_the_same_errors(cfg, tmp_path):
    rows = tiny_rows()
    rows["loans"][0][7] = "overdue"
    csv_errors = [s.replace("file 'loans.csv'", "X") for s in messages_of(validate_upload(upload_of(rows), cfg))]
    xlsx_errors = [s.replace("sheet 'loans'", "X")
                   for s in messages_of(validate_upload(upload_of(rows, "xlsx", tmp_path), cfg))]
    assert csv_errors == xlsx_errors == ["X, row 2: 'status' is not one of: active, repaid, in_arrears"]


# --- One test per validation rule ---------------------------------------------------------------------

def test_missing_sheet_is_an_error(cfg, tmp_path):
    rows = tiny_rows()
    del rows["loans"]
    errors = messages_of(validate_upload(upload_of(rows, "xlsx", tmp_path), cfg))
    assert "workbook: there is no sheet called 'loans'" in errors
    errors = messages_of(check(rows, cfg))
    assert any("no file for the 'loans' table" in e for e in errors)


def test_missing_column_is_an_error(cfg):
    rows = tiny_rows()
    columns = copy.deepcopy(COLUMNS)
    columns["loans"] = [c for c in columns["loans"] if c != "status"]
    rows["loans"] = [r[:7] for r in rows["loans"]]
    files = {}
    for table in TABLES:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(columns[table])
        writer.writerows(rows[table])
        files[f"{table}.csv"] = buffer.getvalue().encode()
    errors = messages_of(validate_upload(read_csvs(files), cfg))
    assert "file 'loans.csv': missing column(s): status" in errors


@pytest.mark.parametrize("table, index, value, expected", [
    ("borrowers", 2, "lots", "'monthly_income' must be a whole number of shillings ("),
    ("loans", 5, "Aug 1st 2026", "'issue_date' is not a date ("),
    ("loans", 5, "31/02/2026", "'issue_date' is not a date ("),
    ("messages", 4, "yesterday", "'sent_at' is not a date and time ("),
    ("loans", 3, "12.5", "'principal' must be a whole number of shillings ("),
])
def test_wrong_types_are_errors_with_row_numbers(cfg, table, index, value, expected):
    rows = tiny_rows()
    rows[table][1][index] = value  # second data row = row 3 of the file
    errors = messages_of(check(rows, cfg))
    assert any(e.startswith(f"file '{table}.csv', row 3: {expected}") for e in errors), errors
    assert not any(value in e for e in errors)  # the cell's value is never repeated


@pytest.mark.parametrize("table, index, value, expected", [
    ("loans", 3, 0, "'principal' must be more than 0"),
    ("loans", 3, -100, "'principal' must be more than 0"),
    ("loans", 4, -5, "'amount_outstanding' cannot be negative"),
    ("borrowers", 2, 0, "'monthly_income' must be more than 0"),
    ("transactions", 3, 0, "'amount' must be more than 0"),
])
def test_zero_and_negative_amounts_are_errors(cfg, table, index, value, expected):
    rows = tiny_rows()
    rows[table][0][index] = value
    assert f"file '{table}.csv', row 2: {expected}" in messages_of(check(rows, cfg))


@pytest.mark.parametrize("table, index, column", [
    ("lenders", 2, "size_category"), ("loans", 7, "status"), ("transactions", 4, "direction"),
    ("transactions", 5, "counterparty_type"), ("messages", 3, "recipient_type"),
])
def test_unknown_enum_values_are_errors(cfg, table, index, column):
    rows = tiny_rows()
    rows[table][0][index] = "banana"
    errors = messages_of(check(rows, cfg))
    assert any(e.startswith(f"file '{table}.csv', row 2: '{column}' is not one of") for e in errors)
    assert not any("banana" in e for e in errors)


def test_enum_values_are_accepted_in_any_letter_case(cfg):
    rows = tiny_rows()
    rows["loans"][0][7] = "In_Arrears"
    assert check(rows, cfg).ok


def test_duplicate_ids_are_errors(cfg):
    rows = tiny_rows()
    rows["loans"][1][0] = "LN1"
    assert "file 'loans.csv', rows 2, 3: the same 'loan_id' appears more than once" in messages_of(check(rows, cfg))


def test_loans_pointing_to_unknown_borrowers_or_lenders_are_errors(cfg):
    rows = tiny_rows()
    rows["loans"][0][1] = "B-nobody"
    rows["loans"][1][2] = "FL9"
    errors = messages_of(check(rows, cfg))
    assert "file 'loans.csv', row 2: 'borrower_id' is not a known borrower" in errors
    assert "file 'loans.csv', row 3: 'lender_id' is not a known lender" in errors
    assert not any("B-nobody" in e or "FL9" in e for e in errors)


def test_transactions_and_messages_pointing_to_unknown_records_are_errors(cfg):
    rows = tiny_rows()
    rows["transactions"][0][6] = "LN99"
    rows["transactions"][1][1] = "B-nobody"
    rows["messages"][0][1] = "FL9"
    rows["messages"][1][2] = "B-ghost"
    errors = messages_of(check(rows, cfg))
    assert "file 'transactions.csv', row 2: 'linked_loan_id' is not a known loan" in errors
    assert "file 'transactions.csv', row 3: 'borrower_id' is not a known borrower" in errors
    assert "file 'messages.csv', row 2: 'lender_id' is not a known lender" in errors
    assert "file 'messages.csv', row 3: 'borrower_id' is not a known borrower" in errors


def test_issue_date_after_due_date_is_an_error(cfg):
    rows = tiny_rows()
    rows["loans"][0][5], rows["loans"][0][6] = "2026-09-10", "2026-09-01"
    assert "file 'loans.csv', row 2: issue_date is after due_date" in messages_of(check(rows, cfg))


def test_repaid_loan_with_money_outstanding_is_only_a_warning(cfg):
    rows = tiny_rows()
    rows["loans"][2][4] = 500  # LN3 is repaid
    report = check(rows, cfg)
    assert report.ok
    assert "file 'loans.csv', row 4: status is 'repaid' but money is still outstanding" in warnings_of(report)


def test_open_loan_with_nothing_outstanding_is_only_a_warning(cfg):
    rows = tiny_rows()
    rows["loans"][4][4] = 0  # LN5 is active
    report = check(rows, cfg)
    assert report.ok
    assert "file 'loans.csv', row 6: status is 'active' but nothing is outstanding" in warnings_of(report)


def test_dates_after_the_as_of_date_are_only_warnings(cfg):
    report = check(tiny_rows(), cfg, as_of="2026-09-20")
    assert report.ok
    assert report.as_of_date == "2026-09-20"
    future = [w for w in warnings_of(report) if "is after the as-of date 2026-09-20" in w]
    assert "file 'messages.csv', row 6: 'sent_at' is after the as-of date 2026-09-20" in future
    assert not any("due_date" in w for w in future)  # a due date in the future is normal


def test_missing_transactions_is_allowed_with_a_note(cfg):
    rows = tiny_rows()
    del rows["transactions"]
    report = check(rows, cfg)
    assert report.ok
    assert f"transactions: {NO_TRANSACTIONS}" in warnings_of(report)
    rows = tiny_rows()
    rows["transactions"] = []
    assert f"transactions: {NO_TRANSACTIONS}" in warnings_of(check(rows, cfg))


def test_template_example_rows_are_refused(cfg):
    rows = tiny_rows()
    rows["lenders"].append(["EXAMPLE-L1", "Example Lender Ltd", "small"])
    errors = messages_of(check(rows, cfg))
    assert any("row 4: this is the template's example row" in e for e in errors)
    assert not any("EXAMPLE-L1" in e for e in errors)


# --- Writing: all or nothing, warnings do not block ----------------------------------------------------

def test_errors_leave_nothing_written(cfg):
    rows = tiny_rows()
    rows["messages"][11][3] = "neighbour"  # one bad value in the very last row
    result = do_import(rows, cfg)
    assert not result.ok
    assert "Nothing was written" in result.message
    assert list_datasets(cfg) == [get_dataset(cfg, DEMO)]
    assert not (Path(cfg["paths"]["datasets_dir"]) / "field-a").exists()


def test_warnings_do_not_block_and_everything_is_written(cfg):
    rows = tiny_rows()
    rows["loans"][2][4] = 500
    result = do_import(rows, cfg)
    assert result.ok, result.message
    assert result.rows_written == {"lenders": 2, "borrowers": 6, "loans": 8, "transactions": 3, "messages": 12}
    paths = get_dataset_paths(cfg, "field-a")
    conn = sqlite3.connect(str(paths.lending_db))
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 12
    meta = dict(conn.execute("SELECT key, value FROM meta"))
    conn.close()
    assert meta["synthetic"] == "false"
    assert meta["as_of_date"] == DEFAULT_AS_OF
    assert meta["notice"].startswith("REAL DATA: collected under permission. Handle as confidential.")


def test_a_real_dataset_reports_not_synthetic(cfg):
    assert do_import(tiny_rows(), cfg).ok
    assert is_synthetic(get_dataset_paths(cfg, "field-a")) is False
    assert is_synthetic(get_dataset_paths(cfg, DEMO)) is True
    info = get_dataset(cfg, "field-a")
    assert info.kind == "real" and info.as_of_date == DEFAULT_AS_OF and info.source_description == "test"


def test_import_labels_the_messages_with_the_local_classifier(cfg):
    result = do_import(tiny_rows(), cfg, classify=True)
    assert result.ok and result.labelled == 12
    conn = sqlite3.connect(str(get_dataset_paths(cfg, "field-a").predictions_db))
    labelled = conn.execute("SELECT COUNT(*) FROM message_predictions WHERE classifier = 'local'").fetchone()[0]
    synthetic = conn.execute("SELECT value FROM meta WHERE key = 'synthetic'").fetchone()[0]
    conn.close()
    assert labelled == 12 and synthetic == "false"


def test_missing_permission_refuses_and_writes_nothing(cfg):
    result = do_import(tiny_rows(), cfg, permission_confirmed=False)
    assert not result.ok and result.message == PERMISSION_REFUSAL
    assert not Path(cfg["paths"]["datasets_dir"]).exists()


def test_new_dataset_name_cannot_be_demo_or_repeated(cfg):
    assert not do_import(tiny_rows(), cfg, dataset_name="Demo").ok
    assert do_import(tiny_rows(), cfg).ok
    second = do_import(tiny_rows(), cfg)
    assert not second.ok and "already exists" in second.message


# --- Redaction -----------------------------------------------------------------------------------------

def test_redaction_counts_and_replaces(cfg):
    result = do_import(tiny_rows(), cfg, redact=True)
    assert (result.phones_redacted, result.emails_redacted) == (PHONES, EMAILS)
    conn = sqlite3.connect(str(get_dataset_paths(cfg, "field-a").lending_db))
    texts = dict(conn.execute("SELECT message_id, text FROM messages"))
    conn.close()
    assert "0772 123 456" not in texts["M4"] and "[PHONE]" in texts["M4"]
    assert "[EMAIL]" in texts["M5"] and "@" not in texts["M5"]
    assert "[PHONE]" in texts["M11"]
    assert "UGX 120,000" in texts["M2"]  # amounts are not phone numbers


def test_without_redaction_the_text_is_kept(cfg):
    result = do_import(tiny_rows(), cfg, redact=False)
    assert result.ok and result.phones_redacted == 0
    conn = sqlite3.connect(str(get_dataset_paths(cfg, "field-a").lending_db))
    text = conn.execute("SELECT text FROM messages WHERE message_id = 'M4'").fetchone()[0]
    conn.close()
    assert "0772 123 456" in text


@pytest.mark.parametrize("text, phones, emails", [
    ("call 0772 123 456 now", 1, 0),
    ("call 0772123456", 1, 0),
    ("call +256 772 123 456", 1, 0),
    ("call 256772123456", 1, 0),
    ("id 123456789", 1, 0),
    ("mail a.b@c.co.ug or x@y.org", 0, 2),
    ("pay UGX 1,250,000 by 5 Oct", 0, 0),
])
def test_phone_and_email_patterns(cfg, text, phones, emails):
    _, counts = redact_text(text, cfg)
    assert (counts["PHONE"], counts["EMAIL"]) == (phones, emails)


# --- Adding to an existing dataset -------------------------------------------------------------------------

def _second_batch():
    """A third lender whose borrowers include the shared borrower, who is already in the dataset."""
    return {
        "lenders": [["FL3", "Gamma Cash", "small"]],
        "borrowers": [[SHARED_BORROWER, "Central", 300000, "2025-02-01"],
                      ["B-000000000007", "Eastern", 400000, "2025-08-01"]],
        "loans": [["LN9", SHARED_BORROWER, "FL3", 70000, 75000, "2026-09-10", "2026-10-10", "active"],
                  ["LN10", "B-000000000007", "FL3", 90000, 95000, "2026-09-12", "2026-10-12", "active"]],
        "transactions": [],
        "messages": [["M13", "FL3", SHARED_BORROWER, "borrower", "2026-09-27 10:00:00", "Reminder from Gamma Cash."]],
    }


def test_adding_a_batch_keeps_existing_borrowers(cfg):
    assert do_import(tiny_rows(), cfg).ok
    result = do_import(_second_batch(), cfg, mode="add", target="field-a")
    assert result.ok, result.message
    assert result.report.skipped_existing_borrowers == 1
    existing = read_existing(get_dataset_paths(cfg, "field-a").lending_db)
    assert len(existing.ids["lenders"]) == 3 and len(existing.ids["borrowers"]) == 7
    assert len(existing.ids["loans"]) == 10 and len(existing.ids["messages"]) == 13


def test_adding_a_repeated_id_is_an_error_and_changes_nothing(cfg):
    assert do_import(tiny_rows(), cfg).ok
    batch = _second_batch()
    batch["loans"][1][0] = "LN1"  # already in the dataset
    result = do_import(batch, cfg, mode="add", target="field-a")
    assert not result.ok
    assert "file 'loans.csv', row 3: this 'loan_id' already exists in this dataset" in messages_of(result.report)
    existing = read_existing(get_dataset_paths(cfg, "field-a").lending_db)
    assert len(existing.ids["lenders"]) == 2 and len(existing.ids["loans"]) == 8


def test_adding_to_the_demo_is_refused(cfg):
    result = do_import(_second_batch(), cfg, mode="add", target=DEMO)
    assert not result.ok and "Adding to the demo dataset is not allowed" in result.message


# --- Templates ------------------------------------------------------------------------------------------------

def test_xlsx_template_has_instructions_headers_examples_and_dropdowns(cfg):
    workbook = openpyxl.load_workbook(io.BytesIO(build_xlsx_template(cfg)))
    assert workbook.sheetnames == ["Instructions", *TABLES]
    for table in TABLES:
        sheet = workbook[table]
        assert [c.value for c in sheet[1]] == COLUMNS[table]
        assert str(sheet.cell(row=2, column=1).value).startswith("EXAMPLE")
    assert len(workbook["loans"].data_validations.dataValidation) == 1
    assert len(workbook["transactions"].data_validations.dataValidation) == 2
    assert '"active,repaid,in_arrears"' in workbook["loans"].data_validations.dataValidation[0].formula1


def test_an_unchanged_template_is_refused_for_its_example_rows(cfg):
    report = validate_upload(read_xlsx(build_xlsx_template(cfg)), cfg)
    assert sum("template's example row" in e for e in messages_of(report)) == 5
    report = validate_upload(read_csvs(build_csv_templates(cfg)), cfg)
    assert sum("template's example row" in e for e in messages_of(report)) == 5


def test_csv_templates_have_the_exact_headers(cfg):
    templates = build_csv_templates(cfg)
    assert sorted(templates) == sorted(f"{t}.csv" for t in TABLES)
    for table in TABLES:
        header = templates[f"{table}.csv"].decode().splitlines()[0]
        assert header.split(",") == COLUMNS[table]


# --- Borrower codes ----------------------------------------------------------------------------------------------

def test_borrower_codes_are_deterministic_and_hide_the_raw_value(tmp_path):
    source = tmp_path / "raw.csv"
    source.write_text("phone,loan\n0772 123 456,LN1\n+256 772 123456,LN2\n0701 999 888,LN3\n", encoding="utf-8")
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    assert convert_file(source, first, "phone", "s3cret-salt") == 3
    convert_file(source, second, "phone", "s3cret-salt")
    assert first.read_text() == second.read_text()
    output = first.read_text()
    for raw in ("0772", "123 456", "772123456", "0701", "999 888", "s3cret"):
        assert raw not in output
    rows = list(csv.DictReader(io.StringIO(output)))
    assert list(rows[0]) == ["borrower_id", "loan"]
    assert rows[0]["borrower_id"] == rows[1]["borrower_id"]  # same person, two ways of writing the number
    assert rows[0]["borrower_id"] != rows[2]["borrower_id"]
    assert rows[0]["borrower_id"].startswith("B-") and len(rows[0]["borrower_id"]) == 14


def test_a_different_salt_gives_different_codes():
    assert make_code("0772123456", "salt-one") == make_code("0772 123 456", "salt-one")
    assert make_code("0772123456", "salt-one") != make_code("0772123456", "salt-two")
    with pytest.raises(ValueError):
        make_code("0772123456", "")


# --- Code checks -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["src/import_data.py", "src/import_templates.py", "src/make_borrower_codes.py",
                                    "src/redaction.py"])
def test_import_modules_never_mention_labels_secrets_or_network(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    assert forbidden_mentions(source, ("ground_truth", *LABEL_TABLES, *NETWORK_AND_SECRETS)) == []


def test_datasets_module_never_mentions_label_tables_secrets_or_network():
    # datasets.py may name the demo's optional answer-label FILE path (for the evaluation modules),
    # but never the label tables, secrets or the network.
    source = (ROOT / "src" / "datasets.py").read_text(encoding="utf-8")
    assert forbidden_mentions(source, (*LABEL_TABLES, *NETWORK_AND_SECRETS)) == []
