"""How money is written (Phase 7A). No Streamlit, no network.

Every amount in FairLend Watch is a whole number of Ugandan shillings (UGX). Whatever
shows money on screen, in a CSV header or in a plain-language explanation uses this
module, so the currency is written the same way everywhere:

    format_money(1500000)        -> "UGX 1,500,000"
    format_money(None)           -> "n/a"
    money_label("Total owed")    -> "Total owed (UGX)"
    money_column("total_owed")   -> "total_owed_ugx"

The code, symbol and number of decimals come from the 'currency' section of config.yaml.
"""

from __future__ import annotations

import math
from numbers import Number

DEFAULT_CURRENCY = {"code": "UGX", "symbol": "UGX", "decimals": 0}
MISSING = "n/a"


def _currency(cfg: dict | None) -> dict:
    return (cfg or {}).get("currency") or DEFAULT_CURRENCY


def format_money(amount, cfg: dict | None = None) -> str:
    """'UGX 1,500,000': the symbol, a space, thousands separators, no decimals for UGX.

    None, NaN, infinity or anything that is not a number gives 'n/a' (never an error).
    """
    currency = _currency(cfg)
    if amount is None or isinstance(amount, bool):
        return MISSING
    try:
        value = float(amount) if isinstance(amount, Number) else float(str(amount))
    except (TypeError, ValueError):
        return MISSING
    if math.isnan(value) or math.isinf(value):
        return MISSING
    decimals = int(currency["decimals"])
    text = f"{abs(value):,.{decimals}f}"
    if float(text.replace(",", "")) == 0:
        value = 0.0  # never write "-0"
    return f"{currency['symbol']} {'-' if value < 0 else ''}{text}"


def money_label(label: str, cfg: dict | None = None) -> str:
    """A column or field label with the currency: 'Total owed (UGX)'."""
    return f"{label} ({_currency(cfg)['code']})"


def money_column(name: str, cfg: dict | None = None) -> str:
    """A CSV column name with the currency: 'total_owed_ugx'."""
    return f"{name}_{_currency(cfg)['code'].lower()}"


def currency_code(cfg: dict | None = None) -> str:
    return str(_currency(cfg)["code"])
