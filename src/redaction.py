"""Remove personal details from message text before it is stored (Phase 5.1). No Streamlit, no network.

What is replaced, in this order (each can be switched off in the 'privacy' section of config.yaml):

  [EMAIL]  email addresses
  [ID]     a run of letters/digits right after a word such as "NIN" or "ID number"
           (privacy.id_keywords), and anything matching privacy.id_patterns
           (the Ugandan national ID number, NIN), matched without regard to letter case
  [PHONE]  Ugandan mobile numbers, and any unbroken run of privacy.phone_min_digits digits
  [NAME]   the names listed in privacy.name_list_file (one per line), whole words, any letter case

NAMES CANNOT BE DETECTED AUTOMATICALLY. Only names somebody has put in the name list
are removed. possible_names() lists frequent capitalised words to help a person spot
names to add; it decides nothing.

Nothing in this module logs or prints message text. Real data is confidential.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT

TOKENS = ("PHONE", "EMAIL", "ID", "NAME")
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_ALNUM = "A-Za-z0-9"
_KEYWORD_GAP = re.compile(r"[ \t:#=.\-]*(?:(?:is|was)(?![A-Za-z0-9])[ \t:#=.\-]*)?", re.IGNORECASE)
_VALUE_GROUP = re.compile(r"[A-Za-z0-9]+")


def phone_pattern(min_digits: int) -> re.Pattern:
    """Ugandan mobile numbers (07xx xxx xxx, +256 7xx xxx xxx, 256 7xx ...) and any run of min_digits+ digits."""
    return re.compile(
        r"(?<![\d+])(?:\+?256[\s-]?|0)7\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)"
        rf"|\d{{{int(min_digits)},}}")


def name_list_path(cfg: dict) -> Path:
    path = Path(cfg["privacy"]["name_list_file"])
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_names(path: Path) -> list[str]:
    """Names from the list file: one per line; blank lines and lines starting with '#' are skipped."""
    if not Path(path).is_file():
        return []
    names = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return sorted(set(names), key=lambda n: (-len(n), n.lower()))


def empty_counts() -> dict[str, int]:
    return {token: 0 for token in TOKENS}


@dataclass
class Redactor:
    """Built once from the config (and the name list), then applied to every message."""

    emails: bool
    phones: re.Pattern | None
    id_patterns: list[re.Pattern]
    id_keywords: re.Pattern | None
    id_min_digits: int
    names: re.Pattern | None
    name_count: int = 0
    notes: list[str] = field(default_factory=list)

    def redact(self, text: str) -> tuple[str, dict[str, int]]:
        """(redacted text, how many of each token were put in)."""
        counts = empty_counts()
        text = "" if text is None else str(text)
        if self.emails:
            text, counts["EMAIL"] = EMAIL_PATTERN.subn("[EMAIL]", text)
        if self.id_keywords is not None:
            text, n = self._keyword_ids(text)
            counts["ID"] += n
        for pattern in self.id_patterns:
            text, n = self._pattern_ids(pattern, text)
            counts["ID"] += n
        if self.phones is not None:
            text, counts["PHONE"] = self.phones.subn("[PHONE]", text)
        if self.names is not None:
            text, counts["NAME"] = self.names.subn("[NAME]", text)
        return text, counts

    def _pattern_ids(self, pattern: re.Pattern, text: str) -> tuple[str, int]:
        found = 0

        def replace(match: re.Match) -> str:
            nonlocal found
            if sum(ch.isdigit() for ch in match.group(0)) < self.id_min_digits:
                return match.group(0)  # mostly letters: an ordinary word, not an ID
            found += 1
            return "[ID]"

        return pattern.sub(replace, text), found

    def _keyword_ids(self, text: str) -> tuple[str, int]:
        """Replace the value after an ID keyword: the first group of letters/digits, then further groups
        (joined by one space or dash) while they contain a digit or are short capitals ("CF 1234 ABCD")."""
        out, position, found = [], 0, 0
        for match in self.id_keywords.finditer(text):
            if match.start() < position:
                continue
            gap = _KEYWORD_GAP.match(text, match.end())
            start = gap.end()
            first = _VALUE_GROUP.match(text, start)
            if first is None:
                continue
            end = first.end()
            while end + 1 < len(text) and text[end] in " -":
                group = _VALUE_GROUP.match(text, end + 1)
                if group is None:
                    break
                word = group.group(0)
                if not (any(c.isdigit() for c in word) or (word.isupper() and len(word) <= 4)):
                    break
                end = group.end()
            value = text[start:end]
            if not any(c.isdigit() for c in value):
                continue  # "ID number please": no value to remove
            out.append(text[position:start])
            out.append("[ID]")
            position = end
            found += 1
        out.append(text[position:])
        return "".join(out), found


def _keyword_pattern(keywords: list[str]) -> re.Pattern | None:
    words = sorted({k.strip() for k in keywords if k.strip()}, key=len, reverse=True)
    if not words:
        return None
    parts = [r"\s+".join(re.escape(piece) for piece in word.split()) for word in words]
    return re.compile(rf"(?<![{_ALNUM}])(?:{'|'.join(parts)})(?![A-Za-z])", re.IGNORECASE)


def names_pattern(names: list[str]) -> re.Pattern | None:
    if not names:
        return None
    parts = [r"\s+".join(re.escape(piece) for piece in name.split()) for name in names]
    return re.compile(rf"(?<!\w)(?:{'|'.join(parts)})(?!\w)", re.IGNORECASE)


def build_redactor(cfg: dict, names: list[str] | None = None) -> Redactor:
    """A Redactor following config.yaml. names=None reads privacy.name_list_file (if it exists)."""
    privacy = cfg["privacy"]
    notes = []
    if names is None:
        path = name_list_path(cfg)
        names = load_names(path) if privacy["redact_names"] else []
        if privacy["redact_names"] and not path.is_file():
            notes.append(f"No name list found ({privacy['name_list_file']}), so no names were removed. "
                         "Names cannot be detected automatically.")
    elif not privacy["redact_names"]:
        names = []
    id_patterns = []
    if privacy["redact_ids"]:
        id_patterns = [re.compile(rf"(?<![{_ALNUM}])(?:{item['pattern']})(?![{_ALNUM}])", re.IGNORECASE)
                       for item in privacy["id_patterns"]]
    return Redactor(
        emails=privacy["redact_emails"],
        phones=phone_pattern(privacy["phone_min_digits"]) if privacy["redact_phones"] else None,
        id_patterns=id_patterns,
        id_keywords=_keyword_pattern(privacy["id_keywords"]) if privacy["redact_ids"] else None,
        id_min_digits=int(privacy["id_min_digits"]),
        names=names_pattern(names),
        name_count=len(names),
        notes=notes,
    )


def redact_all(texts, redactor: Redactor) -> tuple[list[str], dict[str, int]]:
    """Redact every text. Returns the new texts and the total of each token."""
    total = empty_counts()
    out = []
    for text in texts:
        new, counts = redactor.redact(text)
        out.append(new)
        for token, n in counts.items():
            total[token] += n
    return out, total


def preview(frame: pd.DataFrame, redactor: Redactor, limit: int = 20) -> pd.DataFrame:
    """Up to `limit` messages, original and redacted side by side. Messages where something
    changed come first (in file order), then unchanged ones, so the preview shows the redaction at work."""
    rows = []
    for row_number, text in zip(frame["_row"], frame["text"]):
        original = "" if text is None else str(text)
        redacted, counts = redactor.redact(original)
        rows.append({"Row": int(row_number), "Original": original, "Redacted": redacted,
                     "changed": sum(counts.values()) > 0})
    table = pd.DataFrame(rows, columns=["Row", "Original", "Redacted", "changed"])
    table = pd.concat([table[table["changed"]], table[~table["changed"]]]).head(limit)
    return table.drop(columns="changed").reset_index(drop=True)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def possible_names(texts, cfg: dict, exclude_words=(), names: list[str] | None = None) -> pd.DataFrame:
    """Frequent capitalised words that may be names, for a PERSON to check: not the first word of a
    sentence, not in privacy.possible_names.stop_words, not in exclude_words (e.g. lender names).

    Columns: word, messages (how many messages contain it), in_name_list. Names cannot be detected
    automatically; most words here will not be names, and many names will be missing.
    """
    helper = cfg["privacy"]["possible_names"]
    stop = {w.casefold() for w in helper["stop_words"]} | {t.casefold() for t in TOKENS}
    excluded = {w.casefold() for phrase in exclude_words for w in _WORD.findall(str(phrase))}
    listed = {w.casefold() for name in (names if names is not None else load_names(name_list_path(cfg)))
              for w in name.split()}
    counts: Counter = Counter()
    for text in texts:
        seen = set()
        for sentence in _SENTENCE_SPLIT.split(str(text or "")):
            words = _WORD.findall(sentence)
            for word in words[1:]:
                if len(word) < 2 or not (word[0].isupper() and word[1:].replace("'", "").replace("-", "").islower()):
                    continue
                key = word.casefold()
                if key in stop or key in excluded:
                    continue
                seen.add(word)
        counts.update(seen)
    top = counts.most_common(int(helper["top_n"]))
    return pd.DataFrame({"word": [w for w, _ in top], "messages": [n for _, n in top],
                         "in_name_list": [w.casefold() in listed for w, _ in top]})
