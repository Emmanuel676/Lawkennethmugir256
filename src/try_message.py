"""Try one message against the local classifier (Phase 8A). No Streamlit, no network.

A person types one message on the Lenders page and sees the class the model would give it,
with the model's probability for each of the four classes.

  - The model is the active dataset's own retrained model when it has one, otherwise the
    saved local model (trained on the demo's synthetic text). Nothing is trained here.
  - Lender names are masked by the model's own first step (the same LenderNameMasker,
    with the same brand names, that was used when it was trained).
  - The typed text is NOT stored, NOT logged and NOT added to any dataset: it lives only in
    the call to predict() and is gone when the function returns.

A label is a prompt for a human to look, never a verdict.
"""

from __future__ import annotations

from pathlib import Path

from src.classify_local import load_model, predict
from src.classify_messages import dataset_model_path
from src.config import MESSAGE_CLASSES, resolve_path
from src.datasets import DatasetPaths

MAX_CHARS = 1000
NOTE = "A prompt for a human to look, never a verdict."


def model_file(cfg: dict, paths: DatasetPaths) -> tuple[Path | None, str]:
    """(the model file to use, where it comes from). (None, why) when there is no saved model."""
    own = dataset_model_path(paths)
    if own is not None and own.exists():
        return own, "this dataset's own model, retrained on its human labels"
    saved = resolve_path(cfg, "local_model")
    if saved.exists():
        return saved, "the saved local model, trained on the demo's synthetic text"
    return None, "There is no saved model yet. Rebuild the demo with: python -m src.build_all"


def load(path: Path):
    """Load a saved model (the page caches this per file and modification time)."""
    return load_model(Path(path))


def classify_one(model, text: str) -> dict:
    """{'label': class, 'probabilities': {class: p}} for one text, or {'error': plain sentence}."""
    text = (text or "").strip()
    if not text:
        return {"error": "Type a message first."}
    if len(text) > MAX_CHARS:
        return {"error": f"That is longer than {MAX_CHARS} characters. Try a shorter message."}
    row = predict(model, [text]).iloc[0]
    probabilities = {name: float(row.get(f"prob_{name}", 0.0)) for name in MESSAGE_CLASSES}
    return {"label": str(row["predicted_class"]), "probabilities": probabilities}
