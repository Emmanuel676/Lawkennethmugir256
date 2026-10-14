"""Phase 8C: light theme by default, the right logo per theme, readable chart colours, compact UGX tiles."""

from __future__ import annotations

import math
import re
import tomllib
from pathlib import Path

import pytest

import src.dashboard_ui as ui
from src.datasets import DEMO, PRESENT_VARIABLE, get_active_name
from src.money import MISSING, format_money, format_money_compact

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SIDEBAR = {"light": "#F0F2F6", "dark": "#262730"}  # Streamlit 1.65's secondaryBg (gray20 / gray90)
PAGE = {"light": "#FFFFFF", "dark": "#0E1117"}     # Streamlit 1.65's bgColor


def _luminance(colour: str) -> float:
    channels = [int(colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def text_colours(svg: Path) -> dict[str, str]:
    """The fill colour of each piece of text in a logo SVG: the name, 'Watch' and the tagline."""
    source = svg.read_text(encoding="utf-8")
    return {"FairLend": re.search(r'font-size="38"[^>]*fill="(#[0-9A-Fa-f]{6})"', source).group(1),
            "Watch": re.search(r'<tspan fill="(#[0-9A-Fa-f]{6})"', source).group(1),
            "tagline": re.search(r'font-size="13"[^>]*fill="(#[0-9A-Fa-f]{6})"', source).group(1)}


# --- The logo --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("theme, expected", [
    ("light", "fairlend-watch-logo-light.svg"),   # dark text for a light sidebar
    ("dark", "fairlend-watch-logo-dark.svg"),     # pale text for a dark sidebar
    (None, "fairlend-watch-logo-light.svg"),      # unknown: light is the default theme
    ("sepia", "fairlend-watch-logo-light.svg"),
])
def test_the_logo_matches_the_theme(theme, expected):
    assert ui.pick_logo(theme, ui.brand_images(ASSETS)).name == expected


def test_a_missing_file_falls_back_to_the_other_logo(tmp_path):
    (tmp_path / ui.LOGO_DARK).write_text(ASSETS.joinpath(ui.LOGO_DARK).read_text(encoding="utf-8"), encoding="utf-8")
    assert ui.pick_logo("light", ui.brand_images(tmp_path)).name == ui.LOGO_DARK
    assert ui.pick_logo("light", {}) is None


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_chosen_logo_is_readable_on_that_themes_sidebar(theme):
    colours = text_colours(ui.pick_logo(theme, ui.brand_images(ASSETS)))
    assert contrast(colours["FairLend"], SIDEBAR[theme]) >= 7      # the name: well above 4.5:1
    assert contrast(colours["Watch"], SIDEBAR[theme]) >= 4.5
    assert contrast(colours["tagline"], SIDEBAR[theme]) >= 4.5


def test_the_old_mismatch_really_hid_the_name():
    """What was seen on the cloud: the pale-text logo on the light sidebar. 'FairLend' vanishes, 'Watch' does not."""
    colours = text_colours(ASSETS / ui.LOGO_DARK)
    assert contrast(colours["FairLend"], SIDEBAR["light"]) < 1.1
    assert contrast(colours["Watch"], SIDEBAR["light"]) > contrast(colours["FairLend"], SIDEBAR["light"])


@pytest.mark.parametrize("reported, expected", [("light", ui.LOGO_LIGHT), ("dark", ui.LOGO_DARK), (None, ui.LOGO_LIGHT)])
def test_show_logo_asks_the_theme_every_run(monkeypatch, reported, expected):
    shown = []
    monkeypatch.setattr(ui, "theme_type", lambda: reported)
    monkeypatch.setattr(ui.st, "logo", lambda image, **kwargs: shown.append((Path(image).name, kwargs)))
    assert ui.show_logo(ASSETS) is True
    assert shown[0][0] == expected and Path(shown[0][1]["icon_image"]).name == ui.ICON


def test_the_theme_type_is_none_when_streamlit_cannot_tell(monkeypatch):
    class Broken:
        @property
        def theme(self):
            raise RuntimeError("no context")

    monkeypatch.setattr(ui.st, "context", Broken())
    assert ui.theme_type() is None and ui._theme() == "light"


def test_the_about_page_logo_follows_the_theme(monkeypatch):
    shown = []
    monkeypatch.setattr(ui, "theme_type", lambda: "dark")
    monkeypatch.setattr(ui.st, "image", lambda image, **kwargs: shown.append(Path(image).name))
    assert ui.logo_image(assets_dir=ASSETS) is True and shown == [ui.LOGO_DARK]


# --- The theme setting ------------------------------------------------------------------------------------------------

def test_light_is_the_default_theme_and_the_address_stays_unset():
    raw = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    settings = tomllib.loads(raw)
    assert settings["theme"]["base"] == "light"
    assert settings["browser"]["gatherUsageStats"] is False
    assert "address" not in settings.get("server", {})
    assert not re.search(r"(?im)^\s*(key|token|password|secret)\s*=", raw)


def test_presentation_mode_is_unchanged(monkeypatch, tmp_path):
    import copy
    from src.config import load_config
    cfg = copy.deepcopy(load_config())
    cfg["paths"]["active_dataset_file"] = str(tmp_path / "active.txt")
    (tmp_path / "active.txt").write_text("some-real-dataset\n", encoding="utf-8")
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    assert get_active_name(cfg) == DEMO


# --- Chart colours readable on both themes --------------------------------------------------------------------------------

def test_fixed_chart_colours_keep_3_to_1_on_both_page_backgrounds():
    for colour in (ui.CHART_BAR, ui.CHART_INTERVAL):
        assert min(contrast(colour, PAGE["light"]), contrast(colour, PAGE["dark"])) >= 3, colour


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_chart_text_follows_the_theme(monkeypatch, theme):
    import pandas as pd
    monkeypatch.setattr(ui, "theme_type", lambda: theme)
    spec = str(ui.band_chart(pd.DataFrame({"band": ["high"], "borrowers": [3]})).to_dict())
    assert ui.CHART_TEXT[theme] in spec and contrast(ui.CHART_TEXT[theme], PAGE[theme]) >= 7
    ranked = pd.DataFrame({"rank": [1], "name": ["A"], "abusive_share": [0.4], "abusive_low": [0.3],
                           "abusive_high": [0.5], "n_messages": [100]})
    spec = str(ui.lender_interval_chart(ranked).to_dict())
    assert "black" not in spec.lower() and ui.CHART_INTERVAL in spec


# --- Compact money for tiles -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("amount, expected", [
    (0, "UGX 0"), (None, MISSING), (math.nan, MISSING), (999, "UGX 999"), (1000, "UGX 1K"), (1500, "UGX 1.5K"),
    (590_000, "UGX 590K"), (999_999, "UGX 1M"), (1_000_000, "UGX 1M"), (259_829_300, "UGX 259.8M"),
    (999_960_000, "UGX 1B"), (-2_500_000, "UGX -2.5M"), (999.6, "UGX 1K"), ("abc", MISSING),
])
def test_format_money_compact(amount, expected):
    assert format_money_compact(amount) == expected


def test_compact_tiles_are_short_and_the_exact_amount_is_kept():
    for amount in (259_829_300, 1_234_567_890, 748_400):
        compact = format_money_compact(amount)
        assert len(compact) <= 10 and len(compact) < len(format_money(amount))
    assert format_money(259_829_300) == "UGX 259,829,300"  # the exact form is unchanged everywhere else
