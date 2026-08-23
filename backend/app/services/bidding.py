"""Bid validation rules per match stage."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, Match, MatchStage, MatchStatus, User


def compute_gap_range(total_a: int, total_b: int) -> tuple[int, int] | None:
    if total_a == 0 and total_b == 0:
        return None
    if total_a == 0:
        return (0, 0)
    lower = int(total_a * 0.7)
    upper = int(total_a * 1.3) + (1 if total_a * 1.3 > int(total_a * 1.3) else 0)
    if total_a == 100:
        lower = 0
        upper = 140
    return (0, lower) if total_b == 0 else (lower, upper)


def validate_gap(total_a: int, total_b: int) -> bool:
    if total_a == 0 or total_b == 0:
        return True
    if total_a == total_b:
        return False
    larger = max(total_a, total_b)
    smaller = min(total_a, total_b)
    if larger == 0:
        return True
    return abs(larger - smaller) / larger >= 0.30


async def get_team_totals(db: AsyncSession, match_id: int, user_id: int) -> dict[int, int]:
    result = await db.execute(
        select(Bid.team_id, func.sum(Bid.amount))
        .where(Bid.match_id == match_id, Bid.user_id == user_id)
        .group_by(Bid.team_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


async def validate_bid(
    db: AsyncSession,
    user: User,
    match: Match,
    team_id: int,
    amount: int,
) -> None:
    now = datetime.now(UTC)
    if match.status not in (MatchStatus.upcoming,):
        raise HTTPException(status_code=400, detail="Bidding is closed for this match")
    if now >= match.bid_deadline.replace(tzinfo=UTC) if match.bid_deadline.tzinfo is None else now >= match.bid_deadline:
        raise HTTPException(status_code=400, detail="Bid deadline has passed")
    if team_id not in (match.team_a_id, match.team_b_id):
        raise HTTPException(status_code=400, detail="Invalid team for this match")

    result = await db.execute(
        select(Bid).where(Bid.match_id == match.id, Bid.user_id == user.id)
    )
    existing = list(result.scalars().all())

    if match.stage == MatchStage.league:
        if len(existing) >= 3:
            raise HTTPException(status_code=400, detail="Maximum 3 bids per league match")
        if amount < 100:
            raise HTTPException(status_code=400, detail="Minimum wager is 100 points")
        totals = await get_team_totals(db, match.id, user.id)
        totals[team_id] = totals.get(team_id, 0) + amount
        ta = totals.get(match.team_a_id, 0)
        tb = totals.get(match.team_b_id, 0)
        if ta > 0 and tb > 0 and not validate_gap(ta, tb):
            raise HTTPException(
                status_code=400,
                detail=f"30% gap rule: totals must differ by at least 30%. Current A={ta}, B={tb}",
            )
        if user.points_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

    elif match.stage in (MatchStage.qualifier, MatchStage.eliminator):
        if existing:
            raise HTTPException(status_code=400, detail="Only 1 bid allowed in playoffs")
        min_wager = max(100, int(user.points_balance * 0.30))
        if amount < min_wager:
            raise HTTPException(status_code=400, detail=f"Minimum wager is {min_wager} points (30% of balance)")
        other_team = match.team_b_id if team_id == match.team_a_id else match.team_a_id
        if any(b.team_id == other_team for b in existing):
            raise HTTPException(status_code=400, detail="Must pick one team only in playoffs")
        if user.points_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

    elif match.stage == MatchStage.final:
        if existing:
            raise HTTPException(status_code=400, detail="Only 1 bid allowed in the final")
        amount = user.points_balance
        if amount <= 0:
            raise HTTPException(status_code=400, detail="No balance to wager in final")


async def get_bid_hints(db: AsyncSession, user: User, match: Match) -> dict:
    result = await db.execute(
        select(Bid).where(Bid.match_id == match.id, Bid.user_id == user.id)
    )
    existing = list(result.scalars().all())
    totals = await get_team_totals(db, match.id, user.id)

    max_bids = 3 if match.stage == MatchStage.league else 1
    min_amount = 100
    if match.stage in (MatchStage.qualifier, MatchStage.eliminator):
        min_amount = max(100, int(user.points_balance * 0.30))
    elif match.stage == MatchStage.final:
        min_amount = user.points_balance

    ta = totals.get(match.team_a_id, 0)
    tb = totals.get(match.team_b_id, 0)
    allowed = None
    if ta > 0 and match.stage == MatchStage.league:
        if tb == 0:
            lower = int(ta * 0.7)
            allowed = (0, lower) if ta > 100 else (0, 140)
        else:
            allowed = compute_gap_range(ta, tb)

    return {
        "min_amount": min_amount,
        "max_bids": max_bids,
        "current_bids": len(existing),
        "allowed_team_b_range": allowed,
        "team_totals": {"team_a": ta, "team_b": tb},
    }
