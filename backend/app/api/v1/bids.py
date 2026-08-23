from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models import Bid, Match, MatchStage, TransactionType, User
from app.schemas import BidResponse, BidValidationHint, PlaceBidRequest
from app.services.bidding import get_bid_hints, validate_bid
from app.services.ledger import apply_transaction
from app.services.pools import refresh_match_pools
from app.services.tournaments import require_active_tournament

router = APIRouter(prefix="/bids", tags=["bids"])


@router.get("/hints/{match_id}", response_model=BidValidationHint)
async def bid_hints(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await require_active_tournament(db)
    result = await db.execute(
        select(Match).where(Match.id == match_id, Match.tournament_id == active.id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    hints = await get_bid_hints(db, user, match)
    return BidValidationHint(**hints)


@router.post("", response_model=BidResponse)
@limiter.limit("30/minute")
async def place_bid(
    request: Request,
    body: PlaceBidRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await require_active_tournament(db)
    result = await db.execute(
        select(Match).where(Match.id == body.match_id, Match.tournament_id == active.id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    amount = body.amount
    if match.stage == MatchStage.final:
        amount = user.points_balance

    await validate_bid(db, user, match, body.team_id, amount)

    bid = Bid(user_id=user.id, match_id=match.id, team_id=body.team_id, amount=amount)
    db.add(bid)
    await apply_transaction(
        db,
        user,
        -amount,
        TransactionType.bid,
        match_id=match.id,
        tournament_id=match.tournament_id,
        description=f"Bid {amount} on match {match.id}",
    )
    await db.flush()
    await refresh_match_pools(db, match.id)

    result = await db.execute(
        select(Bid).where(Bid.id == bid.id).options(selectinload(Bid.team))
    )
    return result.scalar_one()


@router.get("/mine", response_model=list[BidResponse])
async def my_bids(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Bid).where(Bid.user_id == user.id).options(selectinload(Bid.team)).order_by(Bid.created_at.desc())
    )
    return list(result.scalars().all())
