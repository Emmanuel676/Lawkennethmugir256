"""Build the demo dataset and everything the dashboard needs, in one command (Phase 4).

    python -m src.build_all

Steps, in order:
  1. generate the synthetic dataset (lending.db and the answer-label file)
  2. classify every message with the local model (predictions.db)
  3. score every borrower (borrower_scores.csv)
  4. compare lenders (lender_comparison.csv)

Always works on the demo dataset, never on imported real data, whichever
dataset is active. Prints one line per step with its timing and stops at the
first failure.
Uses the local classifier only: no network service, no API key.
All data is synthetic.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
from collections.abc import Callable

from src import classify_messages, generate_data, lender_comparison, overlap


def steps(config_args: list[str]) -> list[tuple[str, Callable[[], int]]]:
    # Always the demo dataset, whichever dataset is active: a rebuild must never touch real data.
    demo = ["--dataset", "demo", *config_args]
    return [
        ("Generate the synthetic dataset", lambda: generate_data.main(config_args)),
        ("Classify messages with the local model", lambda: classify_messages.main(["--classifier", "local", *demo])),
        ("Score borrowers (borrower_scores.csv)", lambda: overlap.main(demo)),
        ("Compare lenders (lender_comparison.csv)", lambda: lender_comparison.main(demo)),
    ]


def run(config_args: list[str], verbose: bool = False) -> int:
    plan = steps(config_args)
    started = time.perf_counter()
    for number, (title, step) in enumerate(plan, start=1):
        step_start = time.perf_counter()
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(sys.stdout if verbose else captured):
                code = step()
        except Exception as error:  # report any failure plainly and stop
            print(f"[{number}/{len(plan)}] {title} ... FAILED after {time.perf_counter() - step_start:.1f}s")
            print(f"Stopped. {type(error).__name__}: {error}")
            return 1
        if code != 0:
            print(f"[{number}/{len(plan)}] {title} ... FAILED (exit code {code})")
            print(captured.getvalue().strip())
            print("Stopped at the first failure.")
            return code or 1
        print(f"[{number}/{len(plan)}] {title} ... done in {time.perf_counter() - step_start:.1f}s")
    print(f"All steps finished in {time.perf_counter() - started:.1f}s. "
          "Start the dashboard with: streamlit run app.py --server.address localhost")
    print("All data is SYNTHETIC.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the dataset, labels, scores and lender comparison.")
    parser.add_argument("--config", help="Path to a config file (default: config.yaml).")
    parser.add_argument("--verbose", action="store_true", help="Also show each step's own output.")
    args = parser.parse_args(argv)
    return run(["--config", args.config] if args.config else [], verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
