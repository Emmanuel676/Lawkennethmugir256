"""Shared Streamlit helpers for every dashboard page (Phase 4).

Each page calls page_setup() first. It applies the branding (product name and
tagline from config.yaml, page icon, logo), shows the synthetic-data notice and
the human-review line, and loads the data (cached until either database file
changes). If the data is missing or stale, it shows the commands to run and
stops the page, so nobody sees a traceback.

Every page wraps its body in `with guarded("<title>"):`. An unexpected error then shows
"Something went wrong" with a short error code instead of a traceback, and the exception
type and code locations (never data values) go to the app log (src/app_log.py).

In presentation mode (src/datasets.presentation_mode) the dataset switcher is replaced by
a "Presentation mode" tag, and the Data and Review pages call presentation_block().

All logic lives in src/dashboard_data.py; this file only handles layout.
Set the environment variable LENDING_MONITOR_CONFIG to use another config file
(the tests do this to point the dashboard at a temporary dataset).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.config import PROJECT_ROOT, ConfigError, load_config
from src.dashboard_data import REVIEW_LINE, DashboardData, data_signature, load_all
from src.app_log import log_exception
from src.bootstrap import STEPS, demo_status, ensure_demo, signature
from src.datasets import DEMO, PRESENT_VARIABLE, get_active_name, list_datasets, presentation_mode, set_active
from src.overlap import DEFAULT_NOTICE
from src.team_access import (BANNER as TEAM_BANNER, NOT_RECOGNISED, PrivateCopy, matching_hash, parse_hashes,
                             record_attempt, sweep, throttled_for)

CONFIG_VARIABLE = "LENDING_MONITOR_CONFIG"
ASSETS_DIR = PROJECT_ROOT / "assets"
# Logo files. ONE wide logo and ONE icon, each on its own white rounded plate, so they read the same on a
# light and a dark sidebar with NO theme detection (Phase 8D). st.logo shows an <img>, which cannot take the
# page's text colour, and no single text colour reaches 4.5:1 on both sidebars, so the plate is the backing.
LOGO = "fairlend-watch-logo.svg"
ICON = "fairlend-watch-icon.svg"
FALLBACK_NAME = "Dashboard (config.yaml could not be read)"


def config_path() -> str | None:
    return os.environ.get(CONFIG_VARIABLE) or None


def brand_images(assets_dir: Path = ASSETS_DIR) -> dict[str, Path]:
    """The logo files that exist: keys 'logo' and 'icon'. Missing files are simply left out."""
    found = {}
    for key, name in (("logo", LOGO), ("icon", ICON)):
        path = Path(assets_dir) / name
        if path.is_file():
            found[key] = path
    return found


# Charts only (never the logo): text and track colours, per theme (Streamlit's own body-text colours). Lines and bars use
# colours chosen to keep at least 3:1 contrast on BOTH backgrounds, so they need no theme at all.
CHART_TEXT = {"light": "#31333F", "dark": "#FAFAFA"}
CHART_TRACK = {"light": "#D5DAE3", "dark": "#3D4150"}
CHART_BAR = "#4C78A8"       # 4.6:1 on white, 4.1:1 on the dark page
CHART_INTERVAL = "#D97706"  # 3.2:1 on white, 5.9:1 on the dark page


def theme_type() -> str | None:
    """The viewer's theme as Streamlit reports it ('light', 'dark' or None). Never raises.

    Streamlit 1.65 says this can be wrong on the very first run of a session and right after the viewer
    changes theme; it is right again on the next run. config.toml makes light the default theme.
    """
    try:
        value = st.context.theme.type
    except Exception:
        return None
    return value if value in ("light", "dark") else None


def _theme() -> str:
    """For CHART text colours only: 'dark' when Streamlit clearly says dark, otherwise 'light'."""
    return "dark" if theme_type() == "dark" else "light"


def show_logo(assets_dir: Path = ASSETS_DIR) -> bool:
    """Show the wide logo in the sidebar, with the icon as the small version. The same files on every theme.

    Never raises: with missing or unreadable files the page simply has no logo. Returns True if shown.
    """
    images = brand_images(assets_dir)
    wide = images.get("logo")
    if wide is None:
        return False
    try:
        st.logo(str(wide), icon_image=str(images["icon"]) if "icon" in images else None, size="large")
        return True
    except Exception:
        return False


def _page_config(title: str, name: str, assets_dir: Path = ASSETS_DIR) -> None:
    icon = brand_images(assets_dir).get("icon")
    try:
        st.set_page_config(page_title=f"{title} - {name}", page_icon=str(icon) if icon else None, layout="wide")
    except Exception:
        st.set_page_config(page_title=f"{title} - {name}", layout="wide")


def brand_header(title: str, cfg: dict | None) -> None:
    """Page config, logo and the page header. Every page shows the product name and tagline."""
    name = cfg["project"]["name"] if cfg else FALLBACK_NAME
    tagline = cfg["project"]["tagline"] if cfg else ""
    _page_config(title, name)
    show_logo()
    st.title(f"{name} · {title}")
    if tagline:
        st.caption(f"{name}: {tagline}. Synthetic-data prototype.")


@st.cache_resource(show_spinner="Loading the dataset...", max_entries=4)
def _cached_load(path: str | None, signature: tuple, _cfg: dict) -> DashboardData:
    # signature is part of the cache key only: it changes when a database file changes, and it names the
    # files, so a team session's private copy (Phase 11) is cached apart from the shared demo.
    # cache_resource keeps the object as it is. cache_data would pickle it on every store and
    # copy it on every read, which took about 4 seconds at 20,000 borrowers. Pages only read it.
    return load_all(_cfg)


REAL_LABEL_WARNING = ("Message labels come from a model trained on synthetic text. On real messages they are "
                      "unreliable until a person has checked a sample.")


def banner(data: DashboardData | None, notice: str = DEFAULT_NOTICE) -> None:
    """The data-status banner. Demo: the synthetic notice. Real: a confidentiality banner (and a label warning)."""
    if data is not None and data.real:
        st.error(f"REAL DATA - {data.dataset_name}. Confidential.")
        if data.classifier == "local":
            st.warning(REAL_LABEL_WARNING)
    else:
        st.warning(data.notice if data is not None else notice)
    st.info(REVIEW_LINE)


def _switch_dataset(cfg: dict) -> None:
    set_active(cfg, st.session_state["active_dataset"])


PRESENTATION_TAG = "Presentation mode"
PRESENTATION_BLOCKED = ("This page is switched off in presentation mode, so real data cannot appear on screen. "
                        "Only the demo dataset is shown. Turn presentation mode off to use it.")


def dataset_switcher(cfg: dict) -> None:
    """Sidebar choice of the active dataset. Changing it changes the data on every page.

    In presentation mode there is no choice: a tag says so, and real datasets are never listed.
    """
    if presentation_mode(cfg):
        st.sidebar.markdown(f"**:orange-badge[{PRESENTATION_TAG}]**")
        st.sidebar.caption("Demo dataset only. Data and Review pages are off.")
        return
    active = get_active_name(cfg)
    datasets = list_datasets(cfg)
    labels = {d.slug: f"{d.name} ({'demo, synthetic' if d.kind == 'demo' else 'REAL, confidential'})"
              for d in datasets}
    options = [d.slug for d in datasets]
    if active not in options:
        options.insert(0, active)
        labels[active] = f"{active} (no data yet)"
    if st.session_state.get("active_dataset") != active:
        st.session_state["active_dataset"] = active  # follow changes made elsewhere (Data page, command line)
    st.sidebar.selectbox("Dataset", options, format_func=lambda slug: labels.get(slug, slug),
                         key="active_dataset", on_change=_switch_dataset, args=(cfg,))
    st.sidebar.caption("Manage datasets on the Data page.")


def presentation_from_secrets() -> None:
    """On Streamlit Community Cloud, FAIRLEND_PRESENT is set in the app's Secrets box. Top-level secrets are
    also environment variables there, which presentation_mode() reads. As a safety net, copy the secret to
    the environment when only st.secrets has it. Without a secrets file st.secrets raises, which is caught:
    nothing is shown. Only this one value is ever read from secrets.
    """
    if os.environ.get(PRESENT_VARIABLE, "").strip():
        return
    try:
        value = st.secrets.get(PRESENT_VARIABLE)
    except Exception:
        return
    if value is not None and str(value).strip():
        os.environ[PRESENT_VARIABLE] = str(value).strip()


def auto_build_wanted(cfg: dict) -> bool:
    """app.bootstrap.auto_build: 'presentation' (default: only in presentation mode), 'always' or 'never'."""
    mode = cfg["app"]["bootstrap"]["auto_build"]
    if mode == "never":
        return False
    return get_active_name(cfg) == DEMO and (mode == "always" or presentation_mode(cfg))


@st.cache_resource(max_entries=4, show_spinner=False)
def _checked_status(path: str | None, files: tuple) -> tuple[str, str]:
    # files (the demo files' sizes and times) is part of the cache key only: the check runs again when one changes.
    return demo_status(load_config(path))


BUILD_TEXT = ("Preparing the demo: about {minutes} minute(s), first start only. The synthetic demo data is being "
              "generated and the message classifier trained on this server. Nothing real is involved.")


def prepare_demo(cfg: dict) -> None:
    """If the demo is missing or stale, build it (or wait for the visitor who is building it) with a live
    progress screen of the real steps, then reload the page. On failure, stop with a short error code."""
    status, _ = _checked_status(config_path(), signature(cfg))
    if status == "fresh":
        return
    minutes = int(cfg["app"]["bootstrap"]["expected_minutes"])
    st.info(BUILD_TEXT.format(minutes=minutes))
    bar = st.progress(0.0, text="Starting...")
    lines = st.empty()
    done: list[str] = []

    def on_step(number: int, total: int, title: str) -> None:
        done[:] = [f"{'✅' if i < number else '⏳'} {i}. {STEPS[i - 1]}" for i in range(1, min(number, total) + 1)]
        bar.progress(min(max(number - 1, 0) / total, 1.0), text=f"Step {number} of {total}: {title}")
        lines.markdown("\n\n".join(done))

    result = ensure_demo(cfg, on_step=on_step)
    if not result.ok:
        bar.empty()
        st.error(f"The demo could not be prepared (error code {result.code}). Nothing real is involved. Try again "
                 "in a few minutes; if it keeps failing, quote the error code. The details are in the app log.")
        st.stop()
    bar.progress(1.0, text="Ready")
    _checked_status.clear()
    _cached_load.clear()
    st.rerun()


def page_setup(title: str, require_data: bool = True) -> tuple[DashboardData, dict]:
    """Branding, dataset switcher, status banner and data for a page.

    In presentation mode on a fresh server, the demo is built first (prepare_demo). With require_data
    (every page but Data), the page stops with instructions if the data is not ready.
    """
    presentation_from_secrets()
    try:
        cfg = load_config(config_path())
    except ConfigError as error:
        brand_header(title, None)
        banner(None)
        st.error(f"config.yaml has a problem: {error}")
        st.stop()
    brand_header(title, cfg)
    if auto_build_wanted(cfg):
        prepare_demo(cfg)
    cfg = team_config(cfg)  # an unlocked team session gets its private copy; everyone else the shared demo
    dataset_switcher(cfg)
    data = _cached_load(config_path(), data_signature(cfg), cfg)
    banner(data)
    if not data.ok:
        st.error(data.message)
        st.code(data.commands, language="powershell")
        st.caption("Run these in PowerShell from the project folder, then refresh this page.")
        if require_data:
            st.stop()
    return data, cfg


def presentation_block(cfg: dict) -> None:
    """Stop a page (Data, Review) with a short message when presentation mode is on.

    Phase 11: when access hashes are configured, the sidebar offers a "Team access" box. An unlocked session gets
    its private copy (its cfg is marked app.team_session) and the page goes on, with the team banner. Without a
    configured hash nothing changes: the message, and the page does nothing.
    """
    if cfg.get("app", {}).get("team_session"):
        team_controls()
        return
    if presentation_mode(cfg):
        hashes = access_hashes()
        if hashes:
            team_access_box(cfg, hashes)
        st.info(PRESENTATION_BLOCKED)
        st.stop()


# --- Team access (Phase 11) --------------------------------------------------------------------------------------------

ACCESS_VARIABLE = "FAIRLEND_ACCESS_HASHES"
TEAM_KEYS = ("team_unlocked", "team_hash", "team_copy", "team_token")


def access_hashes() -> list[str]:
    """The configured access-code hashes: the Streamlit secret first, else the environment variable. Never shown."""
    value = None
    try:
        value = st.secrets.get(ACCESS_VARIABLE)
    except Exception:  # no secrets file: fine, nothing is shown
        value = None
    if value is None:
        value = os.environ.get(ACCESS_VARIABLE)
    return parse_hashes(value)


def _session_id() -> str:
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
        ctx = get_script_run_ctx()
        return str(ctx.session_id) if ctx else ""
    except Exception:
        return ""


def _is_active_session(session_id: str) -> bool:
    try:
        from streamlit.runtime import Runtime
        return Runtime.instance().is_active_session(session_id) if Runtime.exists() else True
    except Exception:
        return True  # when in doubt, keep the folder; the age limit still removes it


def lock_team_session() -> None:
    """Delete this session's private copy and forget the unlock."""
    private = st.session_state.get("team_copy")
    if isinstance(private, PrivateCopy):
        private.delete()
    for key in TEAM_KEYS:
        st.session_state.pop(key, None)


def team_config(cfg: dict) -> dict:
    """cfg for this session: the private copy's config when unlocked (in presentation mode, with its hash still
    configured), otherwise cfg unchanged. Also sweeps away private copies of sessions that have ended."""
    settings = cfg["team_demo"]
    try:
        sweep(max_age_hours=float(settings["max_session_hours"]), is_active=_is_active_session)
    except OSError:
        pass
    if not st.session_state.get("team_unlocked"):
        return cfg
    if not presentation_mode(cfg) or st.session_state.get("team_hash") not in access_hashes():
        lock_team_session()  # presentation mode off, or the hash was removed (revoked): back to normal
        return cfg
    private = st.session_state.get("team_copy")
    if not isinstance(private, PrivateCopy) or not private.alive:
        private = PrivateCopy(cfg, _session_id())
        st.session_state["team_copy"] = private
    st.sidebar.markdown("**:green-badge[Team demo session]**")
    st.sidebar.caption("Private copy of the demo, for this browser session only.")
    return private.config


def _try_unlock(settings: dict, hashes: list[str]) -> None:
    """Button callback: check the typed code, then clear the box. The code is never stored, shown or logged."""
    code = st.session_state.get("team_code_input", "")
    st.session_state["team_code_input"] = ""
    wait = throttled_for(st.session_state, settings)
    if wait:
        st.session_state["team_flash"] = (f"Too many attempts in this session. Try again in about "
                                          f"{max(1, round(wait / 60))} minute(s).")
        return
    found = matching_hash(code, hashes)
    record_attempt(st.session_state, found is not None, settings)
    if found is None:
        st.session_state["team_flash"] = NOT_RECOGNISED
        return
    st.session_state["team_unlocked"] = True
    st.session_state["team_hash"] = found
    st.session_state.pop("team_flash", None)


def team_access_box(cfg: dict, hashes: list[str]) -> None:
    """The sidebar box on the Data and Review pages (presentation mode, locked)."""
    settings = cfg["team_demo"]
    with st.sidebar:
        st.subheader("Team access")
        st.caption("For the project team: unlock the Data and Review pages for this browser session only, on a "
                   "private copy of the synthetic demo.")
        st.text_input("Access code", type="password", key="team_code_input")
        st.button("Unlock", key="team_unlock", on_click=_try_unlock, args=(settings, hashes))
        flash = st.session_state.pop("team_flash", None)
        if flash:
            st.error(flash)


def _reset_copy() -> None:
    private = st.session_state.pop("team_copy", None)
    if isinstance(private, PrivateCopy):
        private.delete()


def team_controls() -> None:
    """Banner and sidebar buttons for an unlocked team session (Data and Review pages)."""
    st.warning(TEAM_BANNER)
    with st.sidebar:
        st.subheader("Team access")
        st.button("Reset my demo copy", key="team_reset", on_click=_reset_copy)
        st.button("Lock again", key="team_lock", on_click=lock_team_session)


@contextmanager
def guarded(page: str):
    """Run a page body; on an unexpected error show a friendly message and log the type only.

    st.stop(), st.rerun() and st.switch_page() are not errors (they are not Exception subclasses),
    so they pass straight through.
    """
    try:
        yield
    except Exception as error:
        try:
            cfg = load_config(config_path())
        except Exception:
            cfg = None
        code = log_exception(page, error, cfg)
        st.error(f"Something went wrong on this page (error code {code}). Nothing was changed. Try refreshing; "
                 "if it happens again, quote the error code. The details are in the app log.")


FOCUS_KEY = "demo_focus"


def focus_on(kind: str, ident: str, page: str) -> None:
    """Open a page focused on one borrower or lender (used by the Guided Demo buttons).

    The choice travels in session state, and also in the address (?borrower=... or ?lender=...)
    so a bookmarked link works too.
    """
    st.session_state[FOCUS_KEY] = {"kind": kind, "id": ident}
    st.switch_page(page, query_params={kind: ident})


def take_focus(kind: str) -> str | None:
    """The borrower or lender id a page should open, once; None if there is no new request."""
    focus = st.session_state.pop(FOCUS_KEY, None)
    if focus and focus.get("kind") == kind:
        value = str(focus["id"])
    else:
        value = st.query_params.get(kind)
        if not value or st.session_state.get(f"_focused_{kind}") == value:
            return None
    st.session_state[f"_focused_{kind}"] = value
    return value


def band_chart(distribution: pd.DataFrame) -> alt.Chart:
    """Bars per band. The band is written on the axis and on each bar, never shown by colour alone."""
    base = alt.Chart(distribution).encode(
        x=alt.X("band:N", sort=["high", "medium", "low"], title="Band"),
        y=alt.Y("borrowers:Q", title="Borrowers"),
        tooltip=["band", "borrowers"],
    )
    bars = base.mark_bar(color=CHART_BAR)
    labels = base.mark_text(dy=-6, color=CHART_TEXT[_theme()]).encode(text=alt.Text("borrowers:Q", format=","))
    return (bars + labels).properties(height=260)


def lender_interval_chart(ranked: pd.DataFrame) -> alt.Chart:
    """Abusive share per ranked lender with its confidence interval as a line."""
    frame = ranked.assign(
        label=ranked["rank"].astype(int).astype(str) + ". " + ranked["name"],
        share=ranked["abusive_share"] * 100,
        low=ranked["abusive_low"] * 100,
        high=ranked["abusive_high"] * 100,
    )
    order = frame["label"].tolist()
    y = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=170))  # long names fit on a phone
    bars = alt.Chart(frame).mark_bar(color=CHART_BAR, opacity=0.55).encode(
        x=alt.X("share:Q", title="Messages labelled abusive (%)"), y=y,
        tooltip=[alt.Tooltip("name:N", title="Lender"), alt.Tooltip("share:Q", format=".1f", title="Abusive %"),
                 alt.Tooltip("low:Q", format=".1f", title="Interval low %"),
                 alt.Tooltip("high:Q", format=".1f", title="Interval high %"),
                 alt.Tooltip("n_messages:Q", format=",", title="Messages")])
    interval = alt.Chart(frame).mark_rule(color=CHART_INTERVAL, strokeWidth=3).encode(x="low:Q", x2="high:Q", y=y)
    ends = alt.Chart(frame).mark_tick(color=CHART_INTERVAL, thickness=3, size=12).encode(x="low:Q", y=y)
    return (bars + interval + ends).properties(height=max(200, 28 * len(frame)))


def points_chart(points: pd.DataFrame) -> alt.Chart:
    """Points earned per signal (dark) against the maximum for that signal (light)."""
    y = alt.Y("signal:N", sort=points["signal"].tolist(), title=None)
    maximum = alt.Chart(points).mark_bar(color=CHART_TRACK[_theme()]).encode(
        x=alt.X("max_points:Q", title="Points"), y=y)
    earned = alt.Chart(points).mark_bar(color=CHART_BAR).encode(
        x="points:Q", y=y, tooltip=["signal", "points", "max_points"])
    labels = alt.Chart(points).mark_text(align="left", dx=4, color=CHART_TEXT[_theme()]).encode(
        x="max_points:Q", y=y, text=alt.Text("points:Q", format=".1f"))
    return (maximum + earned + labels).properties(height=200)


def timeline_chart(timeline: pd.DataFrame) -> alt.Chart:
    """One bar per loan from issue date to due date. Status is written in the row label."""
    return alt.Chart(timeline).mark_bar(height=14).encode(
        x=alt.X("issue_date:T", title="Issue date to due date"),
        x2="due_date:T",
        y=alt.Y("loan:N", sort=timeline["loan"].tolist(), title=None, axis=alt.Axis(labelLimit=200)),
        tooltip=["loan", "lender", "status", alt.Tooltip("issue_date:T"), alt.Tooltip("due_date:T")],
    ).properties(height=max(120, 32 * len(timeline)))


def logo_image(width: int = 380, assets_dir: Path = ASSETS_DIR) -> bool:
    """Show the wide logo as a picture in the page (About page): the same plated logo on every theme."""
    wide = brand_images(assets_dir).get("logo")
    if wide is None:
        return False
    try:
        st.image(str(wide), width=width)
        return True
    except Exception:
        return False


# Kept for older callers; the About page uses logo_image().
light_logo_image = logo_image
