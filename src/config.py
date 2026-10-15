"""Load and check config.yaml.

Everything tunable lives in config.yaml. This module reads it, checks it for
mistakes that would otherwise show up as confusing errors later, and resolves
file paths relative to the project folder so the code works from any directory.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

MESSAGE_CLASSES = ("normal", "firm_pressure", "threat", "shaming_third_party")
BEHAVIOURS = ("clean", "borderline", "abusive")
SIZES = ("micro", "small", "medium", "large")
PROFILES = ("typical", "stacked", "cycling", "harassed", "look_alike")
CLASSIFIERS = ("local", "gemini")
RISK_SIGNALS = ("open_lenders", "debt_to_income", "arrears", "cycling", "loan_velocity")
RISK_FULL_AT = ("open_lenders", "debt_to_income", "arrears", "cycling_events", "loans_in_window")


class ConfigError(ValueError):
    """Raised when config.yaml is missing something or has an invalid value."""


def load_config(path: Path | str | None = None) -> dict:
    """Read config.yaml (or another file), validate it and return it as a dict."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    validate_config(cfg)
    return cfg


def resolve_path(cfg: dict, key: str) -> Path:
    """Turn a path from the 'paths' section into an absolute path inside the project."""
    relative = Path(cfg["paths"][key])
    return relative if relative.is_absolute() else PROJECT_ROOT / relative


def validate_config(cfg: dict) -> None:
    """Raise ConfigError with a plain message if the configuration is not usable."""
    if not isinstance(cfg, dict):
        raise ConfigError("config.yaml is empty or not a mapping.")

    for section in (
        "project", "paths", "generator", "regions", "loans",
        "lender_sizes", "lenders", "lender_behaviour", "messages", "profiles",
        "risk", "evaluation", "classifier", "lender_comparison", "dashboard", "onboarding", "privacy",
        "app", "demo", "currency",
    ):
        if section not in cfg:
            raise ConfigError(f"config.yaml is missing the '{section}' section.")

    for key in ("name", "tagline"):
        value = cfg["project"].get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"project.{key} must be a non-empty text.")

    for size in SIZES:
        if size not in cfg["lender_sizes"]:
            raise ConfigError(f"lender_sizes is missing '{size}'.")

    if not cfg["lenders"]:
        raise ConfigError("The 'lenders' list is empty.")
    for lender in cfg["lenders"]:
        if lender.get("size") not in SIZES:
            raise ConfigError(f"Lender {lender.get('name')!r}: size must be one of {SIZES}.")
        if lender.get("behaviour") not in BEHAVIOURS:
            raise ConfigError(f"Lender {lender.get('name')!r}: behaviour must be one of {BEHAVIOURS}.")
        cap = lender.get("max_loans")
        if cap is not None and (not isinstance(cap, int) or cap < 1):
            raise ConfigError(f"Lender {lender.get('name')!r}: max_loans must be a whole number of 1 or more.")

    for behaviour in BEHAVIOURS:
        spec = cfg["lender_behaviour"].get(behaviour)
        if spec is None:
            raise ConfigError(f"lender_behaviour is missing '{behaviour}'.")
        probs = spec.get("class_probs", {})
        missing = [c for c in MESSAGE_CLASSES if c not in probs]
        if missing:
            raise ConfigError(f"lender_behaviour.{behaviour}.class_probs is missing {missing}.")
        if not math.isclose(sum(probs[c] for c in MESSAGE_CLASSES), 1.0, abs_tol=1e-6):
            raise ConfigError(f"lender_behaviour.{behaviour}.class_probs must add up to 1.")
        low, high = spec["overdue_messages"]
        if low < 1 or high < low:
            raise ConfigError(f"lender_behaviour.{behaviour}.overdue_messages must be [min, max] with min >= 1.")

    for name in PROFILES:
        spec = cfg["profiles"].get(name)
        if spec is None:
            raise ConfigError(f"profiles is missing '{name}'.")
        for key in ("n_loans", "term_days", "issue_days_ago"):
            low, high = spec[key]
            if high < low:
                raise ConfigError(f"profiles.{name}.{key} must be [min, max].")
        if spec["n_loans"][0] < 1:
            raise ConfigError(f"profiles.{name}.n_loans must start at 1 or more.")
        if spec["distinct_lenders"] and spec["n_loans"][1] > len(cfg["lenders"]):
            raise ConfigError(
                f"profiles.{name}: more loans per borrower than there are lenders, "
                "but distinct_lenders is true."
            )

    if not 0 <= cfg["generator"]["holdout_template_prob"] <= 1:
        raise ConfigError("generator.holdout_template_prob must be between 0 and 1.")
    if cfg["generator"]["min_lender_messages"] < 1:
        raise ConfigError("generator.min_lender_messages must be 1 or more.")
    if not 0 <= cfg["loans"]["arrears_partial_payment_prob"] <= 1:
        raise ConfigError("loans.arrears_partial_payment_prob must be between 0 and 1.")
    if cfg["generator"]["n_borrowers"] < 50:
        raise ConfigError("generator.n_borrowers must be at least 50.")
    if not 0 <= cfg["generator"]["noise_rate"] <= 1:
        raise ConfigError("generator.noise_rate must be between 0 and 1.")
    if sum(cfg["regions"].values()) <= 0:
        raise ConfigError("regions weights must add up to more than 0.")

    _validate_risk(cfg["risk"])
    _validate_evaluation(cfg["evaluation"])
    _validate_classifier(cfg["classifier"])
    _validate_lender_comparison(cfg["lender_comparison"])
    _validate_dashboard(cfg["dashboard"])
    _validate_onboarding(cfg["onboarding"])
    _validate_privacy(cfg["privacy"])
    _validate_currency(cfg["currency"])
    _validate_app(cfg["app"])
    _validate_demo(cfg["demo"])
    for key in ("predictions_db", "local_model", "datasets_dir", "active_dataset_file"):
        if key not in cfg["paths"]:
            raise ConfigError(f"paths is missing '{key}'.")
    if "sample_pack" in cfg:  # optional: only src/make_sample_pack.py needs it
        validate_sample_pack(cfg["sample_pack"])


SAMPLE_PACK_SCENARIOS = ("baseline", "high_overlap", "cycling", "repayment_mix", "clean_control")
PAYER_KINDS = ("on_time", "late_cleared", "not_paid")


def _probability(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and 0 <= value <= 1


def _range(value, minimum: int = 0) -> bool:
    return (isinstance(value, list) and len(value) == 2 and all(_whole(v, minimum) for v in value)
            and value[0] <= value[1])


def validate_sample_pack(pack) -> None:
    """Checks for the 'sample_pack' section (Phase 9A synthetic lender packs)."""
    if not isinstance(pack, dict):
        raise ConfigError("The 'sample_pack' section must be a mapping.")
    for key in ("seed", "output_dir", "as_of_date", "fake_salt", "message_suffix", "lenders", "small_lender",
                "loans", "borrowers", "repayment", "cyclers", "messages", "behaviour", "scenarios"):
        if key not in pack:
            raise ConfigError(f"sample_pack is missing '{key}'.")
    if not _whole(pack["seed"], 0):
        raise ConfigError("sample_pack.seed must be a whole number of 0 or more.")
    if not isinstance(pack["fake_salt"], str) or "FAKE" not in pack["fake_salt"].upper():
        raise ConfigError("sample_pack.fake_salt must be a text containing the word FAKE (it is never a real salt).")
    letters = [lender.get("letter") for lender in pack["lenders"]]
    if len(letters) != len(set(letters)) or not all(isinstance(x, str) and x.isalpha() for x in letters):
        raise ConfigError("sample_pack.lenders: every lender needs a different letter.")
    for lender in pack["lenders"]:
        if not str(lender.get("name", "")).endswith("(Demo)"):
            raise ConfigError("sample_pack.lenders: every name must end in '(Demo)'.")
        if lender.get("size") not in SIZES or lender.get("behaviour") not in BEHAVIOURS:
            raise ConfigError(f"sample_pack.lenders {lender.get('letter')}: size or behaviour is not valid.")
        if isinstance(lender.get("weight"), bool) or not isinstance(lender.get("weight"), (int, float)) \
                or lender["weight"] <= 0:
            raise ConfigError(f"sample_pack.lenders {lender.get('letter')}: weight must be more than 0.")
    if pack["small_lender"].get("letter") not in letters:
        raise ConfigError("sample_pack.small_lender.letter must be one of the sample_pack lenders.")
    split = pack["repayment"]["payer_split"]
    if set(split) != set(PAYER_KINDS) or not math.isclose(sum(split.values()), 1.0, abs_tol=1e-6):
        raise ConfigError(f"sample_pack.repayment.payer_split needs {PAYER_KINDS} adding up to 1.")
    for section, key in (("repayment", "reborrow_prob"), ("repayment", "link_share"),
                         ("messages", "late_night_reminder_prob"), ("messages", "abusive_before_due_prob"),
                         ("messages", "exact_balance_prob"), ("messages", "late_cleared_overdue_prob"),
                         ("messages", "shaming_third_party_prob"), ("messages", "mixed_language_prob")):
        if not _probability(pack[section].get(key)):
            raise ConfigError(f"sample_pack.{section}.{key} must be a number from 0 to 1.")
    for section, key in (("repayment", "late_clear_days"), ("repayment", "not_paid_stop_day"),
                         ("repayment", "reborrow_gap_days"), ("repayment", "history_days"),
                         ("cyclers", "start_days_ago"), ("cyclers", "pay_days_before_switch"),
                         ("cyclers", "payoff_delay_days"), ("messages", "staff_hours"),
                         ("messages", "reminders_per_loan"), ("messages", "overdue_messages")):
        if not _range(pack[section].get(key)):
            raise ConfigError(f"sample_pack.{section}.{key} must be [min, max] whole numbers with min <= max.")
    if pack["messages"]["staff_hours"][1] > 23:
        raise ConfigError("sample_pack.messages.staff_hours must lie between 0 and 23.")
    loans = pack["loans"]
    if not 0 < loans["principal_min"] <= loans["principal_typical"] <= loans["principal_max"]:
        raise ConfigError("sample_pack.loans: need 0 < principal_min <= principal_typical <= principal_max.")
    if not loans["term_days"] < loans["late_charge_day"]:
        raise ConfigError("sample_pack.loans.late_charge_day must come after term_days.")
    if pack["cyclers"]["pay_days_before_switch"][1] >= loans["term_days"]:
        raise ConfigError("sample_pack.cyclers.pay_days_before_switch must end before the loan term.")
    for kind in BEHAVIOURS:
        probs = pack["behaviour"].get(kind, {}).get("class_probs", {})
        if set(probs) != set(MESSAGE_CLASSES) or not math.isclose(sum(probs.values()), 1.0, abs_tol=1e-6):
            raise ConfigError(f"sample_pack.behaviour.{kind}.class_probs needs the four classes adding up to 1.")
    unknown = sorted(set(pack["scenarios"]) - set(SAMPLE_PACK_SCENARIOS))
    if unknown:
        raise ConfigError(f"sample_pack.scenarios: unknown scenario(s) {unknown}.")
    for name, spec in pack["scenarios"].items():
        if not _whole(spec.get("borrowers"), 50) or spec["borrowers"] > 5000:
            raise ConfigError(f"sample_pack.scenarios.{name}.borrowers must be 50 to 5000.")
        if not (_probability(spec.get("multi_lender_share")) and _probability(spec.get("cycler_share"))):
            raise ConfigError(f"sample_pack.scenarios.{name}: multi_lender_share and cycler_share must be 0 to 1.")
        if spec.get("payer_scope") not in ("loan", "borrower") or not isinstance(spec.get("abusive"), bool):
            raise ConfigError(f"sample_pack.scenarios.{name}: payer_scope is loan or borrower; abusive is true/false.")


def _validate_risk(risk: dict) -> None:
    """Checks for the 'risk' section (the Phase 2 borrower risk score)."""
    for key in ("weights", "full_at", "cycling", "velocity_window_days", "bands",
                "cycling_forces_minimum_band", "cycling_minimum_events"):
        if key not in risk:
            raise ConfigError(f"risk is missing '{key}'.")

    weights = risk["weights"] or {}
    missing = [s for s in RISK_SIGNALS if s not in weights]
    if missing:
        raise ConfigError(f"risk.weights is missing {missing}.")
    for signal in RISK_SIGNALS:
        if weights[signal] < 0:
            raise ConfigError(f"risk.weights.{signal} must not be negative.")
    if not math.isclose(sum(weights[s] for s in RISK_SIGNALS), 100, abs_tol=1e-6):
        raise ConfigError("risk.weights must add up to 100.")

    full_at = risk["full_at"] or {}
    missing = [s for s in RISK_FULL_AT if s not in full_at]
    if missing:
        raise ConfigError(f"risk.full_at is missing {missing}.")
    for key in RISK_FULL_AT:
        if full_at[key] <= 0:
            raise ConfigError(f"risk.full_at.{key} must be more than 0.")
    if full_at["open_lenders"] <= 1:
        raise ConfigError("risk.full_at.open_lenders must be more than 1 (one lender alone scores 0).")

    bands = risk["bands"] or {}
    if "medium" not in bands or "high" not in bands:
        raise ConfigError("risk.bands needs both 'medium' and 'high'.")
    if not 0 < bands["medium"] < bands["high"] <= 100:
        raise ConfigError("risk.bands must satisfy 0 < medium < high <= 100.")

    cycling = risk["cycling"] or {}
    if "match_days" not in cycling or "lookback_days" not in cycling:
        raise ConfigError("risk.cycling needs both 'match_days' and 'lookback_days'.")
    if cycling["match_days"] < 0:
        raise ConfigError("risk.cycling.match_days must be 0 or more.")
    if cycling["lookback_days"] < 1:
        raise ConfigError("risk.cycling.lookback_days must be 1 or more.")

    if risk["velocity_window_days"] < 1:
        raise ConfigError("risk.velocity_window_days must be 1 or more.")
    if not isinstance(risk.get("cycling_require_different_lender", True), bool):
        raise ConfigError("risk.cycling_require_different_lender must be true or false.")


def _validate_evaluation(evaluation: dict) -> None:
    """Checks for the 'evaluation' section (which profiles count as positives)."""
    positives = list(evaluation.get("positive_profiles") or [])
    negatives = list(evaluation.get("negative_profiles") or [])
    if not positives:
        raise ConfigError("evaluation.positive_profiles must list at least one profile.")
    for name in positives + negatives:
        if name not in PROFILES:
            raise ConfigError(f"evaluation: unknown profile {name!r}. Known profiles: {PROFILES}.")
    both = sorted(set(positives) & set(negatives))
    if both:
        raise ConfigError(f"evaluation: {both} cannot be both a positive and a negative profile.")


def _validate_classifier(classifier: dict) -> None:
    """Checks for the 'classifier' section (the Phase 3 message classifiers)."""
    if classifier.get("primary") not in CLASSIFIERS:
        raise ConfigError(f"classifier.primary must be one of {CLASSIFIERS}.")

    local = classifier.get("local")
    if not isinstance(local, dict):
        raise ConfigError("classifier is missing the 'local' settings.")
    for key in ("ngram_range", "min_df", "c", "class_weight", "seed", "mask_lender_names"):
        if key not in local:
            raise ConfigError(f"classifier.local is missing '{key}'.")
    ngrams = local["ngram_range"]
    if not (isinstance(ngrams, list) and len(ngrams) == 2 and 1 <= ngrams[0] <= ngrams[1]):
        raise ConfigError("classifier.local.ngram_range must be [min, max] with 1 <= min <= max.")
    if local["min_df"] < 1:
        raise ConfigError("classifier.local.min_df must be 1 or more.")
    if local["c"] <= 0:
        raise ConfigError("classifier.local.c must be more than 0.")
    if local["class_weight"] not in ("balanced", None):
        raise ConfigError("classifier.local.class_weight must be 'balanced' or empty.")

    gemini = classifier.get("gemini")
    if not isinstance(gemini, dict):
        raise ConfigError("classifier is missing the 'gemini' settings.")
    for key in ("model", "batch_size", "temperature", "max_retries", "requests_per_minute", "daily_request_budget"):
        if key not in gemini:
            raise ConfigError(f"classifier.gemini is missing '{key}'.")
    for key in ("backoff_base_seconds", "delay_seconds", "max_calls", "prompt_version", "cache_file",
                "report_file", "summary_file"):
        if key not in gemini:
            raise ConfigError(f"classifier.gemini is missing '{key}'.")
    if not isinstance(gemini["model"], str) or not gemini["model"].strip() or "<" in gemini["model"]:
        raise ConfigError("classifier.gemini.model must be a model name, for example gemini-2.5-flash.")
    if gemini["temperature"] != 0:
        raise ConfigError("classifier.gemini.temperature must be 0 (the check must be repeatable).")
    if not _whole(gemini["max_calls"], 1):
        raise ConfigError("classifier.gemini.max_calls must be a whole number of 1 or more.")
    for key in ("backoff_base_seconds", "delay_seconds"):
        if isinstance(gemini[key], bool) or not isinstance(gemini[key], (int, float)) or gemini[key] < 0:
            raise ConfigError(f"classifier.gemini.{key} must be a number of 0 or more.")
    for key in ("prompt_version", "cache_file", "report_file", "summary_file"):
        if not isinstance(gemini[key], str) or not gemini[key].strip():
            raise ConfigError(f"classifier.gemini.{key} must be a non-empty text.")
    if gemini["batch_size"] < 1:
        raise ConfigError("classifier.gemini.batch_size must be 1 or more.")
    if gemini["max_retries"] < 0:
        raise ConfigError("classifier.gemini.max_retries must be 0 or more.")
    if gemini["requests_per_minute"] <= 0 or gemini["daily_request_budget"] < 0:
        raise ConfigError("classifier.gemini.requests_per_minute must be more than 0 "
                          "and daily_request_budget 0 or more.")
    _validate_review(classifier.get("review"))


def _whole(value, minimum: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= minimum


def _validate_review(review) -> None:
    """Checks for classifier.review (Phase 5.1, people checking labels on real data)."""
    if not isinstance(review, dict):
        raise ConfigError("classifier is missing the 'review' settings.")
    for key, minimum in (("sample_size_default", 1), ("min_reviewed_to_retrain", 1), ("min_per_class", 1),
                         ("cv_folds", 2), ("min_for_accuracy", 1), ("small_sample_warning", 1), ("seed", 0)):
        if not _whole(review.get(key), minimum):
            raise ConfigError(f"classifier.review.{key} must be a whole number of {minimum} or more.")
    for key in ("include_demo_in_retrain", "show_prediction_before_label"):
        if not isinstance(review.get(key), bool):
            raise ConfigError(f"classifier.review.{key} must be true or false.")
    weight = review.get("demo_weight")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
        raise ConfigError("classifier.review.demo_weight must be a number from 0 to 1.")
    confidence = review.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.5 <= confidence < 1:
        raise ConfigError("classifier.review.confidence must be between 0.5 and 1 (for example 0.95).")
    if review["min_per_class"] * len(MESSAGE_CLASSES) > review["min_reviewed_to_retrain"]:
        raise ConfigError("classifier.review.min_reviewed_to_retrain must be at least min_per_class times 4.")
    if review["cv_folds"] > review["min_per_class"]:
        raise ConfigError("classifier.review.cv_folds cannot be more than min_per_class "
                          "(every fold needs an example of every class).")


def _validate_lender_comparison(comparison: dict) -> None:
    """Checks for the 'lender_comparison' section."""
    classes = list(comparison.get("abusive_classes") or [])
    if not classes:
        raise ConfigError("lender_comparison.abusive_classes must list at least one class.")
    for name in classes:
        if name not in MESSAGE_CLASSES:
            raise ConfigError(f"lender_comparison: unknown class {name!r}. Known classes: {MESSAGE_CLASSES}.")
    confidence = comparison.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0.5 <= confidence < 1:
        raise ConfigError("lender_comparison.confidence must be between 0.5 and 1 (for example 0.95).")
    window = comparison.get("late_night_detect")
    if not isinstance(window, dict) or not all(_whole(window.get(k), 0) and window[k] <= 23
                                               for k in ("start_hour", "end_hour")):
        raise ConfigError("lender_comparison.late_night_detect needs start_hour and end_hour, whole hours 0 to 23.")
    if window["start_hour"] == window["end_hour"]:
        raise ConfigError("lender_comparison.late_night_detect: start_hour and end_hour must differ.")


def _validate_dashboard(dashboard: dict) -> None:
    """Checks for the 'dashboard' section (Phase 4)."""
    if not isinstance(dashboard, dict):
        raise ConfigError("The 'dashboard' section must be a mapping.")
    for key in ("top_n", "example_messages_per_class", "table_page_size", "concern_min_abusive_messages"):
        value = dashboard.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"dashboard.{key} must be a whole number of 1 or more.")
    seed = dashboard.get("example_seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ConfigError("dashboard.example_seed must be a whole number of 0 or more.")


def _validate_onboarding(onboarding: dict) -> None:
    """Checks for the 'onboarding' section (Phase 4B, bringing in your own data)."""
    if not isinstance(onboarding, dict):
        raise ConfigError("The 'onboarding' section must be a mapping.")
    if not isinstance(onboarding.get("redact_by_default"), bool):
        raise ConfigError("onboarding.redact_by_default must be true or false.")
    if not isinstance(onboarding.get("day_first_default"), bool):
        raise ConfigError("onboarding.day_first_default must be true or false.")
    prefix = onboarding.get("example_id_prefix")
    if not isinstance(prefix, str) or not prefix.strip():
        raise ConfigError("onboarding.example_id_prefix must be a non-empty text.")


def _validate_privacy(privacy: dict) -> None:
    """Checks for the 'privacy' section (Phase 5.1, redaction of message text)."""
    import re

    if not isinstance(privacy, dict):
        raise ConfigError("The 'privacy' section must be a mapping.")
    for key in ("redact_emails", "redact_ids", "redact_phones", "redact_names"):
        if not isinstance(privacy.get(key), bool):
            raise ConfigError(f"privacy.{key} must be true or false.")
    digits = privacy.get("phone_min_digits")
    if not _whole(digits, 6) or digits > 15:
        raise ConfigError("privacy.phone_min_digits must be a whole number from 6 to 15.")
    if not _whole(privacy.get("id_min_digits"), 1):
        raise ConfigError("privacy.id_min_digits must be a whole number of 1 or more.")
    patterns = privacy.get("id_patterns")
    if not isinstance(patterns, list):
        raise ConfigError("privacy.id_patterns must be a list (it may be empty).")
    for number, item in enumerate(patterns, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("pattern"), str) or not item["pattern"].strip():
            raise ConfigError(f"privacy.id_patterns entry {number} needs a 'pattern' text.")
        try:
            re.compile(item["pattern"])
        except re.error as error:
            raise ConfigError(f"privacy.id_patterns entry {number} is not a valid pattern ({error}).") from None
    keywords = privacy.get("id_keywords")
    if not isinstance(keywords, list) or not all(isinstance(k, str) and k.strip() for k in keywords):
        raise ConfigError("privacy.id_keywords must be a list of words (it may be empty).")
    name_file = privacy.get("name_list_file")
    if not isinstance(name_file, str) or not name_file.strip():
        raise ConfigError("privacy.name_list_file must be a file path, for example data/redaction_names.txt.")
    helper = privacy.get("possible_names")
    if not isinstance(helper, dict) or not _whole(helper.get("top_n"), 1):
        raise ConfigError("privacy.possible_names.top_n must be a whole number of 1 or more.")
    stop = helper.get("stop_words")
    if not isinstance(stop, list) or not all(isinstance(w, str) for w in stop):
        raise ConfigError("privacy.possible_names.stop_words must be a list of words.")


def _validate_app(app: dict) -> None:
    """Checks for the 'app' section (Phase 5.2: presentation mode and the error log)."""
    if not isinstance(app, dict):
        raise ConfigError("The 'app' section must be a mapping.")
    if not isinstance(app.get("presentation_mode"), bool):
        raise ConfigError("app.presentation_mode must be true or false.")
    if not isinstance(app.get("log_file"), str) or not app["log_file"].strip():
        raise ConfigError("app.log_file must be a file path, for example data/logs/app.log.")
    if not _whole(app.get("log_max_bytes"), 10000):
        raise ConfigError("app.log_max_bytes must be a whole number of 10000 or more.")
    if not _whole(app.get("log_backups"), 1):
        raise ConfigError("app.log_backups must be a whole number of 1 or more.")
    boot = app.get("bootstrap")
    if not isinstance(boot, dict):
        raise ConfigError("app.bootstrap must be a mapping (auto_build, lock_timeout_seconds, wait_poll_seconds, "
                          "expected_minutes).")
    if boot.get("auto_build") not in ("presentation", "always", "never"):
        raise ConfigError("app.bootstrap.auto_build must be presentation, always or never.")
    if not _whole(boot.get("lock_timeout_seconds"), 60):
        raise ConfigError("app.bootstrap.lock_timeout_seconds must be a whole number of 60 or more.")
    poll = boot.get("wait_poll_seconds")
    if isinstance(poll, bool) or not isinstance(poll, (int, float)) or not 0.1 <= poll <= 30:
        raise ConfigError("app.bootstrap.wait_poll_seconds must be a number from 0.1 to 30.")
    if not _whole(boot.get("expected_minutes"), 1):
        raise ConfigError("app.bootstrap.expected_minutes must be a whole number of 1 or more.")


def _validate_demo(demo: dict) -> None:
    """Checks for the 'demo' section (Phase 5.2: featured cases on the Guided Demo page)."""
    if not isinstance(demo, dict):
        raise ConfigError("The 'demo' section must be a mapping.")
    if not _whole(demo.get("many_lenders_min_open"), 2):
        raise ConfigError("demo.many_lenders_min_open must be a whole number of 2 or more.")
    value = demo.get("many_lenders_max_dti")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError("demo.many_lenders_max_dti must be a number above 0.")
    if not _whole(demo.get("harassed_min_abusive"), 1):
        raise ConfigError("demo.harassed_min_abusive must be a whole number of 1 or more.")


def _validate_currency(currency: dict) -> None:
    """Checks for the 'currency' section (Phase 7A: how money is written)."""
    if not isinstance(currency, dict):
        raise ConfigError("The 'currency' section must be a mapping with code, symbol and decimals.")
    code = currency.get("code")
    if not isinstance(code, str) or len(code) != 3 or not code.isalpha() or not code.isupper():
        raise ConfigError("currency.code must be a three-letter code in capitals, for example UGX.")
    symbol = currency.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ConfigError("currency.symbol must be a non-empty text, for example UGX.")
    decimals = currency.get("decimals")
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 3:
        raise ConfigError("currency.decimals must be a whole number from 0 to 3 (UGX uses 0).")
