# PitchPool deployment runbook (Render Free)

This guide deploys PitchPool as a **single same-origin web service** on [Render Free](https://render.com/docs/free), with [Neon](https://neon.tech) PostgreSQL and [Upstash](https://upstash.com) Redis. One container serves the React SPA, REST API (`/api/v1`), and WebSocket (`/ws`) from the same URL.

> **Pilot, not guaranteed always-on.** Render Free services sleep after ~15 minutes of inactivity, cold-start in ~30–60 seconds, and are intended for previews. WebSockets drop while the service sleeps. Use the optional cron wake-up below and the admin manual sync as fallbacks.

## Architecture

```
Browser (phone/desktop)
        │
        ▼
Render Free Web Service  ──►  Neon PostgreSQL (DATABASE_URL)
  React dist + FastAPI         Upstash Redis (REDIS_URL)
  Playwright Chromium
        ▲
        │ optional: cron-job.org every 14 min
```

## 1. Create external services

### Neon PostgreSQL (Free)

1. Create a project at [console.neon.tech](https://console.neon.tech).
2. Copy the **pooled** connection string (recommended for serverless-style hosts).
3. Convert the scheme for async SQLAlchemy:

   ```text
   postgresql://user:pass@host/db?sslmode=require
   → postgresql+asyncpg://user:pass@host/db?sslmode=require
   ```

4. **Free tier limits (approx.):** 0.5 GB storage, limited compute hours. Monitor usage in the Neon dashboard; the app logs slow queries when `SQL_ECHO` is enabled.

### Upstash Redis (Free)

1. Create a database at [console.upstash.com](https://console.upstash.com).
2. Copy the **TLS** URL (`rediss://…`). Render requires TLS to external Redis.
3. **Free tier limits (approx.):** 256 MB, 10k commands/day on the free plan. Pub/sub for WebSocket fan-out counts toward command quota.

## 2. Deploy on Render

### Option A — Blueprint (`render.yaml`)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint** → connect the repo.
3. Set secret/sync env vars when prompted (see [Environment variables](#environment-variables)).
4. Deploy. Note the service URL, e.g. `https://pitchpool-xxxx.onrender.com`.

### Option B — Manual Docker web service

1. **New → Web Service** → connect repo.
2. Runtime: **Docker**; Dockerfile path: `./Dockerfile`; context: `.`
3. Plan: **Free**; region: **Singapore** (low latency from India).
4. Health check path: `/health`
5. Add env vars from the table below.
6. Deploy.

### Startup command (automatic)

The production image runs `scripts/start-production.sh`, which:

1. `alembic upgrade head` — apply migrations to Neon
2. `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — bind Render’s dynamic port

Do **not** override the start command unless debugging.

## 3. Environment variables

Set these in the Render dashboard (**Environment** tab). Mark secrets as **Secret**.

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `ENVIRONMENT` | yes | `production` |
| `DATABASE_URL` | yes | `postgresql+asyncpg://…?sslmode=require` (Neon pooled URL) |
| `REDIS_URL` | yes | `rediss://default:…@….upstash.io:6379` |
| `SECRET_KEY` | yes | `openssl rand -hex 32` — JWT signing; rotate invalidates sessions |
| `CRON_SECRET` | yes | `openssl rand -hex 32` — protects internal cron/sync routes |
| `CORS_ORIGINS` | yes | `https://pitchpool-xxxx.onrender.com` (your Render URL; comma-separate if custom domain added) |
| `CRICHEROES_TOURNAMENT_ID` | bootstrap | e.g. `2078243` — seeds the first tournament row on an empty database |
| `CRICHEROES_BASE_URL` | bootstrap | Full CricHeroes tournament URL for first sync, e.g. `https://cricheroes.com/tournament/2078243/big-bash-league-season-5` |
| `BOOTSTRAP_ADMIN_EMAIL` | first deploy | One-time admin account email |
| `BOOTSTRAP_ADMIN_PASSWORD` | first deploy | Strong password; remove after bootstrap |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | optional | default `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | optional | default `7` |
| `SQL_ECHO` | optional | `false` in production |

Render injects `PORT` automatically — do not set it.

### Same-origin frontend

The Docker build sets `VITE_API_URL=` (empty). The SPA calls `/api/v1/…` on the same host; WebSockets use `wss://<host>/ws`. No separate frontend host or CORS cross-origin setup is needed beyond `CORS_ORIGINS`.

## 4. Bootstrap first admin

Render Free has no shell, so the container does this for you on every boot:

1. Set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in Render env.
2. Redeploy. `scripts/start-production.sh` runs `scripts/bootstrap_admin.py` after
   migrations. It creates the admin, or promotes an already-registered account with
   that email to admin (the existing password is kept in that case).
3. Remove or rotate `BOOTSTRAP_ADMIN_PASSWORD` from Render env after bootstrap.
4. Log in at `https://<your-service>/login`, open **Admin**, preview/activate the live tournament.

If you have shell access on a paid plan, `python scripts/bootstrap_admin.py` can also
be run manually; it is idempotent.

## 5. Optional cron wake-up and sync

Render Free has **no background worker**. While the web service is awake, APScheduler runs in-process. When it sleeps, scheduled sync stops until the next wake.

### Keep-alive (optional)

Use [cron-job.org](https://cron-job.org) (free) or similar:

- **URL:** `GET https://<your-service>/health`
- **Schedule:** every 14 minutes
- **Purpose:** reduce cold starts; does not guarantee 100% uptime

### Protected sync endpoint (placeholder)

When implemented by the backend:

```http
POST /internal/cron/sync
X-Cron-Secret: <CRON_SECRET>
```

- Returns `200` when sync completes or is skipped (already running).
- Returns `401` if `CRON_SECRET` header is missing or wrong.
- Schedule every 10–15 minutes via cron-job.org **only while testing**; respect CricHeroes rate limits.

Manual sync from the **Admin** page remains the reliable control if cron is not configured.

## 6. Post-deploy verification

| Check | How |
|-------|-----|
| Health | `GET /health` → `{"status":"ok"}` |
| Readiness | `GET /ready` → DB + Redis up (when implemented) |
| SPA | Open `/` — React app loads |
| API | `GET /docs` — Swagger UI |
| Auth | Register, log in, refresh cookie on same origin |
| Mobile | Open URL on phone; place a test bid |
| WebSocket | Two browsers on same match; pool updates after bid |
| Sync | Admin → manual sync; matches appear |
| Cold start | Wait 20+ min idle; first request may take ~1 min |

## 7. Roll back a tournament activation

1. Admin → archived tournaments (when UI exists) or inspect Neon `tournaments` table.
2. Do **not** delete user accounts unless intentional.
3. Re-activate a previous archived tournament via admin, or re-run preview/activate with the correct CricHeroes ID.
4. If data is corrupted, restore Neon from a branch/backup snapshot (Neon supports point-in-time on paid tiers; free tier: export before risky switches).

## 8. Local production-image smoke test

```bash
cd pitchpool
docker build -t pitchpool:prod .
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e ENVIRONMENT=production \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e REDIS_URL="rediss://..." \
  -e SECRET_KEY="local-test-secret" \
  -e CRON_SECRET="local-cron-secret" \
  -e CORS_ORIGINS="http://localhost:8000" \
  pitchpool:prod
```

Requires a reachable Postgres and Redis (Neon/Upstash URLs work from local Docker).

## 9. Free-tier limitations summary

| Provider | Constraint |
|----------|------------|
| Render Free | Sleeps after ~15 min idle; ~750 instance hours/month; no separate worker |
| Neon Free | Storage and compute caps; use connection pooling |
| Upstash Free | Command/day cap; use for pub/sub + rate limits only |
| Playwright | Chromium adds ~300 MB image size; first sync after cold start is slow |

For a small private league pilot these limits are usually sufficient. For always-on production, upgrade Render to a paid instance.

## 10. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Build fails at `npm run build` | Fix frontend TypeScript errors locally first |
| `alembic upgrade head` fails | Check `DATABASE_URL` scheme and Neon SSL; ensure migration versions exist |
| 502 on first request | Cold start; wait up to 60s |
| WebSocket disconnects | Render slept; reconnect logic should recover; cron wake-up helps |
| Sync timeout | CricHeroes scrape takes 2–4 min; admin sync may hit HTTP timeout on long requests |
| Cookie auth fails | `CORS_ORIGINS` must match exact browser origin; same-origin deploy should use the Render URL |
