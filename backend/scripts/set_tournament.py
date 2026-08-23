"""Point PitchPool at a different CricHeroes tournament.

Usage:
    python scripts/set_tournament.py <tournament-url-or-id> [--confirm-reset] [--dry-run]

``--dry-run``         fetch and report what would be imported, change nothing.
``--confirm-reset``   allow activation when open bids exist on the current tournament.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from app.db.base import AsyncSessionLocal, engine  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.services.tournaments import (  # noqa: E402
    OpenBidsError,
    activate_tournament,
    fetch_tournament_preview,
    get_active_tournament,
    parse_tournament_ref,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Switch the tracked CricHeroes tournament.")
    parser.add_argument("ref", help="CricHeroes tournament URL or numeric ID")
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="confirm reset when open bids exist on the current tournament",
    )
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = parser.parse_args()

    try:
        cricheroes_id, slug, url = parse_tournament_ref(args.ref)
    except ValueError as e:
        raise SystemExit(str(e)) from e

    print(f"Tournament: {url}\nFetching preview...")
    preview = await fetch_tournament_preview(args.ref)
    print(f"  id:      {preview.cricheroes_id}")
    print(f"  name:    {preview.display_name}")
    print(f"  teams:   {len(preview.teams)}")
    print(f"  matches: {preview.match_count}  {preview.status_counts}")
    print(f"  biddable fixtures: {preview.biddable_count}")

    if args.dry_run:
        print("\nDry run - nothing written.")
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        current = await get_active_tournament(db)
        if current and current.cricheroes_id == cricheroes_id and current.slug == slug:
            print("\nTournament is already active.")
            return

        try:
            tournament = await activate_tournament(
                db,
                args.ref,
                confirm_reset=args.confirm_reset,
            )
        except OpenBidsError as e:
            raise SystemExit(
                f"\n{e}. Re-run with --confirm-reset to archive anyway."
            ) from e

        await db.commit()
        print(
            f"\nActivated tournament #{tournament.id}: {tournament.display_name} "
            f"({tournament.match_count} matches)"
        )


if __name__ == "__main__":
    asyncio.run(main())
