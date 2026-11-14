# FairLend Watch web interface v2 (Phases 12A, 12B and 12C)

A web interface built in JavaScript (Next.js + TypeScript + Tailwind + Recharts) on top of the existing Python
engine. It shows **the same numbers as the Streamlit app**, because every figure comes from the code in `src/`
through a small JSON API. No detection logic, threshold or demo data changed. The Streamlit app (`.\dev.ps1`)
still works as before and stays as the fallback.

* **12A:** the read-only pages (Overview, Borrowers, Lenders, Repayments).
* **12B:** sign-in with three roles, shared datasets that persist, and the Data import page.
* **12C:** the Guided demo, Export, About and Review labels pages; the owed amounts split on Repayments; browser
  tests with an accessibility check; a deployment recipe (`docs/DEPLOY_V2.md`).

With 12C the web app can replace Streamlit for presentations.

Synthetic data. A flag is a prompt for a human to look, not a verdict.

---

## Ready checklist

### 1. Run it (Windows, two commands)

One-time setup, from the project folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
npm --prefix web install
npm --prefix web run build
```

Then, in **two** PowerShell windows, both opened in the project folder:

```powershell
# Window 1: the API (http://127.0.0.1:8000). Builds the demo first if it is missing or stale, then loads it.
.\.venv\Scripts\python.exe -m api
```

```powershell
# Window 2: the web app (http://localhost:3000)
npm --prefix web run start
```

Open http://localhost:3000. The built-in demo is open without signing in. Stop either window with Ctrl+C. While
you change the web code, use `npm --prefix web run dev` instead of `build` and `start`.

The browser only talks to the web app. The web app forwards every `/api/...` call to the API, which keeps the
sign-in cookie first-party. **The forwarding address is fixed when the web app is built** (`FAIRLEND_API_URL`,
default `http://127.0.0.1:8000`). If the API runs elsewhere, set it before `npm --prefix web run build`.

### 2. Create the first Admin

Accounts are created by an Admin only. There is no public sign-up and no password-reset email. Create the first
Admin once, in a third PowerShell window in the project folder:

```powershell
.\.venv\Scripts\python.exe -m api.create_admin
```

It asks for the email, then for the password **twice at a hidden prompt**. The password must be at least 10
characters. It is never accepted as a command argument, never read from a file and never printed or logged. Only
its argon2 hash is stored. Then sign in at http://localhost:3000/signin and add other users on the **Users** page.

### 3. The demo script for the web app (5 minutes)

Before you start, off stage:

* Run both windows (step 1) and open http://localhost:3000 **signed out**. Signed out, the app shows the demo only,
  and the trust strip reads "Synthetic data. A flag is a prompt for a human to look, not a verdict."
* Open **Guided demo** (sidebar, under Present; on a phone, **More**) in a second tab.

| Time | Click | Say |
|---|---|---|
| 0:00-0:40 | **Overview** | "FairLend Watch gives a regulator a view **across** lenders that no single lender has. Three things up front: **this data is synthetic**; **the accuracy numbers are optimistic** because the data was built to be separable; and **a person decides**. Of 5,000 made-up borrowers, 280 are in the high band and 863 in medium. 22.8% of the 26,780 collection messages were labelled abusive." |
| 0:40-1:25 | Guided demo, step 1: **Open on the Borrowers page** | "Borrower B01767 scores 89 of 100: 5 open lenders and debt of 3.1 times monthly income. No single lender could see this. Every point is explained in the score breakdown." |
| 1:25-2:05 | Step 2 | "B00030 scores only 28, but took 5 new loans within days of repaying others: borrowing to repay. A rule lifts repeated cycling to medium so a person looks, and the page says the rule did it." |
| 2:05-2:40 | Step 3 | "B00550 has 5 open lenders but owes only 0.23 times monthly income, and stays in medium. The score is not just a lender count." |
| 2:40-3:20 | Step 4 | "B02339 received 81 collection messages, and 48 of them were labelled abusive. Of those 48, 11 were sent late at night and 14 were sent to other people instead of the borrower. The labels are a model's guesses about the wording; late night and third party are facts of the message." |
| 3:20-3:55 | Step 5 (opens Lenders) | "Kestrel Instant Cash sent only 6 messages: too few to rank. Its interval runs from 0% to 39%, so a small lender cannot top or escape the list by luck." |
| 3:55-4:35 | Step 6 (opens Lenders) | "Redstone Loans ranks first: 45% of its 2,094 messages were labelled abusive, and even the low end of the 95% interval is 43%. A rank means 'read these messages', not 'this lender broke the law'." |
| 4:35-5:00 | **About** | "A flag is a prompt, not a verdict. What we have not proven: these are synthetic messages, so real accuracy will be lower. Real data needs legal clearance, redaction (built in), and a person checking a sample of labels on the Review labels page." |

Optional, 45 seconds: **Repayments**.

* "29.2% of loans were repaid on time, 22.8% inside the 3 grace days, and 12.5% are not being paid."
* Point at **What is owed on unpaid loans**: "UGX 359.4M is past due, and UGX 849.1M is not yet due. The total is
  not arrears."
* Then **Export**: "885 borrowers in the follow-up list, downloadable as CSV with the synthetic notice on the first
  line."

Optional, about 2 minutes, signed in as an Importer: the live import of the synthetic sample pack (section
"Import the synthetic sample pack" below). Say: "85 borrower codes were already known; 85 of 387 borrowers appear
at two lenders."

The guided demo's cases are chosen by fixed rules from the computed scores and labels (the same rules as the
Streamlit Guided Demo). `docs/DEMO_SCRIPT.md` keeps the Streamlit version of the script and the hard questions.

### 4. Screenshots of every page

In `docs/ui_v2_screens/`:

| Page | Screenshot |
|---|---|
| Overview | `12c_overview.png`; the same for an imported dataset in the dark theme: `12c_overview_imported_dark.png` |
| Borrowers | `12c_borrowers.png` |
| One borrower | `12c_borrower_detail.png` (B02339, with the messages) |
| Lenders | `12c_lenders.png` (opened on Redstone Loans from the guided demo) |
| Repayments | `12c_repayments.png` (with the past-due / not-yet-due split); phone: `12c_phone_repayments.png` |
| Guided demo | `12c_guided_demo.png`; phone: `12c_phone_guided_demo.png` |
| Export | `12c_export.png` |
| About | `12c_about.png` |
| Sign in | `12c_signin.png` |
| Datasets (Admin) | `12c_datasets_admin.png` |
| Import data (Importer) | `12c_import_importer.png`; check, refusal and finished import: `12b_import_check_ok.png`, `12b_import_refused.png`, `12b_import_done.png` |
| Review labels | `12c_review_imported.png` (an imported dataset, a batch started); `12c_review_demo.png` (the demo explains why it cannot be reviewed) |
| Users (Admin) | `12c_users_admin.png` |
| Audit log (Admin) | `12c_audit_admin.png` |
| No permission, signed out | `12b_no_permission_viewer.png`, `12b_signed_out_datasets.png` |
| Phone | `12b_phone_datasets_more_menu.png`, `12b_phone_overview_imported.png`, `12b_phone_import.png` |

The earlier `12a`- and `12b`-era files show the same pages before the 12C navigation was added.

### 5. Test totals (Phase 12C, run in batches)

This computer runs low on memory, so the Python suite is run **in batches of test files, one process at a time,
with no API or web server running**. The batches on 2026-11-14:

| Batch | Files | Passed | Failed | Time |
|---|---|---:|---:|---:|
| 1 | test_api, test_api_12c, test_api_auth | 57 | 0 | 69 s |
| 2 | test_api_datasets | 17 | 0 | 64 s |
| 3 | test_bootstrap, test_branding_and_paths, test_classifier_local, test_dashboard_data | 130 | 0 | 91 s |
| 4 | test_dashboard_pages, test_data_page, test_datasets, test_edge_cases | 82 | 0 | 194 s |
| 5 | test_gemini_check, test_generate_data, test_import_data, test_import_robustness | 185 | 0 | 72 s |
| 6 | test_lender_comparison, test_money, test_overlap, test_phase9a_rules, test_presentation_and_demo | 147 | 0 | 61 s |
| 7 | test_redaction, test_repayments, test_review, test_review_page | 76 | 0 | 65 s |
| 8 | test_sample_pack | 59 | 0 | 142 s |
| 9 | test_shipped_dataset, test_team_access, test_theme_and_tiles, test_try_message | 89 | 0 | 46 s |
| **Total (committed test files)** | 30 files | **842** | **0** | about 13 min |
| extra | test_first_start_phase11 (in the folder but not committed) | 4 | 0 | 24 s |

To repeat a batch:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_api.py tests\test_api_12c.py tests\test_api_auth.py
```

**Browser tests** (separate from the Python suite):

* 6 passed in about 1.5 minutes: keyboard sign-in, keyboard import, keyboard delete, phone width, light theme and
  dark theme.
* The accessibility check found no serious or critical problems on any page checked.
* The web type check and production build pass.

### 6. Known limits

See "Not production-grade yet" at the end, and `docs/DEPLOY_V2.md` before anyone reaches the app over a network.

---

## Add users

Signed in as an Admin, open **Users** (sidebar, under Manage; on a phone, **More**).

* **Add a user:** email, role and a first password of at least 10 characters. Give the password to the person
  yourself; nothing is emailed.
* **Roles:** each includes the one before it.
  * **Viewer** reads every dataset.
  * **Importer** is a Viewer who can also add datasets and review labels.
  * **Admin** is an Importer who can also manage users, delete datasets and read the audit log.
* **Change a role, reset a password, disable or enable** a user from the list. A role change, a password reset or
  disabling signs that user out at once. You cannot remove your own Admin role or disable yourself, and the last
  active Admin cannot be demoted.

**Sign-in:**

* After **5 wrong passwords** for one account, sign-in for that account pauses for **10 minutes**.
* Every failure shows only "Email or password not recognised."
* A sign-in lasts 8 hours (`FAIRLEND_SESSION_HOURS`).
* **Sign out** is in the account menu.

## Import the synthetic sample pack

1. Build the sample packs once: `.\dev.ps1 -SamplePack` (writes `sample_pack\`, git-ignored).
2. Sign in as an Importer or Admin and open **Import data**.
3. **Step 1** offers the templates (one Excel workbook, or five CSV files in a zip), from the same template builder
   as the Streamlit Data page.
4. **Step 2:** choose *Create a new dataset*. Name it `SYNTHETIC sample baseline`; where the data came from:
   `synthetic sample pack`.
5. **Step 3:** choose *Five CSV files*, select the five files in `sample_pack\baseline\lender_A`, then press
   **Check the files**.
   * Expect "No errors found": 1 lender, 244 borrowers, 666 loans, 20,144 transactions and 1,291 messages.
6. **Step 4:** tick the permission box and press **Import**.
   * The message is labelled **"Imported dataset. Passed the synthetic-only check."**
   * It points to the **Review labels** page.
7. Add lender B: choose *Add another lender's files to an imported dataset*, pick `SYNTHETIC sample baseline`,
   select `sample_pack\baseline\lender_B`, then Check and Import.
   * The import reports **85 borrower codes already known**.
   * The dataset has **85 of 387** borrowers at two lenders.
   * Overview shows 0 high, 7 medium and 380 low, the same as the Streamlit import.

**Every upload must pass the synthetic-only check first** (the existing gate in `src/team_access.py`):

* lender names end in "(Demo)";
* every message ends in "(SYNTHETIC)";
* no phone-, ID- or email-like text;
* at most 25 MB and 100,000 rows per file.

The check runs in memory. A refused upload is never validated, stored or written anywhere. Then the existing
importer validates the files and lists errors with row numbers, never cell values. Nothing is saved until there are
no errors. Message text is always redacted. Passing the check does **not** prove the data is synthetic, so imported
datasets are labelled "Imported dataset. Passed the synthetic-only check." They are never called synthetic, and they
never show the REAL DATA banner.

## Review labels (Importer and Admin)

**Review labels** checks a sample of the model's message labels on an **imported** dataset. It reuses
`src/review.py`.

* **Random check:** the fair measure of how often the model is right.
* **Hard cases:** low confidence, spread across lenders and labels.
* **Skipped messages** are not stored and may come up again.

Each label a person saves:

* is stored with that dataset, in its own `predictions.db`;
* replaces the model's label on every page;
* is counted as one of the "labels a person has checked";
* shows a **Checked by a person** tag on the borrower page;
* is recorded in the audit log.

The page reports measured accuracy once 20 random checks exist. The checked labels download as CSV, with the notice
on the first line. The demo cannot be changed, so on the demo the page explains this instead.

## Datasets

**Datasets** (any signed-in user) lists the built-in demo first, then every imported dataset, with counts, who
added it and when. The list is shared. **Show this dataset**, or the switcher in the sidebar (under **More** on a
phone), chooses what the data pages show. The demo is the default. An Admin can delete an imported dataset after
typing its exact name. The demo cannot be deleted or changed.

## Export

**Export** offers the same three downloads as Streamlit, each with its notice on the first line:

* flagged borrowers, filtered by band and messages labelled abusive;
* the lender comparison;
* the repayment follow-up list.

The demo's exports are public. An imported dataset's exports need a signed-in Viewer or above.

## Where the data lives

Everything users create is under `data\web\` (git-ignored, like all of `data\`). Set `FAIRLEND_WEB_DATA` to put it
elsewhere.

| Path | What |
|---|---|
| `data\web\app.db` | SQLite: users (argon2 password hashes), sessions (SHA-256 of each token), dataset metadata, audit log |
| `data\web\datasets\<name>\` | one folder per imported dataset: `lending.db`, `predictions.db` (model labels and labels a person has checked), `dataset.json` |
| `data\web\session_secret.txt` | the session-signing secret, generated on first start unless `FAIRLEND_SESSION_SECRET` is set |

The built-in demo stays in `data\` as always, and nothing in the web API writes to it. To start the web data from
scratch, stop the API and delete `data\web\`. The demo is not affected.

## Settings (environment variables, all optional)

| Variable | Default | What it does |
|---|---|---|
| `FAIRLEND_WEB_ORIGINS` | `http://localhost:3000` | Front-end origins. CORS allows them, and every state-changing call must come from one (cross-site protection). Comma-separated. |
| `FAIRLEND_API_HOST` / `FAIRLEND_API_PORT` | `127.0.0.1` / `8000` | Where the API listens. The default is this computer only. |
| `FAIRLEND_API_URL` | `http://127.0.0.1:8000` | Where the web app forwards `/api/...`. **Read when the web app is built** (`npm run build`) or when `npm run dev` starts. |
| `FAIRLEND_WEB_DATA` | `data\web` | Users, sessions, dataset metadata, audit log, imported datasets. |
| `FAIRLEND_SESSION_SECRET` | generated file | Session-signing secret. Never commit it. |
| `FAIRLEND_SESSION_HOURS` | `8` | How long a sign-in lasts. |
| `FAIRLEND_COOKIE_SECURE` | off | Set to `1` when the app is served over HTTPS. |
| `LENDING_MONITOR_CONFIG` | `config.yaml` | Another config file (the same variable the Streamlit app uses). |

Set one for the current PowerShell window only, then start the program in that window:

```powershell
$env:FAIRLEND_SESSION_HOURS = "4"
.\.venv\Scripts\python.exe -m api
```

No settings file is needed, and none is read: there is no `.env` and no API key of any kind.

## How it fits together

```
browser --> web/ (Next.js; forwards /api/*) --> api/ (FastAPI) --> api/data_source.py --> src/ (unchanged engine)
                                                     |                    |
                                     api/accounts.py, api/audit.py   api/store.py (catalog + files)
                                                     \________ data\web\app.db ________/
```

* **Data:**
  * `api/data_source.py` is the single data-source layer: the demo, plus imported datasets loaded with the same
    engine calls.
  * `api/views.py` lays the engine's results out as JSON, including the Guided demo, About and Export.
  * `api/store.py` holds the dataset catalog and the folder storage, behind interfaces.
* **Accounts and access:**
  * `api/accounts.py` and `api/security.py` handle users, roles, sign-in, the throttle and sessions.
  * `api/deps.py` holds the access rule for every endpoint, plus the cross-site check.
  * `api/audit.py` is the audit log.
* **Import and review:** `api/imports.py` wraps the template, gate, validation and import. `api/review.py` wraps
  Review labels.
* **Endpoints:** `api/main.py` (data pages), `api/routes.py` (sign-in, users, datasets, import) and
  `api/routes_12c.py` (guided demo, about, export, review).

### Who can call what

| Endpoint | Anyone | Viewer | Importer | Admin |
|---|:-:|:-:|:-:|:-:|
| `GET /api/health`, `/api/auth/me`; `POST /api/auth/login`, `/api/auth/logout` | yes | yes | yes | yes |
| Data, guided demo, about and export endpoints for the **demo** | yes | yes | yes | yes |
| The same with `?dataset=<imported dataset>` | no | yes | yes | yes |
| `GET /api/datasets`, `/api/datasets/{name}` | no | yes | yes | yes |
| Import (`/api/imports/*`) and Review labels (`/api/review*`, imported datasets only) | no | no | yes | yes |
| Users, audit log, `DELETE /api/datasets/{name}` | no | no | no | yes |

Not signed in gives 401. Signed in without the role gives 403. Every POST, PATCH and DELETE also needs the request
to come from `FAIRLEND_WEB_ORIGINS`, on top of the httpOnly, SameSite=Strict session cookie.

## The web app (web/)

**Pages:**

* For the chosen dataset: **Overview**, **Borrowers** (list and one borrower), **Lenders**, **Repayments**.
* **Present:** **Guided demo**, **Export**, **About**.
* **Sign in**.
* **Manage:** **Datasets** (signed in), **Import data** and **Review labels** (Importer and Admin), **Users** and
  **Audit log** (Admin).

**Layout:** a left sidebar on a desktop. On a phone there is a bottom bar with the four main pages plus **More**
(dataset switcher, Present and Manage pages).

**Friendly states:** signed out, no permission, empty lists, upload refused, validation errors, loading skeletons,
and errors with "Try again".

**Repayments** shows what is owed on unpaid loans as **past due** and **not yet due**, side by side with the total,
so the total is never read as arrears.

**About** describes what the message model labels, in plain words about the wording. It makes no legal judgement:
no label says a lender did something unlawful.

## Tests

```powershell
# Python, in batches (see the table above); the web API tests:
.\.venv\Scripts\python.exe -m pytest -q tests\test_api.py tests\test_api_12c.py tests\test_api_auth.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_datasets.py
# Web:
npm --prefix web run typecheck
npm --prefix web run build
# Browser tests (stop your own API and web servers first; they start their own on ports 8000 and 3100):
npm --prefix web run test:e2e
```

**API tests:**

* **`tests/test_api.py`** checks number parity with Streamlit for the demo.
* **`tests/test_api_auth.py`** checks the role matrix, the throttle, session expiry, cross-site refusal, user
  management and the create-admin prompt.
* **`tests/test_api_datasets.py`** checks the gate and imports, the sample pack (85 already known, 85 of 387), that
  datasets do not leak into each other, and the demo fingerprint.
* **`tests/test_api_12c.py`** checks:
  * the same six guided-demo cases and wording as Streamlit;
  * the B02339 sentence computed from the engine (48, 11, 14);
  * no "lawful" wording in About;
  * exports byte-for-byte equal to the Streamlit files;
  * imported exports need sign-in;
  * the owed split adds up;
  * the import message points to Review labels;
  * Review labels is for Importers on imported datasets only, stored with the dataset, audited and shown as checked.

**Browser tests (`web/e2e/`, Playwright with the installed Chrome and axe-core):**

* One worker, a throwaway data folder, and test accounts with a random password per run.
* The keyboard paths through sign-in, import and delete.
* No sideways scrolling at phone width (390 px) on nine pages.
* An accessibility check (WCAG 2 A and AA) on every page visited, in both themes. It fails on any serious or
  critical problem.

## Not production-grade yet

* **Single process, single machine.** SQLite, local folders and an in-process import lock suit a small team on
  one computer. The `DatasetCatalog` and `DatasetFiles` interfaces are where Postgres or object storage would plug
  in (`docs/DEPLOY_V2.md`, section 8).
* **No HTTPS of its own.** Put it behind an HTTPS reverse proxy and set `FAIRLEND_COOKIE_SECURE=1` first
  (`docs/DEPLOY_V2.md`).
* **No multi-factor sign-in, no self-service password change, no reset email.** The login throttle is per account,
  not per address.
* **Imports run inside the web call.** That takes seconds for a sample pack; a job queue would be better at scale.
* **Review labels does not retrain the model** (the Streamlit Review page can). Every saved label reloads that
  dataset once.
* **Not covered yet:** no audit-log export, no retention rule, no built-in backups of `data\web\`.
* **The synthetic-only check is a guard, not a proof.**
