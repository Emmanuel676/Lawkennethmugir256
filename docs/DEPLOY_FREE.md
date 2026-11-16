# Free hosting: Neon + Render + Vercel (step by step, PREPARED, NOT DEPLOYED)

This puts the web interface on three free services:

* **Neon** (Postgres) keeps users, sessions, the audit log, the dataset list and every imported dataset's files.
* **Render** runs the API.
* **Vercel** runs the web app.

Free Render and Vercel machines have **no permanent disk**: anything written to their disk disappears at the next
restart. That is why, with `DATABASE_URL` set, everything that must last goes to Neon. The built-in demonstration
dataset is rebuilt during every Render build and needs no storage.

Read `docs/DEPLOY_V2.md` first (what is safe to show publicly, HTTPS, backups). Nothing here has been deployed.

Demonstration data. A flag is a prompt for a human to look, not a verdict.

```
browser --HTTPS--> Vercel (web/, Next.js) --/api/* forwarded--> Render (api/, FastAPI) ---> Neon (Postgres)
```

## Before you start

* A GitHub copy of this repository that the three services can read. The branch is `ui-v2`; nothing here pushes it
  for you.
* The demo works locally (`docs/UI_V2.md`, "Ready checklist").
* Never paste a connection string or a secret into a file, a commit, a chat or a command line. Each one goes only
  into the dashboard field named below.

## 1. Neon: the database

1. Create a Neon project (any region close to the Render region; `render.yaml` uses Frankfurt).
2. In **Connection Details**, choose the **pooled** connection and copy the connection string. It looks like
   `postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`. This is `DATABASE_URL`. Keep it in your password manager.
3. You do not create tables: the API creates them on first use (`users`, `sessions`, `datasets`, `audit`,
   `dataset_files`).

## 2. A fixed session secret

Make one random secret, once, in PowerShell 7, and put it in your password manager:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

This is `FAIRLEND_SESSION_SECRET`. With `DATABASE_URL` set, the API **refuses to start** without it, and session
cookies are always Secure (HTTPS only). Changing it later signs everyone out.

## 3. Render: the API

1. **New > Blueprint**, pick the repository and branch `ui-v2`. Render reads `render.yaml` in the project folder:
   * **build:** `pip install -r requirements-api.txt && python -m api.prepare`. The build installs the requirements
     and prepares the demonstration dataset, so no visitor ever waits for it.
   * **start:** `python -m api`
   * **health check:** `/api/health`
2. When Render asks for the values marked `sync: false`, type them in **Environment**:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Neon pooled connection string (step 1) |
   | `FAIRLEND_SESSION_SECRET` | the secret from step 2 |
   | `FAIRLEND_WEB_ORIGINS` | the web app's address, for example `https://fairlend-watch.vercel.app` (add preview addresses separated by commas if you use them) |
   | `LENDING_MONITOR_CONFIG` | leave **empty**. Set it to `deploy/config.small.yaml` only if the API runs out of memory (section 6). |

   Already set by `render.yaml`:
   * `FAIRLEND_API_HOST=0.0.0.0` (the port comes from Render's own `PORT`);
   * `FAIRLEND_PRESENT=1`;
   * `PYTHON_VERSION=3.12.8`.
3. Deploy. When the build log ends with "Demo data built." (or "Demo data is ready.") and the health check
   passes, open `https://<your-api>.onrender.com/api/health`. It should answer `{"status":"ok", ...}`.
4. Note the API's address. Vercel needs it in step 4.

**Free-plan behaviour:**

* Render stops a free service after about 15 minutes without visits, and the next visit waits for it to start
  again. Measured locally, the start takes about 11 to 13 seconds after Render's own start-up.
* The first page after a quiet spell may show "The data service is not reachable"; press **Try again**.

## 4. Vercel: the web app

1. **Add New > Project**, pick the repository and branch `ui-v2`.
2. **Root Directory:** `web`. Vercel then finds `web/vercel.json` (framework Next.js, `npm ci`, `npm run build`).
3. **Environment Variables:**

   | Variable | Value | Environments |
   |---|---|---|
   | `FAIRLEND_API_URL` | `https://<your-api>.onrender.com` (no trailing slash) | Production (and Preview if used) |

   Next.js fixes the `/api/*` forwarding address **when the web app is built**, so the variable must exist before the
   build. If you change it later, redeploy.
4. Deploy and open the Vercel address. The trust strip reads "Demonstration data. A flag is a prompt for a human
   to look, not a verdict." and the demo pages work signed out.
5. If the address differs from what you typed in Render's `FAIRLEND_WEB_ORIGINS`, fix it there. Without the exact
   address, sign-in answers "Cross-site request refused."

## 5. The first Admin on the hosted database

Run the same script as locally, on your own computer, pointed at Neon **for this one PowerShell window only**. The
connection string is read at a masked prompt (not typed on the command line, not saved in history), and the Admin
password is asked at the script's own hidden prompt.

```powershell
# PowerShell 7, in the project folder
$env:DATABASE_URL = Read-Host -MaskInput "Paste the Neon connection string"
.\.venv\Scripts\python.exe -m api.create_admin --email admin@example.org
Remove-Item Env:DATABASE_URL
```

In Windows PowerShell 5.1, replace the first line with:

```powershell
$env:DATABASE_URL = [Net.NetworkCredential]::new('', (Read-Host -AsSecureString "Paste the Neon connection string")).Password
```

The script prints "Stored in the hosted database (DATABASE_URL)." and never shows the connection string. Then sign
in on the Vercel address and add other users on the **Users** page.

## 6. If the API runs out of memory

**Measured locally** on Windows, as the peak working set of the API process:

| Built-in dataset | After start-up and every main page | Peak during an import of the largest sample folder (lender A) |
|---|---:|---:|
| Full demo, 5,000 borrowers (`config.yaml`) | 225 MB | 290 MB |
| Small demo, 1,500 borrowers (`deploy/config.small.yaml`) | 207 MB | 271 MB |

Both fit the free plan's 512 MB. Most of the memory is the Python libraries (pandas, scikit-learn, FastAPI), not the
data, so the small demo saves less than its size suggests. Linux on Render reports a similar figure. If Render still
shows "Out of memory" or restarts the service:

1. In Render, **Environment**, set `LENDING_MONITOR_CONFIG` to `deploy/config.small.yaml` and redeploy. The build
   then prepares the smaller demonstration dataset under `data/small/`.
   * Every rule and threshold is the same, but the numbers on screen are smaller.
   * The figures quoted in `docs/UI_V2.md` (5,000 borrowers, 280 high, and so on) no longer apply.
2. To choose another size, run `.\.venv\Scripts\python.exe -m api.small_config --borrowers 1000` locally, then
   commit the regenerated `deploy/config.small.yaml`.
3. Keep uploads small: the import of one lender's files is the heaviest moment. The size limit is
   `team_demo.max_upload_mb` in config.yaml (25 MB).

## 7. What lives where, and what to back up

| Where | What | Survives a restart? |
|---|---|---|
| Neon | users (argon2 hashes), sessions (SHA-256 of each token), audit log, dataset list, every imported dataset's files (as blobs) | yes |
| Render disk | the built-in demonstration dataset (rebuilt at every build), a cache of imported datasets' files in a temporary folder (downloaded again when needed) | no, and it does not need to |
| Render / Vercel environment | `DATABASE_URL`, `FAIRLEND_SESSION_SECRET`, `FAIRLEND_WEB_ORIGINS`, `FAIRLEND_API_URL` | yes |

* **Back up Neon** with Neon's own backups or branches, before every upgrade and regularly.
* **One API instance only.** Each instance keeps its own cache of dataset files, so do not scale the Render
  service to more than one instance.

## 8. Upgrading a live deployment to Phase 14 (landing page, request access)

**What happens to the database on first start.** The new version adds six columns to the `users` table in Neon:
`full_name`, `organisation`, `user_type`, `reason`, `status` and `requested_at`. It adds them **in place**, at start-up,
with `ADD COLUMN IF NOT EXISTS`:

* nothing is dropped or rewritten;
* every existing user, including the live Admin, gets `status = 'active'` and keeps their password;
* running it again is harmless.

No manual SQL is needed. Make a Neon backup or branch first anyway.

**Redeploy order.**

1. **Render (API) first.** In the service's **Environment**, add `FAIRLEND_PROXY_HOPS=2`. It is already in
   `render.yaml` for new blueprints: Vercel and Render sit in front of the API, so the visitor's address for the
   access-request limit is two places from the end of `X-Forwarded-For`. Then **Manual Deploy > Deploy latest commit**.
   Wait for `/api/health` to answer `ok`. The old web app keeps working against the new API meanwhile; it simply does
   not use the new endpoints.
2. **Vercel (web app) second.** Redeploy so the new landing page, `/overview`, `/request-access` and the waking-up
   screen go live. `FAIRLEND_API_URL` does not change.
3. **Check.**
   * Open the Vercel address signed out: the landing page appears.
   * **Explore the demo** opens `/overview`.
   * Sign in as the Admin: **Users** now has a **Pending requests** tab.
   * Send one test request from `/request-access`, then reject it.

**Settings that may need a look** (all optional, on Render):

* `FAIRLEND_REQUESTS_PER_HOUR` (default 5 per address);
* `FAIRLEND_MAX_PENDING` (default 50 requests waiting at once).

**No email is ever sent.** Tell people to check back and sign in once approved, as the pages say.

## 9. Checklist before sharing the address

- [ ] `/api/health` answers `ok`; the landing page loads signed out and its trust strip shows "Demonstration data."
- [ ] `FAIRLEND_SESSION_SECRET` set in Render; the API would refuse to start without it.
- [ ] `FAIRLEND_WEB_ORIGINS` (Render) equals the Vercel address; `FAIRLEND_API_URL` (Vercel) equals the Render address.
- [ ] The first Admin was created with the hidden prompt; sign-in works; no test accounts remain.
- [ ] Signed out, only the built-in demonstration dataset is visible.
- [ ] A Neon backup exists.
- [ ] Per-address rate limits are understood: the free services do not add them (`docs/DEPLOY_V2.md`, section 5).
