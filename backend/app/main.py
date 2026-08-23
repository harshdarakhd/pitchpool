import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.internal import cron as internal_cron
from app.api.v1 import admin, auth, bids, matches, predictions, profile, ws
from app.api.v1.ws import start_redis_listener
from app.core.config import get_settings
from app.core.origin import OriginGuardMiddleware
from app.core.rate_limit import limiter
from app.core.redis import check_redis
from app.db.base import engine
from app.db.models import Base
from app.worker.scheduler import shutdown_scheduler, stale_startup_sync, start_scheduler

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_SPA_EXCLUDED_PREFIXES = (
    "/api",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/ready",
    "/ws",
    "/internal",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ensured (dev mode)")

    start_redis_listener()
    scheduler = start_scheduler()
    startup_sync_task = asyncio.create_task(stale_startup_sync())

    yield

    startup_sync_task.cancel()
    shutdown_scheduler()


def _spa_path_allowed(path: str) -> bool:
    return not any(path.startswith(prefix) for prefix in _SPA_EXCLUDED_PREFIXES)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PitchPool API", version="0.1.0", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(OriginGuardMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(matches.router, prefix="/api/v1")
    app.include_router(bids.router, prefix="/api/v1")
    app.include_router(predictions.router, prefix="/api/v1")
    app.include_router(profile.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(ws.router)
    app.include_router(internal_cron.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "pitchpool"}

    @app.get("/ready")
    async def ready():
        checks: dict[str, str] = {}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"

        checks["redis"] = "ok" if await check_redis() else "error"

        if any(v != "ok" for v in checks.values()):
            raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
        return {"status": "ready", "checks": checks}

    if STATIC_DIR.is_dir():

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str, request: Request):
            path = request.url.path
            if not _spa_path_allowed(path):
                raise HTTPException(status_code=404)

            if full_path:
                asset = STATIC_DIR / full_path
                if asset.is_file():
                    cache = "public, max-age=31536000, immutable" if "/assets/" in path else "no-cache"
                    return FileResponse(asset, headers={"Cache-Control": cache})

            index = STATIC_DIR / "index.html"
            if index.is_file():
                return FileResponse(index, headers={"Cache-Control": "no-cache"})
            raise HTTPException(status_code=404, detail="SPA not built")

    return app


app = create_app()
