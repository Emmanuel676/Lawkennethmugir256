# Changes in Phase 8D (one logo that reads on any theme, shorter tile labels)

- **Why the logo still failed after 8C:** the sidebar logo was still one of two files, chosen from `st.context.theme.type`. Streamlit 1.65 can report that wrongly on a session's first run. In your case the browser was in dark mode while the app was light, and the pale-text file was chosen: "FairLend" at 1.02:1 on the light sidebar.
- **Why not inline HTML that takes the sidebar's text colour:**
  - `st.logo` draws an `<img>`, which cannot take the page's text colour, and an SVG media query inside it follows the device's dark mode, the very failure seen.
  - `st.sidebar.html` would sit below the page menu and lose the small header icon.
  - No single text colour reaches 4.5:1 on both sidebars (`#F0F2F6` and `#262730`), so an accent like "Watch" cannot be theme-proof by colour alone.
- **Fix:** one wide logo (`assets/fairlend-watch-logo.svg`) and one icon (`assets/fairlend-watch-icon.svg`), each drawn on an opaque white rounded plate with a slate border.
  - The two theme files `fairlend-watch-logo-light.svg` and `-dark.svg` were removed, and so was `pick_logo()`.
  - `show_logo()`, `logo_image()` (About page) and the page icon no longer read the theme at all; `theme_type()` and `_theme()` are now used for chart text colours only.
  - The icon's amber ring went from `#D97706` (3.19:1 on white) to `#B45309` (5.02:1).
- **Contrast after** (every element sits on the opaque plate, so the plate is its background on either sidebar):
  - "FairLend" `#0F172A` 17.85:1
  - "Watch" and the teal ring `#0F766E` 5.47:1
  - the tagline and the slate ring `#475569` 7.58:1
  - the amber ring `#B45309` 5.02:1
  - The plate stands out on the dark sidebar at 14.84:1; on the light sidebar its border shows at 2.29:1.
- **Tile labels**, now at most 20 characters, with the full wording in each tile's help:
  - "Owed by high-band borrowers" became "Owed, high band", with help "Owed by high-band borrowers. Exact amount: UGX ...".
  - "Labels checked by a person" became "Checked by a person".
  - The "Flagged AND harassed" sub-line is shorter.
- A static preview of the logo on both sidebars, with the old pale logo for comparison, can be written to `data/logo_preview.html` (git-ignored).
- **Tests:**
  - `tests/test_theme_and_tiles.py` now checks: one logo and one icon; the plate is opaque, white, drawn first and full size; the wordmark is at least 4.5:1 and the icon marks at least 3:1; the plate or its border stands out on each sidebar; why a plate is needed; that the logo never asks for the theme (by calling it and by reading the code); and that tile labels are at most 20 characters.
  - The presentation-mode test now uses a real active dataset; before, it could not fail.
  - The branding, money and preflight checks were updated for the single logo and the new label.
- **Mutation checks:** 12 breaks of the logo colours, the plate, the no-detection rule, the labels, the theme setting and the presentation lock; every one was caught. The presentation one was missed at first, which is how the weak test was found.

# Changes in Phase 8C (light theme, logo per theme, compact UGX tiles)

- **Why "FairLend" vanished:** the app read the theme from `st.context.theme.type`. Streamlit 1.65 documents that this can be wrong on a session's first run and right after a theme change. With no default theme set, the cloud showed the pale-text logo (`fairlend-watch-logo-dark.svg`) on a light sidebar.
  - "FairLend" `#F1F5F9` on the light sidebar `#F0F2F6` is **1.02:1**, invisible.
  - "Watch" `#2DD4BF` is 1.66:1, faint but visible. That is exactly what was seen.
- **Fix:**
  - `.streamlit/config.toml` sets `[theme] base = "light"`, so new visitors start light. There is still no `server.address`, usage statistics are still off, and there are no secrets.
  - `pick_logo()` and `theme_type()` in `src/dashboard_ui.py`: the dark-text logo on light, the pale-text logo on dark, and the light-theme logo whenever the theme is unknown. `show_logo()` asks on every run, so a wrong first reading corrects itself on the next interaction.
  - The About page now uses `logo_image()`, which follows the theme. It used to always show the dark-text logo, which was invisible on a dark page; `light_logo_image` stays as an alias.
- **Contrast, measured from the SVG fills against Streamlit 1.65's sidebar colours** (light `#F0F2F6`, dark `#262730`):
  - light logo on light: "FairLend" 15.93:1, "Watch" 4.88:1, tagline 6.76:1
  - dark logo on dark: 13.54:1, 7.97:1 and 5.79:1
- **Charts:** the black confidence-interval line and ticks were invisible on dark (1.11:1). They are now amber `#D97706` (3.2:1 on white, 5.9:1 on dark). The share bars moved from `#9ecae9` (1.74:1 on white) to `#4C78A8` at 55% opacity, which is 4.6:1 and 4.1:1 at full strength. Labels and score tracks follow the theme. Long lender and loan names get a label limit, so the charts fit narrow screens.
- **Money tiles:** a new `format_money_compact()` in `src/money.py` writes `UGX 259.8M`, `UGX 590K` or `UGX 999`, moves 999,999 up to `UGX 1M`, and gives `n/a` for missing values.
  - The Overview's "Owed by high-band borrowers" tile and the Borrowers page's "Total owed" and "Monthly income" tiles use it, with "Exact amount: UGX ..." as the tile's help.
  - The Review page's "Messages reviewed" now shows the count, with "of N (share)" underneath.
  - Exact amounts stay everywhere else.
- **Tests:** new `tests/test_theme_and_tiles.py` (33). `tests/test_money.py` and `tests/test_review_page.py` were updated for the compact tiles.
- **Mutation checks:** 12 breaks of the logo choice, the theme setting, the compact formatter, the Overview tile and the chart colours; every one was caught.

# Changes after Phase 8B (listening address)

- `.streamlit/config.toml` no longer sets `server.address`, so Streamlit Community Cloud can choose its own. It still turns usage statistics off and holds no secrets.
- Local runs stay on this computer by passing `--server.address localhost` instead:
  - `dev.ps1`: its one Streamlit start line, used with no switch and with `-Present`
  - the README's start commands
  - the hint printed by `build_all`
  - the usage line in `app.py`
- Checked live: `.\dev.ps1 -Present` listens on 127.0.0.1 only and its health check answers `ok`.
- The README note in "Deploying to Streamlit Community Cloud" explains this, and warns that Streamlit started without the flag listens on every network interface.
- Test: `test_streamlit_never_phones_home` now checks that `config.toml` sets no address and that every start command in `dev.ps1` and the README passes `--server.address localhost`.

# Changes in Phase 8B (ready for Streamlit Community Cloud; not deployed)

First-start build
- New `src/bootstrap.py`. When the demo is missing or stale, the app builds it itself. Stale means:
  - the data doesn't match its manifest fingerprint
  - the labels were made from other messages, or are incomplete
  - a file can't be read
  - the saved model was trained with a different scikit-learn

  A build regenerates the data from `config.yaml` and the seed, retrains the classifier under the running scikit-learn (the version is now stored in `local_model.json`), labels every message and checks the result. It deletes the demo's old files first, so a damaged file is never reused, and writes only the demo's files plus `.demo_build.lock` and `.demo_build_progress.json` in the same folder.
- Build once: a lock file created with `O_EXCL`; other visitors wait and see the builder's real steps. A lock older than `app.bootstrap.lock_timeout_seconds` (900) is taken over.
- Failures return an error code. The app log gets the exception type and code locations only, never the message. The page shows "The demo could not be prepared (error code FW-...)" with no traceback.
- `src/dashboard_ui.py`: `page_setup` builds the demo before loading data when `app.bootstrap.auto_build` allows it. `presentation` (the default) means only in presentation mode, which is the cloud; the other values are `always` and `never`. The progress screen says "Preparing the demo: about 1 minute(s), first start only" and shows the real steps.
- `presentation_from_secrets()`: if `FAIRLEND_PRESENT` is only in `st.secrets`, it is copied to the environment. On Streamlit Cloud top-level secrets are environment variables already, so this is a safety net.
- Preflight boots the pages with auto-build switched off, so a check never writes data.
- Measured on this laptop (Python 3.14, empty data folder, presentation mode): build 13.8 s, peak memory 256 MB. First request to first page, build included, 27.4 s at 309 MB peak. A second page after that 0.7 s.

Dependencies
- `requirements.txt` holds only what the app needs, pinned to versions installed and tested on Python 3.12: altair 6.3.0, joblib 1.6.0, numpy 2.5.4, openpyxl 3.1.5, pandas 3.0.6, pyyaml 6.0.3, scikit-learn 1.9.1, streamlit 1.65.0.
- New `requirements-dev.txt`: `-r requirements.txt`, plus pytest 9.1.1 and google-genai 2.30.1.
- `dev.ps1 -Install`, the README and the Gemini check's install hint use the dev file.
- `.gitignore`: `.streamlit/secrets.toml` and `secrets.toml`. `.streamlit/config.toml` has no secrets and usage statistics are off.

README
- "Deploying to Streamlit Community Cloud", with the exact form values and a note to restrict viewers.

Tests
- New `tests/test_bootstrap.py` (25). It covers:
  - builds when missing, skips when fresh, rebuilds after five kinds of staleness
  - two visitors at once build only once
  - an abandoned lock is taken over; a held lock makes others wait and report the builder's failure
  - a failure logs the type only; an unwritable folder fails politely
  - the app builds on first start in presentation mode; a failed first start shows a plain message
  - when the app builds by itself; presentation mode from the environment variable and from `st.secrets`
  - the requirements split and pins; every imported package is in `requirements.txt`; no network names; the Streamlit settings
- Mutation checks: each of 13 safeguards was broken in turn and the tests failed every time.

# Phase 8A, finished

- Fresh-clone test: a clean clone of the commit into a short temp path, a new Python 3.12.10 environment, and `pip install -r requirements.txt` (376 s, after the network was fixed). Then:
  - `python -m src.build_all`: 34.9 s, the same fingerprint `3945277a`
  - preflight: 7 of 7 PASS; git sees no changed files after the build
  - the full suite in the clone: 567 passed in 5 min 12 s
- No test fixture, template or asset is hidden by the `*.csv`, `*.xlsx`, `*.joblib` or `*salt*` patterns: nothing outside `data/`, `.venv` and the caches is ignored.
- The first 3.12 install failed on Windows' 260-character path limit in a deep temp folder; a shorter clone path fixed it.
- The model saved under Python 3.14 loads and predicts under Python 3.12 with the same scikit-learn (1.9.1). Across scikit-learn versions that is not guaranteed, which is why the cloud retrains at start-up.

# Changes in Phase 8A (GitHub preparation and the try-a-message box)

Try a message
- New `src/try_message.py` and a "Try a message" box at the bottom of the Lenders page:
  - one typed message gets its predicted class, with the probability of each class
  - the model is the active dataset's own retrained model if there is one, otherwise the saved local model; nothing is trained on the page
  - lender names are masked by the model's own masking step, as in training
  - the text is cleared on the server as soon as it is labelled, and is never stored, logged or added to a dataset
  - empty and over-long input get a plain message, and the page shows "A prompt for a human to look, never a verdict."
- Hidden in presentation mode: the demo script does not use it.
- Tests: `tests/test_try_message.py` (12). They check:
  - the class and probabilities
  - empty and long input
  - masking: the same answer with and without lender names, in any case
  - which model is used
  - that no file under the world folder or `data/` is created or changed and none contains the text
  - that the session keeps no text
  - that the box is hidden in presentation mode, and the message when there is no saved model

Git
- The repository was initialised on `main`. Your commit `7b2efa6` added `README.md`, and its stray last line (`# Lawkennethmugir256` from GitHub's quick-start snippet) was removed. The README is plain UTF-8 with no byte-order mark, and the repository stores LF line endings.
- A complete `.gitignore`. It excludes:
  - secrets: `.env`, salt and pepper files
  - tools: `.venv/`, caches, `.claude/settings.local.json`
  - everything under `data/` except `data/.gitkeep`, plus databases, models, CSV and Excel files, logs, the Gemini files and the redaction name list
- New `.gitattributes`: LF in the repository, CRLF for `.ps1` files.
- README:
  - a clearer UGX and privacy notice at the top
  - "Try a message"
  - "Getting the code and rebuilding the demo"
  - "License" (not decided yet)

License: a question for you (nothing was chosen)
- Without a license, nobody else may use, copy or change the code. Which do you want?
  1. Keep it closed for now (no LICENSE file): fine for a private repository.
  2. MIT or Apache-2.0: anyone may reuse it, including commercially. Apache-2.0 adds an explicit patent grant.
  3. GPL-3.0 or AGPL-3.0: reuse is allowed, but changed versions must stay open. AGPL also covers running it as a web service.
  4. Something your organisation or funder requires.

# Changes in Phase 3B (Gemini second opinion on the synthetic test set)

- New `src/gemini_check.py` (`python -m src.gemini_check`). It is an evaluation module like `evaluate_*`, so it may read the demo's answer labels, and only to select the test split and score. The safeguards:
  - **Demo only:** it refuses unless the dataset is the demo and its meta table says `synthetic = 'true'`.
  - **Test split only:** only `test` messages are selected, and the split is checked again after selection.
  - **Key from the environment only:** `GEMINI_API_KEY` is read with `os.environ`. There is no `python-dotenv` in the project, and nothing opens `.env`. If the key is missing, a friendly message names the variable and the `Read-Host` command; nothing secret is echoed.
  - **Masking:** lender names are masked with the existing masker.
  - **Distinct texts:** only distinct texts are sent, and answers are mapped back to every message. The brief expected about 16; in fact 400 test messages give 395 distinct texts.
  - **Fixed prompt:** the prompt defines the four classes, asks for JSON at temperature 0 with a response schema, and replies are validated. An invalid or contradictory reply is "no answer": never guessed, never cached.
  - **Cache and resume:** answers are cached in `data/gemini_cache.json`, keyed by sha256 of prompt version, model and text (labels only, written atomically). Runs are resumable.
  - **Free-tier limits:** batches of `batch_size`, a pause of the larger of `delay_seconds` and `60 / requests_per_minute`, exponential backoff on 429 and 5xx, and a hard `max_calls` cap per run (retries count).
  - **Outputs:** `data/gemini_check_report.csv` (per phrasing: truth, local, Gemini, one example text; the only file with text), `data/gemini_check_summary.json` (counts only), and a printed summary with agreement rates, disagreeing phrasings and both confusion matrices. It says it is a second opinion on synthetic text.
  - **Errors:** never the error text or request details; only the type and status code.
- `classifier.gemini` in `config.yaml` gained `backoff_base_seconds`, `delay_seconds`, `max_calls`, `prompt_version`, `cache_file`, `report_file` and `summary_file`, all validated. `model` is now `gemini-2.5-flash` (it was a placeholder); this was **not checked online**, so confirm it before running. `temperature` must be 0.
- `requirements.txt`: `google-genai>=1.0`. It is **not installed in this environment** and was never imported by the tests. The real-client code follows the documented SDK (`genai.Client`, `client.models.generate_content`, `types.GenerateContentConfig`, `errors.APIError.code`), but it has not been run against the real package.
- About page: a read-only "Second opinion on the synthetic test set" section when the summary file exists, read by `gemini_summary()` in `dashboard_data` (a file read, no network). It is hidden in presentation mode, because the demo script does not cover it.
- `.gitignore`: the cache and summary files (the report is already covered by `data/*.csv`).
- Tests: new `tests/test_gemini_check.py` (40 tests, the network always mocked):
  - refusals: a real dataset, a demo not marked synthetic, non-test messages, a missing key
  - the key never printed or stored, even when an SDK error contains it
  - dedupe, cache hits, resume after a capped run, the call cap counting retries, backoff on 429 and 5xx, giving up
  - invalid replies; reply parsing; a report built by hand
  - the wrapper's error mapping and its request settings
  - the About section, including hidden in presentation mode
  - no key-shaped strings, no `.env` access, and no label or SDK names in the dashboard
- Mutation checks: each of 16 safeguards was broken in turn and the tests failed every time. One planned mutation (appending the key to the missing-key message) could not fail any test, because the key is empty on that path. It was replaced by two that print or store a key that is set; both were caught.

# Changes in Phase 7A (currency: Ugandan shilling, UGX)

- New `currency` section in `config.yaml` (`code: UGX`, `symbol: "UGX"`, `decimals: 0`), validated. It replaces `project.currency`, so the currency lives in one place. The value stored in each dataset's meta table is still `UGX`, so the demo's fingerprint is unchanged.
- New `src/money.py`: `format_money(x)` gives `UGX 1,500,000` (no decimals, thousands separators; `n/a` for None, NaN, infinity or text), plus `money_label("Total owed")` (`Total owed (UGX)`) and `money_column("total_owed")` (`total_owed_ugx`).
- Used everywhere money is shown:
  - Overview: owed by high-band borrowers, and the top-borrowers table header
  - Borrowers page: total owed and monthly income, the borrower table header, and the loan table headers
  - the plain-language score explanation ("Owes UGX 748,400, ...")
- The old `money()` helper in `dashboard_ui` was removed.
- Flagged-borrowers download: the money columns are now `monthly_income_ugx` and `total_owed_ugx`. The import templates, the database and `borrower_scores.csv` keep the plain names (`monthly_income`, `principal`, `amount_outstanding`, `amount`), so existing files still import.
- Import:
  - the template's Instructions sheet says amounts are Ugandan shillings (UGX), whole shillings, no decimals
  - each money header cell in the Excel template has a note saying so
  - the Data page says it on the Import and Templates tabs
  - amount errors say "whole number of shillings (Ugandan shillings, UGX, no decimals; ...)"
- README ("Money") and `docs/DEMO_SCRIPT.md` wording; no numbers changed.
- Audit: no `$`, `USD` or `KES` was found anywhere a user reads (the README lists `$200,000` only as an amount the import refuses).
- Tests: new `tests/test_money.py` (50 tests):
  - the formatter, including NaN and None
  - currency config validation
  - no `$`, `USD`, `KES` or "dollars" in UI string literals or the docs, with a check that the scan itself can fail
  - UGX on the Overview, the Borrowers page, the exports, the templates, the import errors and the Data page

# Changes in Phase 5.2 (demo readiness and robustness)

Presentation mode (Part A)
- New `app` section in `config.yaml`: `presentation_mode` (default false) and the error-log settings. The environment variable `FAIRLEND_PRESENT` wins over the setting (1/true/yes/on or 0/false/no/off).
- `src/datasets.py`: `presentation_mode(cfg)`. In presentation mode:
  - `get_active_name` always returns the demo and never reads `active_dataset.txt`
  - `list_datasets` returns the demo only and never lists or opens a real dataset folder
  - `set_active` is refused
- Pages: the dataset switcher is replaced by a "Presentation mode" tag; the Data and Review pages stop with a short message (`presentation_block`).
- New `dev.ps1`. There was no `dev.ps1` in the project before, so it was written from scratch. Switches: `-Install`, `-Rebuild`, `-Test`, `-Preflight`, `-Present` (sets `FAIRLEND_PRESENT=1` for that run only). They can be combined and run in that order. Without a switch it starts the dashboard.

Featured cases and the guided demo (Part B)
- New `demo` section in `config.yaml` (`many_lenders_min_open` 4, `many_lenders_max_dti` 0.5, `harassed_min_abusive` 1), validated.
- `featured_cases(data, cfg)` in `src/dashboard_data.py` picks six cases by rules from computed signals only. Ties go to the lowest id. A rule that finds nobody is left out and named; it never crashes. The cases:
  1. the top high-band borrower
  2. a borrower placed in medium by the cycling rule
  3. many lenders but little debt
  4. the most abusive messages with a late-night or third-party one
  5. the unranked lender with the fewest messages
  6. the top-ranked lender
- New page `pages/0_Guided_Demo.py`. It is first in the page menu: Streamlit sorts `pages/` by number prefix, and the main script, `app.py` (Overview), is always above them. It has six numbered steps, each with a sentence to say and a button. The button opens the Borrowers or Lenders page focused on the case, through session state plus `st.switch_page(..., query_params=...)`. Both work in Streamlit 1.65; the address form also works as a bookmark, and it is applied once. On a real dataset the page asks you to switch to the demo.
- New `docs/DEMO_SCRIPT.md`: a 5-minute script with timings, clicks and lines; three caveats to say out loud; twelve hard questions with short, true answers. Its numbers were read from `evaluate_overlap`, `evaluate_classifier` and `evaluate_lenders` on the demo and from `config.yaml`, and are marked as synthetic.

Pre-flight (Part C)
- New `src/preflight.py` (`python -m src.preflight`, `.\dev.ps1 -Preflight`), with seven PASS/FAIL checks:
  - the config is valid
  - the demo matches its manifest fingerprint
  - the labels are fresh and complete
  - every page boots in presentation mode under AppTest
  - presentation mode hides a temporary real dataset
  - the logos exist
  - `.env` is in `.gitignore`, named by no page, and static serving is off; `.env` itself is never opened

  It prints a summary line and exits 0 or 1. About 20 seconds.

Edge cases and robustness (Part D)
- `load_all` now gives friendly statuses for these cases (it used to raise on them):
  - an **empty** dataset ("has no borrowers yet")
  - an **unreadable** dataset, where `lending.db` or `predictions.db` is damaged or zero bytes ("cannot be read")
- `dataset_counts` and `data_health` survive damaged files too.
- Every page body runs inside `guarded()` (`src/dashboard_ui.py`). An unexpected error shows "Something went wrong on this page (error code FW-XXXXXX)" and writes one line to `data/logs/app.log` (new `src/app_log.py`): the time, the code, the page, the exception type and the code locations only. No message, values or source lines are logged. The log rotates at 2 MB and keeps 3 old files, and `data/logs/` is git-ignored. `st.stop`, `st.rerun` and `st.switch_page` pass through, since they are not `Exception` subclasses.
- Lender ranking ties: the order (interval low end, then share, then lender id) is now documented and tested.
- Speed at 20,000 borrowers (107,401 messages, 44,857 loans):

  | | Before | After |
  |---|---|---|
  | `load_all` | 5.1 s on an idle machine | 3.1 to 3.8 s idle, about 4.4 s under load |
  | Borrowers page, first (uncached) run | 8.0 s | 6 to 9 s, depending on load |
  | Borrowers page, cached run | | 0.4 to 0.6 s |
  | Opening one borrower | | under 1 s |
  | Lenders page, cached | | under 1 s |

  - Fixed: pandas' Arrow-string `isin` between two large columns (1.8 s, now 0.06 s), and the message fingerprint is remembered while `lending.db` is unchanged (0.9 s per reload saved).
  - The page cache uses `st.cache_resource` (no copy per read).
  - **Still over 5 seconds: the first uncached load** at this size. The rest of `load_all` is spread over reading the tables, scoring and comparing lenders (0.3 to 0.7 s each). A real fix would store the scores and comparison at import time instead of computing them per load; that was not done in this phase.

Tests
- New: `tests/test_presentation_and_demo.py` (presentation mode, including that it ignores `active_dataset.txt` and never touches real folders; featured-case rules and determinism; Guided Demo AppTest and its buttons; the error wrapper with an injected failure and log rotation; preflight, including checks that can fail; AST leak and no-network checks on the new code) and `tests/test_edge_cases.py` (every edge case listed in the brief, on every relevant page). `tests/worlds.py` now also writes the demo manifest. The page lists include the Guided Demo page. 465 tests in total (403 before).

# Changes in Phase 5.1 (ready for real field data)

Label review (Part A)
- New `classifier.review` settings in `config.yaml`, all validated with plain messages: `sample_size_default` 50, `min_reviewed_to_retrain` 60, `min_per_class` 5, `include_demo_in_retrain` true, `demo_weight` 0.3, `cv_folds` 5, `show_prediction_before_label` false, `confidence` 0.95, plus `min_for_accuracy` 20, `small_sample_warning` 200 and `seed` 2026.
- `predictions.db` gets a `human_labels` table (message_id, label, batch 'random'/'hard', reviewer, reviewed_at, note). Older files get it added on first use (`CREATE TABLE IF NOT EXISTS`); nothing else changes. When a dataset's messages change (for example after adding a batch), human labels are kept for messages that still exist.
- New `src/review.py` (no Streamlit):
  - `next_batch` (random = seeded uniform sample of unreviewed messages; hard = half lowest-confidence, half spread across lenders and predicted classes)
  - `save_label`, `progress`
  - `measured_accuracy`: random batch only, Wilson intervals, refuses below 20 and says why
  - `effective_labels`
  - `retrain`
  - `reviewed_labels_csv`
- Human labels win everywhere: `lender_comparison.load_inputs`, the dashboard's harassment summary and message table (`predictions.read_effective_labels`). The coverage sentence on the Overview and Lenders pages, and the command-line comparison, report the share of labels checked by a person.
- Each real dataset can have its own retrained model, `dataset_model.joblib` (with `dataset_model.json`), in its folder. `classify_messages` uses it when it exists. The demo cannot be retrained, and its saved model is never overwritten. The demo's model now gets a small note file (`data/local_model.json`, gitignored) saying what it was trained on.
- New page `pages/6_Review.py` with:
  - progress and per-class counts
  - the measured-accuracy box
  - one message at a time, with four class buttons and "Not sure / skip"
  - the model's guess hidden until you choose
  - a choice of batch kind, and a reviewer initials box
  - Retrain, with its report
  - CSV export with a `#` notice line
  - the classes explained, with a link to About
  - on the demo, a note that review is meant for real data

Redaction and privacy (Part B)
- New `privacy` section: enable flags for emails, IDs, phones and names, plus `phone_min_digits` (moved here from `onboarding`), `id_patterns`, `id_min_digits`, `id_keywords`, `name_list_file` (default `data/redaction_names.txt`, gitignored) and `possible_names`.
- New `src/redaction.py`:
  - `[EMAIL]`, then `[ID]` (keyword-led values, and the Ugandan NIN pattern `C[MF]` + 11 or 12 characters, any case, spaces or dashes between groups, at least 5 digits), then `[PHONE]`, then `[NAME]` from the name list (whole words, any case)
  - counts per token, the preview, and the "possible names" helper
- NIN: the `CM`/`CF` prefix is confirmed by several guides; the length is not confirmed (13 or 14 characters, conflicting sources, no official NIRA specification found). Both lengths are accepted, and the config comment says so.
- Data page, Import tab:
  - a "Dates in my files are day/month/year" option
  - a Redaction preview (up to 20 messages, original and redacted side by side, counts for the four tokens)
  - a "Possible names" box after validation, which says plainly that names cannot be detected automatically
- No original text is kept after a redacted import: text is redacted before it is written, and the report's in-memory copy is replaced too.
- Errors, warnings and notes never repeat a cell's value; they give the row numbers and column names only. Read and write failures report the error type, not its text.

Import robustness (Part C)
- Dates:
  - ISO, or day/month/year with `/`, `-` or `.`, `YYYY/MM/DD`, and real Excel date cells
  - times `HH:MM` or `HH:MM:SS`, also after a `T`
  - with day-first off, an ambiguous date is an error naming the row
  - the choice is stored in the report and in the dataset's meta (`dates_day_first`); converted dates are counted in a note
- Amounts: `UGX 200,000`, `Ush 200,000`, `200,000/=`, `200 000`, `200,000.00` and similar are accepted; anything else, including `200k`, is a row-numbered error. Converted amounts are counted.
- CSV files:
  - UTF-8 with or without a BOM, or Windows-1252 text (with a note)
  - comma, semicolon or tab delimiters, detected from the header line (with a note)
- Values:
  - fixed-list values are normalised for spaces, case and `-`/space vs `_` (" Active ", "IN_ARREARS", "In Arrears", "Third-Party"), and the adjusted cells are counted in a note
  - extra columns are ignored, with a notice listing them
  - a blank region is a warning, never an error
- Speed: duplicate-id checks now group once instead of filtering per duplicate, and references and future dates are checked on columns rather than row by row. The parsers for dates, amounts and fixed-list values are cached, because field files repeat the same values. Timing on this laptop for 12 lenders, 9,000 borrowers, 20,000 loans, 15,000 transactions and 50,000 messages: read 3.8 s, validate 8.6 s (was 13.2 s), validate again + redact + write 12.1 s (was 15.9 s), label 50,000 messages 10.3 s; about 35 s in all (was 44 s).

Tests
- New: `tests/test_review.py`, `tests/test_redaction.py`, `tests/test_import_robustness.py`, `tests/test_review_page.py`. `tests/test_import_data.py` was updated for the value-free messages and the new `redact_text` return value (text, counts per token). The page-list checks include the Review page. 403 tests in total (282 before).

# Changes in Phase 4B (bringing your own data)

Datasets
- `src/datasets.py` is now a registry. "demo" is the synthetic data, registered where it is (no files moved). Real datasets live in `data/datasets/<slug>/` with `lending.db`, `predictions.db` and `dataset.json`. The active dataset is stored in `data/active_dataset.txt` (default demo). Both paths are in config, and both are gitignored.
- Functions: `list_datasets`, `create_dataset`, `set_active`, `delete_dataset`, `get_active_paths`, `get_dataset_paths`, `paths_for`, `is_synthetic`, `restore_demo`, `saved_model_exists`, `evaluation_paths`; and a small CLI, `python -m src.datasets --list / --use NAME`.
- Delete guards: the active dataset cannot be deleted; the name must be typed; the demo also needs an extra confirmation and a saved classifier model.
- Every module now gets its paths from the registry. `overlap`, `lender_comparison`, `classify_messages` and the `evaluate_*` modules use the active dataset or `--dataset`. Training (`training_data`) and `generate_data` always use the demo. `build_all` passes `--dataset demo` to every step.
- The `evaluate_*` modules print "No answer labels for this dataset" and exit 0 for real data.
- The classifier trains on the demo when it is there, and otherwise uses the saved model.

Import
- `src/import_data.py`: reads one .xlsx workbook or five CSV files, validates everything (errors and warnings with sheet or file and row), and imports all or nothing in one SQLite transaction. Modes: new dataset, or add to a real dataset (never the demo; existing borrower codes are expected and kept).
- Privacy: a permission confirmation is required; phone and email detection with optional redaction (on by default). It cannot detect names, and says so.
- Real meta: `synthetic = 'false'`, the real-data notice, `as_of_date` (chosen; default the latest event date), currency, last import time.
- After an import, the messages are labelled with the local classifier.
- `src/make_borrower_codes.py`: HMAC-SHA256 borrower codes (`B-` plus 12 hex characters). The salt comes from getpass only. Phone numbers are normalised first, so different ways of writing the same number give the same code.
- `src/import_templates.py`: an Excel template (Instructions sheet, headers, a shaded EXAMPLE row, dropdowns) and five CSV templates. Example rows are refused on import.
- New config section `onboarding` (`redact_by_default`, `phone_min_digits`, `example_id_prefix`), validated; new requirement `openpyxl`.

App
- Every page has a sidebar dataset switcher. Real data shows "REAL DATA - <name>. Confidential." and, with local labels, the warning that they come from a model trained on synthetic text.
- New page `pages/5_Data.py` with Datasets (list, switch, delete with guards, train and save the model, restore demo), Import (validate, then import), Templates and Data health tabs.
- Cached data reloads when the active dataset or its files change.
- The Overview shows the dataset name. The Overview and Lenders pages say so when no lender can be ranked.
- `is_late_night` treats a message without a time as not late (it used to need an hour).

Tests
- New: `tests/test_import_data.py`, `tests/test_datasets.py`, `tests/test_data_page.py` and the tiny hand-made dataset `tests/tiny_data.py` (2 lenders, 6 borrowers, 8 loans, 3 transactions, 12 messages, one borrower at both lenders). 282 tests in total.
- The two test helpers that build their own config paths also got the new keys, so tests never touch `data/`.

# Changes in Phase 4 amendments (FairLend Watch name, logo, dataset-aware paths)

- **Name:** the product is now **FairLend Watch** ("Lending conduct monitor"). `project.name` and the new `project.tagline` in `config.yaml` (both validated) feed the browser-tab title and every page header; the About page uses them too. The folder, package, modules and database meta tables are unchanged, and the lending.db fingerprint is unchanged (`3945277a...df9e`).
- **Logo:** `assets/` holds SVG files only (the PNG copies were not supplied). Streamlit 1.65 accepts SVG for `st.logo`, `page_icon` and `st.image`, so the SVGs are used. `st.logo` has no light/dark parameter in this version, so the shared helper picks the light or dark wide logo from the viewer's theme (`st.context.theme`), with the icon as the small logo and the page icon. The About page shows the light logo. Missing or broken files never raise; the pages fall back to text.
- **Paths:** new `src/datasets.py` with `get_active_paths(cfg)` (dataset "demo": lending.db, predictions.db, optional ground_truth.db from `config.yaml`). `src/dashboard_data.py` now takes its paths only from there, and the pages never handle paths.
- **Tests:** `tests/test_branding_and_paths.py` (39 tests, 193 in total). It checks that the name appears on every page, with and without data, and that it is read from the config. It checks that the logo helpers survive missing and broken files, and that the About page shows the logo. It checks the active paths, and that no page or dashboard module has a string literal containing `lending.db`, `predictions.db` or `ground_truth.db` or uses `resolve_path`.

# Changes in Phase 4 (dashboard)

Code
- `src/dashboard_data.py`: all dashboard logic as pure functions (no Streamlit): `load_all` (returns a status with the exact PowerShell commands when data is missing, stale or not fully classified, instead of raising), `overview_kpis`, `filter_borrowers`, `sort_borrowers`, paging, `borrower_detail`, `lender_detail` (seeded examples), table builders, and `flagged_borrowers_csv` / `lender_comparison_csv` (a `#` notice line, plain snake_case columns).
- `src/dashboard_ui.py`: one `page_setup()` used by every page (notice, review line, cached loading keyed on the database files' modification times, friendly stop on missing data) and the Altair charts.
- `app.py` (Overview) rewritten; new pages `pages/1_Borrowers.py`, `2_Lenders.py`, `3_Export.py`, `4_About.py`.
- `src/build_all.py`: `python -m src.build_all` runs generate, classify (local), score and compare, with one line and a timing per step, stopping at the first failure.
- `src/lender_comparison.py`: the late-night helper is now public (`is_late_night`) so the dashboard uses the same hours.
- `.streamlit/config.toml`: no usage statistics, serves on localhost only.

Config
- New `dashboard` section (`top_n`, `example_messages_per_class`, `table_page_size`, `concern_min_abusive_messages`, `example_seed`), validated.

Tests
- `tests/test_dashboard_data.py` and `tests/test_dashboard_pages.py` (49 tests, 154 in total). They cover the data layer, missing, stale and incomplete data, the exports, the AST check of every dashboard file (labels, `.env`, `dotenv`, `requests`, `urllib`, `genai`), headless AppTest runs of every page with and without data, and interactions on the Borrowers, Lenders and Export pages. Shared helper `tests/worlds.py`.

Docs
- README: status, one-command build, the pages, reading the CSVs. Also fixed a stray control character in the Quick start section (from Phase 2).

# Changes in Phase 3, Part A (local message classifier and lender comparison)

Code
- `src/classify_local.py`: TF-IDF (word 1-2 grams, lowercase) and logistic regression, settings from `classifier.local`. `train()` takes texts and labels; `predict()` returns class, confidence and per-class probabilities. Lender brand names are masked before training (`mask_lender_names: true`). The model is saved to `data/local_model.joblib`.
- `src/training_data.py`: the only non-evaluation module that reads the answer labels, and only for `split = 'dev'`. This keeps `classify_local.py` free of any label access, so the AST leak check covers it.
- `src/predictions.py`: a separate `data/predictions.db` with `message_predictions` (a CHECK constraint limits labels to the four classes; the primary key is `(message_id, classifier)`) plus meta rows (the synthetic flag, the notice, and a fingerprint of the messages, so stale labels are caught after a rebuild).
- `src/classify_messages.py`: CLI `--classifier local`. Trains on dev, labels all messages, upserts. Repeatable, with identical labels each run.
- `src/evaluate_classifier.py`: per-class precision, recall, F1, macro-F1, accuracy and confusion matrix on test and dev, plus the 10 most confidently wrong test messages.
- `src/lender_comparison.py`: per-lender shares, Wilson interval, ranking by its lower bound, unranked lenders below `generator.min_lender_messages`, one sentence per lender, CSV with a `#` notice, `borrower_harassment_summary()`.
- `src/evaluate_lenders.py`: ranking vs `gt_lenders.behaviour`, model vs true abusive share per lender.

Config
- New `classifier` and `lender_comparison` sections, `paths.predictions_db` and `paths.local_model`, all validated. `classifier.gemini.model` is a placeholder until Part B.
- requirements: scikit-learn, joblib. `.gitignore`: generated CSVs and the model file.

Tests
- `tests/test_classifier_local.py` and `tests/test_lender_comparison.py` (35 tests, 105 in total). The AST leak helper moved to `tests/leak_check.py` and is shared with the Phase 2 tests.
- A Wilson edge-case bug was found by the tests and fixed (0 of n gave a lower bound of 2.8e-17 instead of 0).

Results (seed 42)
- Test split: accuracy 93.2%, macro-F1 0.932 (dev 1.000, in-sample). The test set covers only 16 held-out phrasings; two of them account for 23 of the 27 errors.
- Lender ranking: abusive 1-3, borderline 4-6, clean 7-12; Kestrel unranked (6 messages).

Decision made on the team's behalf: `classifier.primary: local`.

# Changes in Phase 2 (overlap detection and borrower risk score)

Code
- `src/overlap.py`: `score_borrowers(conn, cfg)` scores every borrower from `lending.db` only, using five signals (open lenders, debt to income, arrears share, cycling events, loan velocity). The score runs 0-100 and gives a low/medium/high band, with points per signal kept as `pts_*` columns. `explain(row, cfg)` gives plain-language reasons, biggest first. "Today" is `meta.as_of_date`. The database is opened read-only.
- CLI `python -m src.overlap` writes `data/borrower_scores.csv` (its first line is a `#` synthetic-data notice) and prints band counts and the top 3 explanations.
- `src/evaluate_overlap.py`: the only module that reads `ground_truth.db`. `evaluate(scores, truth, cfg)` returns precision, recall, counts and per-profile band shares. It raises `ValueError` if a scored borrower has no label. CLI `python -m src.evaluate_overlap`.

Config
- New `risk` and `evaluation` sections, validated: weights must be non-negative and add up to 100; full_at values > 0 and full_at.open_lenders > 1; 0 < medium < high <= 100; match_days >= 0, lookback_days >= 1, velocity_window_days >= 1; evaluation profiles must be known and not in both lists.

Tests
- `tests/test_overlap.py` (29 tests, 70 in total). It covers hand-built databases with arithmetic answers, config errors, an AST check that `overlap.py` never names the answer labels (shown to fail when a leak is added), and a 1,500-borrower world (seed 11).

Results (seed 42, 5,000 borrowers; thresholds set before evaluation, not tuned)
- Precision 85.3%, recall 87.0%. Typical 0.2% flagged; stacked 91% flagged (48% high); cycling 97% medium (91% only through the forcing rule); harassed 75% flagged (13% high); look-alike 0% high, 47% medium.
- Weak spots: the look-alike median score (34.3) sits just under the medium threshold (35), which makes it fragile. Cycling detection depends on the forcing rule. A quarter of harassed borrowers are left to Phase 3.

Decisions made on the team's behalf (switchable in config.yaml)
- `risk.cycling_forces_minimum_band: true`: 3+ cycling events lift a borrower from low to medium.
- `evaluation.positive_profiles: [stacked, cycling, harassed]`.

# Changes in Phase 1.1 (after the inspection report)

Data
- Test set now uses held-out message wording; 0 test messages have a near-twin in dev. Splits are dev/test/reserve; template ids stored in ground truth.
- "Days overdue" in messages now matches the send date; "1 days" and "due tomorrow" removed.
- Cycling borrowers: chain runs to today, so they still owe money (no "zero debt" cyclers).
- Look-alikes: recent loans, so they genuinely look stacked on open-loan count but with low debt-to-income.
- Arrears loans get partial repayments in about 25% of cases.
- Loan ids follow issue-date order.
- Tiny lender (Kestrel) guaranteed under 50 messages; loud error otherwise. Harassed borrowers never use micro lenders.
- Per-lender `max_loans` option; new config keys validated.

Tests
- Rewritten so they can fail (41 tests, was 23), plus tests of the real built dataset.

Docs
- README updated (timing, splits, caveats, notes).

Open decisions for you: does a cycling borrower with no debt today count as at risk; which profiles are positives (suggested: stacked, cycling, harassed); confirm the two-database decision.
