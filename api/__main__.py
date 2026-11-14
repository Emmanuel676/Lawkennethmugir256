"""Start the API: python -m api   (listens on 127.0.0.1:8000 unless FAIRLEND_API_HOST / FAIRLEND_API_PORT say otherwise)."""

from __future__ import annotations

import os

import uvicorn

from src.datasets import PRESENT_VARIABLE

from api.main import create_app
from api.settings import load_settings


def main() -> None:
    os.environ.setdefault(PRESENT_VARIABLE, "1")  # presentation mode is the default
    settings = load_settings()
    print(f"FairLend Watch API on http://{settings.host}:{settings.port}  (allowed web origins: "
          f"{', '.join(settings.web_origins)})", flush=True)
    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
