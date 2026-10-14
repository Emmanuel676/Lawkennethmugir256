"""Pre-flight checks before a demo (Phase 5.2). No network.

    python -m src.preflight            # or: .\\dev.ps1 -Preflight

Prints PASS or FAIL per check, then a summary line. Exit code 0 when every check passes, 1 otherwise.

  1. config.yaml loads and passes validation
  2. the demo dataset exists and matches the fingerprint in its manifest (it was not changed by hand)
  3. the demo's message labels are fresh (made from these messages) and complete
  4. every page boots under Streamlit's test runner in presentation mode, with no exception
  5. presentation mode hides real data: a temporary real dataset, made the active one in a temporary
     config, must stay invisible (no listing, no switcher, no real-data banner)
  6. the logo and icon files exist
  7. .env is protected: it is named in .gitignore, no page names it, and Streamlit's static file
     serving is off. The .env file itself is never opened.

The pages are booted with the demo only, so nothing real is read. All data is synthetic.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

import yaml

from src.config import PROJECT_ROOT, ConfigError, load_config, resolve_path

PAGES = ["app.py"] + sorted(f"pages/{p.name}" for p in (PROJECT_ROOT / "pages").glob("*.py"))
CONFIG_VARIABLE = "LENDING_MONITOR_CONFIG"  # the same name as in src/dashboard_ui.py (not imported: no Streamlit here)
PRESENT_VARIABLE = "FAIRLEND_PRESENT"
SECRET_FILE = ".env"


@contextlib.contextmanager
def _environment(**values: str | None):
    """Set environment variables for a block and put the old values back afterwards."""
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def check_demo_fingerprint(cfg: dict) -> tuple[bool, str]:
    from src import db
    from src.datasets import DEMO, get_dataset_paths

    paths = get_dataset_paths(cfg, DEMO)
    if not paths.lending_db.exists():
        return False, "the demo dataset is missing. Rebuild it: python -m src.build_all"
    manifest_path = resolve_path(cfg, "manifest") if "manifest" in cfg["paths"] else None
    if manifest_path is None or not manifest_path.exists():
        return False, "the demo's manifest is missing, so its fingerprint cannot be checked. Run python -m src.build_all"
    expected = json.loads(manifest_path.read_text(encoding="utf-8")).get("lending_db_content_hash")
    try:
        conn = sqlite3.connect(f"{paths.lending_db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            actual = db.content_hash(conn)
        finally:
            conn.close()
    except sqlite3.Error as error:
        return False, f"the demo database cannot be read ({type(error).__name__}). Run python -m src.build_all"
    if actual != expected:
        return False, "the demo database does not match its manifest (changed since it was built). Run python -m src.build_all"
    return True, f"demo matches its manifest (fingerprint {actual[:8]}...)"


def check_predictions(cfg: dict) -> tuple[bool, str]:
    from src.datasets import DEMO, get_dataset_paths
    from src.overlap import connect_read_only
    from src.predictions import StalePredictionsError, check_matches, read_predictions

    paths = get_dataset_paths(cfg, DEMO)
    if not paths.lending_db.exists() or not paths.predictions_db.exists():
        return False, "the demo has no message labels. Run python -m src.build_all"
    lending, predictions = connect_read_only(paths.lending_db), connect_read_only(paths.predictions_db)
    try:
        check_matches(predictions, lending)
        classifier = cfg["classifier"]["primary"]
        labelled = set(read_predictions(predictions, classifier)["message_id"])
        total = {row[0] for row in lending.execute("SELECT message_id FROM messages")}
    except StalePredictionsError:
        return False, "the labels were made from different messages (stale). Run python -m src.build_all"
    except sqlite3.Error as error:
        return False, f"the labels cannot be read ({type(error).__name__}). Run python -m src.build_all"
    finally:
        lending.close()
        predictions.close()
    if not total <= labelled:
        return False, f"{len(total - labelled):,} of {len(total):,} messages have no '{classifier}' label"
    return True, f"all {len(total):,} demo messages have fresh '{classifier}' labels"


def _boot(page: str, config_file: str | None) -> tuple[bool, str]:
    from streamlit.testing.v1 import AppTest

    with _environment(**{PRESENT_VARIABLE: "1", CONFIG_VARIABLE: config_file}):
        at = AppTest.from_file(str(PROJECT_ROOT / page), default_timeout=180).run()
    if at.exception:
        return False, "raised an exception"
    if any("Something went wrong" in e.value for e in at.error):
        return False, "showed 'Something went wrong' (see data/logs/app.log)"
    if any(e.value.startswith("No dataset found") for e in at.error):
        return False, "found no demo data"
    return True, "boots"


def check_pages(cfg: dict) -> tuple[bool, str]:
    """Boot every page. Automatic demo building is switched off here: a check must never write data."""
    failures = []
    with tempfile.TemporaryDirectory() as folder:
        quiet = copy.deepcopy(cfg)
        quiet["app"]["bootstrap"]["auto_build"] = "never"
        config_file = Path(folder) / "config.yaml"
        config_file.write_text(yaml.safe_dump(quiet), encoding="utf-8")
        for page in PAGES:
            ok, why = _boot(page, str(config_file))
            if not ok:
                failures.append(f"{page} {why}")
    if failures:
        return False, "; ".join(failures)
    return True, f"all {len(PAGES)} pages boot in presentation mode with no exception"


def check_presentation_hides_real_data(cfg: dict) -> tuple[bool, str]:
    from streamlit.testing.v1 import AppTest

    from src.datasets import create_dataset, get_active_name, list_datasets, set_active

    with tempfile.TemporaryDirectory() as folder:
        hidden = copy.deepcopy(cfg)
        hidden["app"]["presentation_mode"] = False
        hidden["app"]["bootstrap"]["auto_build"] = "never"  # a check must never write data
        hidden["paths"]["datasets_dir"] = str(Path(folder) / "datasets")
        hidden["paths"]["active_dataset_file"] = str(Path(folder) / "active_dataset.txt")
        config_file = Path(folder) / "config.yaml"
        config_file.write_text(yaml.safe_dump(hidden), encoding="utf-8")
        with _environment(**{PRESENT_VARIABLE: "0"}):
            create_dataset(hidden, "Preflight Hidden Real", "preflight check, no rows")
            set_active(hidden, "preflight-hidden-real")
            if get_active_name(hidden) != "preflight-hidden-real":  # the check itself must be able to fail
                return False, "could not set up the temporary real dataset"
        with _environment(**{PRESENT_VARIABLE: "1", CONFIG_VARIABLE: str(config_file)}):
            if get_active_name(hidden) != "demo":
                return False, "presentation mode did not force the demo"
            if [d.slug for d in list_datasets(hidden)] not in ([], ["demo"]):
                return False, "presentation mode still lists a real dataset"
            at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=180).run()
        if at.exception:
            return False, "the Overview raised an exception in presentation mode"
        if any(e.value.startswith("REAL DATA") for e in at.error):
            return False, "the real-data banner appeared in presentation mode"
        if any(box.key == "active_dataset" for box in at.sidebar.selectbox):
            return False, "the dataset switcher is visible in presentation mode"
        if not any("Presentation mode" in m.value for m in at.sidebar.markdown):
            return False, "the 'Presentation mode' tag is missing from the sidebar"
    return True, "a temporary real dataset stayed invisible (no listing, no switcher, no banner)"


def check_assets() -> tuple[bool, str]:
    names = ("fairlend-watch-logo.svg", "fairlend-watch-icon.svg")
    missing = [name for name in names if not (PROJECT_ROOT / "assets" / name).is_file()]
    if missing:
        return False, f"missing in assets/: {', '.join(missing)}"
    return True, "logos and icon are present"


def _literals(source: str) -> list[str]:
    return [node.value for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def check_secret_file() -> tuple[bool, str]:
    """Never opens .env: only .gitignore, the page sources and the Streamlit settings are read."""
    ignore = PROJECT_ROOT / ".gitignore"
    lines = [line.strip() for line in ignore.read_text(encoding="utf-8").splitlines()] if ignore.exists() else []
    if SECRET_FILE not in lines:
        return False, f"{SECRET_FILE} is not listed in .gitignore"
    naming = [page for page in PAGES
              if any(SECRET_FILE in text for text in _literals((PROJECT_ROOT / page).read_text(encoding="utf-8")))]
    if naming:
        return False, f"these pages name {SECRET_FILE}: {', '.join(naming)}"
    settings = PROJECT_ROOT / ".streamlit" / "config.toml"
    text = settings.read_text(encoding="utf-8") if settings.exists() else ""
    if re.search(r"enableStaticServing\s*=\s*true", text):
        return False, "Streamlit static file serving is on (.streamlit/config.toml)"
    return True, f"{SECRET_FILE} is in .gitignore, named by no page, and no folder is served as static files"


def run(config_file: str | None = None) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    try:
        cfg = load_config(config_file)
        results.append(("config.yaml is valid", True, "loaded and validated"))
    except ConfigError as error:
        return [("config.yaml is valid", False, str(error))]
    with _environment(**{PRESENT_VARIABLE: "0"}):
        checks = [
            ("demo dataset matches its fingerprint", lambda: check_demo_fingerprint(cfg)),
            ("demo labels are fresh and complete", lambda: check_predictions(cfg)),
        ]
        for name, check in checks:
            results.append((name, *_safely(check)))
    results.append(("every page boots", *_safely(lambda: check_pages(cfg))))
    results.append(("presentation mode hides real data", *_safely(lambda: check_presentation_hides_real_data(cfg))))
    results.append(("logo files exist", *_safely(check_assets)))
    results.append((".env is not served or listed", *_safely(check_secret_file)))
    return results


def _safely(check) -> tuple[bool, str]:
    try:
        return check()
    except Exception as error:  # a check that crashes is a failed check, never a traceback
        return False, f"the check itself failed ({type(error).__name__})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that everything is ready for a demo.")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    args = parser.parse_args(argv)
    quiet = io.StringIO()
    with contextlib.redirect_stderr(quiet):  # Streamlit's test runner is chatty on stderr
        results = run(args.config)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    failed = sum(not ok for _, ok, _ in results)
    print("")
    print(f"Preflight: {len(results) - failed} of {len(results)} checks passed. "
          + ("READY for the demo." if not failed else "NOT ready: fix the FAIL lines above."))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
