from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.core.deps import get_current_user
from app.db.base import get_db
from app.db.models import Bid, Match, MatchPool, MatchStatus, User
from app.schemas import BidResponse, MatchDetail, MatchPoolResponse, MatchSummary, TeamResponse
from app.services.tournaments import get_active_tournament, require_active_tournament

router = APIRouter(prefix="/matches", tags=["matches"])


def _match_summary(m: Match) -> MatchSummary:
    return MatchSummary(
        id=m.id,
        stage=m.stage.value,
        stage_label=m.stage_label,
        status=m.status.value,
        venue=m.venue,
        start_time=m.start_time,
        bid_deadline=m.bid_deadline,
        multiplier=m.multiplier,
        team_a=TeamResponse.model_validate(m.team_a),
        team_b=TeamResponse.model_validate(m.team_b),
        winner_team=TeamResponse.model_validate(m.winner_team) if m.winner_team else None,
        result_raw=m.result_raw,
    )


@router.get("", response_model=list[MatchSummary])
async def list_matches(
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await get_active_tournament(db)
    if not active:
        return []

    q = select(Match).where(Match.tournament_id == active.id).options(
        selectinload(Match.team_a),
        selectinload(Match.team_b),
        selectinload(Match.winner_team),
    ).order_by(Match.start_time.desc())

    if status_filter == "upcoming":
        q = q.where(Match.status == MatchStatus.upcoming)
    elif status_filter == "awaiting":
        q = q.where(Match.status == MatchStatus.awaiting_result)
    elif status_filter == "completed":
        q = q.where(Match.status == MatchStatus.completed)
    elif status_filter == "locked":
        q = q.where(Match.status == MatchStatus.locked)

    result = await db.execute(q)
    return [_match_summary(m) for m in result.scalars().all()]


@router.get("/{match_id}", response_model=MatchDetail)
async def get_match(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await require_active_tournament(db)
    result = await db.execute(
        select(Match)
        .where(Match.id == match_id, Match.tournament_id == active.id)
        .options(
            selectinload(Match.team_a),
            selectinload(Match.team_b),
            selectinload(Match.winner_team),
            selectinload(Match.pools).selectinload(MatchPool.team),
        )
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    bids_result = await db.execute(
        select(Bid).where(Bid.match_id == match_id, Bid.user_id == user.id).options(selectinload(Bid.team))
    )
    user_bids = list(bids_result.scalars().all())

    pools = [
        MatchPoolResponse(
            team_id=p.team_id,
            team=TeamResponse.model_validate(p.team),
            total_wager=p.total_wager,
            bidder_count=p.bidder_count,
        )
        for p in match.pools
    ]

    summary = _match_summary(match)
    return MatchDetail(
        **summary.model_dump(),
        pools=pools,
        user_bid_count=len(user_bids),
        user_bids=[BidResponse.model_validate(b) for b in user_bids],
    )


@router.get("/{match_id}/bidders")
async def list_bidders(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await require_active_tournament(db)
    result = await db.execute(
        select(Bid, User)
        .join(User, User.id == Bid.user_id)
        .join(Match, Match.id == Bid.match_id)
        .where(Bid.match_id == match_id, Match.tournament_id == active.id)
        .order_by(Bid.amount.desc())
    )
    rows = result.all()
    return [
        {
            "user_id": u.id,
            "display_name": u.display_name,
            "team_id": b.team_id,
            "amount": b.amount,
        }
        for b, u in rows
    ]
