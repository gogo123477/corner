# Deploying Corner to Vercel

One Vercel project serves everything: the web app as static files, the FastAPI backend
as a Python serverless function (`api/index.py`), and the morning job as a Vercel Cron.
The database is Neon Postgres.

## 1. Import the repo

Vercel dashboard → **Add New… → Project** → pick `gogo123477/corner`. Leave the
root directory as `/`. Framework preset: **Other**. The build and output settings come
from `vercel.json`; don't override them.

## 2. Add a database

In the project, **Storage → Create Database → Neon** (or paste an existing Neon
connection string). Vercel injects `DATABASE_URL`; add a variable that maps it:

| Variable | Value |
|---|---|
| `CORNER_DATABASE_URL` | the Neon `postgres://…` connection string (pooled is fine) |

The backend accepts `postgres://` and adds the driver itself. Tables are created on
first request.

## 3. Environment variables (Settings → Environment Variables)

| Variable | Value | Notes |
|---|---|---|
| `CORNER_DATABASE_URL` | Neon URL | required |
| `CRON_SECRET` | any long random string | Vercel sends it as the bearer token to the cron path |
| `CORNER_VAPID_PUBLIC_KEY` / `CORNER_VAPID_PRIVATE_KEY` | from `python -m app.jobs.push keygen` | for the morning nudge |
| `CORNER_VAPID_SUBJECT` | `mailto:you@example.com` | required by push services |
| `CORNER_TIMEZONE` | `Asia/Jerusalem` | which calendar day "today" is for the job |
| `CORNER_AUTH_MODE` | `dev` for now, `jwt` once managed auth is wired | see README |
| `ANTHROPIC_API_KEY` | optional | unset = template briefs |

`VITE_API_BASE` is intentionally **not** set: the web app calls the same origin and
`vercel.json` rewrites `/v1/*` to the Python function, so no CORS is involved.

## 4. Deploy

Click **Deploy**. Every push to `main` redeploys. First open of `/v1/brief/<date>`
creates the tables.

## 5. The morning cron

`vercel.json` schedules `GET /v1/jobs/morning` at `0 4 * * *` UTC (07:00 Israel in
summer, 06:00 in winter — adjust the hour if you care about DST). The route refuses
any call without `Authorization: Bearer $CRON_SECRET`. Test it by hand:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://<your-app>.vercel.app/v1/jobs/morning
```

## 6. On your phone

Open the Vercel URL in Chrome (Android) or Safari (iPhone) and add it to the home
screen. Open it from there, go to **Settings → Morning nudge → Turn on**. iPhone only
allows web notifications for home-screen apps.

## Local development is unchanged

`backend`: `uvicorn app.main:app --reload` · `web`: `npm run dev` (talks to
`http://localhost:8000`).

## Known limits of this setup

- **Dev auth.** Anyone with the URL can create a dev account. Fine while the URL is
  private; switch `CORNER_AUTH_MODE=jwt` before sharing.
- **Cold starts.** The Python function sleeps between requests; the first request after a
  while takes a couple of seconds. The cron pre-computes the brief so the morning open is
  still instant.
- **create_all on start.** No migrations yet; schema changes need Alembic (Phase 1).
