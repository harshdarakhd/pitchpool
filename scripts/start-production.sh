#!/bin/sh
set -e

PORT="${PORT:-8000}"
cd /app

echo "[start] Running Alembic migrations..."
alembic upgrade head

# Render Free has no shell, so the one-time admin is created here. The script is
# idempotent and exits non-zero when the bootstrap variables are unset.
if [ -n "${BOOTSTRAP_ADMIN_EMAIL}" ] && [ -n "${BOOTSTRAP_ADMIN_PASSWORD}" ]; then
  echo "[start] Ensuring bootstrap admin account..."
  python scripts/bootstrap_admin.py || echo "[start] Admin bootstrap skipped"
fi

echo "[start] Starting PitchPool on 0.0.0.0:${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
