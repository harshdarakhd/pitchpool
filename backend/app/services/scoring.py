"""Scoring engine: parimutuel, streaks, penalties, season decay, badges."""

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    Badge,
    Bid,
    Match,
    MatchStage,
    MatchStatus,
    Streak,
    TransactionType,
    User,
    UserBadge,
)
from app.services.ledger import apply_transaction

STREAK_MILESTONES = {3: 100, 5: 300, 7: 500, 10: 1000, 15: 2000, 20: 3500, 25: 5000}

BADGE_DEFS = [
    ("first_blood", "First Blood", "Your first correct prediction", "🩸"),
    ("all_in", "All In", "Wager 1,000+ pts on a single match", "💰"),
    ("on_fire", "On Fire", "Reach a 7-win streak", "🔥"),
    ("oracle", "Oracle", "Reach a 10-win streak", "🔮"),
    ("unstoppable", "Unstoppable", "Reach a 15-win streak", "⚡"),
    ("legend", "Legend", "Reach a 20-win streak", "👑"),
    ("goat", "GOAT", "Reach a 25-win streak", "🐐"),
    ("survivor", "Survivor", "Win a bet with less than 500 pts remaining", "🛡️"),
]

SEASON_START = date(2026, 4, 17)
SEASON_CLOSE = date(2026, 5, 24)
SEASON_CAP_START = 5000
SEASON_CAP_FLOOR = 250
SEASON_DAYS = 37


def season_cap_for_date(d: date | None = None) -> int:
    d = d or date.today()
    if d >= SEASON_CLOSE:
        return SEASON_CAP_FLOOR
    day_index = max(0, (d - SEASON_START).days)
    decay_per_day = (SEASON_CAP_START - SEASON_CAP_FLOOR) / max(1, SEASON_DAYS - 1)
    cap = SEASON_CAP_START - int(decay_per_day * day_index)
    return max(SEASON_CAP_FLOOR, cap)


def compute_late_join_balance(completed_matches: int) -> int:
    settings = get_settings()
    penalty = completed_matches * settings.late_join_penalty_per_match
    return max(settings.late_join_floor, settings.starting_points - penalty)


def effective_pick_team(bids: list[Bid]) -> int | None:
    if not bids:
        return None
    if len({b.team_id for b in bids}) == 1:
        return bids[0].team_id
    return max(bids, key=lambda b: b.amount).team_id


def non_bid_penalty(stage: MatchStage, balance: int) -> int:
    if stage == MatchStage.league:
        return min(balance, 100)
    if stage in (MatchStage.qualifier, MatchStage.eliminator):
        return int(balance * 0.30)
    if stage == MatchStage.final:
        return balance
    return 0


async def ensure_badges_seeded(db: AsyncSession) -> None:
    for slug, name, desc, icon in BADGE_DEFS:
        result = await db.execute(select(Badge).where(Badge.slug == slug))
        if not result.scalar_one_or_none():
            db.add(Badge(slug=slug, name=name, description=desc, icon=icon))


async def award_badge(db: AsyncSession, user_id: int, slug: str) -> None:
    badge_result = await db.execute(select(Badge).where(Badge.slug == slug))
    badge = badge_result.scalar_one_or_none()
    if not badge:
        return
    existing = await db.execute(
        select(UserBadge).where(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
    )
    if existing.scalar_one_or_none():
        return
    db.add(UserBadge(user_id=user_id, badge_id=badge.id))


async def update_streak(
    db: AsyncSession,
    user: User,
    won: bool,
    match_id: int,
    *,
    tournament_id: int | None = None,
) -> int:
    result = await db.execute(select(Streak).where(Streak.user_id == user.id))
    streak = result.scalar_one_or_none()
    if not streak:
        streak = Streak(user_id=user.id, current=0, best=0)
        db.add(streak)

    bonus = 0
    if won:
        streak.current += 1
        streak.best = max(streak.best, streak.current)
        streak.last_result_match_id = match_id
        if streak.current in STREAK_MILESTONES:
            bonus = STREAK_MILESTONES[streak.current]
            await apply_transaction(
                db,
                user,
                bonus,
                TransactionType.streak_bonus,
                match_id=match_id,
                tournament_id=tournament_id,
                description=f"Streak milestone {streak.current} wins",
            )
        slug_map = {7: "on_fire", 10: "oracle", 15: "unstoppable", 20: "legend", 25: "goat"}
        if streak.current in slug_map:
            await award_badge(db, user.id, slug_map[streak.current])
    else:
        streak.current = 0
        streak.last_result_match_id = match_id

    return bonus


async def settle_match_payouts(
    db: AsyncSession,
    match: Match,
    winner_team_id: int,
) -> dict:
    """Settle parimutuel payouts. Returns summary stats."""
    bids_result = await db.execute(select(Bid).where(Bid.match_id == match.id))
    all_bids = list(bids_result.scalars().all())

    users_result = await db.execute(select(User))
    all_users = list(users_result.scalars().all())
    bidders = {b.user_id for b in all_bids}

    losing_pool = sum(b.amount for b in all_bids if b.team_id != winner_team_id)
    winning_pool = sum(b.amount for b in all_bids if b.team_id == winner_team_id)

    penalty_pool = 0
    for user in all_users:
        if user.id in bidders:
            continue
        penalty = non_bid_penalty(match.stage, user.points_balance)
        if penalty <= 0:
            continue
        penalty_pool += penalty
        await apply_transaction(
            db,
            user,
            -penalty,
            TransactionType.penalty,
            match_id=match.id,
            tournament_id=match.tournament_id,
            description=f"Non-bid penalty ({match.stage.value})",
        )

    profit_pool = int((losing_pool + penalty_pool) * match.multiplier)
    payouts: dict[int, int] = {}

    for bid in all_bids:
        if bid.team_id != winner_team_id:
            continue
        user = next(u for u in all_users if u.id == bid.user_id)
        share = (bid.amount / winning_pool * profit_pool) if winning_pool else 0
        net = int(share)
        payouts[user.id] = payouts.get(user.id, 0) + net + bid.amount

    for user_id, total in payouts.items():
        user = next(u for u in all_users if u.id == user_id)
        user_bids = [b for b in all_bids if b.user_id == user_id and b.team_id == winner_team_id]
        wager = sum(b.amount for b in user_bids)
        profit = total - wager
        await apply_transaction(
            db,
            user,
            profit,
            TransactionType.payout,
            match_id=match.id,
            tournament_id=match.tournament_id,
            description=f"Match payout (+{profit} net)",
        )
        if wager >= 1000:
            await award_badge(db, user.id, "all_in")
        if user.points_balance - profit < 500 and profit > 0:
            await award_badge(db, user.id, "survivor")

    for user in all_users:
        user_bids = [b for b in all_bids if b.user_id == user.id]
        if not user_bids:
            continue
        pick = effective_pick_team(user_bids)
        won = pick == winner_team_id
        await update_streak(db, user, won, match.id, tournament_id=match.tournament_id)
        if won:
            count_result = await db.execute(
                select(func.count())
                .select_from(Bid)
                .join(Match, Match.id == Bid.match_id)
                .where(
                    Bid.user_id == user.id,
                    Match.status == MatchStatus.completed,
                    Match.settled_at.isnot(None),
                )
            )
            if count_result.scalar() == 1:
                await award_badge(db, user.id, "first_blood")

    return {"profit_pool": profit_pool, "winning_pool": winning_pool, "payouts": payouts}
