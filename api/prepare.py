"""Prepare the built-in demonstration dataset for the API: build it if missing or stale, otherwise do nothing.

    python -m api.prepare

The API runs this during start-up (api.main lifespan), before it accepts any request, so a visitor never
waits for a build. It uses the existing src.bootstrap.ensure_demo (the same build-once logic as the Streamlit
app's first start). Exit code 0 when the demo is ready, 1 otherwise. Prints no data values.
"""

from __future__ import annotations

import os
import sys

from src.bootstrap import ensure_demo
from src.datasets import PRESENT_VARIABLE

from api.data_source import presentation_config


def prepare_demo(config_path: str | None = None) -> bool:
    os.environ.setdefault(PRESENT_VARIABLE, "1")  # presentation mode is the API's default
    cfg = presentation_config(config_path)

    def step(number, total, title):
        print(f"  step {number} of {total}: {title}", flush=True)

    result = ensure_demo(cfg, on_step=step)
    if result.status == "failed":
        print(f"Demo build failed (error code {result.code}). Details are in the app log.", flush=True)
        return False
    print({"fresh": "Demo data is ready.", "built": "Demo data built.",
           "waited": "Demo data built by another process."}.get(result.status, result.status), flush=True)
    return True


def main() -> int:
    return 0 if prepare_demo(os.environ.get("LENDING_MONITOR_CONFIG") or None) else 1


if __name__ == "__main__":
    sys.exit(main())
