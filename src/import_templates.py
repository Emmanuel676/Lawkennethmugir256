"""Import templates: an Excel workbook and five CSV files, generated in code (Phase 4B).

The workbook has an Instructions sheet, the five data sheets with the exact
column headers, one example row each (ids start with the configured example
prefix and the row is shaded; the importer refuses example rows), and dropdowns
for the columns with a fixed list of values.
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src.import_data import COLUMNS, ENUMS, MONEY, PERMISSION_TEXT, TABLES

DROPDOWN_ROWS = 5000


def example_rows(cfg: dict) -> dict[str, list]:
    p = str(cfg["onboarding"]["example_id_prefix"])
    borrower = f"{p}-B-3f9a1c2d4e5b"
    return {
        "lenders": [f"{p}-L1", "Example Lender Ltd", "small"],
        "borrowers": [borrower, "Central", 450000, "2025-01-15"],
        "loans": [f"{p}-LN1", borrower, f"{p}-L1", 200000, 230000, "2026-08-01", "2026-08-31", "in_arrears"],
        "transactions": [f"{p}-T1", borrower, "2026-08-05", 50000, "out", "lender", f"{p}-LN1"],
        "messages": [f"{p}-M1", f"{p}-L1", borrower, "borrower", "2026-09-02 21:15:00",
                     "Your loan of UGX 230,000 is overdue. Please pay today."],
    }


def instructions(cfg: dict) -> list[str]:
    p = cfg["onboarding"]["example_id_prefix"]
    return [
        f"{cfg['project']['name']} - data import template",
        "",
        "1. Fill in the five sheets: lenders, borrowers, loans, transactions, messages. Do not rename sheets or columns.",
        f"2. Delete the shaded example row in every sheet (its ids start with {p}). The import refuses example rows.",
        "3. Dates: YYYY-MM-DD (for example 2026-08-01) or day/month/year (01/08/2026, 01-08-2026, 01.08.2026),",
        "   or Excel date cells. sent_at may also have a time: HH:MM or HH:MM:SS after the date.",
        f"4. Money: every amount is in Ugandan shillings ({cfg['currency']['code']}), whole shillings, no decimals",
        "   (230000, 230,000, UGX 230,000 or 230,000/= are all fine; 230k is not). Money columns: monthly_income,",
        "   principal, amount_outstanding and amount; each has a note on its header cell.",
        "5. Columns with a fixed list of values have a dropdown.",
        "6. borrower_id must be a code, never a name, phone number or ID number. Make the codes with",
        "   python -m src.make_borrower_codes, using the SAME secret salt for every lender, so the same person",
        "   gets the same code everywhere. Otherwise overlaps between lenders cannot be found.",
        "7. transactions may be left empty, but then cycling (borrowing to repay) cannot be detected.",
        "8. Remove names from message text. Phone numbers, email addresses and ID numbers (NIN) can be",
        "   redacted on import, and names from a name list, but names cannot be detected automatically.",
        f"9. On import you must confirm: \"{PERMISSION_TEXT}\".",
        "",
        "Real data is confidential. Do not email this file once it holds real data.",
    ]


def build_xlsx_template(cfg: dict) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Instructions"
    for number, line in enumerate(instructions(cfg), start=1):
        sheet.cell(row=number, column=1, value=line)
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.column_dimensions["A"].width = 110

    shade = PatternFill("solid", fgColor="FFF2CC")
    examples = example_rows(cfg)
    for table in TABLES:
        ws = workbook.create_sheet(table)
        for col, name in enumerate(COLUMNS[table], start=1):
            ws.cell(row=1, column=col, value=name).font = Font(bold=True)
            ws.column_dimensions[get_column_letter(col)].width = max(14, len(name) + 4)
            ws.cell(row=2, column=col, value=examples[table][col - 1]).fill = shade
            if (table, name) in MONEY:
                ws.cell(row=1, column=col).comment = Comment(
                    f"Ugandan shillings ({cfg['currency']['code']}), whole shillings, no decimals.", "template")
        ws.cell(row=2, column=1).comment = Comment("EXAMPLE ROW - delete this row before importing.", "template")
        ws.freeze_panes = "A2"
        for (enum_table, column), values in ENUMS.items():
            if enum_table != table:
                continue
            letter = get_column_letter(COLUMNS[table].index(column) + 1)
            check = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True,
                                   showErrorMessage=True, errorTitle="Not allowed",
                                   error=f"Choose one of: {', '.join(values)}")
            check.add(f"{letter}2:{letter}{DROPDOWN_ROWS}")
            ws.add_data_validation(check)
        if table == "messages":
            ws.column_dimensions[get_column_letter(len(COLUMNS[table]))].width = 70
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_csv_templates(cfg: dict) -> dict[str, bytes]:
    """{file name: CSV bytes} with the header and the example row."""
    import csv

    files = {}
    examples = example_rows(cfg)
    for table in TABLES:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(COLUMNS[table])
        writer.writerow(examples[table])
        files[f"{table}.csv"] = buffer.getvalue().encode("utf-8")
    return files
