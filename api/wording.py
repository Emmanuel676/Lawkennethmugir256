"""User-facing wording for the web app (Phase 13). One neutral phrase for every dataset: "Demonstration data".

The web app never calls a dataset synthetic, mock, real, verified, collected or field data. The engine in src/ is
unchanged and keeps its own wording for Streamlit; anything of it that reaches the web app (for example the demo's
stored notice line) is replaced here. tests/test_wording.py fails if any of those words reaches user-facing text.
"""

from __future__ import annotations

import re

DEMONSTRATION = "Demonstration data"
FLAG_LINE = "A flag is a prompt for a human to look, not a verdict."
TRUST_LINE = f"{DEMONSTRATION}. {FLAG_LINE}"
NOTICE = f"{DEMONSTRATION}."                     # the first words of every export's '#' line
DEMO_NAME = "Demonstration data (built in)"      # the built-in dataset in lists and the switcher
DEMO_LABEL = "Demonstration data. Built in; cannot be changed or deleted."
IMPORTED_LABEL = DEMONSTRATION                   # every imported dataset, in the list, the switcher and the strip
CHECK_NAME = "the upload check"

# Words the web app must never show about data. "real" is matched as a whole word.
BANNED = re.compile(r"synthetic|\bmock|\breal\b|\bverified\b|\bcollected\b|field data", re.IGNORECASE)

_REWRITES = (
    # Engine wording that can reach the web app, mapped to neutral wording.
    (re.compile(r"SYNTHETIC DATA:[^\n#]*?messages\.", re.IGNORECASE), NOTICE),
    (re.compile(r"\bsynthetic\b\s*", re.IGNORECASE), ""),
)


def neutral(text: str) -> str:
    """Engine text with any 'synthetic' wording removed (used only on text that is not dataset content)."""
    value = str(text)
    for pattern, replacement in _REWRITES:
        value = pattern.sub(replacement, value)
    return re.sub(r"\s{2,}", " ", value).strip()
