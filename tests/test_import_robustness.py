"""Field spreadsheets are messy (Phase 5.1): dates, amounts, file encodings, delimiters, spaces and case."""

from __future__ import annotations

import copy
import sqlite3

import pytest

from src.config import load_config
from src.datasets import get_dataset_paths
from src.import_data import (decode_text, import_upload, parse_amount, parse_day, parse_timestamp, read_csvs, read_xlsx,
                             validate_upload)

from tiny_data import COLUMNS, csv_bytes, tiny_rows, write_xlsx


@pytest.fixture
def cfg(tmp_path):
    custom = copy.deepcopy(load_config())
    custom["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    custom["paths"]["active_dataset_file"] = str(tmp_path / "active_dataset.txt")
    custom["privacy"]["name_list_file"] = str(tmp_path / "no_names.txt")
    return custom


def check(rows, cfg, **kwargs):
    return validate_upload(read_csvs(csv_bytes(rows)), cfg, **kwargs)


def errors_of(report):
    return [str(issue) for issue in report.errors]


# --- Dates ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("2026-08-31", "2026-08-31"),
    ("31/08/2026", "2026-08-31"),
    ("31-08-2026", "2026-08-31"),
    ("31.08.2026", "2026-08-31"),
    ("1/8/2026", "2026-08-01"),
    ("03/04/2026", "2026-04-03"),  # day first: 3 April
    ("2026/08/31", "2026-08-31"),
])
def test_day_first_dates_are_converted(cfg, text, expected):
    rows = tiny_rows()
    rows["loans"][0][5] = text  # issue_date of LN1, row 2
    report = check(rows, cfg, day_first=True)
    assert report.ok, errors_of(report)
    assert report.clean["loans"].loc[0, "issue_date"] == expected
    assert report.dates_converted == (0 if text == expected else 1)
    assert report.day_first is True


def test_converted_dates_are_counted_in_a_note(cfg):
    rows = tiny_rows()
    rows["loans"][0][5] = "01/08/2026"
    rows["loans"][0][6] = "31.08.2026"
    rows["borrowers"][0][3] = "1-2-2025"
    report = check(rows, cfg)
    assert report.ok and report.dates_converted == 3
    assert any("3 date(s) were converted to YYYY-MM-DD (read as day/month/year)" in str(n) for n in report.notes)


def test_an_ambiguous_date_is_an_error_naming_the_row_when_day_first_is_off(cfg):
    rows = tiny_rows()
    rows["loans"][1][5] = "03/04/2026"  # LN2, row 3: 3 April or 4 March?
    report = check(rows, cfg, day_first=False)
    assert not report.ok
    assert any(e.startswith("file 'loans.csv', row 3: 'issue_date' could be day/month or month/day")
               for e in errors_of(report))
    assert not any("03/04/2026" in e for e in errors_of(report))


def test_an_unambiguous_date_is_read_either_way_when_day_first_is_off(cfg):
    rows = tiny_rows()
    rows["loans"][0][5] = "25/07/2026"
    rows["loans"][0][6] = "08/30/2026"  # month first, clear because 30 > 12
    report = check(rows, cfg, day_first=False)
    assert report.ok, errors_of(report)
    assert report.clean["loans"].loc[0, ["issue_date", "due_date"]].tolist() == ["2026-07-25", "2026-08-30"]


def test_month_first_dates_are_errors_when_day_first_is_on(cfg):
    rows = tiny_rows()
    rows["loans"][0][6] = "08/30/2026"  # month 30 does not exist when read day first
    assert any("row 2: 'due_date' is not a date" in e for e in errors_of(check(rows, cfg, day_first=True)))


def test_the_option_defaults_to_the_config(cfg):
    rows = tiny_rows()
    rows["loans"][1][5] = "03/04/2026"
    assert check(rows, cfg).ok  # onboarding.day_first_default is true
    off = copy.deepcopy(cfg)
    off["onboarding"]["day_first_default"] = False
    assert not check(rows, off).ok


@pytest.mark.parametrize("text, expected", [
    ("2026-08-25 09:10:00", "2026-08-25 09:10:00"),
    ("25/08/2026 09:10", "2026-08-25 09:10:00"),
    ("25.08.2026 21:05:30", "2026-08-25 21:05:30"),
    ("2026-08-25T09:10:00", "2026-08-25 09:10:00"),
    ("25/08/2026", "2026-08-25"),
])
def test_timestamps_in_several_forms(cfg, text, expected):
    rows = tiny_rows()
    rows["messages"][0][4] = text
    report = check(rows, cfg)
    assert report.ok, errors_of(report)
    assert report.clean["messages"].loc[0, "sent_at"] == expected


@pytest.mark.parametrize("text", ["25/08/2026 25:10", "yesterday", "2026-08-25 9am"])
def test_bad_timestamps_are_errors(cfg, text):
    rows = tiny_rows()
    rows["messages"][0][4] = text
    assert any("row 2: 'sent_at' is not a date and time" in e for e in errors_of(check(rows, cfg)))


def test_parsers_by_hand():
    assert parse_day("31/02/2026") == (None, "invalid")
    assert parse_day("03/04/2026", day_first=False) == (None, "ambiguous")
    assert parse_day("04/04/2026", day_first=False)[1] == "converted"  # the same either way
    assert parse_timestamp("2026-08-25 09:10:00")[2] == "iso"


def test_excel_date_cells_still_work_and_text_dates_too(cfg, tmp_path):
    rows = tiny_rows()
    rows["loans"][0][5] = "01/08/2026"  # typed as text in the workbook; other dates are real Excel dates
    report = validate_upload(read_xlsx(write_xlsx(rows, tmp_path / "t.xlsx").read_bytes()), cfg)
    assert report.ok, errors_of(report)
    assert report.clean["loans"].loc[0, "issue_date"] == "2026-08-01"
    assert report.clean["messages"].loc[0, "sent_at"] == "2026-08-25 09:10:00"
    assert report.dates_converted == 1


# --- Amounts ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("200000", 200000), ("200,000", 200000), ("200 000", 200000), ("UGX 200,000", 200000), ("ugx200000", 200000),
    ("Ush 200,000", 200000), ("USh. 200,000", 200000), ("200,000/=", 200000), ("200,000 /=", 200000),
    ("UGX 1,250,000/=", 1250000), ("200,000.00", 200000), (" 200,000 ", 200000), ("200,000 UGX", 200000),
])
def test_accepted_amounts(cfg, text, expected):
    assert parse_amount(text)[0] == expected
    rows = tiny_rows()
    rows["loans"][0][3] = text
    report = check(rows, cfg)
    assert report.ok, errors_of(report)
    assert report.clean["loans"].loc[0, "principal"] == expected


@pytest.mark.parametrize("text", ["200k", "200K", "2,00,000", "200,00", "UGX", "20O000", "1.5", "200.000.000",
                                  "about 200000", "$200,000"])
def test_rejected_amounts_are_row_numbered_errors(cfg, text):
    assert parse_amount(text)[0] is None
    rows = tiny_rows()
    rows["loans"][2][3] = text  # LN3, row 4
    errors = errors_of(check(rows, cfg))
    assert any(e.startswith("file 'loans.csv', row 4: 'principal' must be a whole number of shillings") for e in errors)


def test_converted_amounts_are_counted(cfg):
    rows = tiny_rows()
    rows["loans"][0][3] = "UGX 100,000"
    rows["borrowers"][0][2] = "300,000/="
    report = check(rows, cfg)
    assert report.amounts_converted == 2
    assert any("2 amount(s)" in str(n) for n in report.notes)


# --- Files ------------------------------------------------------------------------------------------------

def test_a_utf8_bom_is_handled(cfg):
    assert decode_text(b"\xef\xbb\xbflender_id,name") == ("lender_id,name", "utf-8")  # the mark is removed
    files = csv_bytes(tiny_rows(), bom=True)
    assert files["lenders.csv"].startswith(b"\xef\xbb\xbf")
    report = validate_upload(read_csvs(files), cfg)
    assert report.ok, errors_of(report)
    assert report.counts["lenders"] == 2


def test_windows_1252_text_is_read_with_a_note(cfg):
    rows = tiny_rows()
    rows["messages"][0][5] = "Café owner – pay today"  # e-acute and an en dash
    files = csv_bytes(rows, encoding="cp1252")
    with pytest.raises(UnicodeDecodeError):
        files["messages.csv"].decode("utf-8")  # the file really is not UTF-8
    report = validate_upload(read_csvs(files), cfg)
    assert report.ok, errors_of(report)
    assert report.clean["messages"].loc[0, "text"] == "Café owner – pay today"
    assert any("messages.csv" in str(n) and "Windows-1252" in str(n) for n in report.notes)


@pytest.mark.parametrize("delimiter, word", [(";", "semicolons"), ("\t", "tabs")])
def test_semicolon_and_tab_delimiters_are_detected(cfg, delimiter, word):
    report = validate_upload(read_csvs(csv_bytes(tiny_rows(), delimiter=delimiter)), cfg)
    assert report.ok, errors_of(report)
    assert report.counts == {"lenders": 2, "borrowers": 6, "loans": 8, "transactions": 3, "messages": 12}
    assert report.clean["messages"].loc[0, "text"] == tiny_rows()["messages"][0][5]  # commas inside text survive
    assert any(f"columns are separated by {word}" in str(n) for n in report.notes)


def test_whitespace_and_case_on_list_columns_are_normalised_and_counted(cfg):
    rows = tiny_rows()
    rows["loans"][0][7] = " Active "
    rows["loans"][1][7] = "IN_ARREARS"
    rows["loans"][7][7] = "In Arrears"
    rows["messages"][2][3] = "Third-Party"
    rows["lenders"][0][2] = "SMALL"
    rows["lenders"][1][1] = "  Beta Loans  "  # free text: trimmed and counted too
    report = check(rows, cfg)
    assert report.ok, errors_of(report)
    assert report.clean["loans"]["status"].tolist()[:2] == ["active", "in_arrears"]
    assert report.clean["loans"].loc[7, "status"] == "in_arrears"
    assert report.clean["messages"].loc[2, "recipient_type"] == "third_party"
    assert report.clean["lenders"].loc[1, "name"] == "Beta Loans"
    assert report.cells_adjusted == 6
    assert any("6 cell(s) had extra spaces" in str(n) for n in report.notes)


def test_extra_columns_are_ignored_with_a_notice_listing_them(cfg):
    columns = copy.deepcopy(COLUMNS)
    columns["loans"] = COLUMNS["loans"] + ["officer", "branch"]
    rows = tiny_rows()
    rows["loans"] = [r + ["X", "Y"] for r in rows["loans"]]
    report = validate_upload(read_csvs(csv_bytes(rows, columns=columns)), cfg)
    assert report.ok, errors_of(report)
    assert "file 'loans.csv': extra column(s) ignored: officer, branch" in [str(w) for w in report.warnings]
    assert list(report.clean["loans"].columns) == COLUMNS["loans"] + ["_row"]


def test_a_blank_region_is_a_warning_never_an_error(cfg):
    rows = tiny_rows()
    rows["borrowers"][1][1] = ""
    rows["borrowers"][3][1] = "   "
    rows["borrowers"][4][1] = "Gulu town"  # free text is fine
    report = check(rows, cfg)
    assert report.ok, errors_of(report)
    assert "file 'borrowers.csv', row(s) 3, 5: 'region' is blank (2 row(s)); it is kept blank" in [
        str(w) for w in report.warnings]
    result = import_upload(read_csvs(csv_bytes(rows)), cfg, mode="new", permission_confirmed=True, redact=True,
                           dataset_name="Regions", classify=False)
    assert result.ok, result.message
    conn = sqlite3.connect(str(get_dataset_paths(cfg, "regions").lending_db))
    try:
        stored = dict(conn.execute("SELECT borrower_id, region FROM borrowers"))
    finally:
        conn.close()
    assert stored["B-000000000002"] == "" and stored["B-000000000005"] == "Gulu town"


def test_day_first_choice_is_stored_with_the_dataset(cfg):
    rows = tiny_rows()
    rows["loans"][0][5] = "01/08/2026"
    result = import_upload(read_csvs(csv_bytes(rows)), cfg, mode="new", permission_confirmed=True, redact=True,
                           dataset_name="Dates", classify=False, day_first=True)
    assert result.ok and result.report.day_first is True and result.report.dates_converted == 1
    conn = sqlite3.connect(str(get_dataset_paths(cfg, "dates").lending_db))
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta"))
        issued = conn.execute("SELECT issue_date FROM loans WHERE loan_id = 'LN1'").fetchone()[0]
    finally:
        conn.close()
    assert meta["dates_day_first"] == "true" and issued == "2026-08-01"
