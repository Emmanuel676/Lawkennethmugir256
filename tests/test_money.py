"""Phase 7A: every amount is Ugandan shillings (UGX), written one way everywhere."""

from __future__ import annotations

import ast
import copy
import io
import math
import re
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.config import ConfigError, load_config, validate_config
from src.dashboard_data import BORROWER_EXPORT_COLUMNS, borrower_table, flagged_borrowers_csv, load_all
from src.dashboard_ui import CONFIG_VARIABLE
from src.import_data import MONEY, read_csvs, validate_upload
from src.import_templates import build_xlsx_template, instructions
from src.money import MISSING, format_money, money_column, money_label
from src.overlap import explain

from tiny_data import csv_bytes, tiny_rows
from worlds import build_classified_world

ROOT = Path(__file__).resolve().parents[1]
UI_FILES = (["app.py"] + sorted(f"pages/{p.name}" for p in (ROOT / "pages").glob("*.py"))
            + ["src/dashboard_data.py", "src/dashboard_ui.py", "src/import_templates.py", "src/overlap.py",
               "src/money.py", "src/review.py", "src/lender_comparison.py"])
FOREIGN = re.compile(r"\$\s?\d|\bUSD\b|\bKES\b|\bKSh\b|\bdollars?\b|US\$", re.IGNORECASE)


# --- The formatter -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("amount, expected", [
    (1500000, "UGX 1,500,000"), (0, "UGX 0"), (999, "UGX 999"), (1000, "UGX 1,000"),
    (1234567890, "UGX 1,234,567,890"), (748400.0, "UGX 748,400"), (1499.6, "UGX 1,500"),
    (-5000, "UGX -5,000"), (-0.2, "UGX 0"), ("250000", "UGX 250,000"),
    (None, MISSING), (math.nan, MISSING), (float("inf"), MISSING), ("abc", MISSING), (True, MISSING),
    (pd.NA, MISSING), (pd.Series([7])[0], "UGX 7"),
])
def test_format_money(amount, expected):
    assert format_money(amount) == expected


def test_format_money_follows_the_config():
    cfg = copy.deepcopy(load_config())
    assert format_money(2500, cfg) == "UGX 2,500"
    cfg["currency"] = {"code": "TZS", "symbol": "TSh", "decimals": 2}
    assert format_money(2500, cfg) == "TSh 2,500.00"
    assert money_label("Total owed", cfg) == "Total owed (TZS)"
    assert money_column("total_owed", cfg) == "total_owed_tzs"


def test_labels_and_columns_default_to_ugx():
    assert money_label("Total owed") == "Total owed (UGX)"
    assert money_column("monthly_income") == "monthly_income_ugx"


# --- Config ---------------------------------------------------------------------------------------------------

def test_the_config_says_ugx_with_no_decimals():
    assert load_config()["currency"] == {"code": "UGX", "symbol": "UGX", "decimals": 0}
    assert "currency" not in load_config()["project"]  # one place only


@pytest.mark.parametrize("change, message", [
    (lambda c: c.pop("currency"), "missing the 'currency' section"),
    (lambda c: c["currency"].__setitem__("code", "ugx"), "currency.code"),
    (lambda c: c["currency"].__setitem__("code", "UGXX"), "currency.code"),
    (lambda c: c["currency"].__setitem__("symbol", " "), "currency.symbol"),
    (lambda c: c["currency"].__setitem__("decimals", -1), "currency.decimals"),
    (lambda c: c["currency"].__setitem__("decimals", 1.5), "currency.decimals"),
    (lambda c: c["currency"].__setitem__("decimals", True), "currency.decimals"),
])
def test_bad_currency_settings_are_rejected(change, message):
    broken = copy.deepcopy(load_config())
    change(broken)
    with pytest.raises(ConfigError, match=message):
        validate_config(broken)


# --- No other currency anywhere the user reads --------------------------------------------------------------------

def _literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


@pytest.mark.parametrize("module", UI_FILES)
def test_no_dollars_usd_or_kes_in_ui_text(module):
    hits = [text for text in _literals(ROOT / module) if FOREIGN.search(text)]
    assert hits == []


def test_no_dollars_usd_or_kes_in_the_docs():
    script = (ROOT / "docs" / "DEMO_SCRIPT.md").read_text(encoding="utf-8")
    assert [m.group(0) for m in FOREIGN.finditer(script) if m.group(0).lower() != "dollars"] == []
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    refused_example = "`$200,000`"  # listed on purpose: the import REFUSES amounts written in dollars
    assert [m.group(0) for m in FOREIGN.finditer(readme.replace(refused_example, ""))] == []


def test_the_foreign_currency_check_can_fail():
    assert FOREIGN.search("Pay $200 now") and FOREIGN.search("amount in USD") and FOREIGN.search("KES 500")
    assert not FOREIGN.search("UGX 200,000") and not FOREIGN.search(r"^\d+$")


# --- Where money is shown --------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return build_classified_world(tmp_path_factory.mktemp("money_world"), n_borrowers=300)


def test_the_explanation_writes_ugx(world):
    cfg, _ = world
    data = load_all(cfg)
    row = data.borrowers[data.borrowers["pts_debt_to_income"] > 0].iloc[0]
    line = next(x for x in explain(row, cfg) if x.startswith("Owes "))
    assert line.startswith(f"Owes {format_money(row['total_owed'], cfg)}, which is ")
    assert re.match(r"Owes UGX \d{1,3}(,\d{3})*, which is", line)


def test_screen_tables_and_exports_name_the_currency(world):
    cfg, _ = world
    data = load_all(cfg)
    assert data.currency == "UGX"
    assert "Total owed (UGX)" in borrower_table(data.borrowers.head(3), cfg).columns
    assert BORROWER_EXPORT_COLUMNS["total_owed"] == "total_owed_ugx"
    assert BORROWER_EXPORT_COLUMNS["monthly_income"] == "monthly_income_ugx"
    frame = pd.read_csv(io.BytesIO(flagged_borrowers_csv(data.borrowers.head(5))), comment="#")
    assert {"total_owed_ugx", "monthly_income_ugx"} <= set(frame.columns)
    assert frame["total_owed_ugx"].dtype.kind in "iu"  # plain whole shillings in the file, no symbol


def _run(page, config_path, monkeypatch):
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    monkeypatch.delenv("FAIRLEND_PRESENT", raising=False)
    return AppTest.from_file(str(ROOT / page), default_timeout=120).run()


def test_overview_and_borrower_pages_show_ugx(world, monkeypatch):
    cfg, config_path = world
    at = _run("app.py", config_path, monkeypatch)
    tile = next(m for m in at.metric if m.label == "Owed, high band")
    assert re.fullmatch(r"UGX \d{1,3}(\.\d)?[KMB]?", tile.value)  # compact, so it is never cut off
    assert re.fullmatch(r"Owed by high-band borrowers\. Exact amount: UGX \d{1,3}(,\d{3})*", tile.help)  # full wording
    assert "Total owed (UGX)" in at.dataframe[0].value.columns

    at = _run("pages/1_Borrowers.py", config_path, monkeypatch)
    first = at.dataframe[0].value["Borrower"].iloc[0]
    at.selectbox(key="borrower_pick").set_value(first).run()
    for label in ("Total owed", "Monthly income"):
        tile = next(m for m in at.metric if m.label == label)
        assert tile.value.startswith("UGX ") and tile.help.startswith("Exact amount: UGX ")
    loans = next(d.value for d in at.dataframe if "principal (UGX)" in d.value.columns)
    assert "owed (UGX)" in loans.columns


# --- Import side ---------------------------------------------------------------------------------------------------

def test_templates_say_amounts_are_ugx_whole_shillings():
    cfg = load_config()
    text = "\n".join(instructions(cfg))
    assert "Ugandan shillings (UGX), whole shillings, no decimals" in text
    workbook = openpyxl.load_workbook(io.BytesIO(build_xlsx_template(cfg)))
    for (table, column) in MONEY:
        sheet = workbook[table]
        header = next(c for c in sheet[1] if c.value == column)
        assert header.comment is not None and "Ugandan shillings (UGX)" in header.comment.text
        assert [c.value for c in sheet[1]][0] != "UGX"  # column names are unchanged
    assert [c.value for c in workbook["loans"][1]][3] == "principal"


def test_amount_errors_say_ugx_without_echoing_the_value():
    cfg = load_config()
    rows = tiny_rows()
    rows["loans"][0][3] = "200k"
    errors = [str(e) for e in validate_upload(read_csvs(csv_bytes(rows)), cfg).errors]
    message = next(e for e in errors if "'principal'" in e)
    assert "whole number of shillings (Ugandan shillings, UGX, no decimals" in message
    assert "200k" not in message


def test_the_data_page_says_ugx(world, monkeypatch):
    _, config_path = world
    at = _run("pages/5_Data.py", config_path, monkeypatch)
    assert any("are in Ugandan shillings (UGX), whole shillings" in c.value for c in at.caption)
    assert any("Ugandan shillings (UGX)" in m.value for m in at.markdown)
