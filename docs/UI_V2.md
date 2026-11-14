# FairLend Watch web interface v2 (Phase 12A and 12B)

A web interface built in JavaScript (Next.js + TypeScript + Tailwind + Recharts) on top of the existing Python
engine. It shows **the same numbers as the Streamlit app**, because every figure comes from the code in `src/`
through a small JSON API. No detection logic, threshold or demo data changed. The Streamlit app (`.\dev.ps1`)
still works as before and stays as the fallback.

Phase 12B adds sign-in with three roles, shared datasets that persist, and the Data import page.

Synthetic data. A flag is a prompt for a human to look, not a verdict.

## Run it on Windows (two commands)

One-time setup, from the project folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
npm --prefix web install
```

Then, in **two** PowerShell windows, both opened in the project folder:

```powershell
# Window 1: the API (http://127.0.0.1:8000). Builds the demo first if it is missing or stale, then loads it.
.\.venv\Scripts\python.exe -m api
```

```powershell
# Window 2: the web app (http://localhost:3000)
npm --prefix web run dev
```

Open http://localhost:3000. Stop either one with Ctrl+C. The built-in demo is open without signing in.

For a faster, production-style web app use `npm --prefix web run build` once, then `npm --prefix web run start`
instead of `run dev`.

The browser only ever talks to the web app: the web app forwards every `/api/...` call to the API
(`web/next.config.ts`). Keeping both on one address is what lets the sign-in cookie work safely.

## Create the first Admin

Accounts are created by an Admin only. There is no public sign-up and no password-reset email. Create the first
Admin once, in a third PowerShell window in the project folder (the API may be running or not):

```powershell
.\.venv\Scripts\python.exe -m api.create_admin
```

It asks for the email, then for the password **twice at a hidden prompt** (nothing is shown as you type). The
password must be at least 10 characters. It is never accepted as a command argument, never read from a file and
never printed or logged. Only its argon2 hash is stored. You can also give the email on the command line:

```powershell
.\.venv\Scripts\python.exe -m api.create_admin --email admin@example.org
```

Then sign in at http://localhost:3000/signin.

## Add users

Signed in as an Admin, open **Users** (in the sidebar under Manage, or **More** on a phone).

* **Add a user:** email, role and a first password of at least 10 characters. Give the password to the person
  yourself, in person or by phone. Nothing is emailed.
* **Roles:** each includes the one before it.
  * **Viewer** reads every dataset.
  * **Importer** is a Viewer who can also add datasets on the Data import page.
  * **Admin** is an Importer who can also manage users, delete datasets and read the audit log.
* **Change a role, reset a password, disable or enable** a user from the list. A role change, a password reset or
  disabling signs that user out at once.
* You cannot remove your own Admin role or disable yourself, and the last active Admin cannot be demoted.

Signing in: after **5 wrong passwords** for one account, sign-in for that account pauses for **10 minutes**, even
with the right password. Every failure shows only "Email or password not recognised." A sign-in lasts 8 hours
(`FAIRLEND_SESSION_HOURS`). **Sign out** is in the account menu.

## Import the synthetic sample pack

1. Build the sample packs once: `.\dev.ps1 -SamplePack` (writes `sample_pack\`, git-ignored).
2. Sign in as an Importer or Admin and open **Import data**.
3. **Step 1** offers the templates (one Excel workbook, or five CSV files in a zip). They come from the same template
   builder as the Streamlit Data page.
4. **Step 2:** choose *Create a new dataset*. Name it `SYNTHETIC sample baseline`. For "Where the data came from",
   enter `synthetic sample pack`.
5. **Step 3:** choose *Five CSV files* and select the five files in `sample_pack\baseline\lender_A`. Press
   **Check the files**.
   * Expect: "No errors found", with 1 lender, 244 borrowers, 666 loans, 20,144 transactions and 1,291 messages.
   * The as-of date fills in as 2026-10-01.
6. **Step 4:** tick the permission box and press **Import**. The message is labelled
   **"Imported dataset. Passed the synthetic-only check."** Press **Show this dataset**.
7. Add lender B: choose *Add another lender's files to an imported dataset*, pick `SYNTHETIC sample baseline`,
   select `sample_pack\baseline\lender_B`, then Check and Import.
   * The import reports **85 borrower codes already known**.
   * **Datasets** shows 387 borrowers.
   * The API's dataset detail reports **85 of 387** borrowers at two lenders.
   * Overview shows 0 high, 7 medium and 380 low.

   These are the same numbers as the Streamlit import of the same pack (docs\ONBOARDING_DEMO.md).

**Every upload must pass the synthetic-only check first** (the existing gate from `src/team_access.py`):

* lender names end in "(Demo)";
* every message ends in "(SYNTHETIC)";
* no phone-, ID- or email-like text in lender names or messages;
* at most 25 MB and 100,000 rows per file (`team_demo` in config.yaml).

The check runs on the upload in memory. A refused upload is never validated, stored or written anywhere: the page
says "Upload refused. Nothing was stored." and lists the reasons with row numbers. After the gate, the existing
importer (`src/import_data.py`) validates the files. Errors and warnings are listed in plain words with sheet or
file and row number (never the cell's value). Nothing is saved until the check finds no errors. Message text is
always redacted.

Passing the check does **not** prove the data is synthetic. That is why imported datasets are labelled
"Imported dataset. Passed the synthetic-only check." and are never called synthetic. They never show the REAL DATA
banner either. Their trust strip reads "Imported dataset. Passed the synthetic-only check. A flag is a prompt for
a human to look, not a verdict."

## Datasets

**Datasets** (any signed-in user) lists the built-in demo first, then every imported dataset. Each entry shows
counts, who added it and when, and how many imports went into it. The list is shared, so every user sees the same
datasets. **Show this dataset** (or the dataset switcher in the sidebar, or under **More** on a phone) chooses what
Overview, Borrowers, Lenders and Repayments show. The choice is remembered in this browser. The demo is the default.

An Admin can **Delete** an imported dataset after typing its exact name. The demo cannot be deleted or changed:
the API refuses both. **Audit log** (Admin) lists who did what, and when:

* imports, including refused and invalid ones;
* deletes;
* user changes;
* sign-in lockouts.

Entries hold no passwords, cell values or message text.

## Where the data lives

Everything is under `data\web\` (git-ignored, like all of `data\`). Set `FAIRLEND_WEB_DATA` to put it elsewhere.

| Path | What |
|---|---|
| `data\web\app.db` | SQLite: users (argon2 password hashes), sessions (SHA-256 of each token), dataset metadata, audit log |
| `data\web\datasets\<name>\` | one folder per imported dataset: `lending.db`, `predictions.db`, `dataset.json` (written by the existing importer) |
| `data\web\session_secret.txt` | the session-signing secret, generated on first start unless `FAIRLEND_SESSION_SECRET` is set |

The built-in demo stays where it always was (`data\lending.db` and friends), and nothing in the web API writes to
it. To start the web data from scratch, stop the API and delete `data\web\`. Users, sessions and imported
datasets are then gone; the demo is not affected.

## Settings (environment variables, all optional)

| Variable | Default | What it does |
|---|---|---|
| `FAIRLEND_WEB_ORIGINS` | `http://localhost:3000` | Front-end origins. CORS allows them, and every state-changing call must come from one (cross-site protection). Comma-separated. |
| `FAIRLEND_API_HOST` / `FAIRLEND_API_PORT` | `127.0.0.1` / `8000` | Where the API listens. The default is this computer only. |
| `FAIRLEND_API_URL` | `http://127.0.0.1:8000` | Where the web app forwards `/api/...` calls. Read when the web app starts. |
| `FAIRLEND_WEB_DATA` | `data\web` | Users, sessions, dataset metadata, audit log, imported datasets. |
| `FAIRLEND_SESSION_SECRET` | generated file | Session-signing secret. Never commit it. |
| `FAIRLEND_SESSION_HOURS` | `8` | How long a sign-in lasts. |
| `FAIRLEND_COOKIE_SECURE` | off | Set to `1` when the app is served over HTTPS, so the cookie is sent over HTTPS only. |
| `LENDING_MONITOR_CONFIG` | `config.yaml` | Another config file (the same variable the Streamlit app uses). |

Set one for the current PowerShell window only, then start the program in that window, for example:

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

* **`api/data_source.py`** is the single data-source layer.
  * `DemoDataSource` loads the demo once at start-up.
  * `DataSources` adds the imported datasets. Each is loaded with the same engine calls (`load_all`,
    `repayments.load`) on first use, and again right after an import.
* **`api/store.py`** keeps dataset storage behind two interfaces, `DatasetCatalog` (metadata) and `DatasetFiles`
  (one folder per dataset). A Postgres catalog or object storage can replace either one later.
* **`api/accounts.py`** handles users, roles, sign-in, the throttle and sessions. **`api/security.py`** handles
  argon2 hashing, signed session tokens and the secret.
* **`api/deps.py`** holds the access rule for every endpoint, plus the cross-site check.
* **`api/imports.py`** wraps the template, gate, validation and import around the existing `src/` code.
* **`api/routes.py`** has the Phase 12B endpoints. **`api/main.py`** is the app and the data endpoints.

### Who can call what

| Endpoint | Anyone | Viewer | Importer | Admin |
|---|:-:|:-:|:-:|:-:|
| `GET /api/health`, `/api/auth/me`; `POST /api/auth/login`, `/api/auth/logout` | yes | yes | yes | yes |
| Data endpoints (`/api/meta`, `/overview`, `/borrowers`, `/lenders`, `/repayments`, follow-up and CSV) for the demo | yes | yes | yes | yes |
| The same with `?dataset=<imported dataset>` | no | yes | yes | yes |
| `GET /api/datasets`, `/api/datasets/{name}` | no | yes | yes | yes |
| `GET /api/imports/info`, `/api/imports/template`; `POST /api/imports/check`, `/api/imports` | no | no | yes | yes |
| `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/password`, `GET /api/audit`, `DELETE /api/datasets/{name}` | no | no | no | yes |

Not signed in gives 401. Signed in without the role gives 403. Every POST, PATCH and DELETE also needs the
request to come from `FAIRLEND_WEB_ORIGINS` (checked on the Origin header, or the Referer if there is no Origin),
on top of the httpOnly, SameSite=Strict session cookie. Any other method on any other route gives 405.

Interactive API docs: http://127.0.0.1:8000/docs while the API runs.

## The web app (web/)

**Pages:**

* **Overview**, **Borrowers** (list and one borrower), **Lenders** and **Repayments**, for the chosen dataset.
* **Sign in**.
* **Datasets** (signed in).
* **Import data** (Importer and Admin).
* **Users** and **Audit log** (Admin).

**Layout:** a left sidebar on a desktop. On a phone there is a bottom bar with the four main pages plus **More**
(dataset switcher and the manage pages). The account menu shows your email, your role and Sign out.

**Friendly states:**

* signed out: "Sign in to …";
* no permission: "You do not have permission to …" with the role it needs;
* empty lists;
* upload refused;
* validation errors with row numbers;
* loading skeletons;
* errors with "Try again".

**Design:**

* Brand colours from the logo: navy `#0F172A`, teal `#0F766E`, slate `#475569`, amber `#D97706`.
* The font is Inter, bundled with the app. The light theme is the default; a dark theme is optional.
* Risk bands are always words (Low, Medium, High), never colour alone.
* Every chart has a title, axis labels and alt text.
* The trust strip is on every page.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api.py tests\test_api_auth.py tests\test_api_datasets.py -q
npm --prefix web run typecheck
npm --prefix web run build
```

**`tests/test_api.py`** (Phase 12A) checks number parity with Streamlit for the demo, CORS, redaction and the CSV
notice line.

**`tests/test_api_auth.py`** (Phase 12B) checks:

* every endpoint declares exactly one access rule;
* a role matrix where each of anonymous, Viewer, Importer and Admin is tried on every protected endpoint;
* argon2-only password storage, and the same message for every sign-in failure;
* the 5-wrong-passwords lockout and its 10 minutes;
* session expiry, sign-out (a copied cookie stops working) and forged cookies;
* cross-site refusal, even for a signed-in Admin;
* user management and the last-Admin guard;
* the create-admin hidden prompt and its refusal of a `--password` argument.

**`tests/test_api_datasets.py`** (Phase 12B) checks:

* templates;
* gate refusals (a missing "(Demo)", or a phone number in a message) write nothing and are never validated;
* uploads stay in memory and are capped;
* validation errors carry row numbers and never repeat a cell value;
* the baseline sample pack, lender A then lender B, gives 85 already known, 85 of 387, and 0/7/380, equal to a
  direct engine import;
* imported datasets are labelled and never called REAL DATA;
* datasets need a signed-in user, are shared, and do not leak into each other;
* delete needs the exact name;
* the audit log;
* datasets persist across a restart;
* the demo fingerprint is unchanged after imports and deletes.

The demo-based tests skip with a message if the demo has not been built (`python -m api.prepare`).

## Not production-grade yet

* **Single process, single machine.** SQLite, local folders and an in-process import lock are fine for a small
  team on one computer. They are not enough for several API servers. The `DatasetCatalog` and `DatasetFiles`
  interfaces are where Postgres or object storage would plug in.
* **No HTTPS of its own.** Put it behind an HTTPS reverse proxy and set `FAIRLEND_COOKIE_SECURE=1` before anyone
  reaches it over a network. The defaults listen on this computer only.
* **No multi-factor sign-in, no self-service password change, no password-reset email.** An Admin resets
  passwords by hand.
* **The login throttle is per account.** It does not slow down one address that tries many accounts; a reverse
  proxy should rate-limit by address.
* **Imports run inside the web call.** A large upload ties up that call while it is checked and labelled (the
  baseline pack takes a few seconds). A job queue would be better at scale.
* **Imported datasets are labelled by a model trained on synthetic text.** There is no Review page in the web app
  yet (the importer's message still points to one); use the Streamlit Review page for now.
* **Not covered yet:** no audit log export, no retention rule for old entries, no backups of `data\web\`.
* **The synthetic-only check is a guard, not a proof.** It cannot tell synthetic data from real data that was
  edited to pass it.

## Screenshots

In `docs/ui_v2_screens/`:

* **Phase 12A:** desktop Overview, Borrowers, one borrower, Lenders and Repayments, in light and dark themes;
  phone views; the loading skeleton.
* **Phase 12B (`12b_*`):**
  * sign-in;
  * Datasets (Admin);
  * the Overview of an imported dataset;
  * Import with a clean check, a refused upload and a finished import;
  * Users and Audit log (Admin);
  * no permission (Viewer on Users) and signed out (Datasets);
  * the phone Datasets page with the More menu, the phone Overview of an imported dataset, and the phone Import page.
