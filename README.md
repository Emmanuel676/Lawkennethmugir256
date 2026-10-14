# FairLend Watch

**Lending conduct monitor.** (Previously called the "Digital Lending Harassment and Over-Indebtedness Monitor". The project folder and the Python package keep their old names.)

A two-week prototype. A web dashboard that helps a regulator or consumer body see
which borrowers are buried under overlapping app loans, and which lenders harass
them, using a view across lenders that no single lender has.

> **All data in this project is synthetic.** It describes no real people, loans,
> lenders or messages. Lender names are fictional and end in "(Demo)".
> All amounts are in **Ugandan shillings (UGX)**, whole shillings: illustrative values,
> not researched statistics. Real data must only be loaded with permission, and the
> privacy rules below (redaction, nothing leaves this computer) always apply.

The full requirements are in the PRD (Word document, v0.2). Phases 1, 2, 4, 4B (bringing your own data) and 5 (5.1 ready for real field data; 5.2 demo readiness: presentation mode, guided demo, preflight, edge cases) are done, and Phase 3 is done: Part A (local classifier and lender comparison) and Part B (a Gemini second opinion on the synthetic test set; you run the real call). See `CHANGES.md`.

## Status

| Phase | Days | Work | State |
|-------|------|------|-------|
| 1. Foundation | 1-2 | Project structure, schema, synthetic data generator | **Done** |
| 2. Overlap detection | 3-5 | Signals, risk score, bands, score breakdown | **Done** |
| 3. Abuse detection | 6-8 | Local classifier and lender comparison; Gemini second opinion on the synthetic test set (offline check, not used in the app) | **Done** (3B code; the real Gemini run is yours) |
| 4. Dashboard | 9-11 | Overview, borrower and lender screens, CSV export | **Done** |
| 4B. Data onboarding | - | Import your own data, switch and delete datasets, templates, data health | **Done** |
| 5.1 Ready for field data | - | Label review and retraining, redaction (IDs, names), messy dates, amounts and files | **Done** |
| 5.2 Demo readiness | 12-13 | Presentation mode, guided demo, demo script, preflight, edge cases, error log, speed | **Done** |
| 5. Integration and polish | 12-13 | 5.1 and 5.2 | **Done** |
| 6. Demo | 14 | Rehearsal and one-page write-up | Next |

We confirm with the team before moving to the next phase.

## Quick start (Windows PowerShell)

You need Python 3.11 or newer. Check with `py --version`.

```powershell
cd $HOME\projects\lending-monitor

# 1. Create and activate a virtual environment (once)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install the packages (once). requirements-dev.txt = the app's requirements.txt + pytest + google-genai
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

# 3. Build everything in one command (15 to 35 seconds; no network, no API key):
#    dataset, message labels, data\borrower_scores.csv and data\lender_comparison.csv
python -m src.build_all

# 4. Open the dashboard (it opens in your browser at http://localhost:8501).
#    --server.address localhost keeps it on this computer only; .\dev.ps1 does this for you.
streamlit run app.py --server.address localhost

# 5. Run the tests (about 2 minutes)
python -m pytest -q
```

Stop the dashboard with Ctrl+C in the PowerShell window.

The individual steps that `build_all` runs, and the accuracy checks (which read
the answer labels and are not part of the dashboard), can also be run one by one:

```powershell
python -m src.generate_data                         # synthetic dataset
python -m src.classify_messages --classifier local  # label every message (data\predictions.db)
python -m src.overlap                               # score borrowers (data\borrower_scores.csv)
python -m src.lender_comparison                     # compare lenders (data\lender_comparison.csv)

python -m src.evaluate_overlap                      # risk score vs answer labels
python -m src.evaluate_classifier --classifier local
python -m src.evaluate_lenders
```

If PowerShell refuses to activate the environment with a "running scripts is
disabled" message, run this once in the same window and try step 1 again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Next time, you only need to `cd` into the folder, activate the environment
(`.\.venv\Scripts\Activate.ps1`) and run what you need.

## What is in the folder

| Path | Purpose |
|------|---------|
| `config.yaml` | Every tunable number: seed, size, lenders, profiles, message styles. |
| `app.py` | Dashboard: Overview page. |
| `pages/` | Dashboard: Borrowers, Lenders, Export and About pages. |
| `.streamlit/config.toml` | Keeps the dashboard on this computer and switches off Streamlit's usage statistics. |
| `assets/` | FairLend Watch logos (light and dark backgrounds) and icon, as SVG. |
| `src/config.py` | Loads and checks `config.yaml`. |
| `src/db.py` | Database schemas and helpers. |
| `src/templates.py` | The message templates, by class. |
| `src/generate_data.py` | The seeded generator. |
| `src/overlap.py` | Phase 2: borrower risk score and plain-language breakdown. Reads `lending.db` only. |
| `src/evaluate_overlap.py` | Phase 2: measures the score against the answer labels. The only module that reads `ground_truth.db`. |
| `src/training_data.py` | Phase 3: hands the classifier its training examples, dev messages only. The one non-evaluation module that reads the labels. |
| `src/classify_local.py` | Phase 3: the local classifier (TF-IDF + logistic regression). No network. |
| `src/predictions.py` | Phase 3: `data/predictions.db`, where message labels are stored. |
| `src/classify_messages.py` | Phase 3: trains on dev messages and labels every message. |
| `src/evaluate_classifier.py` | Phase 3: classifier accuracy on the test split (and dev, to show the gap). |
| `src/lender_comparison.py` | Phase 3: per-lender abusive share with a confidence interval, ranking, borrower harassment summary. |
| `src/evaluate_lenders.py` | Phase 3: checks the lender ranking against each lender's true behaviour. |
| `src/dashboard_data.py` | Phase 4: everything the dashboard shows, as plain functions (no Streamlit). |
| `src/dashboard_ui.py` | Phase 4: shared page setup (name, logo, notice, review line, cached loading) and charts. |
| `src/datasets.py` | Datasets: the demo and imported real data, which one is active, delete guards, restore demo. `get_active_paths()` is where the app and commands get their paths. |
| `src/import_data.py` | Phase 4B: reads, validates and imports your own data (xlsx or CSV), all or nothing. |
| `src/import_templates.py` | Phase 4B: builds the Excel and CSV import templates. |
| `src/make_borrower_codes.py` | Phase 4B: turns phone or ID numbers into borrower codes with a secret salt. |
| `pages/5_Data.py` | Phase 4B: the Data page (datasets, import with redaction preview, templates, data health). |
| `src/redaction.py` | Phase 5.1: replaces phone numbers, emails, ID numbers (NIN) and listed names in message text. |
| `src/review.py` | Phase 5.1: review batches, human labels, measured accuracy, retraining a dataset's own model. |
| `pages/6_Review.py` | Phase 5.1: the Review page, where a person checks message labels. |
| `pages/0_Guided_Demo.py` | Phase 5.2: the Guided Demo page, six featured cases with a button each. |
| `src/preflight.py` | Phase 5.2: `python -m src.preflight`, PASS/FAIL checks before a demo. |
| `src/app_log.py` | Phase 5.2: the error log behind "Something went wrong" (types and code locations only). |
| `dev.ps1` | Phase 5.2: `-Install`, `-Rebuild`, `-Test`, `-Preflight`, `-Present`; no switch starts the dashboard. |
| `docs/DEMO_SCRIPT.md` | Phase 5.2: the 5-minute spoken demo script, caveats and hard questions. |
| `src/build_all.py` | Phase 4: builds dataset, labels, scores and lender comparison in one command. |
| `tests/` | Automatic checks (see CHANGES.md for the count), including headless runs of every dashboard page. |
| `data/` | Generated databases, `predictions.db`, the trained model and CSV outputs. Rebuilt by commands, so not stored in Git. |
| `.env.example` | Names the Gemini key variable. Nothing in the project reads `.env`: set `GEMINI_API_KEY` for one PowerShell session instead (see the Gemini section). Never commit `.env`. |
| `src/gemini_check.py` | Phase 3B: `python -m src.gemini_check`, a Gemini second opinion on the demo's synthetic test split only. |

## How the data works

**Two database files, built by one command:**

- `data/lending.db` is everything a detector or the dashboard may see: lenders,
  borrowers, loans, transactions and collection messages, plus a `meta` table
  holding the seed, the "as of" date and the synthetic-data notice.
- `data/ground_truth.db` holds the answer labels (each borrower's profile, each
  message's true class, each lender's real behaviour, and which messages are in
  the held-out test set). **Detection code must never read it.** It exists only
  to measure accuracy.

**Reproducible.** The same seed and config always give the same data. The
generator uses a fixed "today" (`as_of_date` in the config), so it does not
change with the date you run it. `data/dataset_manifest.json` records the seed,
row counts and a fingerprint of `lending.db`.

**Five borrower profiles** (PRD section 8.2): typical, stacked, cycling,
harassed and look-alike. Look-alikes hold several loans at once but have high
income and almost no arrears, so they test whether the risk score raises false
alarms. Cycling borrowers take a new loan as each old one is repaid, and the
chain runs up to today. Loans in arrears sometimes get partial repayments.

**Thirteen fictional lenders** behave as clean, borderline or abusive, and
differ in size. One tiny lender (Kestrel Instant Cash) has fewer than 50
messages on purpose, to test the rule that very small lenders are not ranked.
The generator guarantees this and stops with a clear error if a config or seed
would break it. Harassed borrowers never use the tiny lender.

**Four message classes** (PRD section 9.2): normal, firm pressure, threat, and
shaming or third-party contact. Some messages are deliberately hard (veiled
threats, firm messages that mention a reference person without shaming anyone).
About 15 percent carry typos or SMS shorthand.

**Held-out wording and three-way split.** Each message style has development
templates and separate held-out templates written in a different voice. Every
message is marked in `ground_truth.db` as `dev`, `test` or `reserve`. The 400
test messages (100 per class) come only from held-out wording; leftover
held-out messages are `reserve` and must also stay out of tuning. Never tune on
`test` or `reserve`.

**Caveat:** this text is synthetic, so accuracy measured on it will be higher
than on real messages. Report it that way.

**Notes.** The class name `shaming_third_party` also covers shaming sent
directly to the borrower, matching the PRD class "shaming or third-party
contact". Messages carry no loan id on purpose: real SMS rarely say which loan
they refer to, so the detector must work from borrower and lender.

To change the dataset, edit `config.yaml` and run `python -m src.generate_data`
again. Useful options:

```powershell
python -m src.generate_data --seed 7 --borrowers 1000
python -m src.generate_data --out-dir C:\temp\scratch   # build somewhere else, leave data\ alone
```

## How the risk score works (Phase 2)

> **The score prompts a human to look at a borrower. It is never a verdict.**
> All results below come from synthetic data.

`python -m src.overlap` scores every borrower from `lending.db` alone. "Today"
is the dataset's `as_of_date`, not the real date. Unpaid loans are those whose
status is not `repaid`. Each signal gets a strength from 0 to 1 (1 once it
reaches its "full at" value), times its weight. The weights add up to 100, so
the score runs from 0 to 100.

| Signal | What is measured | Full points at | Weight |
|--------|------------------|----------------|-------:|
| Open lenders | Distinct lenders among unpaid loans (1 lender = 0 points) | 5 lenders | 25 |
| Debt to income | Total owed on unpaid loans / monthly income | 2.0 x income | 30 |
| Arrears | Share of what is owed that sits in loans in arrears | 100% | 20 |
| Cycling | Recent loans (last 180 days) issued within 2 days of repaying a *different* loan | 3 events | 15 |
| Loan velocity | Loans of any status issued in the last 60 days | 4 loans | 10 |

Bands: **low** below 35, **medium** from 35, **high** from 60. Every number
is in the `risk` section of `config.yaml`. Each borrower gets a breakdown
(`explain`) listing the signals by points, biggest first, for example:

```
B02555  score 89.0  band high
  - Owes UGX 748,400, which is 2.1 times monthly income (30.0 of 30 points).
  - Has unpaid loans with 6 different lenders at the same time (25.0 of 25 points).
  - 4 new loans taken within 2 days of repaying a different loan (borrowing to repay) (15.0 of 15 points).
  ...
```

The scores are written to `data/borrower_scores.csv`. Its first line is a `#`
line carrying the synthetic-data notice. Read the file with
`pandas.read_csv(path, comment="#")`.

### Results on the default dataset (seed 42, 5,000 borrowers)

The thresholds were set before evaluation and have not been tuned on these numbers.
"Flagged" means the medium or high band.

| Profile | Should be flagged? | n | High | Medium | Low | Median score |
|---------|--------------------|--:|-----:|-------:|----:|-------------:|
| typical | no | 3,500 | 0% | 0% | 100% | 0.0 |
| stacked | yes | 500 | 48% | 43% | 9% | 59.2 |
| cycling | yes | 250 | 0% | 97% | 3% | 27.6 |
| harassed | yes | 400 | 13% | 62% | 25% | 42.8 |
| look-alike | no | 350 | 0% | 47% | 53% | 34.3 |

Precision 85.3%, recall 87.0% (1,001 found, 173 false alarms, 149 missed).

**Weak spots, stated plainly:**

- **These numbers are optimistic.** The data is synthetic and the profiles were
  generated to be separable. Real borrowers will be messier.
- **Look-alikes sit on a knife edge.** Their median score (34.3) is just under
  the medium threshold of 35, so about half of them land in medium. 165 of the
  173 false alarms are look-alikes (the other 8 are typical borrowers, 0.2% of
  them). A small change to their income or the
  threshold would swing this share a lot. None of them reach high, which is
  the property that matters most.
- **Cycling borrowers are found almost only because of the forcing rule.** Their
  median score is 27.6. Without the rule, 91% of them would be low. The cycling
  signal itself is sharp (it picks out cycling borrowers and almost nobody
  else), but its weight alone does not lift them over 35.
- **A quarter of harassed borrowers are missed.** That is expected: their
  problem is abusive messages, which this score does not read. The Phase 3
  message classifier should catch them.

### Decisions made on your behalf (both switchable in `config.yaml`)

1. **Repeated cycling forces at least the medium band**
   (`risk.cycling_forces_minimum_band: true`, from `cycling_minimum_events: 3`).
   Borrowing to repay is a warning sign even when today's debt looks small.
   Such borrowers are marked `band_forced_by_cycling`, and their breakdown says so.
   Set it to `false` to rely on the score alone. Only 6% of cycling borrowers
   are then flagged, and overall recall falls from 87% to 67% (precision 82%).
2. **Positive profiles are stacked, cycling and harassed**
   (`evaluation.positive_profiles`). Typical and look-alike borrowers should not
   be flagged.

## Message classifier and lender comparison (Phase 3, Part A)

> **A label is a model's guess, and a lender's rank prompts a human to read its
> messages. Neither is a finding of misconduct.** All results come from synthetic data.

**Local classifier** (`src/classify_local.py`): TF-IDF word features (single
words and pairs) and logistic regression. It runs on this computer, needs no
key and sends nothing anywhere. It is trained **only on the `dev` split**. The
`test` and `reserve` messages never reach training; a test checks this.
Lender brand names are replaced by one placeholder word before training, so
the model learns from what a message says, not from which lender sent it.
Without that, the lender comparison would partly echo each lender's identity.
Labels are stored in `data/predictions.db` (a separate file; nothing is
written into `lending.db`). If the dataset is rebuilt, the stored labels are
detected as stale and you are asked to classify again.

**Lender comparison** (`src/lender_comparison.py`): per lender, it shows the
share of messages labelled threat or shaming (`lender_comparison.abusive_classes`)
with a 95% Wilson interval, plus the threat, shaming, third-party and
late-night shares and the messages per borrower. Lenders with fewer than 50
messages (`generator.min_lender_messages`) are **not ranked**. The others are
ranked by the **lower end** of the interval, so a small lender with a few bad
messages cannot top the list by luck. Results go to `data/lender_comparison.csv`;
its first line is a `#` notice, so read it with `comment="#"`.

### Results on the default dataset (seed 42)

Local classifier, **test split** (400 messages written in held-out phrasings it
never saw): accuracy 93.2%, macro-F1 0.932.

| Class | Precision | Recall |
|-------|----------:|-------:|
| normal | 0.99 | 0.90 |
| firm_pressure | 0.99 | 0.99 |
| threat | 0.85 | 0.99 |
| shaming_third_party | 0.91 | 0.85 |

On the dev split (its own training data) it scores 1.000. That is in-sample
and shown only to make the gap (0.068) visible.

**Read the test number with care:**

- **It is optimistic.** All the text is synthetic.
- **The 400 test messages come from only 16 held-out phrasings.** The errors
  come in whole phrasings. "Pay ... or your colleagues will receive a message
  about your debt" (shaming) was called a threat 15 times out of 15. A polite
  "we kindly request that you settle ... we will try to help" reminder was
  called shaming 8 times out of 8. So the honest summary is "about 14 of 16
  unseen phrasings handled", not "93% of real messages".
- **The model errs towards "abusive".** It over-estimates each lender's
  abusive share by about 1 percentage point.

Lender ranking: the three abusive lenders rank 1 to 3, the three borderline
lenders 4 to 6, and the six clean lenders 7 to 12. Every abusive lender ranks
above every clean and every borderline one. The tiny lender (Kestrel, 6
messages, truly abusive) is correctly left unranked, with an interval of 0% to
39%. The lenders were built to differ clearly, so real lenders will be far
harder to separate.

## The dashboard (Phase 4)

> Every page shows the synthetic-data notice and the line **"Flags prompt a
> human to look. They are not findings and not a verdict."**

`streamlit run app.py` opens five pages. They read `lending.db` and
`predictions.db` only. They never read the answer labels, never use the network
and need no API key. Bands are always written as words (low / medium / high),
never shown by colour alone. If the data is missing or out of date, each page
shows the PowerShell commands to fix it instead of an error.

| Page | What it shows |
|------|---------------|
| **Overview** (`app.py`) | Headline numbers (borrowers per band, money owed by high-band borrowers, messages classified and the share labelled abusive, lenders ranked and unranked, borrowers who are both flagged and received 3 or more abusive messages). Also a band chart, the 10 highest-risk borrowers, the lender chart with confidence intervals, the data date and the classifier used. |
| **Borrowers** | Filters (band, region, minimum score, open lenders, abusive messages, id search), sorting and a paged table. Choosing a borrower shows the score breakdown (points per signal and the plain-language reasons), the cycling-rule note where it applies, the borrower's loans across all lenders, a loan timeline and every message they received with its class, lender, late-night and third-party flags. |
| **Lenders** | The ranked table (rank, size, messages, abusive share with interval, threat, shaming, third-party and late-night shares), the interval chart, a separate "Too few messages to rank" section, and example threat and shaming messages for any lender (the same examples every time). |
| **Export** | Downloads of the flagged borrowers (medium and high by default; adjustable) and the lender comparison, with row counts. |
| **About** | What the system does, the score signals and weights (read from `config.yaml`), the four message classes, ethics and limits, and the known weak spots. |

**Name and logo.** The product name and tagline come from `project.name` and
`project.tagline` in `config.yaml` and appear in every page header and in the
browser tab. The sidebar logo follows the viewer's light or dark theme; the
icon is used as the browser-tab icon and the small logo. The About page shows
the light logo. If the files in `assets/` are missing, pages show text only.

**Where the data comes from.** Pages and `src/dashboard_data.py` get their
database paths only from `get_active_paths()` in `src/datasets.py`. Today it
returns the "demo" dataset at the paths in `config.yaml`; dataset switching
will be added there.

Settings are in the `dashboard` section of `config.yaml` (`top_n`,
`example_messages_per_class`, `table_page_size`, `concern_min_abusive_messages`,
`example_seed`). Data is cached and reloads by itself when either database file
changes (for example after `python -m src.build_all`).

**Reading the CSV files.** Every CSV this project writes (`data\borrower_scores.csv`,
`data\lender_comparison.csv` and both downloads on the Export page) starts with
one line beginning with `#` that carries the synthetic-data notice. Read them with:

```python
import pandas as pd
borrowers = pd.read_csv("flagged_borrowers.csv", comment="#")
```

In Excel the notice simply appears as the first row. Column names are plain
English, for example `risk_score`, `placed_in_medium_by_cycling_rule`,
`abusive_share_lower_bound` and `labels_from_classifier`.

**Money.** Every amount is a whole number of **Ugandan shillings (UGX)**, with no
decimals. On screen amounts are written like `UGX 1,500,000` (one formatter,
`src\money.py`, set by the `currency` section of `config.yaml`). In the flagged-borrowers
download the money columns carry the currency in their name (`monthly_income_ugx`,
`total_owed_ugx`). The import templates and the database keep the plain column names
(`monthly_income`, `principal`, `amount_outstanding`, `amount`), and say on the
Instructions sheet and on each money header that the amounts are UGX.

**Seen on screen with the default dataset:** 293 high, 881 medium and 3,826 low
borrowers; 22.8% of messages labelled abusive; 395 borrowers both flagged and
harassed. Note that **108 borrowers in the low band received 3 or more abusive
messages**. Their debt looks manageable but their messages do not. They are not
in the "flagged and harassed" number, so find them on the Borrowers page with
band = low and a minimum of 3 abusive messages.

## Bringing your own data (Phase 4B)

> **Real data is confidential.** When a real dataset is active, every page shows
> **"REAL DATA - <name>. Confidential."** The demo stays exactly as it is, and
> you can switch back to it at any time.

FairLend Watch can hold several **datasets**. **demo** is the synthetic data
(the files in `data\`). Each dataset you import gets its own folder in
`data\datasets\<name>\`, which Git ignores. The **Dataset** box in the sidebar of
every page chooses the active one; the choice is stored in `data\active_dataset.txt`.
The command-line tools follow the same choice, and most of them also take `--dataset <name>`.

### Steps

1. **Get the template.** Open the app, go to the **Data** page, then the
   **Templates** tab, and download the Excel template (or the five CSV
   templates). Each sheet has the exact column names, one shaded example row
   (ids start with `EXAMPLE`; delete it), and dropdowns for fixed lists.
2. **Make borrower codes at each lender.** Never put names, phone numbers or ID
   numbers in `borrower_id`. Each lender runs, on its own computer:
   ```powershell
   python -m src.make_borrower_codes raw_borrowers.csv --column phone --output coded_borrowers.csv
   ```
   It asks twice for a **secret salt**. The salt is hidden while you type, and is
   never stored or printed. Use the **same salt for every lender**, so the same
   person gets the same code everywhere (for example `B-3f9a1c2d4e5b`). Phone
   numbers written `0772 123 456`, `+256 772 123456` or `256772123456` give the
   same code. Keep the salt secret: anyone with it can test whether a known
   number is in the data.
3. **Fill in the five sheets** (`lenders`, `borrowers`, `loans`, `transactions`,
   `messages`). See **Accepted formats** below. Without a time, a message cannot
   count as late-night. `transactions` may be left empty, but then cycling
   cannot be detected.
4. **Import.** On the Data page, open the **Import** tab:
   - Choose **Create a new dataset**, or **Add to an existing real dataset**. Adding to the demo is not allowed.
   - Upload the workbook or the five CSV files.
   - Set the **as-of date**, which is "today" for this data. The default is the latest date found in it.
   - Tick or untick **Dates in my files are day/month/year** (ticked by default).
   - Choose redaction, and look at the **Redaction preview** (up to 20 messages, before and after).
   - Tick the permission box.
   - Press **Validate**, then **Import**.
5. **Switch** to the new dataset in the sidebar, and check the **Data health** tab
   (see below).

### Accepted formats

Field spreadsheets are messy, so the import accepts:

| What | Accepted | Refused |
|------|----------|---------|
| Dates | `2026-08-31`; day/month/year with `/`, `-` or `.` (`31/08/2026`, `31-08-2026`, `31.08.2026`, `1/8/2026`); `2026/08/31`; real Excel date cells | `Aug 1st 2026`, `31/02/2026`, two-digit years |
| Day or month first | "Dates in my files are day/month/year" is ticked by default (Uganda writes the day first). Unticked, a date is read either way round only when one part is above 12; `03/04/2026` is then an error naming the row | |
| Times (`sent_at`) | the date followed by `HH:MM` or `HH:MM:SS` (also `2026-08-25T09:10:00`), or the date alone | `9am`, hours above 23 |
| Amounts | `200000`, `200,000`, `200 000`, `UGX 200,000`, `Ush 200,000`, `200,000/=`, `200,000.00`, `200,000 UGX` | `200k`, `2,00,000`, `1.5`, `$200,000` |
| CSV files | UTF-8 with or without a byte-order mark, or Windows-1252 text; commas, semicolons or tabs between columns (detected from the header line) | |
| Fixed lists | any letter case and extra spaces: ` Active `, `IN_ARREARS`, `In Arrears`, `Third-Party` | values outside the list |
| Region | free text. A blank region is a warning, never an error | |
| Extra columns | ignored, with a notice that lists them | |

The check reports how many dates and amounts were converted and how many cells
were adjusted (spaces, letter case). The day/month choice is stored with the
dataset (`dates_day_first` in its meta table).

### What the import checks

Everything is checked before anything is written. The import is **all or
nothing**: one database transaction, so if there is a single error, nothing is
written. Errors name the sheet or file, the row (the header is row 1) and the
column. **They never repeat the value in the cell**, so an error message cannot
leak a message, an ID number or a borrower code.

- **Errors (block the import):**
  - missing sheets or columns
  - wrong types (not a whole number, not a date)
  - zero or negative amounts
  - values outside the fixed lists
  - repeated ids
  - loans, transactions or messages that point to an unknown borrower, lender or loan
  - an issue date after the due date
  - the template's example rows
- **Warnings (do not block):**
  - a repaid loan with money still outstanding
  - an active or in-arrears loan with nothing outstanding
  - things that happened after the as-of date (joining, issuing, transactions, messages; a future *due* date is normal)
  - messages without a time
  - phone numbers, email addresses, ID numbers or listed names found in message text
  - a blank region
  - missing transactions
- **Adding to an existing dataset:** a borrower code that already exists is
  expected (the same person borrows from several lenders), and the stored
  borrower row is kept. Any other repeated id is an error. A sheet may be left
  with headers only if there is nothing new for it.

After a successful import, the messages are labelled with the local classifier.
**These labels come from a model trained on synthetic text. On real messages
they are unreliable until a person has checked a sample.** Every page says so
while a real dataset is active.

### Privacy rules

- Import only data you have **permission** to use. The import refuses to run
  unless you confirm: *"I have permission to use this data and have removed names
  and ID numbers."*
- **Redaction** (next section) is on by default. With it on, the original text
  is never written anywhere: it is replaced before it reaches the database.
- Errors, warnings and notes never repeat a cell's value.
- Real data never leaves this computer. Nothing here uses the network. Real data
  must never be sent to the Gemini free tier.
- Real datasets have no answer labels, so `evaluate_overlap`,
  `evaluate_classifier` and `evaluate_lenders` print "No answer labels for this
  dataset" and stop. Use the **Review** page instead (see below).

### Redaction

With redaction on, message text is changed on import, in this order:

| Token | What is replaced | Setting (`privacy` in `config.yaml`) |
|-------|------------------|--------------------------------------|
| `[EMAIL]` | email addresses | `redact_emails` |
| `[ID]` | a run of letters and digits right after a word such as *NIN*, *ID number*, *ID no* or *national ID* (it must contain a digit, so "ID no longer valid" is kept); and the Ugandan national ID number (NIN) anywhere: `CM` or `CF` followed by 11 or 12 letters/digits, any letter case, spaces or dashes allowed between groups, at least 5 digits | `redact_ids`, `id_keywords`, `id_patterns`, `id_min_digits` |
| `[PHONE]` | Ugandan mobile numbers (`0772 123 456`, `+256 772 123456`, `256772123456`) and any run of 9 or more digits | `redact_phones`, `phone_min_digits` |
| `[NAME]` | every name in `data\redaction_names.txt` (one name per line; lines starting with `#` are skipped), as whole words in any letter case | `redact_names`, `name_list_file` |

**About the NIN format.** It is confirmed that a NIN starts with `CM` or `CF`.
The length is **not** confirmed: guides disagree (13 or 14 characters) and no
official NIRA specification was found, so both lengths are accepted. See the
comment in `config.yaml`.

**Names cannot be detected automatically.** Only names in the name list are
removed. The list is personal data: it is in `.gitignore`, so never share it. To
help you build it, the Import tab has a **Possible names** box after Validate.
It lists the most frequent capitalised words that are not at the start of a
sentence, not a lender's name and not in a stop list
(`privacy.possible_names.stop_words`). Most will not be names and many names will
be missing; a person decides.

The **Redaction preview** on the Import tab shows up to 20 messages as uploaded
and as they would be stored (changed ones first), with counts of `[PHONE]`,
`[EMAIL]`, `[ID]` and `[NAME]` over all messages. It is shown on screen only.

## Checking labels on real data

The local classifier is trained on synthetic text. **On real messages its labels
are unreliable until a person has checked a sample.** The **Review** page
(`pages/6_Review.py`) is for that:

1. Type your **initials or a code** (a name is never needed).
2. Choose a batch:
   - **Random check**: a seeded random sample of messages nobody has reviewed
     yet. This is the only fair measure of accuracy. Do it first.
   - **Hard cases**: half the messages the model is least sure about, half
     spread across lenders and predicted classes. Good for retraining, but it
     makes the model look worse than it is, so it never counts toward accuracy.
3. Read each message and press one of the four class buttons, or **Not sure /
   skip** (a skipped message is not stored and may come up again). The model's
   guess is hidden until you have chosen
   (`classifier.review.show_prediction_before_label: false`), so it cannot
   anchor you.
4. The **Measured accuracy** box compares the current model with your
   random-check labels, for example *"On 80 randomly checked messages the model
   was right 61% of the time, 95% range 50-71%"*, with recall per class. It
   reports nothing below 20 random-check labels (`min_for_accuracy`), because the
   range would be too wide to mean anything.

One caution about the random check: it draws only from messages nobody has
reviewed. If you review hard cases first, those messages can no longer be drawn,
which tilts the random sample slightly toward easier messages. Do the random
check before the hard cases.

Your labels are stored in the dataset's own `predictions.db`, in the table
`human_labels`. They are a person's judgement, not answer labels. **A human
label replaces the model's label everywhere**: the lender comparison, the
borrower harassment counts, the Overview and the exports. The Overview and
Lenders pages say what share of labels a person has checked.

**Retrain** becomes possible with at least 60 human labels and at least 5 of each
class (`min_reviewed_to_retrain`, `min_per_class`); until then the page says
exactly what is missing. Retraining:
- trains on your labels (weight 1) plus, if `include_demo_in_retrain` is on, the
  demo's synthetic dev messages at `demo_weight` (0.3) each. **Note:** the demo
  has far more messages than you will have labels, so at 0.3 the demo still
  carries most of the training weight; the report shows the share. If the demo
  has been deleted, only your labels are used, and the report says so.
- checks itself with stratified cross-validation on **your labels only**. It
  reports macro-F1 and recall per class with the number of labels behind each,
  and warns below 200 labels.
- saves the model as `dataset_model.joblib` in the dataset's folder. The demo's
  model (`data\local_model.joblib`) is never overwritten, and the demo cannot be
  retrained. From then on, labelling this dataset (on import, or with
  `python -m src.classify_messages --dataset <name>`) uses its own model.
- re-labels the dataset and reports how many model labels changed and how the
  class shares moved.

**Export reviewed labels** downloads them as CSV. The first line is a `#`
notice; the columns include the model's current label and the message text as
stored (already redacted if redaction was on).

### Managing datasets (Data page, Datasets tab)

- **Switch:** choose a dataset in the sidebar or on the Datasets tab.
- **Delete:** you must type the dataset's name. The active dataset cannot be
  deleted; switch first. Deleting the **demo** needs an extra tick, and is
  refused until the trained classifier has been saved (`data\local_model.joblib`),
  because the classifier is trained on the demo's text. There is a button to
  train and save it.
- **Restore demo:** rebuilds the synthetic demo with the generator and labels it
  (15 to 35 seconds). Real datasets are not touched. `python -m src.build_all`
  also always rebuilds the demo, whichever dataset is active.

### Data health (Data page)

For the active dataset, this shows, per lender:
- loans, messages and distinct borrowers
- the date range
- the share of loans with transaction records
- whether it has enough messages to be ranked

It also shows how many borrowers appear at two or more lenders. **If this is zero
or tiny, the overlap detector has nothing to find: check that every lender used
the same borrower codes.**

From the command line:

```powershell
python -m src.datasets --list                 # datasets, * marks the active one
python -m src.datasets --use demo             # switch
python -m src.overlap --dataset demo          # most commands also take --dataset
```

## Giving the demo (Phase 5.2)

### Run order

```powershell
.\dev.ps1 -Rebuild       # only if the demo data is missing or changed (15 to 35 seconds)
.\dev.ps1 -Preflight     # every check must say PASS; exit code 0
.\dev.ps1 -Present       # the dashboard in presentation mode
```

Then open the **Guided Demo** page and follow `docs\DEMO_SCRIPT.md` (5 minutes, with
timings, what to click, what to say, three caveats to say out loud, and twelve hard
questions with short, true answers). Its numbers come from the synthetic demo.

`dev.ps1` is new in this phase (there was none before). Its switches are `-Install`
(create `.venv` if needed and install `requirements-dev.txt`), `-Rebuild`, `-Test`, `-Preflight`
and `-Present`. They can be combined and run in that order. Without a switch, or with
`-Present`, it starts the dashboard.

### Presentation mode

Presentation mode makes sure real data can never appear on a projector by accident:
- The app uses **only the demo dataset**, whatever `data\active_dataset.txt` says. It
  never reads that file and never lists or opens a real dataset folder.
- The dataset switcher is replaced by a **Presentation mode** tag in the sidebar.
- The **Data** page (import, delete, restore) and the **Review** page are switched off,
  with a short message.

Turn it on for one run with `.\dev.ps1 -Present` (it sets `FAIRLEND_PRESENT=1`), or always
with `app.presentation_mode: true` in `config.yaml`. The environment variable wins over the
setting: `FAIRLEND_PRESENT=0` turns it off even when the config says true.

### The Guided Demo page

`pages\0_Guided_Demo.py` comes first in the page menu, under the Overview. Streamlit
always lists the main script first and sorts the pages in `pages\` by their number
prefix. It shows six numbered steps, each with one sentence to say and a button that
opens the Borrowers or Lenders page already showing that case. The button passes the
case in session state and in the address (`?borrower=B01767`, `?lender=L08`), so a
bookmarked link opens the case too. The page then lets you choose freely again.

The cases come from `featured_cases()` in `src\dashboard_data.py`. They are picked **by
rules from computed signals only** (never from answer labels), with thresholds in the
`demo` section of `config.yaml`. Ties go to the lowest id.
1. The highest-scoring high-band borrower.
2. A borrower placed in medium only by the cycling rule (the most cycling events).
3. "Many lenders, little debt": at least 4 open lenders, debt under 0.5 times monthly
   income, and not in the high band.
4. The borrower with the most abusive messages who also had a late-night or
   third-party message.
5. The unranked lender with the fewest messages, and its "too few messages" reason.
6. The top-ranked lender.

If a rule finds nobody, that step is left out and the page says why. On a real dataset
the page asks you to switch to the demo.

### Preflight

`python -m src.preflight` (or `.\dev.ps1 -Preflight`) prints PASS or FAIL per check and a
summary line. It exits with 0 when every check passes and 1 otherwise. It checks:
- `config.yaml` is valid.
- The demo exists and matches the fingerprint in its manifest.
- The demo's labels are fresh and complete.
- Every page boots in presentation mode with no exception.
- Presentation mode hides a temporary real dataset that it sets up as the active one.
- The logo files exist.
- `.env` is listed in `.gitignore`, no page names it, and Streamlit's static file serving is off.

It never opens `.env`. It takes about 20 seconds.

### When something goes wrong

Every page runs inside a small wrapper (`guarded()` in `src\dashboard_ui.py`). An
unexpected error shows **"Something went wrong on this page (error code FW-XXXXXX)"**
instead of a traceback. One line goes to `data\logs\app.log`: the time, the code, the
page, the exception type and the code locations (file, line, function). The log never
holds the error message, values or source lines, because those can contain data. The
log is git-ignored and rotates at 2 MB with 3 old files (`app.log_*` in `config.yaml`).

Odd data gets a plain message, not a traceback. This covers:
- an empty dataset
- a damaged or zero-byte database file
- files deleted by hand
- stale labels
- a lender with no loans or no messages, and a borrower with no loans
- one lender only, all loans repaid, all messages in one class, no abusive messages
- very long, emoji or non-Latin messages
- dates after the as-of date

**Ties in the lender ranking** are broken in a fixed, documented order: the lower end of
the interval (highest first), then the abusive share (highest first), then the lender id
(A to Z).

### Speed (20,000 borrowers)

Measured on a 20,000-borrower demo-style world (107,401 messages, 44,857 loans) on this
laptop. `load_all` took 5.1 s before this phase and 3.1 to 3.8 s after: pandas' Arrow-string
`isin` between two large columns was 30 times slower than on plain object columns. See
`CHANGES.md` for the page timings.

## A second opinion from Gemini (Phase 3B)

`python -m src.gemini_check` asks Google's Gemini to label the demo's held-out
**synthetic test messages**, and compares its answers with the truth and with the local
classifier. It is an outside check of the local model. It is **not** used in the app,
**not** used for training, and **never** run on real data.

- **Synthetic only.** It refuses to run unless the dataset is the demo, its own meta table
  says `synthetic = 'true'`, and every selected message is in the `test` split. Dev,
  reserve and real messages are never sent.
- **The key** is read from the `GEMINI_API_KEY` environment variable only. Nothing in the
  project opens `.env`. The key is never printed, logged, written to a file or put in a
  URL, and errors give only the error type and status code.
- **What is sent.** Lender names are masked first. Only distinct texts are sent: 400 test
  messages give 395 distinct texts, because amounts, dates and typos differ even within one
  of the 16 phrasings. They go in batches of 20, so about 20 calls.
- **Limits.**
  - At least `delay_seconds` (7 s) and `60 / requests_per_minute` between calls.
  - Exponential backoff on 429 and 5xx (5, 10, 20, 40 s; `max_retries` 4).
  - A hard cap of `max_calls` (40) calls per run; retries count.
- **Resumable.** Valid answers are cached in `data\gemini_cache.json` (labels only, keyed
  by a hash of prompt version, model and text). A stopped run continues where it left off,
  and a cached text is never sent again. An invalid reply counts as "no answer". It is
  never guessed and is asked again next time.
- **Output.**
  - `data\gemini_check_report.csv`: one row per phrasing, with truth, the local model,
    Gemini and one example text.
  - `data\gemini_check_summary.json`: counts only.
  - A printed summary: agreement rates, the phrasings where the two models disagree, and
    both confusion matrices.
- **About page.** If the summary file exists, the About page shows it, read-only. It is
  **hidden in presentation mode**, because the demo script does not cover it.
- Settings are in `classifier.gemini` in `config.yaml`. **Check the model name** there
  before running: it was set from memory and could not be checked online.

**This is a second opinion on synthetic text, not proof of real-world accuracy.**

To run it (the key is typed into this PowerShell session only; it is not saved anywhere):

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt       # once: installs google-genai and pytest
$env:GEMINI_API_KEY = Read-Host "Paste key (will not be saved)"
python -m src.gemini_check --dataset demo
Remove-Item Env:GEMINI_API_KEY            # forget the key when done
```

## Look and feel (Phase 8C)

- **Light theme by default** (`[theme] base = "light"` in `.streamlit/config.toml`). Viewers
  can still switch to dark in Settings.
- **Logo per theme:** dark text (`fairlend-watch-logo-light.svg`) on a light theme, pale text
  (`fairlend-watch-logo-dark.svg`) on a dark theme. When the theme cannot be read, the
  light-theme logo is used. Streamlit can misreport the theme on a session's very first run
  and right after a theme switch; the logo corrects itself on the next interaction.
- **Charts read on both themes:** the bars and the orange confidence-interval line keep at
  least 3:1 contrast on white and on the dark background, and labels follow the theme.
- **Money tiles never get cut off:** large amounts use a short form (`UGX 259.8M`), and the
  exact amount is in the tile's help (the `?` next to it). Tables and downloads keep exact
  amounts.

## Try a message (Phase 8A)

At the bottom of the **Lenders** page you can type one message and see the class the
local model would give it, with its probability for each of the four classes. It uses
the active dataset's own retrained model if there is one, otherwise the saved model
trained on the demo's synthetic text. Lender names are masked exactly as in training.
What you type is **not stored, not logged and not added to any dataset**: the box is
emptied as soon as the message is labelled. The box is hidden in presentation mode.
A label is a prompt for a human to look, never a verdict.

## Getting the code and rebuilding the demo

The repository holds code, configuration, documents, tests and logos only. **No data is
committed**: everything under `data\` is either rebuilt from `config.yaml` and the seed,
or is real and confidential (see `.gitignore`). On a fresh clone:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # the app (requirements.txt) plus pytest and google-genai
python -m src.build_all        # rebuilds the demo dataset, labels, model, scores and comparison
python -m src.preflight        # every check must say PASS
streamlit run app.py --server.address localhost
```

**Two requirements files.** `requirements.txt` is what the running app needs (Streamlit
Community Cloud installs exactly this; every version is pinned and checked on Python 3.12).
`requirements-dev.txt` adds `pytest` and `google-genai` for the tests and the offline Gemini
check. `.\dev.ps1 -Install` installs the dev file.

## Deploying to Streamlit Community Cloud

The cloud app runs in **presentation mode**: the synthetic demo only, the Data and Review
pages switched off, no real data, no Gemini key and no network calls. A fresh server has an
empty `data\` folder and no shell, so **the app builds the demo itself on first start**. The
first visitor sees "Preparing the demo: about 1 minute(s), first start only" with the real
steps (generate the data, train the classifier under the server's scikit-learn, check). Anyone
else who arrives meanwhile waits for the same build; it runs only once. The demo is rebuilt
automatically if it is ever missing or stale. On this laptop the build takes about 14 seconds
and the first page appears after about 27 seconds, with a peak of about 310 MB of memory; a
cloud server may be slower.

Fill in the "Deploy an app" form like this:

| Field | Value |
|-------|-------|
| Repository / app URL | `https://github.com/Emmanuel676/Lawkennethmugir256/blob/main/app.py` |
| Branch | `main` |
| Main file path | `app.py` |
| Python version (Advanced settings) | `3.12` |
| Secrets (Advanced settings) | exactly one line: `FAIRLEND_PRESENT = "1"` |

- Put **nothing else** in Secrets: no Gemini key, no real data.
- Before anyone else opens the link, use the app's **Share** settings to restrict who can view
  it, if your workspace offers that.
- If the first start shows "The demo could not be prepared (error code FW-...)", reboot the app
  from its menu; the code is in the app log.
- `.streamlit/config.toml` keeps usage statistics off and holds no secrets. It does **not** set
  the listening address, so Community Cloud can choose its own. Local runs stay on this
  computer because `.\dev.ps1` (every switch that starts the dashboard, including `-Present`)
  and the commands in this README pass `--server.address localhost`. If you start Streamlit
  yourself, add that flag too: without it Streamlit listens on every network interface.

## License

**Not decided yet.** Until a license is chosen, nobody else has the right to use, copy
or change this code. See the question in `CHANGES.md` (Phase 8A).

## Decisions made in Phase 1 (please confirm)

1. **Two database files instead of one.** The PRD asks for a single database
   (FR-D5) and also for labels kept apart from detection code (FR-D3). Two
   files satisfies the second properly; one command still builds both.
2. **No Faker library.** The data has no personal names or phone numbers, so
   numpy is enough and there is one dependency fewer.
3. **Column name `txn_date`** instead of `date` in the transactions table, to
   avoid clashing with the SQL word.

## Not done yet

- The demo itself (Phase 6): rehearsal and the one-page write-up.

## Ethics

This tool is meant to support a human analyst, never to make an enforcement
decision. Real borrower data must not be used without legal clearance, and must
never be sent to the Gemini free tier, where Google may use submitted content to
improve its products.
