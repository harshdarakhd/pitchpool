"""Background scheduler for sync and deadline sweeps (in-process on the API)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import get_settings
from app.core.redis import acquire_lock, publish_event, release_lock
from app.db.base import AsyncSessionLocal
from app.db.models import Match, MatchStatus
from app.services.cricheroes.sync import sync_cricheroes
from app.services.tournaments import (
    SYNC_LOCK_KEY,
    SYNC_LOCK_TTL_SECONDS,
    ensure_active_tournament,
    get_active_tournament,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_sync_job() -> None:
    if not get_settings().enable_auto_scrape:
        logger.debug("Sync skipped — auto scrape disabled")
        return
    if not await acquire_lock(SYNC_LOCK_KEY, ttl=SYNC_LOCK_TTL_SECONDS):
        logger.debug("Sync skipped — lock held")
        return
    try:
        async with AsyncSessionLocal() as db:
            run = await sync_cricheroes(db)
            await db.commit()
            logger.info("Sync completed: %s matches updated", run.matches_updated)
    except Exception:
        logger.exception("Sync job failed")
    finally:
        await release_lock(SYNC_LOCK_KEY)


async def run_deadline_sweep() -> None:
    async with AsyncSessionLocal() as db:
        active = await get_active_tournament(db)
        if not active:
            return

        now = datetime.now(UTC)
        result = await db.execute(
            select(Match).where(
                Match.tournament_id == active.id,
                Match.status == MatchStatus.upcoming,
                Match.bid_deadline <= now,
            )
        )
        changed = False
        for match in result.scalars().all():
            match.status = MatchStatus.awaiting_result
            await publish_event("events", {"type": "match_locked", "match_id": match.id})
            changed = True
        if changed:
            await db.commit()


async def stale_startup_sync() -> None:
    """Run one sync on startup when the active tournament data is stale."""
    settings = get_settings()
    await asyncio.sleep(2)

    if not settings.enable_auto_scrape:
        # Still seed the tournament row so Admin and the import endpoint work.
        async with AsyncSessionLocal() as db:
            await ensure_active_tournament(db)
            await db.commit()
        logger.info("Startup sync skipped — auto scrape disabled")
        return

    async with AsyncSessionLocal() as db:
        # A freshly migrated production database has no tournament yet, so seed
        # one from the environment instead of skipping every automatic sync.
        active = await ensure_active_tournament(db)
        await db.commit()

        stale = True
        if active.last_sync_at and (active.match_count or 0) > 0:
            age = datetime.now(UTC) - active.last_sync_at
            stale = age > timedelta(minutes=settings.sync_stale_minutes)

        if not stale:
            logger.info("Startup sync skipped — last sync still fresh")
            return

    logger.info("Running stale startup sync")
    await run_sync_job()


def start_scheduler() -> AsyncIOScheduler | None:
    """Start in-process scheduler (single API instance — no separate worker)."""
    global _scheduler
    settings = get_settings()
    if not settings.enable_inprocess_scheduler:
        return None
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    scheduler = AsyncIOScheduler()
    if settings.enable_auto_scrape:
        scheduler.add_job(
            run_sync_job, "interval", minutes=3, id="cricheroes_sync", replace_existing=True
        )
    scheduler.add_job(run_deadline_sweep, "interval", minutes=1, id="deadline_sweep", replace_existing=True)
    scheduler.start()
    _scheduler = scheduler
    logger.info("In-process scheduler started")
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def main() -> None:
    """Standalone worker entrypoint for local docker-compose only."""
    logging.basicConfig(level=logging.INFO)
    start_scheduler()
    logger.info("Worker started")
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    main()
