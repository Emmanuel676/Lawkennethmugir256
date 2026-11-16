# FairLend Watch web interface v2 (Phases 12A to 14)

A web interface built in JavaScript (Next.js + TypeScript + Tailwind + Recharts) on top of the existing Python
engine. It shows **the same numbers as the Streamlit app**, because every figure comes from the code in `src/`
through a small JSON API. No detection logic, threshold or demo data changed. The Streamlit app (`.\dev.ps1`)
still works as before and stays as the fallback.

* **12A:** the read-only pages (Overview, Borrowers, Lenders, Repayments).
* **12B:** sign-in with three roles, shared datasets that persist, and the Data import page.
* **12C:** the Guided demo, Export, About and Review labels pages; the owed amounts split on Repayments; browser
  tests with an accessibility check; a deployment recipe (`docs/DEPLOY_V2.md`).

* **13:** neutral wording ("Demonstration data" everywhere); imports need no special endings on lender names or messages;
  Postgres storage for hosts with no permanent disk (`DATABASE_URL`); deployment files for Render and Vercel
  (`render.yaml`, `web/vercel.json`, `docs/DEPLOY_FREE.md`).

* **14:**
  * a public landing page at `/`, with the dashboard Overview moved to `/overview`;
  * Request access with Admin approval;
  * a waking-up screen for sleeping free hosts, and a first-visit guide;
  * shadcn/ui components, Lucide icons and restrained Motion animation.

With 12C the web app can replace Streamlit for presentations.

Demonstration data. A flag is a prompt for a human to look, not a verdict.

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

Open http://localhost:3000: the landing page. **Explore the demo** opens the dashboard at http://localhost:3000/overview. The built-in demo is open without signing in. Stop either window with Ctrl+C. While
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

* Run both windows (step 1) and open http://localhost:3000/overview **signed out** (http://localhost:3000 is the landing page; start there if you want to show it). Signed out, the app shows the demo only,
  and the trust strip reads "Demonstration data. A flag is a prompt for a human to look, not a verdict."
* Open **Guided demo** (sidebar, under Present; on a phone, **More**) in a second tab.

| Time | Click | Say |
|---|---|---|
| 0:00-0:40 | **Overview** | "FairLend Watch gives a regulator a view **across** lenders that no single lender has. Three things up front: **this is demonstration data**; **the accuracy numbers are optimistic** because the data was built to be separable; and **a person decides**. Of 5,000 made-up borrowers, 280 are in the high band and 863 in medium. 22.8% of the 26,780 collection messages were labelled abusive." |
| 0:40-1:25 | Guided demo, step 1: **Open on the Borrowers page** | "Borrower B01767 scores 89 of 100: 5 open lenders and debt of 3.1 times monthly income. No single lender could see this. Every point is explained in the score breakdown." |
| 1:25-2:05 | Step 2 | "B00030 scores only 28, but took 5 new loans within days of repaying others: borrowing to repay. A rule lifts repeated cycling to medium so a person looks, and the page says the rule did it." |
| 2:05-2:40 | Step 3 | "B00550 has 5 open lenders but owes only 0.23 times monthly income, and stays in medium. The score is not just a lender count." |
| 2:40-3:20 | Step 4 | "B02339 received 81 collection messages, and 48 of them were labelled abusive. Of those 48, 11 were sent late at night and 14 were sent to other people instead of the borrower. The labels are a model's guesses about the wording; late night and third party are facts of the message." |
| 3:20-3:55 | Step 5 (opens Lenders) | "Kestrel Instant Cash sent only 6 messages: too few to rank. Its interval runs from 0% to 39%, so a small lender cannot top or escape the list by luck." |
| 3:55-4:35 | Step 6 (opens Lenders) | "Redstone Loans ranks first: 45% of its 2,094 messages were labelled abusive, and even the low end of the 95% interval is 43%. A rank means 'read these messages', not 'this lender broke the law'." |
| 4:35-5:00 | **About** | "A flag is a prompt, not a verdict. What we have not proven: this is demonstration data, built to be separable, so accuracy on other data will be lower. Any other data needs legal clearance, redaction (built in), and a person checking a sample of labels on the Review labels page." |

Optional, 45 seconds: **Repayments**.

* "29.2% of loans were repaid on time, 22.8% inside the 3 grace days, and 12.5% are not being paid."
* Point at **What is owed on unpaid loans**: "UGX 359.4M is past due, and UGX 849.1M is not yet due. The total is
  not arrears."
* Then **Export**: "885 borrowers in the follow-up list, downloadable as CSV with the notice on the first
  line."

Optional, about 2 minutes, signed in as an Importer: the live import of a sample pack (section
"Import a sample pack" below). Say: "85 borrower codes were already known; 85 of 387 borrowers appear
at two lenders."

The guided demo's cases are chosen by fixed rules from the computed scores and labels (the same rules as the
Streamlit Guided Demo). `docs/DEMO_SCRIPT.md` keeps the Streamlit version of the script and the hard questions.

### 4. Screenshots of every page

All retaken in Phase 14 with the current wording, in `docs/ui_v2_screens/`:

| Page | Screenshot |
|---|---|
| Landing page | `14_landing_desktop.png` (full page), `14_landing_desktop_dark.png`, `14_landing_phone.png` |
| Request access | `14_request_access.png` |
| Overview | `14_overview_first_visit.png` (with the first-visit guide); imported dataset, dark theme: `14_overview_imported_dark.png`; phone: `14_phone_overview.png` |
| Borrowers | `14_borrowers.png` |
| One borrower | `14_borrower_detail.png` (B02339, with the messages) |
| Lenders | `14_lenders.png` (opened on Redstone Loans from the guided demo) |
| Repayments | `14_repayments.png` (with the past-due / not-yet-due split) |
| Guided demo | `14_guided_demo.png` |
| Export | `14_export.png` |
| About | `14_about.png` |
| Sign in | `14_signin.png` |
| Datasets (Admin) | `14_datasets_admin.png` |
| Import data (Importer) | `14_import_importer.png` |
| Review labels | `14_review_imported.png` (an imported dataset, a batch started) |
| Users, pending requests (Admin) | `14_users_pending_requests.png` |
| Audit log (Admin) | `14_audit_admin.png` |
| Waking-up screen | `14_waking_up.png` (shown when the API does not answer quickly, for example on a sleeping free host) |
| Phone menu | `14_phone_more_menu.png` |

### 5. Test totals (Phase 14, run in batches)

This computer runs low on memory, so the Python suite is run **in batches of test files, one process at a time, with
no web or API server running** (checked before and after every batch). The batches on 2026-11-16:

| Batch | Files | Passed | Failed |
|---|---|---:|---:|
| 1 | test_api, test_api_12c, test_api_auth, test_wording, test_api_access | 84 | 0 |
| 2 | test_api_datasets, test_api_postgres (with a throwaway local Postgres) | 26 | 0 |
| 3 | test_bootstrap, test_branding_and_paths, test_classifier_local, test_dashboard_data | 130 | 0 |
| 4 | test_dashboard_pages, test_data_page, test_datasets, test_edge_cases | 82 | 0 |
| 5 | test_gemini_check, test_generate_data, test_import_data, test_import_robustness | 185 | 0 |
| 6 | test_lender_comparison, test_money, test_overlap, test_phase9a_rules, test_presentation_and_demo | 147 | 0 |
| 7 | test_redaction, test_repayments, test_review, test_review_page | 76 | 0 |
| 8 | test_sample_pack | 59 | 0 |
| 9 | test_shipped_dataset, test_team_access, test_theme_and_tiles, test_try_message, test_first_start_phase11 | 93 | 0 |
| **Total** | 34 files | **882** | **0** |

After the last edits (the Users page buttons and the new README), the batches that cover them were run again:

* batches 4 and 6: 82 and 147 passed, 0 failed;
* batch 1: 83 passed. Its one Postgres migration test could not run because the throwaway test database had been
  stopped for low memory; that test passed in the full run above.

The Postgres tests (9 in test_api_postgres, 1 migration test in test_api_access) run only when
`FAIRLEND_TEST_DATABASE_URL` points at a test database; without it they are skipped.

**Browser tests:** 13 passed in about 3 minutes.

* The landing page at phone and desktop width, in both themes.
* Keyboard paths through sign-in, Request access with Admin approval, import and delete.
* Phone width on 11 pages, and the first-visit guide.
* The accessibility check (WCAG 2 A and AA) found no serious or critical problems on any page visited, in both
  themes.

The web type check and production build pass.

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

## Request access (Phase 14)

Anyone can ask for an account on the public **Request access** page (`/request-access`, linked from the landing page
and the sign-in page). The form asks for:

* full name, email and organisation;
* the type of user: Regulator or consumer body, Lender, Researcher or student, or Other;
* a short reason;
* a password, twice, with the usual rules.

A note on the form says an administrator will see these details and that the account stays inactive until approved.

* **Submitting creates a pending account that cannot sign in.** The confirmation is the same whether or not the email
  already has an account, so the form cannot be used to find out who has one.
* **Signing in before approval:** with the right password, the person is told the account is waiting for approval.
  With a wrong password, or for a rejected or disabled account, they see the usual "Email or password not
  recognised."
* **Admin:** **Users** has a **Pending requests** tab with each request's name, organisation, type, reason and date.
  * **Approve as Viewer** or **Approve as Importer**. To make someone an Admin, change their role later in the user list.
  * **Reject** deletes the request.
  * Both are recorded in the audit log, without the password or its hash.
* **Abuse limits:**
  * a hidden honeypot field;
  * at most `FAIRLEND_REQUESTS_PER_HOUR` requests per address per hour (default 5);
  * at most `FAIRLEND_MAX_PENDING` requests waiting at once (default 50);
  * length limits on every field;
  * the same cross-site check as every other change.

  Behind a host's proxies, set `FAIRLEND_PROXY_HOPS` to the number of trusted proxies (2 for Vercel in front of
  Render). Otherwise the connection address is used, which cannot be forged.
* **No email is ever sent**, for requests, approvals or anything else. The pages say "check back later".
* **Storage:** the users table gains `full_name`, `organisation`, `user_type`, `reason`, `status` and `requested_at`.
  On both SQLite and Postgres they are added in place at start-up, and existing users become active
  (tests/test_api_access.py checks this from the Phase 13 schema).

## Import a sample pack

1. Build the sample packs once: `.\dev.ps1 -SamplePack` (writes `sample_pack\`, git-ignored).
2. Sign in as an Importer or Admin and open **Import data**.
3. **Step 1** offers the templates (one Excel workbook, or five CSV files in a zip), from the same template builder
   as the Streamlit Data page.
4. **Step 2:** choose *Create a new dataset*. Name it `Sample baseline`; where the data came from:
   `sample pack`.
5. **Step 3:** choose *Five CSV files*, select the five files in `sample_pack\baseline\lender_A`, then press
   **Check the files**.
   * Expect "No errors found": 1 lender, 244 borrowers, 666 loans, 20,144 transactions and 1,291 messages.
6. **Step 4:** tick the permission box and press **Import**.
   * The message reads **"Imported. Shown as demonstration data."**
   * It points to the **Review labels** page.
7. Add lender B: choose *Add another lender's files to an imported dataset*, pick `Sample baseline`,
   select `sample_pack\baseline\lender_B`, then Check and Import.
   * The import reports **85 borrower codes already known**.
   * The dataset has **85 of 387** borrowers at two lenders.
   * Overview shows 0 high, 7 medium and 380 low, the same as the Streamlit import.

**Every upload goes through the upload check first** (Phase 13, `api/upload_check.py`, built from the checks of
the earlier gate in `src/team_access.py`):

* no phone-, ID- or email-like text in lender names or messages;
* at most 25 MB and 100,000 rows per file.

Lender names and messages need no special endings. The check runs in memory, and a refused upload is never
validated, stored or written anywhere. Then the existing importer validates the files and lists errors with row
numbers, never cell values. Nothing is saved until there are no errors. Message text is always redacted, and every
import, refusal and failure is recorded in the audit log.

Every imported dataset is labelled **"Demonstration data"** in the dataset list, the switcher, the trust strip and
the first line of every export. No marker is added to rows or lenders.

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

**With `DATABASE_URL` set** (hosts with no permanent disk, `docs/DEPLOY_FREE.md`), the same things live in Postgres
instead: the tables `users`, `sessions`, `datasets` and `audit`, and each imported dataset's files as blobs in
`dataset_files`. Those files are cached to a temporary folder on first use and uploaded again after an import or a
saved review label. Without `DATABASE_URL` nothing changes: SQLite and local folders, as below.

The built-in demo stays in `data\` as always, and nothing in the web API writes to it. To start the web data from
scratch, stop the API and delete `data\web\`. The demo is not affected.

## Settings (environment variables, all optional)

| Variable | Default | What it does |
|---|---|---|
| `FAIRLEND_WEB_ORIGINS` | `http://localhost:3000` | Front-end origins. CORS allows them, and every state-changing call must come from one (cross-site protection). Comma-separated. |
| `FAIRLEND_API_HOST` / `FAIRLEND_API_PORT` | `127.0.0.1` / `8000` | Where the API listens. The default is this computer only. |
| `FAIRLEND_API_URL` | `http://127.0.0.1:8000` | Where the web app forwards `/api/...`. **Read when the web app is built** (`npm run build`) or when `npm run dev` starts. |
| `FAIRLEND_WEB_DATA` | `data\web` | Users, sessions, dataset metadata, audit log, imported datasets. |
| `DATABASE_URL` | not set | Postgres for users, sessions, the audit log, the dataset list and the imported datasets' files (Phase 13). Read only from the environment and never printed. When set, `FAIRLEND_SESSION_SECRET` is required and cookies are always Secure. |
| `FAIRLEND_PROXY_HOPS` | `0` | Trusted proxies in front of the API, for the visitor's address in `X-Forwarded-For` (Vercel + Render: `2`). |
| `FAIRLEND_REQUESTS_PER_HOUR` | `5` | Access requests accepted per address per rolling hour. |
| `FAIRLEND_MAX_PENDING` | `50` | Most access requests waiting for an Admin at once. |
| `FAIRLEND_CACHE_DIR` | a temporary folder | Where Postgres-stored datasets are cached as files on first use. |
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

**First visit (Phase 14):**

* The landing page at `/` explains the tool in plain words, with a live preview read from the API. Signed-in users
  go straight to `/overview`.
* If the API does not answer within a few seconds, for example a free host waking up, a full-page "The service is
  waking up" message appears. It retries by itself and opens the app when the API is ready.
* `/overview` shows a short first-visit guide. Dismissing it is remembered in the browser.
* Every main page has a one-line "What you are looking at".

**Design (Phase 14):**

* shadcn/ui components (Radix) for buttons, inputs, selects, dialogs, menus, tabs, tooltips and toasts, themed with
  the brand tokens.
* Lucide icons.
* Motion for the landing page's fade-and-rise on scroll.
* Number tiles count up once.
* Page changes fade in with CSS.
* No animation hides content that is already on screen, and every animation stops when the system asks for reduced
  motion.
* Fonts, icons and illustrations are bundled; nothing is downloaded from other sites at run time.

**Bundle size** (JavaScript a first-time visitor downloads, gzip, measured on a production build):

| Page | Phase 13: needed to show the page | Phase 14: needed to show the page | Phase 14: everything within 4 s |
|---|---:|---:|---:|
| Landing page `/` | not there | 236 KB | 299 KB |
| `/overview` (was `/` before Phase 14) | 258 KB | 198 KB | 281 KB |
| `/borrowers` | 152 KB | 196 KB | 281 KB |
| `/signin` | 150 KB | 195 KB | 303 KB |

* The chart library now loads only on pages with charts, after the page has rendered.
* The signed-in menus, toasts and Motion's animation features also load on demand.
* The roughly 45 KB more on the simpler pages is the shared shadcn/ui foundation: the tooltip used for term
  explanations, the class helpers and the icons.

**Pages:**

* Public: the **landing page** (`/`) and **Request access** (`/request-access`).
* For the chosen dataset: **Overview** (`/overview`), **Borrowers** (list and one borrower), **Lenders**, **Repayments**.
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

* **One API instance at a time.** Locally: SQLite and local folders. Hosted: Postgres (`DATABASE_URL`), with each
  instance caching dataset files in its own temporary folder, so run one instance only. Imports use an in-process
  lock.
* **No HTTPS of its own.** Put it behind an HTTPS reverse proxy and set `FAIRLEND_COOKIE_SECURE=1` first
  (`docs/DEPLOY_V2.md`).
* **No multi-factor sign-in, no self-service password change, no reset email.** The login throttle is per account,
  not per address.
* **Imports run inside the web call.** That takes seconds for a sample pack; a job queue would be better at scale.
* **Review labels does not retrain the model** (the Streamlit Review page can). Every saved label reloads that
  dataset once.
* **Not covered yet:** no audit-log export, no retention rule, no built-in backups of `data\web\`.
* **The upload check only refuses phone-, ID- and email-like text.** It says nothing else about where data came from.
