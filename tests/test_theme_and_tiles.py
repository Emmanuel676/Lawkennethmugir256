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


def colours(svg: Path) -> dict[str, list[str]]:
    """Every colour in a logo file: the plate (first rect), the text and the icon strokes and fills."""
    source = svg.read_text(encoding="utf-8")
    plate = re.search(r'<rect[^>]*fill="(#[0-9A-Fa-f]{6})"', source)
    found = {"plate": [plate.group(1)] if plate else [],
             "wordmark": re.findall(r'<(?:text|tspan)[^>]*fill="(#[0-9A-Fa-f]{6})"', source),
             "icon": re.findall(r'<(?:circle|line)[^>]*(?:stroke|fill)="(#[0-9A-Fa-f]{6})"', source)}
    return found


LOGO_FILE, ICON_FILE = ASSETS / ui.LOGO, ASSETS / ui.ICON


# --- The logo: one file for every theme ---------------------------------------------------------------------------------

def test_there_is_one_logo_and_one_icon_and_no_theme_variants():
    assert sorted(p.name for p in ASSETS.glob("*.svg")) == ["fairlend-watch-icon.svg", "fairlend-watch-logo.svg"]
    assert set(ui.brand_images(ASSETS)) == {"logo", "icon"}


@pytest.mark.parametrize("svg", [LOGO_FILE, ICON_FILE])
def test_the_plate_is_opaque_white_and_covers_the_whole_image(svg):
    source = svg.read_text(encoding="utf-8")
    width, height = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', source).groups())
    rect = re.search(r"<rect([^>]*)/>", source).group(1)
    assert source.index("<rect") < source.index("<g")  # drawn first, so everything sits on it
    assert 'fill="#FFFFFF"' in rect and "opacity" not in rect
    assert float(re.search(r'width="([\d.]+)"', rect).group(1)) >= width - 2
    assert float(re.search(r'height="([\d.]+)"', rect).group(1)) >= height - 2


def test_the_wordmark_reads_at_4_5_to_1_or_better_on_both_sidebars():
    """The text sits on the opaque plate, so the plate is its background on a light AND a dark sidebar."""
    found = colours(LOGO_FILE)
    assert len(found["wordmark"]) == 3  # FairLend, Watch, the tagline
    for colour in found["wordmark"]:
        assert contrast(colour, found["plate"][0]) >= 4.5, colour


@pytest.mark.parametrize("svg", [LOGO_FILE, ICON_FILE])
def test_the_icon_marks_read_at_3_to_1_or_better_on_both_sidebars(svg):
    found = colours(svg)
    assert found["icon"]
    for colour in found["icon"]:
        assert contrast(colour, found["plate"][0]) >= 3, colour


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_plate_or_its_border_stands_out_on_each_sidebar(theme):
    """So the logo has a visible edge: the white plate on the dark sidebar, its slate border on the light one."""
    source = LOGO_FILE.read_text(encoding="utf-8")
    border = re.search(r'<rect[^>]*stroke="(#[0-9A-Fa-f]{6})"', source).group(1)
    plate = colours(LOGO_FILE)["plate"][0]
    assert max(contrast(plate, SIDEBAR[theme]), contrast(border, SIDEBAR[theme])) >= 2


def test_no_single_text_colour_could_work_on_both_sidebars_without_a_plate():
    """Why the plate is needed: no colour reaches 4.5:1 on both #F0F2F6 and #262730."""
    best = max(min(contrast(f"#{v:02X}{v:02X}{v:02X}", SIDEBAR["light"]), contrast(f"#{v:02X}{v:02X}{v:02X}",
                                                                                    SIDEBAR["dark"]))
               for v in range(256))
    assert best < 4.5


def test_the_logo_never_asks_for_the_theme(monkeypatch):
    def forbidden():
        raise AssertionError("the logo asked for the theme")

    monkeypatch.setattr(ui, "theme_type", forbidden)
    monkeypatch.setattr(ui, "_theme", forbidden)
    shown, pictures = [], []
    monkeypatch.setattr(ui.st, "logo", lambda image, **kwargs: shown.append((Path(image).name, kwargs)))
    monkeypatch.setattr(ui.st, "image", lambda image, **kwargs: pictures.append(Path(image).name))
    assert ui.show_logo(ASSETS) is True and ui.logo_image(assets_dir=ASSETS) is True
    assert shown[0][0] == ui.LOGO and Path(shown[0][1]["icon_image"]).name == ui.ICON
    assert pictures == [ui.LOGO]


def test_no_logo_code_reads_streamlit_theme_detection():
    import inspect
    import textwrap
    from leak_check import names_used
    for function in (ui.show_logo, ui.logo_image, ui.brand_images, ui._page_config):
        used = names_used(textwrap.dedent(inspect.getsource(function)))  # names in the code, not docstrings
        assert used.isdisjoint({"theme_type", "_theme", "context", "theme"}), (function.__name__, used)
    for page in ["app.py", *(f"pages/{p.name}" for p in (ROOT / "pages").glob("*.py"))]:
        assert "context.theme" not in (ROOT / page).read_text(encoding="utf-8"), page


def test_the_theme_type_is_none_when_streamlit_cannot_tell(monkeypatch):
    class Broken:
        @property
        def theme(self):
            raise RuntimeError("no context")

    monkeypatch.setattr(ui.st, "context", Broken())
    assert ui.theme_type() is None and ui._theme() == "light"  # used for chart text only


# --- Tile labels fit -------------------------------------------------------------------------------------------------------

def _metric_calls(file: str):
    import ast
    tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "metric":
            yield node


@pytest.mark.parametrize("file", ["app.py", "pages/1_Borrowers.py", "pages/6_Review.py"])
def test_tile_labels_fit_a_row_of_tiles(file):
    """At most 20 characters: 'Owed by high-band borrowers' (27) was cut off in a row of four on a laptop."""
    import ast
    labels = []
    for call in _metric_calls(file):
        label = call.args[0]
        if isinstance(label, ast.Constant):
            labels.append(label.value)
        elif isinstance(label, ast.JoinedStr):  # e.g. f"Band: {band}" with the longest band name
            labels.append("".join(part.value if isinstance(part, ast.Constant) else "medium" for part in label.values))
    assert labels and all(len(text) <= 20 for text in labels), [t for t in labels if len(t) > 20]


# --- The theme setting ------------------------------------------------------------------------------------------------

def test_light_is_the_default_theme_and_the_address_stays_unset():
    raw = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    settings = tomllib.loads(raw)
    assert settings["theme"]["base"] == "light"
    assert settings["browser"]["gatherUsageStats"] is False
    assert "address" not in settings.get("server", {})
    assert not re.search(r"(?im)^\s*(key|token|password|secret)\s*=", raw)


def test_presentation_mode_is_unchanged(monkeypatch, tmp_path):
    """A REAL dataset that is active in active_dataset.txt must still be ignored in presentation mode."""
    import copy
    from src.config import load_config
    from src.datasets import create_dataset, set_active
    cfg = copy.deepcopy(load_config())
    cfg["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    cfg["paths"]["active_dataset_file"] = str(tmp_path / "active.txt")
    monkeypatch.delenv(PRESENT_VARIABLE, raising=False)
    create_dataset(cfg, "Field Real", "test")
    set_active(cfg, "field-real")
    assert get_active_name(cfg) == "field-real"  # without presentation mode the real one is active...
    monkeypatch.setenv(PRESENT_VARIABLE, "1")
    assert get_active_name(cfg) == DEMO          # ...and with it, only the demo


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
