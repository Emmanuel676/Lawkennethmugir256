"""Turn phone numbers or ID numbers into borrower codes before data leaves a lender.

    python -m src.make_borrower_codes INPUT.csv --column phone --output OUTPUT.csv

Each raw value is replaced by a code: "B-" followed by the first 12 hex
characters of HMAC-SHA256(secret salt, normalised value). The same person gets
the same code at every lender, as long as everyone uses the SAME salt, so the
overlap detector can see one borrower across lenders without anyone sharing
the raw numbers.

The salt is typed in at a hidden prompt (getpass). It is never read from a file,
never stored and never printed. Keep it secret, and reuse it for every lender:
with a different salt the codes will not match.

Normalisation: spaces, dashes, dots and brackets are removed and letters are
upper-cased. Ugandan phone numbers written +256 7xx..., 256 7xx... or 07xx...
all become 07xxxxxxxx first, so they give the same code.

The output has the raw column replaced by a 'borrower_id' column of codes.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import hmac
import re
import sys
from pathlib import Path

CODE_PREFIX = "B-"
CODE_HEX_LENGTH = 12
OUTPUT_COLUMN = "borrower_id"


def normalise(raw: str) -> str:
    value = re.sub(r"[\s\-.()]", "", str(raw)).upper()
    if value.startswith("+"):
        value = value[1:]
    if re.fullmatch(r"2567\d{8}", value):
        value = "0" + value[3:]
    elif re.fullmatch(r"7\d{8}", value):
        value = "0" + value
    return value


def make_code(raw: str, salt: str) -> str:
    """The borrower code for one raw value. Same value + same salt = same code."""
    if not salt:
        raise ValueError("The salt must not be empty.")
    digest = hmac.new(salt.encode("utf-8"), normalise(raw).encode("utf-8"), hashlib.sha256).hexdigest()
    return CODE_PREFIX + digest[:CODE_HEX_LENGTH]


def convert_file(input_path: Path, output_path: Path, column: str, salt: str) -> int:
    """Write a copy of input_path with the raw column replaced by borrower codes. Returns the number of rows."""
    with Path(input_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        if column not in fields:
            raise ValueError(f"The file has no column called {column!r}. Columns: {', '.join(fields)}")
        if OUTPUT_COLUMN in fields and OUTPUT_COLUMN != column:
            raise ValueError(f"The file already has a {OUTPUT_COLUMN!r} column; remove it or use it as --column.")
        rows = list(reader)
    out_fields = [OUTPUT_COLUMN if f == column else f for f in fields]
    with Path(output_path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields)
        writer.writeheader()
        for row in rows:
            raw = row.pop(column)
            row[OUTPUT_COLUMN] = make_code(raw, salt) if str(raw).strip() else ""
            writer.writerow({f: row.get(f, "") for f in out_fields})
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replace phone or ID numbers with borrower codes.")
    parser.add_argument("input", help="CSV file with a column of raw phone or ID numbers.")
    parser.add_argument("--column", required=True, help="Name of the column holding the raw values.")
    parser.add_argument("--output", required=True, help="Where to write the new CSV.")
    args = parser.parse_args(argv)

    if Path(args.output).resolve() == Path(args.input).resolve():
        print("Write the output to a different file; the original is not overwritten.")
        return 1
    salt = getpass.getpass("Secret salt (typing is hidden): ")
    again = getpass.getpass("Type the secret salt again: ")
    if not salt or salt != again:
        print("The two entries were empty or did not match. Nothing was written.")
        return 1
    try:
        count = convert_file(Path(args.input), Path(args.output), args.column, salt)
    except (OSError, ValueError) as error:
        print(error)
        return 1
    print(f"Wrote {count:,} rows to {args.output}, with '{args.column}' replaced by '{OUTPUT_COLUMN}' codes.")
    print("Keep the salt secret and use exactly the same salt for every lender, or the same person will get")
    print("different codes and the overlap detector will not see them. The salt was not saved anywhere.")
    print("Delete the original file with the raw numbers once you no longer need it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
