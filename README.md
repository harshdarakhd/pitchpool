# PitchPool — Cricket Bidding Platform

Production-ready cricket bidding platform with FastAPI backend, React frontend, PostgreSQL, Redis, and CricHeroes tournament sync.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, Alembic
- **Frontend:** React 18, Vite, TypeScript, Tailwind CSS, TanStack Query
- **Data:** PostgreSQL 16, Redis 7
- **Jobs:** APScheduler worker + Playwright scraper
- **Realtime:** WebSockets + Redis pub/sub

## Quick start (no Docker)

Docker is optional. Local development uses **SQLite** and an in-memory Redis fallback.

```bash
cd pitchpool\backend
pip install -e ".[dev]"
python -m playwright install chromium
copy .env.example .env
python scripts/seed.py
python -m uvicorn app.main:app --reload --port 8001
```

API docs: http://127.0.0.1:8001/docs

### Tournament data

Teams and fixtures are **never hardcoded** — `scripts/seed.py` creates the demo
accounts and then pulls the real tournament from the CricHeroes URL in
`CRICHEROES_BASE_URL`. The scrape needs Chromium, hence the `playwright install`
step above.

```bash
python scripts/seed.py --no-sync   # accounts + badges only, skip the scrape
python scripts/show_db.py          # print the synced teams and fixtures
python scripts/reset_db.py         # delete the local SQLite file
```

After the first seed the APScheduler worker re-syncs automatically, so results
and new fixtures land in the app without a restart.

### Switching tournaments

Any public CricHeroes tournament works. `--dry-run` reports what would be
imported (including how many fixtures are still biddable) without touching
anything:

```bash
python scripts/set_tournament.py <tournament-url> --dry-run
python scripts/set_tournament.py <tournament-url>
python scripts/set_tournament.py <tournament-url> --reset   # also wipe bids/points
```

Use `--reset` when moving to an unrelated tournament so old bids, payouts and
streaks do not carry over. The command updates `.env`, re-syncs, and asks you to
restart the API.

> **Note on scraping.** cricheroes.com is behind Cloudflare bot protection and
> renders match cards with hashed CSS-module class names. `client.py` handles the
> former and `parser.py` matches only the stable class suffixes. Scores are drawn
> into a `<canvas>`, so runs/wickets cannot be scraped — the winner and margin are
> read from the result line instead.

## Quick start (Docker)

If you have Docker Desktop installed:

```bash
cd pitchpool
docker compose up -d postgres redis
cd backend && pip install -e ".[dev]" && copy .env.example .env
python scripts/seed.py
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

**Demo login:** `demo@pitchpool.local` / `demo12345`  
**Admin:** `admin@pitchpool.local` / `admin12345`

## Worker (CricHeroes sync)

```bash
cd backend
python -m app.worker.scheduler
```

Syncs from: https://cricheroes.com/tournament/1691351/maheshwari-tennis-premier-league-season-4-2026/matches/past-matches

## Tests

```bash
cd backend && pytest
```

## Deployment (Render Free pilot)

Production deploys as **one same-origin container** (React + FastAPI + WebSocket + Playwright) on Render Free, with Neon PostgreSQL and Upstash Redis.

| Component | Host |
|-----------|------|
| Web (SPA + API + sync) | [Render](https://render.com) Free — `render.yaml` |
| PostgreSQL | [Neon](https://neon.tech) Free |
| Redis | [Upstash](https://upstash.com) Free |

**Full runbook:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — accounts, env vars, migrations, bootstrap admin, optional cron wake-up, verification, rollback.

Quick summary:

1. Create Neon DB → set `DATABASE_URL` as `postgresql+asyncpg://…?sslmode=require`
2. Create Upstash Redis → set `REDIS_URL` as `rediss://…`
3. Connect repo to Render Blueprint (`render.yaml`) or manual Docker web service
4. Set secrets: `SECRET_KEY`, `CRON_SECRET`, `CORS_ORIGINS` (your Render URL), bootstrap admin vars
5. Deploy — startup runs `alembic upgrade head` then binds `$PORT`

> Render Free sleeps after ~15 minutes idle. WebSockets and background sync pause while asleep. See the runbook for cron wake-up and admin manual sync.

Local dev Docker (`docker-compose.yml`) and `backend/fly.toml` remain for alternative setups; the root `Dockerfile` is the production image.

## API docs

- Health: `GET /health`
- Swagger: `GET /docs`
- WebSocket: `WS /ws?token=<access_token>`

## Features

- Email/password auth with JWT + rotating refresh tokens
- Parimutuel bidding with 30% gap rule, stage-specific limits
- Quiz predictions (+100 pts) and season bets with decay cap
- Win streaks, badges, leaderboard, points ledger
- Real-time pool/settlement updates via WebSocket
- CricHeroes tournament sync with admin override fallback
