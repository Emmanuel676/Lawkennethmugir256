"""Expected results for the sample lender packs (Phase 9A). EVALUATION ONLY. No network.

    python -m src.evaluate_sample_pack            # every scenario (builds the packs first if missing)

Each pack is imported with the REAL importer (src/import_data.py) into a temporary datasets folder, labelled
with the saved local classifier, and scored with the real score_borrowers. Only then are the results compared
with the answer key (sample_pack\\_answer_keys). Like the evaluate_* modules, this is the only kind of code
allowed to read an answer key; detection and the dashboard never do. Nothing is written into data\\.

Also reported:
  - lenders A, B, C, D imported one after the other: how the cross-lender matches grow;
  - realism setting (f): how much of the cycling signal is lost when repayments carry no linked_loan_id.

All data is synthetic.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

from src.classify_local import load_model
from src.classify_messages import classify_dataset, model_id
from src.config import load_config, resolve_path
from src.datasets import get_dataset_paths
from src.import_data import TABLES, import_upload, read_csvs
from src.lender_comparison import compare_lenders, load_inputs
from src.make_sample_pack import ALL_LENDERS, ANSWER_DIR, build_scenario, output_root
from src.overlap import connect_read_only, score_borrowers

FLAGGED = ("medium", "high")


def temp_config(cfg: dict, work: Path) -> dict:
    custom = copy.deepcopy(cfg)
    custom["paths"]["datasets_dir"] = str(work / "datasets")
    custom["paths"]["active_dataset_file"] = str(work / "active_dataset.txt")
    return custom


def read_truth(root: Path, scenario: str, name: str) -> pd.DataFrame:
    return pd.read_csv(root / ANSWER_DIR / scenario / f"{scenario}_{name}.csv")


def import_folder(cfg: dict, folder: Path, name: str, mode: str = "new", target: str = "") -> tuple[object, float]:
    """Import one pack folder (five CSV files) with the real importer. Returns (ImportResult, seconds)."""
    files = {f"{table}.csv": (folder / f"{table}.csv").read_bytes() for table in TABLES}
    started = time.perf_counter()
    result = import_upload(read_csvs(files), cfg, mode=mode, permission_confirmed=True, redact=True,
                           as_of=str(cfg["sample_pack"]["as_of_date"]), dataset_name=name,
                           source_description="synthetic sample pack", target=target, classify=False)
    seconds = time.perf_counter() - started
    if not result.ok:
        raise RuntimeError(f"Import of {folder} failed: {result.message} "
                           + "; ".join(str(e) for e in (result.report.errors[:5] if result.report else [])))
    return result, seconds


def scores_for(paths) -> pd.DataFrame:
    conn = connect_read_only(paths.lending_db)
    try:
        return score_borrowers(conn, _cfg_holder["cfg"])
    finally:
        conn.close()


_cfg_holder: dict = {}


def scenario_results(cfg: dict, root: Path, scenario: str, work: Path, model) -> dict:
    """Import all_lenders, label, score, then compare with the answer key."""
    tmp = temp_config(cfg, work / scenario)
    _cfg_holder["cfg"] = tmp
    result, seconds = import_folder(tmp, root / scenario / ALL_LENDERS, f"pack {scenario}")
    paths = get_dataset_paths(tmp, result.dataset)
    classify_dataset(tmp, paths, model, "saved local model", model_id(tmp))
    scores = scores_for(paths)
    lending = connect_read_only(paths.lending_db)
    predictions = connect_read_only(paths.predictions_db)
    try:
        messages, labels, lenders = load_inputs(lending, predictions, tmp["classifier"]["primary"])
        loans = pd.read_sql_query("SELECT borrower_id, lender_id FROM loans", lending)
    finally:
        lending.close()
        predictions.close()
    table = compare_lenders(messages, labels, lenders, tmp)
    abusive = tmp["lender_comparison"]["abusive_classes"]
    truth_b = read_truth(root, scenario, "borrower_truth")
    truth_m = read_truth(root, scenario, "message_truth")
    merged = scores.merge(truth_b, on="borrower_id", how="left", validate="one_to_one")
    flagged = merged["band"].isin(FLAGGED)
    small = cfg["sample_pack"]["small_lender"]["letter"]
    small_row = table[table["lender_id"] == f"L{small}"].iloc[0]
    per_borrower = loans.groupby("borrower_id")["lender_id"].nunique()
    cyclers = merged["cycler"].astype(bool)
    bad = merged["bad_payer"].astype(bool)
    return {
        "scenario": scenario, "borrowers": result.rows_written["borrowers"], "loans": result.rows_written["loans"],
        "repayments": result.rows_written["transactions"], "messages": result.rows_written["messages"],
        "import_seconds": round(seconds, 1),
        "high": int((merged["band"] == "high").sum()), "medium": int((merged["band"] == "medium").sum()),
        "low": int((merged["band"] == "low").sum()),
        "cycling_events": int(merged["cycling_events"].sum()),
        "with_cycling_event": int((merged["cycling_events"] >= 1).sum()),
        "forced_by_cycling": int(merged["band_forced_by_cycling"].sum()),
        "share_2plus_lenders": float((per_borrower >= 2).mean()),
        "abusive_share_model": float(labels["predicted_class"].isin(abusive).mean()) if len(labels) else 0.0,
        "abusive_share_true": float(truth_m["true_class"].isin(abusive).mean()) if len(truth_m) else 0.0,
        "cyclers": int(cyclers.sum()), "cyclers_flagged": int((cyclers & flagged).sum()),
        "cyclers_with_event": int((cyclers & (merged["cycling_events"] >= 1)).sum()),
        "non_cyclers_with_event": int((~cyclers & (merged["cycling_events"] >= 1)).sum()),
        "non_cyclers_with_event_multi": int((~cyclers & (merged["cycling_events"] >= 1)
                                             & merged["high_overlap"].astype(bool)).sum()),
        "non_cyclers_multi": int((~cyclers & merged["high_overlap"].astype(bool)).sum()),
        "non_cyclers_forced": int((~cyclers & merged["band_forced_by_cycling"].astype(bool)).sum()),
        "bad_payers": int(bad.sum()), "bad_payers_flagged": int((bad & flagged).sum()),
        "good_payers_flagged": int((~bad & ~cyclers & flagged).sum()),
        "small_lender": {"messages": int(small_row["n_messages"]), "rank": small_row["rank"],
                         "abusive_share": float(small_row["abusive_share"]),
                         "interval": (float(small_row["abusive_low"]), float(small_row["abusive_high"]))},
        "ranked_lenders": table.dropna(subset=["rank"])[["name", "n_messages", "abusive_share", "late_night_share"]]
        .to_dict("records"),
    }


def sequential_import(cfg: dict, root: Path, scenario: str, work: Path) -> list[dict]:
    """Import lender_A as a new dataset, then B, C and D into it; after each, how many borrowers match."""
    tmp = temp_config(cfg, work / f"{scenario}_sequence")
    letters = [lender["letter"] for lender in cfg["sample_pack"]["lenders"]]
    truth = read_truth(root, scenario, "borrower_truth")
    rows, slug = [], ""
    for number, letter in enumerate(letters):
        folder = root / scenario / f"lender_{letter}"
        if number == 0:
            result, seconds = import_folder(tmp, folder, f"pack {scenario} sequence")
            slug = result.dataset
        else:
            result, seconds = import_folder(tmp, folder, "", mode="add", target=slug)
        paths = get_dataset_paths(tmp, slug)
        conn = connect_read_only(paths.lending_db)
        try:
            per = pd.read_sql_query("SELECT borrower_id, COUNT(DISTINCT lender_id) n FROM loans GROUP BY borrower_id",
                                    conn)
            n_borrowers = conn.execute("SELECT COUNT(*) FROM borrowers").fetchone()[0]
        finally:
            conn.close()
        so_far = letters[:number + 1]
        expected = int(truth["lenders"].fillna("").map(
            lambda s: len(set(s.split(";")) & set(so_far)) >= 2).sum())
        rows.append({"after": f"lender {letter}", "borrowers": int(n_borrowers),
                     "already_known": int(result.report.skipped_existing_borrowers),
                     "matched_2plus": int((per["n"] >= 2).sum()), "expected_2plus": expected,
                     "import_seconds": round(seconds, 1)})
    return rows


def link_check(cfg: dict, scenario: str, work: Path, shares=(1.0, None, 0.5, 0.0)) -> list[dict]:
    """Realism (f): rebuild the scenario with different link shares; how many cyclers keep a cycling event."""
    out = []
    default = float(cfg["sample_pack"]["repayment"]["link_share"])
    for share in shares:
        value = default if share is None else share
        root = work / f"link_{value}"
        build_scenario(cfg, scenario, root, overrides={"link_share": value})
        tmp = temp_config(cfg, work / f"link_{value}_import")
        _cfg_holder["cfg"] = tmp
        result, _ = import_folder(tmp, root / scenario / ALL_LENDERS, f"pack link {value}")
        scores = scores_for(get_dataset_paths(tmp, result.dataset))
        merged = scores.merge(read_truth(root, scenario, "borrower_truth"), on="borrower_id")
        cyclers = merged["cycler"].astype(bool)
        out.append({"link_share": value, "default": share is None, "cyclers": int(cyclers.sum()),
                    "with_event": int((cyclers & (merged["cycling_events"] >= 1)).sum()),
                    "forced_or_flagged": int((cyclers & merged["band"].isin(FLAGGED)).sum()),
                    "events_total": int(merged.loc[cyclers, "cycling_events"].sum())})
    return out


def _pct(x: float) -> str:
    return f"{x:.0%}"


def format_report(results: list[dict], sequence: list[dict], links: list[dict], scenario: str) -> str:
    lines = ["SYNTHETIC sample packs: expected results (real importer + score_borrowers; answer key read only "
             "to count hits).", "",
             "| Scenario | Borrowers | Loans | Messages | High / medium / low | Cycling events (borrowers) | "
             "2+ lenders | Abusive share (model / true) | Cyclers flagged | Bad payers flagged | Import s |",
             "|---|---:|---:|---:|---|---|---:|---|---|---|---:|"]
    for r in results:
        cyc = f"{r['cyclers_flagged']} of {r['cyclers']}" if r["cyclers"] else "n/a (none)"
        lines.append(
            f"| {r['scenario']} | {r['borrowers']:,} | {r['loans']:,} | {r['messages']:,} | "
            f"{r['high']} / {r['medium']} / {r['low']} | {r['cycling_events']:,} ({r['with_cycling_event']}) | "
            f"{_pct(r['share_2plus_lenders'])} | {r['abusive_share_model']:.1%} / {r['abusive_share_true']:.1%} | "
            f"{cyc} | {r['bad_payers_flagged']} of {r['bad_payers']} | {r['import_seconds']} |")
    lines += ["", "Borrowers who are NOT cyclers but get cycling events (daily repayments at one lender while "
              "a loan starts at another):"]
    lines += [f"  {r['scenario']}: {r['non_cyclers_with_event']} with an event, all multi-lender: "
              f"{r['non_cyclers_with_event_multi']} of {r['non_cyclers_multi']} multi-lender borrowers; "
              f"{r['non_cyclers_forced']} lifted to medium by the cycling rule" for r in results]
    lines += ["", "Small lender (realism e):"]
    for r in results:
        s = r["small_lender"]
        rank = "unranked" if pd.isna(s["rank"]) else f"rank {int(s['rank'])}"
        lines.append(f"  {r['scenario']}: {s['messages']} messages, {rank}, labelled abusive {s['abusive_share']:.0%} "
                     f"(95% interval {s['interval'][0]:.0%} to {s['interval'][1]:.0%})")
    lines += ["", f"Sequential import ({scenario}): lender by lender",
              "| After | Borrowers | Codes already known | Borrowers at 2+ lenders | Expected from answer key | Import s |",
              "|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['after']} | {r['borrowers']:,} | {r['already_known']:,} | {r['matched_2plus']:,} | "
              f"{r['expected_2plus']:,} | {r['import_seconds']} |" for r in sequence]
    lines += ["", "Realism (f): cycling signal and linked_loan_id (cycling scenario)",
              "| Repayments with a link | Cyclers with an event | Cyclers flagged | Cycling events on cyclers |",
              "|---|---|---|---:|"]
    for r in links:
        label = f"{r['link_share']:.0%}" + (" (default)" if r["default"] else "")
        lines.append(f"| {label} | {r['with_event']} of {r['cyclers']} | {r['forced_or_flagged']} of {r['cyclers']} | "
                     f"{r['events_total']} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expected results for the synthetic sample packs (evaluation only).")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--out-dir", help="Pack folder (default: sample_pack.output_dir).")
    parser.add_argument("--sequence-scenario", default="baseline")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    root = output_root(cfg, args.out_dir)
    scenarios = list(cfg["sample_pack"]["scenarios"])
    if any(not (root / s / ALL_LENDERS).exists() for s in scenarios):
        from src.make_sample_pack import build_all
        build_all(cfg, root)
    model = load_model(resolve_path(cfg, "local_model"))
    with tempfile.TemporaryDirectory(prefix="fairlend_pack_eval_") as folder:
        work = Path(folder)
        with contextlib.redirect_stdout(io.StringIO()):
            results = [scenario_results(cfg, root, s, work, model) for s in scenarios]
            sequence = sequential_import(cfg, root, args.sequence_scenario, work)
            links = link_check(cfg, "cycling", work)
    print(format_report(results, sequence, links, args.sequence_scenario))
    return 0


if __name__ == "__main__":
    sys.exit(main())
