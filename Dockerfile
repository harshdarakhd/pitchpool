# syntax=docker/dockerfile:1
# Production image: Vite SPA + FastAPI + Playwright Chromium (same-origin on Render).

# --- Stage 1: build frontend (relative /api and /ws; no VITE_API_URL) ---
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ENV VITE_API_URL=
RUN npm run build

# --- Stage 2: backend runtime with Chromium ---
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Layer cache: install deps before copying the rest of the backend tree.
COPY backend/pyproject.toml .
COPY backend/app ./app
RUN pip install --no-cache-dir . && \
    playwright install --with-deps chromium

COPY backend/ .

# SPA assets served by FastAPI from ./static (see docs/DEPLOYMENT.md).
COPY --from=frontend-build /frontend/dist ./static

COPY scripts/start-production.sh /start-production.sh
RUN sed -i 's/\r$//' /start-production.sh && chmod +x /start-production.sh

EXPOSE 8000

# Render uses healthCheckPath in render.yaml; this helps local docker run.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1'

CMD ["/start-production.sh"]
