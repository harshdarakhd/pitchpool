"""Quiz and season bet services."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import QuizAnswer, QuizQuestion, SeasonBet, SeasonCategory, SeasonResult, User
from app.services.scoring import season_cap_for_date
from app.services.tournaments import get_active_tournament, require_active_tournament


async def submit_quiz_answer(
    db: AsyncSession,
    user: User,
    question_id: int,
    chosen_option: str,
) -> QuizAnswer:
    result = await db.execute(select(QuizQuestion).where(QuizQuestion.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    now = datetime.now(UTC)
    locks_at = question.locks_at.replace(tzinfo=UTC) if question.locks_at.tzinfo is None else question.locks_at
    if now >= locks_at:
        raise HTTPException(status_code=400, detail="Quiz deadline has passed")

    existing = await db.execute(
        select(QuizAnswer).where(
            QuizAnswer.user_id == user.id,
            QuizAnswer.question_id == question_id,
        )
    )
    answer = existing.scalar_one_or_none()
    if answer:
        answer.chosen_option = chosen_option
        answer.updated_at = now
    else:
        answer = QuizAnswer(
            user_id=user.id,
            question_id=question_id,
            chosen_option=chosen_option,
        )
        db.add(answer)
    await db.flush()
    return answer


async def place_season_bet(
    db: AsyncSession,
    user: User,
    category: str,
    pick: str,
) -> SeasonBet:
    try:
        cat = SeasonCategory(category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid season category") from e

    active = await require_active_tournament(db)

    existing = await db.execute(
        select(SeasonBet).where(
            SeasonBet.user_id == user.id,
            SeasonBet.category == cat,
            SeasonBet.tournament_id == active.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already placed bet for this category")

    cap = season_cap_for_date()
    bet = SeasonBet(
        user_id=user.id,
        tournament_id=active.id,
        category=cat,
        pick=pick,
        locked_cap=cap,
    )
    db.add(bet)
    await db.flush()
    return bet


async def get_community_picks(db: AsyncSession, category: SeasonCategory) -> list[dict]:
    active = await get_active_tournament(db)
    if not active:
        return []

    result = await db.execute(
        select(SeasonBet).where(
            SeasonBet.category == category,
            SeasonBet.tournament_id == active.id,
        )
    )
    bets = list(result.scalars().all())
    if not bets:
        return []
    counts: dict[str, int] = {}
    for b in bets:
        counts[b.pick] = counts.get(b.pick, 0) + 1
    total = len(bets)
    ranked = sorted(counts.items(), key=lambda x: -x[1])
    return [
        {"pick": pick, "count": count, "pct": round(count / total * 100, 1)}
        for pick, count in ranked[:10]
    ]
