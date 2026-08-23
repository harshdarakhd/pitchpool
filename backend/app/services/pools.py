"""Update match pool aggregates after bids."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import publish_event
from app.db.models import Bid, MatchPool


async def refresh_match_pools(db: AsyncSession, match_id: int) -> list[MatchPool]:
    result = await db.execute(select(Bid).where(Bid.match_id == match_id))
    bids = list(result.scalars().all())

    team_stats: dict[int, tuple[int, set[int]]] = {}
    for bid in bids:
        total, bidders = team_stats.get(bid.team_id, (0, set()))
        total += bid.amount
        bidders.add(bid.user_id)
        team_stats[bid.team_id] = (total, bidders)

    pool_result = await db.execute(select(MatchPool).where(MatchPool.match_id == match_id))
    pools = {p.team_id: p for p in pool_result.scalars().all()}

    for team_id, (total, bidders) in team_stats.items():
        if team_id in pools:
            pools[team_id].total_wager = total
            pools[team_id].bidder_count = len(bidders)
        else:
            pool = MatchPool(
                match_id=match_id,
                team_id=team_id,
                total_wager=total,
                bidder_count=len(bidders),
            )
            db.add(pool)
            pools[team_id] = pool

    await db.flush()

    await publish_event(
        "events",
        {
            "type": "pool_updated",
            "match_id": match_id,
            "pools": [
                {"team_id": tid, "total_wager": t, "bidder_count": len(b)}
                for tid, (t, b) in team_stats.items()
            ],
        },
    )
    return list(pools.values())
