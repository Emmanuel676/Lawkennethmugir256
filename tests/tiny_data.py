"""A tiny hand-made dataset for the import tests: 2 lenders, 6 borrowers, 8 loans, 3 transactions, 12 messages.

Borrower B-000000000001 borrows from BOTH lenders. Two messages contain a phone
number and one contains an email address, so redaction can be counted. Every
value is made up; the dataset contains no real person.
"""

from __future__ import annotations

import copy
import csv
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from src.import_data import COLUMNS, TABLES

SHARED_BORROWER = "B-000000000001"
DEFAULT_AS_OF = "2026-09-28"  # the latest event date in the rows below
PHONES = 2
EMAILS = 1

ROWS = {
    "lenders": [
        ["FL1", "Alpha Credit", "small"],
        ["FL2", "Beta Loans", "medium"],
    ],
    "borrowers": [
        ["B-000000000001", "Central", 300000, "2025-02-01"],
        ["B-000000000002", "Western", 450000, "2025-03-10"],
        ["B-000000000003", "Eastern", 520000, "2025-04-22"],
        ["B-000000000004", "Northern", 380000, "2025-01-05"],
        ["B-000000000005", "Central", 610000, "2025-06-18"],
        ["B-000000000006", "Western", 270000, "2025-07-30"],
    ],
    "loans": [
        ["LN1", "B-000000000001", "FL1", 100000, 120000, "2026-08-01", "2026-08-31", "in_arrears"],
        ["LN2", "B-000000000001", "FL2", 150000, 170000, "2026-08-20", "2026-09-20", "in_arrears"],
        ["LN3", "B-000000000002", "FL1", 80000, 0, "2026-06-01", "2026-06-30", "repaid"],
        ["LN4", "B-000000000002", "FL1", 90000, 95000, "2026-07-01", "2026-10-15", "active"],
        ["LN5", "B-000000000003", "FL2", 200000, 210000, "2026-09-01", "2026-10-01", "active"],
        ["LN6", "B-000000000004", "FL2", 50000, 0, "2026-05-10", "2026-06-10", "repaid"],
        ["LN7", "B-000000000005", "FL1", 120000, 130000, "2026-09-05", "2026-10-05", "active"],
        ["LN8", "B-000000000006", "FL2", 60000, 65000, "2026-08-15", "2026-09-14", "in_arrears"],
    ],
    "transactions": [
        ["T1", "B-000000000002", "2026-06-28", 80000, "out", "lender", "LN3"],
        ["T2", "B-000000000004", "2026-06-08", 50000, "out", "lender", "LN6"],
        ["T3", "B-000000000001", "2026-08-01", 100000, "in", "lender", "LN1"],
    ],
    "messages": [
        ["M1", "FL1", "B-000000000001", "borrower", "2026-08-25 09:10:00",
         "Reminder: your Alpha Credit loan of UGX 120,000 is due on 31 Aug."],
        ["M2", "FL1", "B-000000000001", "borrower", "2026-09-03 22:30:00",
         "Your loan is overdue. Pay UGX 120,000 today or we will come to your home."],
        ["M3", "FL1", "B-000000000001", "third_party", "2026-09-10 23:05:00",
         "Your friend owes Alpha Credit UGX 120,000 and is hiding. Tell them to pay."],
        ["M4", "FL2", "B-000000000001", "borrower", "2026-09-22 10:00:00",
         "Beta Loans: your payment of UGX 170,000 is 2 days late. Call us on 0772 123 456."],
        ["M5", "FL2", "B-000000000001", "borrower", "2026-09-28 21:45:00",
         "Final notice. Pay now or face the police. Questions: collections@beta.example"],
        ["M6", "FL1", "B-000000000002", "borrower", "2026-06-25 08:00:00",
         "Hello, a friendly reminder that UGX 80,000 is due on 30 Jun."],
        ["M7", "FL2", "B-000000000003", "borrower", "2026-09-25 14:20:00",
         "Your loan of UGX 210,000 is due on 1 Oct. Thank you."],
        ["M8", "FL2", "B-000000000004", "borrower", "2026-06-05 11:00:00",
         "Reminder: UGX 50,000 is due on 10 Jun."],
        ["M9", "FL1", "B-000000000005", "borrower", "2026-09-20 16:00:00",
         "Your repayment of UGX 130,000 is due on 5 Oct."],
        ["M10", "FL2", "B-000000000006", "borrower", "2026-09-16 09:30:00",
         "Your account is overdue by 2 days. Late fees apply. Pay UGX 65,000 today."],
        ["M11", "FL2", "B-000000000006", "borrower", "2026-09-19 02:15:00",
         "Pay UGX 65,000 or we will tell everyone in your contacts. Agent +256 772 987654."],
        ["M12", "FL2", "B-000000000006", "borrower", "2026-09-24", "Please settle UGX 65,000 as soon as you can."],
    ],
}

DATE_LIKE = {("borrowers", "joined_date"), ("loans", "issue_date"), ("loans", "due_date"),
             ("transactions", "txn_date"), ("messages", "sent_at")}


def tiny_rows() -> dict[str, list[list]]:
    return copy.deepcopy(ROWS)


def _as_excel_value(table: str, column: str, value):
    """Dates go into the workbook as real Excel dates, as a spreadsheet user would type them."""
    if (table, column) in DATE_LIKE and isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
    return value


def write_xlsx(rows: dict[str, list[list]], path: Path, columns: dict[str, list[str]] | None = None) -> Path:
    columns = columns or COLUMNS
    workbook = Workbook()
    workbook.active.title = "Instructions"
    workbook.active["A1"] = "Tiny test workbook"
    for table, table_rows in rows.items():
        sheet = workbook.create_sheet(table)
        sheet.append(columns[table])
        for row in table_rows:
            sheet.append([_as_excel_value(table, c, v) for c, v in zip(columns[table], row)])
    workbook.save(path)
    return path


def write_csvs(rows: dict[str, list[list]], folder: Path, columns: dict[str, list[str]] | None = None) -> dict[str, Path]:
    columns = columns or COLUMNS
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for table, table_rows in rows.items():
        path = folder / f"{table}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns[table])
            writer.writerows(table_rows)
        files[path.name] = path
    return files


def csv_bytes(rows: dict[str, list[list]], delimiter: str = ",", encoding: str = "utf-8", bom: bool = False,
              columns: dict[str, list[str]] | None = None) -> dict[str, bytes]:
    """The tables as CSV file contents. delimiter, encoding and a UTF-8 byte-order mark can be chosen."""
    import io
    columns = columns or COLUMNS
    out = {}
    for table in TABLES:
        if table not in rows:
            continue
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=delimiter)
        writer.writerow(columns[table])
        writer.writerows(rows[table])
        data = buffer.getvalue().encode(encoding)
        out[f"{table}.csv"] = (b"\xef\xbb\xbf" + data) if bom else data
    return out
