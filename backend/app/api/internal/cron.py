"""Protected cron endpoints for external wake/sync triggers."""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import (
    acquire_lock,
    clear_sync_request,
    release_lock,
    sync_is_requested,
)
from app.db.base import get_db
from app.schemas import ImportRequest, SyncRunResponse
from app.services.cricheroes.sync import import_matches, sync_cricheroes
from app.services.tournaments import (
    SYNC_LOCK_KEY,
    SYNC_LOCK_TTL_SECONDS,
    ensure_active_tournament,
)
from app.worker.scheduler import run_sync_job

router = APIRouter(prefix="/internal/cron", tags=["internal"])


def _verify_cron_secret(x_cron_secret: str | None) -> None:
    settings = get_settings()
    expected = settings.cron_secret
    if not expected or not x_cron_secret or not secrets.compare_digest(x_cron_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/sync", response_model=SyncRunResponse)
async def cron_sync(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    _verify_cron_secret(x_cron_secret)

    if not await acquire_lock(SYNC_LOCK_KEY, ttl=SYNC_LOCK_TTL_SECONDS):
        raise HTTPException(status_code=409, detail="Sync already running")
    try:
        run = await sync_cricheroes(db)
        return run
    finally:
        await release_lock(SYNC_LOCK_KEY)


@router.post("/sync-job")
async def cron_sync_job_only(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Lightweight wake endpoint that reuses the shared lock + sync job."""
    _verify_cron_secret(x_cron_secret)
    await run_sync_job()
    return {"ok": True}


@router.post("/import", response_model=SyncRunResponse)
async def cron_import(
    body: ImportRequest,
    db: AsyncSession = Depends(get_db),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Accept fixtures scraped by a trusted client that Cloudflare does not block."""
    _verify_cron_secret(x_cron_secret)

    tournament = await ensure_active_tournament(db)
    if body.cricheroes_id is not None and body.cricheroes_id != tournament.cricheroes_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Payload is for tournament {body.cricheroes_id}, "
                f"but {tournament.cricheroes_id} is active"
            ),
        )

    if not await acquire_lock(SYNC_LOCK_KEY, ttl=SYNC_LOCK_TTL_SECONDS):
        raise HTTPException(status_code=409, detail="Sync already running")
    try:
        return await import_matches(
            db,
            tournament=tournament,
            teams=body.teams,
            matches=[m.model_dump() for m in body.matches],
        )
    finally:
        await release_lock(SYNC_LOCK_KEY)
        await clear_sync_request()


@router.get("/pending-sync")
async def cron_pending_sync(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    _verify_cron_secret(x_cron_secret)
    return {"pending": await sync_is_requested()}


@router.post("/ack-sync")
async def cron_ack_sync(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    _verify_cron_secret(x_cron_secret)
    await clear_sync_request()
    return {"ok": True}
