# Deploying the FairLend Watch web interface (v2): a recipe, not a deployment

This document describes how the web interface (`web/`) and its API (`api/`) **could** be put on a server. Nothing
here has been deployed. Read it before anyone outside this computer can reach the app. The Streamlit app stays the
fallback and is not covered here.

Synthetic data. A flag is a prompt for a human to look, not a verdict.

## 1. What is safe to show publicly, and what is not

| Safe to show publicly | Not safe to show publicly |
|---|---|
| The built-in **synthetic demo**: Overview, Borrowers, Lenders, Repayments, Guided demo, Export (demo files), About. It describes no real people, loans, lenders or messages. | **Imported datasets.** They passed the synthetic-only check, which does not prove they are synthetic. Keep them behind sign-in, as the API already does. |
| The demo's CSV exports (each starts with the synthetic notice line). | **`data\web\app.db`** (users, password hashes, session hashes, dataset metadata, audit log). |
| `/api/health` | **`data\web\session_secret.txt`** or the `FAIRLEND_SESSION_SECRET` value. |
| | **`data\web\datasets\`** (imported data and its labels) and **backups** of `data\web\`. |
| | The Import, Review labels, Users and Audit pages (they need sign-in and the right role; the API enforces it). |
| | The interactive API docs at `/docs` (turn them off or keep them internal; see step 6). |

If the goal is a public demo only, the simplest safe option is to run the API with **no users at all**. Without an
account nobody can sign in, so only the demo is visible.

## 2. The shape of a deployment

```
internet --HTTPS--> reverse proxy (TLS, rate limits) --> web app (next start, port 3000)
                                                       \-> /api/* forwarded by the web app --> API (port 8000, local only)
                                                                                                   |
                                                                                persistent disk: data\  (demo + data\web)
```

* Only the reverse proxy is reachable from the internet. The web app and the API listen on the server itself
  (`FAIRLEND_API_HOST=127.0.0.1`, the default).
* The browser talks to one address only. The web app forwards `/api/*` to the API, so the session cookie stays
  first-party. **Next.js fixes the forwarding address when the web app is built**, so set `FAIRLEND_API_URL`
  before `npm --prefix web run build` if the API is not at `http://127.0.0.1:8000`.

## 3. HTTPS and the cookie

1. Put a reverse proxy with a real certificate in front (for example Caddy, nginx or the host's own TLS front
   end). Redirect plain HTTP to HTTPS.
2. Set these settings for the API:

   ```powershell
   $env:FAIRLEND_COOKIE_SECURE = "1"                     # the session cookie is sent over HTTPS only
   $env:FAIRLEND_WEB_ORIGINS   = "https://fairlend.example.org"   # the public address, exactly as the browser shows it
   ```

   `FAIRLEND_WEB_ORIGINS` is also the cross-site check: every sign-in, import, review, user change and delete must
   come from one of these origins.
3. The reverse proxy must pass the browser's `Origin` and `Referer` headers through unchanged.

## 4. A fixed session secret

On a server, do not rely on the generated `data\web\session_secret.txt`. Set the secret once in the host's secret
store and give it to the API as `FAIRLEND_SESSION_SECRET` (at least 32 random bytes). To make one in PowerShell:

```powershell
-join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
```

Store it in the host's secret settings, never in Git and never in a `.env` file in the project. Changing the secret
signs everyone out. That is the way to end every session at once.

## 5. Per-address rate limiting

The API locks one account for 10 minutes after 5 wrong passwords. It does **not** slow down one address that tries
many accounts. Add limits in the reverse proxy, by client address. Suggested starting points:

| Path | Limit |
|---|---|
| `POST /api/auth/login` | 10 a minute per address |
| `POST /api/imports`, `POST /api/imports/check` | 5 a minute per address; request body at most 26 MB |
| `POST /api/review/*`, `/api/users*`, `DELETE /api/datasets/*` | 60 a minute per address |
| everything else | 300 a minute per address |

The API already refuses uploads over the configured size (`team_demo.max_upload_mb`, 25 MB) before reading them.

## 6. Other settings for a server

* `FAIRLEND_SESSION_HOURS`: shorten from 8 if the app is shared on public computers.
* Hide the interactive API docs from the internet: block `/docs`, `/redoc` and `/openapi.json` in the reverse
  proxy. The API itself keeps them for local use.
* Run the API and the web app as a normal user, not an administrator. Restart them automatically if they stop.
* Start order: the API first (`.\.venv\Scripts\python.exe -m api` builds the demo if needed, then loads it), then
  `npm --prefix web run start`.
* Create the first Admin on the server itself, with `.\.venv\Scripts\python.exe -m api.create_admin`. The
  password is asked at a hidden prompt.

## 7. Backups of data\web\

Everything users create lives in `data\web\`: accounts, the audit log, dataset metadata and every imported dataset.
The demo can always be rebuilt (`python -m src.build_all`); `data\web\` cannot.

* Back it up at least daily, and before every upgrade. Stop the API first, or copy `app.db` with SQLite's own
  backup command, so you never copy it half-written.
* A simple PowerShell backup while the API is stopped:

  ```powershell
  $stamp = Get-Date -Format "yyyyMMdd-HHmm"
  Compress-Archive -Path .\data\web\* -DestinationPath "D:\fairlend-backups\web-$stamp.zip"
  ```

* Treat backups like the data itself: encrypted at rest, access limited to Admins, kept off the public server.
* Test a restore now and then: unzip into a fresh `data\web\`, start the API, sign in, open a dataset.

## 8. Free hosts without a persistent disk

Many free hosts (and Streamlit Community Cloud) give the app a disk that is **wiped on every restart or redeploy**.
On such a host:

* **Users, sessions, the audit log and every imported dataset disappear** at the next restart. People cannot keep
  accounts and imports do not last.
* The demo still works, because the API rebuilds it at start-up.

So the web interface can only be used **as a public demo** there (no accounts). To keep users and datasets on such
a host, the storage must move to managed services first:

| Today (local disk) | On a host without a persistent disk |
|---|---|
| `data\web\app.db` (users, sessions, catalog, audit) | a managed database (for example Postgres): implement the account, catalog and audit stores on it (`api/accounts.py`, `api/store.py` `DatasetCatalog`, `api/audit.py`) |
| `data\web\datasets\<name>\` folders | object storage: implement `DatasetFiles` in `api/store.py` to download a dataset's folder to a local cache before loading, and upload after an import or a review |
| `data\web\session_secret.txt` | the host's secret store (`FAIRLEND_SESSION_SECRET`) |

The interfaces in `api/store.py` exist for exactly this. Until they are implemented and tested, do not invite users
to an app on a host without a persistent disk.

## 9. Before you open it to anyone: checklist

- [ ] HTTPS works, and plain HTTP redirects to it.
- [ ] `FAIRLEND_COOKIE_SECURE=1`, `FAIRLEND_WEB_ORIGINS` = the public address, and `FAIRLEND_SESSION_SECRET` set
      from the secret store.
- [ ] Per-address rate limits in the reverse proxy; `/docs` blocked from the internet.
- [ ] The disk is persistent (or storage has moved to managed services), and a backup has been made and restored once.
- [ ] Only the reverse proxy is reachable from outside; the API and web app listen on the server only.
- [ ] The first Admin was created on the server; no test accounts remain.
- [ ] Opened signed out, only the demo is visible, and the trust strip is on every page.
- [ ] The browser tests (`npm --prefix web run test:e2e`) and the Python suite (in batches) pass on this version.
