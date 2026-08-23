#!/bin/sh
set -e

PORT="${PORT:-8000}"
cd /app

echo "[start] Running Alembic migrations..."
alembic upgrade head

echo "[start] Starting PitchPool on 0.0.0.0:${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
