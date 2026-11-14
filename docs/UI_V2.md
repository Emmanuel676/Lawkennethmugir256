# FairLend Watch web interface v2 (Phase 12A)

A new web interface built in JavaScript (Next.js + TypeScript + Tailwind + Recharts) on top of the existing
Python engine. It shows **the same numbers as the Streamlit app**, because every figure comes from the code in
`src/` through a small read-only JSON API. No detection logic, threshold or data changed. The Streamlit app
(`.\dev.ps1`) still works as before and stays as the fallback.

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

Open http://localhost:3000. Stop either one with Ctrl+C.

For a faster, production-style web app use `npm --prefix web run build` once, then `npm --prefix web run start`
instead of `run dev`.

### Settings (environment variables, all optional)

| Variable | Default | What it does |
|---|---|---|
| `FAIRLEND_WEB_ORIGINS` | `http://localhost:3000` | Front-end origins the API allows (CORS). Comma-separated. |
| `FAIRLEND_API_HOST` / `FAIRLEND_API_PORT` | `127.0.0.1` / `8000` | Where the API listens. The default is this computer only. |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Where the web app finds the API. Read when the web app starts or is built. |
| `LENDING_MONITOR_CONFIG` | `config.yaml` | Another config file (the same variable the Streamlit app uses). |

Set one for the current PowerShell window only, then start the program in that window, for example:

```powershell
$env:FAIRLEND_WEB_ORIGINS = "http://localhost:3000,http://localhost:3001"
.\.venv\Scripts\python.exe -m api
```

No settings file is needed, and none is read: there is no `.env` and no key of any kind.

## How it fits together

```
web/ (Next.js, browser)  --GET JSON-->  api/ (FastAPI)  -->  api/data_source.py  -->  src/ (unchanged engine)
```

* `api/prepare.py` (`python -m api.prepare`) builds the demo if it is missing or stale, using the existing
  `src.bootstrap.ensure_demo`. The API runs it during start-up, so a visitor never waits for a build.
* `api/data_source.py` is the **single data-source layer**. `DemoDataSource` loads the demo once at start-up with
  `src.dashboard_data.load_all` and `src.repayments.load` (the same calls the Streamlit pages make) and keeps a
  read-only snapshot. Later phases add other sources behind the same interface.
* `api/views.py` lays the engine's results out as JSON. Money is sent as the exact integer **plus** the engine's
  own strings (`format_money`, `format_money_compact`), so "UGX 251.9M" reads exactly as in Streamlit.
  Message text is passed through the existing redactor (`src/redaction.py`) before it is sent.
* `api/main.py` is the FastAPI app.

### Safety rules the API enforces

* **Presentation mode is the default.** The API forces the demo as the active dataset and refuses to start
  serving if anything else would be active (for example `FAIRLEND_PRESENT=0` with a stored real dataset).
* **Read-only.** Every route is GET. Any POST, PUT, PATCH or DELETE gets 405. There is no import or write endpoint.
* **CORS** allows only the origins in `FAIRLEND_WEB_ORIGINS`, and only GET.
* Data endpoints answer 503 with a plain reason until the data has loaded. `/api/health` always answers.

### Endpoints

| Endpoint | What it returns |
|---|---|
| `GET /api/health` | `ok` / `loading` / `error`, source, presentation mode, read-only |
| `GET /api/meta` | product name, dataset, trust line, band thresholds, message classes, glossary for tooltips |
| `GET /api/overview` | KPIs, band counts and shares, UGX owed by the high band, highest-scoring borrowers |
| `GET /api/borrowers` | filtered, sorted, paged list (`bands`, `regions`, `min_score`, `min_open_lenders`, `min_abusive`, `q`, `sort`, `order`, `page`, `page_size`) |
| `GET /api/borrowers/{id}` | one borrower: score, band, plain-language explanation, points, loans, messages with labels (redacted text) |
| `GET /api/lenders` | ranked lenders with confidence intervals, and the lenders too small to rank |
| `GET /api/lenders/{id}` | one lender's sentence and fixed example messages (redacted) |
| `GET /api/repayments` | status mix, owed, ageing buckets, per-lender mix, worst-status counts, known limits |
| `GET /api/repayments/follow-up` | the follow-up list, filtered, sorted and paged |
| `GET /api/repayments/follow-up.csv` | the same CSV as the Streamlit download, first line `#` with the synthetic notice |

Interactive API docs: http://127.0.0.1:8000/docs while the API runs.

## The web app (web/)

Pages: **Overview**, **Borrowers** (list and one borrower), **Lenders**, **Repayments**. There is a left sidebar
on a desktop and a bottom bar on a phone.

* Brand colours from the logo: navy `#0F172A`, teal `#0F766E`, slate `#475569`, amber `#D97706`, with the
  tints and line colour from the brief. The font is Inter, bundled with the app (no font is downloaded from the internet).
  The light theme is the default. The dark theme is a button in the sidebar (or add `?theme=dark` to the address).
* A risk band is always a **word** (Low, Medium, High) with a colour and a shape, never colour alone. The chart
  colours were checked with a palette validator for both themes (colour-blind separation and contrast).
* Every chart has a title, axis labels and alt text, and is backed by a table or direct labels.
* The trust strip ("Synthetic data. A flag is a prompt for a human to look, not a verdict.") is always visible.
  Repayments repeats it and says that the total owed includes loans not yet due.
* Tables have sticky headers, sortable columns (the arrow shows the sort), UGX with thousands separators and plain
  column names. On the Borrowers and follow-up lists the API sorts (the same sort as Streamlit), so only the
  columns Streamlit can sort by have sort arrows there.
* Loading skeletons, friendly empty and error states (with "Try again"), keyboard focus rings, a "Skip to content"
  link, and tooltips (hover, focus or tap) for overlap score, band, cycling, grace period, labelled abusive,
  confidence interval and too small to rank.
* Borrower filters are kept in the address, so Back from a borrower returns to the same filtered list.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q     # API, including the number-parity tests
npm --prefix web run typecheck                                 # TypeScript
npm --prefix web run build                                     # production build
```

`tests/test_api.py` checks every endpoint's headline numbers against the values the brief quotes from Streamlit
(Overview 5,000 / 280 / 863 / 3,857, UGX 251.9M; Repayments 29.2% / 22.8% / 12.5%, 885 follow-up borrowers).
It also renders `app.py` and `pages/7_Repayments.py` headless with Streamlit's AppTest and compares the API with
the values those pages actually show. It also checks that the demo fingerprint is unchanged, that nothing can
be written, the CORS rule, the 503-until-loaded behaviour, redaction, and the CSV notice line. The parity tests skip
with a message if the demo has not been built (`python -m api.prepare`).

## Screenshots

`docs/ui_v2_screens/`: desktop Overview, Borrowers (filtered), one borrower, Lenders, Repayments (light theme),
Overview and Repayments in the dark theme, Overview and Repayments on a 390-pixel-wide phone, and the loading
skeleton on a phone.
