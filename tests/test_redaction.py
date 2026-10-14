"""Redaction and privacy (Phase 5.1): ID numbers, the name list, counts, nothing original kept, no echoed values."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.config import ConfigError, load_config, validate_config
from src.datasets import get_dataset_paths
from src.import_data import import_upload, read_csvs, redaction_preview, validate_upload
from src.redaction import build_redactor, load_names, possible_names

from leak_check import forbidden_mentions
from tiny_data import csv_bytes, tiny_rows

ROOT = Path(__file__).resolve().parents[1]
NIN = "CM1234567890AB"  # made up: 14 characters, CM + 12


@pytest.fixture
def cfg(tmp_path):
    custom = copy.deepcopy(load_config())
    custom["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    custom["paths"]["active_dataset_file"] = str(tmp_path / "active_dataset.txt")
    names = tmp_path / "names.txt"
    names.write_text("# names to remove\nOkello\nGrace Akello\n\n", encoding="utf-8")
    custom["privacy"]["name_list_file"] = str(names)
    return custom


def redact(cfg, text):
    return build_redactor(cfg).redact(text)


# --- ID numbers ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "CM1234567890AB",           # 14 characters
    "CF123456789AB",            # 13 characters (sources disagree on the length; both are accepted)
    "cm1234567890ab",           # any letter case
    "Cf1234567890Ab",
    "CM 1234 5678 90AB",        # spaces between groups
    "CF-1234-5678-90AB",        # dashes between groups
    "CM 12345-67890 AB",
    "CM12AB34CD56EF",           # letters and digits mixed, no long digit run
])
def test_nin_variants_are_replaced(cfg, text):
    out, counts = redact(cfg, f"Your NIN on file {text}, pay today.")
    assert out == "Your NIN on file [ID], pay today."
    assert counts["ID"] == 1


@pytest.mark.parametrize("text", [
    "Visit CMS Ltd today",               # a word, not an ID
    "CFABCDEFGHIJKL is a code",          # letters only: not enough digits
    "XCM12AB34CD56EF",                   # inside a longer run
    "CM12AB34CD56EFG",                   # one character too long
    "Pay UGX 120,000 by 31 Aug",
])
def test_things_that_are_not_ids_are_kept(cfg, text):
    out, counts = redact(cfg, text)
    assert out == text and counts["ID"] == 0


@pytest.mark.parametrize("text, expected", [
    ("NIN: 9988 7766 55", "NIN: [ID]"),
    ("ID number is AB 1234 567 thanks", "ID number is [ID] thanks"),
    ("national ID 99887766.", "national ID [ID]."),
    ("id no. X7Y8Z9 call us", "id no. [ID] call us"),
    ("Send your ID number please", "Send your ID number please"),   # no value: nothing to remove
    ("Your ID no longer works", "Your ID no longer works"),
])
def test_keyword_led_ids(cfg, text, expected):
    assert redact(cfg, text)[0] == expected


def test_ids_can_be_switched_off(cfg):
    cfg["privacy"]["redact_ids"] = False
    assert redact(cfg, "NIN CM12AB34CD56EF")[0] == "NIN CM12AB34CD56EF"
    cfg["privacy"]["redact_ids"] = True
    assert redact(cfg, "NIN CM12AB34CD56EF")[0] == "NIN [ID]"


def test_a_bad_id_pattern_is_a_plain_config_error():
    broken = copy.deepcopy(load_config())
    broken["privacy"]["id_patterns"] = [{"name": "x", "pattern": "C[MF"}]
    with pytest.raises(ConfigError, match="privacy.id_patterns entry 1 is not a valid pattern"):
        validate_config(broken)


# --- The name list -------------------------------------------------------------------------------------------

def test_names_from_the_list_are_replaced_as_whole_words_in_any_case(cfg):
    out, counts = redact(cfg, "Tell OKELLO and grace  akello to pay. Okellos shop is fine.")
    assert out == "Tell [NAME] and [NAME] to pay. Okellos shop is fine."
    assert counts["NAME"] == 2


def test_no_name_list_means_no_names_removed_and_a_note(cfg, tmp_path):
    cfg["privacy"]["name_list_file"] = str(tmp_path / "missing.txt")
    redactor = build_redactor(cfg)
    assert redactor.name_count == 0
    assert redactor.redact("Tell Okello")[0] == "Tell Okello"
    assert any("Names cannot be detected automatically" in n for n in redactor.notes)


def test_load_names_skips_comments_and_blanks(cfg):
    assert load_names(Path(cfg["privacy"]["name_list_file"])) == ["Grace Akello", "Okello"]


def test_counts_for_every_token(cfg):
    text = f"Okello, call 0772 123 456 or mail a@b.example. NIN {NIN}. Also 256701999888."
    out, counts = redact(cfg, text)
    assert counts == {"PHONE": 2, "EMAIL": 1, "ID": 1, "NAME": 1}
    assert out == "[NAME], call [PHONE] or mail [EMAIL]. NIN [ID]. Also [PHONE]."


# --- Preview and possible names ------------------------------------------------------------------------------

def _sensitive_rows():
    rows = tiny_rows()
    rows["messages"][0][5] = f"Okello, your NIN {NIN} is on file. Pay Alpha Credit."
    rows["messages"][6][5] = "Grace Akello says pay. Ask Nakato about it."
    return rows


def test_redaction_preview_shows_changed_messages_first_with_counts(cfg):
    table, found = redaction_preview(read_csvs(csv_bytes(_sensitive_rows())), cfg, limit=20)
    assert list(table.columns) == ["Row", "Original", "Redacted"]
    assert len(table) == 12
    changed = table[table["Original"] != table["Redacted"]]
    assert list(table.index[:len(changed)]) == list(changed.index)  # changed ones come first
    assert found == {"PHONE": 2, "EMAIL": 1, "ID": 1, "NAME": 2}
    assert not table["Redacted"].str.contains(NIN).any()
    assert redaction_preview(read_csvs(csv_bytes(_sensitive_rows())), cfg, limit=3)[0].shape[0] == 3


def test_possible_names_skip_sentence_starts_lenders_and_stop_words(cfg):
    texts = ["Dear customer, pay now. Tell Nakato and Okello today.", "Alpha Credit: Nakato must pay on Monday.",
             "Nakato is late."]
    found = possible_names(texts, cfg, exclude_words=["Alpha Credit"])
    assert found["word"].tolist() == ["Nakato", "Okello"]
    assert found["messages"].tolist() == [2, 1]  # "Nakato is late." starts a sentence, so it is not counted
    assert found["in_name_list"].tolist() == [False, True]


# --- Nothing original is kept; no message ever echoes a value -------------------------------------------------

def test_after_a_redacted_import_no_original_text_is_kept_anywhere(cfg):
    rows = _sensitive_rows()
    result = import_upload(read_csvs(csv_bytes(rows)), cfg, mode="new", permission_confirmed=True, redact=True,
                           dataset_name="Private", source_description="test", classify=False)
    assert result.ok, result.message
    assert result.redacted == {"PHONE": 2, "EMAIL": 1, "ID": 1, "NAME": 2}
    secrets = [NIN, "Okello", "Akello", "0772 123 456", "772 987654", "collections@beta.example"]
    folder = get_dataset_paths(cfg, "private").lending_db.parent
    files = [p for p in folder.rglob("*") if p.is_file()]
    assert files
    for path in files:
        raw = path.read_bytes()
        for secret in secrets:
            assert secret.encode("utf-8") not in raw, f"{secret!r} found in {path.name}"
    # The report handed back holds the redacted text too, not the original.
    kept = " ".join(result.report.clean["messages"]["text"])
    assert not any(secret in kept for secret in secrets)
    assert "[NAME]" in kept and "[ID]" in kept


def test_errors_warnings_and_notes_never_echo_values(cfg):
    secret = NIN
    rows = tiny_rows()
    rows["lenders"].append([secret, "Gamma", secret])             # bad size_category
    rows["borrowers"][0][2] = secret                                # bad income
    rows["borrowers"][1][3] = secret                                # bad date
    rows["loans"][0][1] = secret                                    # unknown borrower
    rows["loans"][1][0] = secret                                    # (would also be a duplicate below)
    rows["loans"][2][0] = secret
    rows["messages"][0][4] = secret                                 # bad timestamp
    rows["messages"][1][2] = secret                                 # unknown borrower
    rows["messages"][2][5] = f"Okello {secret} 0772 123 456"        # sensitive text
    rows["transactions"][0][6] = secret                             # unknown loan
    upload = read_csvs(csv_bytes(rows))
    report = validate_upload(upload, cfg)
    assert len(report.errors) == 7  # the transaction's loan exists (two loans now carry that id)
    assert "file 'loans.csv', rows 3, 4: the same 'loan_id' appears more than once" in [str(e) for e in report.errors]
    issues = [str(i) for i in report.errors + report.warnings + report.notes]
    result = import_upload(upload, cfg, mode="new", permission_confirmed=True, redact=True, dataset_name="Leaky",
                           classify=False)
    for text in issues + [result.message]:
        for value in (secret, "Okello", "0772", "Gamma"):
            assert value not in text, text
    assert any("row 2: 'monthly_income'" in t for t in issues)  # row numbers and column names are given


# --- Code checks ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["src/redaction.py", "src/review.py", "pages/6_Review.py"])
def test_new_modules_never_mention_labels_secrets_or_network(module):
    names = ("ground_truth", "gt_borrowers", "gt_messages", "gt_lenders", "profile_type",
             ".env", "dotenv", "requests", "urllib", "genai", "http.client", "socket")
    assert forbidden_mentions((ROOT / module).read_text(encoding="utf-8"), names) == []


@pytest.mark.parametrize("module", ["src/redaction.py", "src/import_data.py", "src/review.py"])
def test_privacy_modules_never_print_or_log(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    assert "print(" not in source and "logging" not in source
