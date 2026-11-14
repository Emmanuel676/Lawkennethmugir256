"""The upload check for Importer and Admin imports in the web app (Phase 13).

The Phase 11 gate (src.team_access.synthetic_gate) also requires lender names ending in "(Demo)" and messages
ending in "(SYNTHETIC)". It cannot be told to skip those two rules, and src/ must not change, so its other checks are
wrapped here, using the same building blocks and the same settings:

  size       the whole upload at most team_demo.max_upload_mb
  rows       each table (sheet or CSV file) at most team_demo.max_rows_per_file rows
  personal   no phone-, ID- or email-like text in lender names or message text, found with the existing redactor
             (src.redaction, names list not used) exactly as the gate does

It works on the uploaded bytes in memory and writes nothing. A refused upload is never validated, stored or written.
Messages give file, column and row numbers, never values.
"""

from __future__ import annotations

from src.import_data import read_csvs, read_xlsx
from src.redaction import build_redactor

PERSONAL_TOKENS = ("PHONE", "ID", "EMAIL")
MAX_ROWS_LISTED = 10


def _rows(rows: list[int]) -> str:
    shown = ", ".join(str(r) for r in rows[:MAX_ROWS_LISTED])
    return shown + (f" and {len(rows) - MAX_ROWS_LISTED} more" if len(rows) > MAX_ROWS_LISTED else "")


def check(files: dict[str, bytes], file_type: str, cfg: dict) -> list[str]:
    """Plain reasons to refuse the upload. An empty list means it may go on to the normal validation."""
    limits = cfg["team_demo"]
    total = sum(len(content) for content in files.values())
    if total > float(limits["max_upload_mb"]) * 1024 * 1024:
        return [f"The upload is {total / 1024 / 1024:.1f} MB; this app accepts at most {limits['max_upload_mb']} MB."]
    upload = read_xlsx(next(iter(files.values()))) if file_type == "xlsx" else read_csvs(files)
    problems = []
    for table, frame in upload.tables.items():
        if len(frame) > int(limits["max_rows_per_file"]):
            problems.append(f"{upload.sources.get(table, table)} has {len(frame):,} rows; this app accepts at most "
                            f"{int(limits['max_rows_per_file']):,} rows per file.")
    redactor = build_redactor(cfg, names=[])

    def personal_like(frame, column: str, source: str, what: str) -> None:
        hits = [int(row) for text, row in zip(frame[column].astype(str), frame["_row"])
                if any(n for token, n in redactor.redact(text)[1].items() if token in PERSONAL_TOKENS)]
        if hits:
            problems.append(f"{source}: {len(hits)} {what} contain something that looks like a phone number, an ID "
                            f"number or an email address (rows {_rows(hits)}). Remove it and upload again.")

    lenders = upload.tables.get("lenders")
    if lenders is not None and "name" in lenders.columns:
        personal_like(lenders, "name", upload.sources["lenders"], "lender name(s)")
    messages = upload.tables.get("messages")
    if messages is not None and "text" in messages.columns:
        personal_like(messages, "text", upload.sources["messages"], "message(s)")
    return problems
