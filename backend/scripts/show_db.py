"""Print a summary of the synced tournament for a quick sanity check."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db.base import AsyncSessionLocal  # noqa: E402
from app.db.models import Match, Team  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as db:
        teams = (await db.execute(select(Team).order_by(Team.name))).scalars().all()
        print(f"TEAMS ({len(teams)})")
        for t in teams:
            print(f"  {t.short_name:<6} {t.name}")

        result = await db.execute(
            select(Match)
            .options(
                selectinload(Match.team_a),
                selectinload(Match.team_b),
                selectinload(Match.winner_team),
            )
            .order_by(Match.start_time, Match.id)
        )
        matches = result.scalars().all()
        print(f"\nMATCHES ({len(matches)})")
        counts: dict[str, int] = {}
        for m in matches:
            counts[m.status.value] = counts.get(m.status.value, 0) + 1
            winner = m.winner_team.short_name if m.winner_team else "-"
            print(
                f"  {m.cricheroes_match_key:>9} {str(m.start_time)[:16]} "
                f"{(m.stage_label or ''):<15} {m.team_a.short_name:>5} v "
                f"{m.team_b.short_name:<5} win={winner:<5} {m.status.value}"
            )
        print("\nSTATUS:", counts)


asyncio.run(main())
