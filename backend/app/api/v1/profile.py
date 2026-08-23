from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.services.tournaments import get_active_tournament
from app.db.base import get_db
from app.db.models import Badge, Bid, Match, MatchStatus, Streak, Transaction, TransactionType, User, UserBadge
from app.schemas import LeaderboardEntry, ProfileStats, TransactionResponse, UserResponse

router = APIRouter(tags=["leaderboard", "profile"])


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await get_active_tournament(db)

    result = await db.execute(select(User).order_by(User.points_balance.desc()))
    users = list(result.scalars().all())
    entries = []
    for rank, u in enumerate(users, 1):
        streak_r = await db.execute(select(Streak).where(Streak.user_id == u.id))
        streak = streak_r.scalar_one_or_none()
        badge_r = await db.execute(select(func.count()).select_from(UserBadge).where(UserBadge.user_id == u.id))
        badge_count = badge_r.scalar() or 0

        wins = 0
        total = 0
        if active:
            bids_r = await db.execute(
                select(Bid, Match.winner_team_id)
                .join(Match, Match.id == Bid.match_id)
                .where(
                    Bid.user_id == u.id,
                    Match.tournament_id == active.id,
                    Match.status == MatchStatus.completed,
                )
            )
            for bid, winner_team_id in bids_r.all():
                total += 1
                if winner_team_id == bid.team_id:
                    wins += 1

        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_id=u.id,
                display_name=u.display_name,
                points_balance=u.points_balance,
                win_rate=round(wins / total * 100, 1) if total else 0,
                current_streak=streak.current if streak else 0,
                best_streak=streak.best if streak else 0,
                badge_count=badge_count,
            )
        )
    return entries


@router.get("/profile/stats", response_model=ProfileStats)
async def profile_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    streak_r = await db.execute(select(Streak).where(Streak.user_id == user.id))
    streak = streak_r.scalar_one_or_none()

    badges_r = await db.execute(
        select(UserBadge, Badge)
        .join(Badge, Badge.id == UserBadge.badge_id)
        .where(UserBadge.user_id == user.id)
    )
    badges = [
        {"slug": b.slug, "name": b.name, "icon": b.icon, "earned_at": ub.earned_at.isoformat()}
        for ub, b in badges_r.all()
    ]

    active = await get_active_tournament(db)

    tx_q = select(func.sum(Transaction.delta)).where(
        Transaction.user_id == user.id,
        Transaction.type.in_(["payout", "penalty", "bid"]),
    )
    if active:
        tx_q = tx_q.where(Transaction.tournament_id == active.id)
    tx_r = await db.execute(tx_q)
    net = tx_r.scalar() or 0

    wins = losses = 0
    if active:
        bids_r = await db.execute(
            select(Bid, Match)
            .join(Match, Match.id == Bid.match_id)
            .where(Bid.user_id == user.id, Match.tournament_id == active.id)
        )
        for bid, m in bids_r.all():
            if m.status != MatchStatus.completed:
                continue
            if m.winner_team_id == bid.team_id:
                wins += 1
            else:
                losses += 1

    milestones = [
        {"wins": 3, "bonus": 100},
        {"wins": 5, "bonus": 300},
        {"wins": 7, "bonus": 500},
        {"wins": 10, "bonus": 1000},
        {"wins": 15, "bonus": 2000},
        {"wins": 20, "bonus": 3500},
        {"wins": 25, "bonus": 5000},
    ]

    return ProfileStats(
        user=UserResponse.model_validate(user),
        win_rate=round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0,
        wins=wins,
        losses=losses,
        net_profit=int(net),
        current_streak=streak.current if streak else 0,
        best_streak=streak.best if streak else 0,
        badges=badges,
        streak_milestones=milestones,
    )


@router.get("/profile/transactions", response_model=list[TransactionResponse])
async def profile_transactions(
    tx_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await get_active_tournament(db)
    q = select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.created_at.desc()).limit(100)
    if active:
        q = q.where(Transaction.tournament_id == active.id)
    if tx_type and tx_type != "all":
        q = q.where(Transaction.type == TransactionType(tx_type))
    result = await db.execute(q)
    return list(result.scalars().all())
