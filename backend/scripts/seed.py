"""Seed database with badges and optional dev tournament sync.

Demo/admin accounts are never created in production — use scripts/bootstrap_admin.py instead.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import AsyncSessionLocal, engine
from app.db.models import Base, Match, MatchStatus, QuizQuestion, Team
from app.services.cricheroes.sync import sync_cricheroes
from app.services.scoring import ensure_badges_seeded


async def seed(sync: bool = True) -> None:
    settings = get_settings()
    if settings.is_production:
        print("Refusing to run seed in production. Use bootstrap_admin.py for admin setup.")
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await ensure_badges_seeded(db)
        await db.commit()

        if sync:
            print("Syncing tournament from CricHeroes...")
            run = await sync_cricheroes(db)
            await db.commit()
            print(
                f"  sync {run.status}: {run.matches_seen} seen, "
                f"{run.matches_updated} written"
                + (f" ({run.error})" if run.error else "")
            )

        await _seed_quiz(db)
        await db.commit()

        teams = (await db.execute(select(Team))).scalars().all()
        matches = (await db.execute(select(Match))).scalars().all()
        print(f"Teams: {len(teams)} | Matches: {len(matches)}")
        print("Seed complete (development only — no demo accounts).")


async def _seed_quiz(db) -> None:
    """Attach a starter quiz question to any match that has none."""
    open_matches = await db.execute(
        select(Match).where(Match.status.in_([MatchStatus.upcoming, MatchStatus.locked]))
    )
    for match in open_matches.scalars().all():
        existing = await db.execute(
            select(QuizQuestion).where(QuizQuestion.match_id == match.id)
        )
        if existing.scalars().first():
            continue
        db.add(
            QuizQuestion(
                match_id=match.id,
                text="Will any batter score 30+ runs without hitting a six?",
                options={"A": "Yes", "B": "No", "C": "Maybe", "D": "N/A"},
                correct_option=None,
                points=100,
                locks_at=match.bid_deadline,
            )
        )


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Seed the PitchPool database (development only).")
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Only seed badges; skip the CricHeroes fetch.",
    )
    args = parser.parse_args()
    asyncio.run(seed(sync=not args.no_sync))
