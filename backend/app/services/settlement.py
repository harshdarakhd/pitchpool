"""Match settlement orchestration."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import publish_event
from app.db.models import (
    Bid,
    Match,
    MatchStatus,
    QuizAnswer,
    QuizQuestion,
    TransactionType,
)
from app.services.ledger import apply_transaction
from app.services.quizzes import resolve_auto_quiz_answers
from app.services.scoring import ensure_badges_seeded, settle_match_payouts


async def refund_match(db: AsyncSession, match: Match) -> None:
    from app.db.models import User

    result = await db.execute(select(Bid).where(Bid.match_id == match.id))
    bids = list(result.scalars().all())
    for bid in bids:
        u_result = await db.execute(select(User).where(User.id == bid.user_id))
        user = u_result.scalar_one()
        await apply_transaction(
            db,
            user,
            bid.amount,
            TransactionType.refund,
            match_id=match.id,
            tournament_id=match.tournament_id,
            description="Match no result — bid refunded",
        )


async def score_quizzes(db: AsyncSession, match: Match) -> None:
    q_result = await db.execute(select(QuizQuestion).where(QuizQuestion.match_id == match.id))
    questions = list(q_result.scalars().all())
    for q in questions:
        if not q.correct_option:
            continue
        a_result = await db.execute(select(QuizAnswer).where(QuizAnswer.question_id == q.id))
        for ans in a_result.scalars().all():
            correct = ans.chosen_option == q.correct_option
            ans.is_correct = correct
            if correct and ans.awarded_points == 0:
                ans.awarded_points = q.points
                from app.db.models import User

                u_result = await db.execute(select(User).where(User.id == ans.user_id))
                user_obj = u_result.scalar_one()
                await apply_transaction(
                    db,
                    user_obj,
                    q.points,
                    TransactionType.quiz,
                    match_id=match.id,
                    tournament_id=match.tournament_id,
                    description=f"Quiz correct: {q.text[:50]}",
                )


async def settle_match(db: AsyncSession, match: Match) -> dict:
    if match.settled_at:
        return {"status": "already_settled"}

    await ensure_badges_seeded(db)

    if match.status == MatchStatus.no_result:
        await refund_match(db, match)
        await resolve_auto_quiz_answers(db, match)
        await score_quizzes(db, match)
        match.settled_at = datetime.now(UTC)
        await db.flush()
        return {"status": "refunded"}

    if not match.winner_team_id:
        return {"status": "no_winner"}

    summary = await settle_match_payouts(db, match, match.winner_team_id)
    await resolve_auto_quiz_answers(db, match)
    await score_quizzes(db, match)
    match.settled_at = datetime.now(UTC)
    match.status = MatchStatus.completed
    await db.flush()

    await publish_event(
        "events",
        {
            "type": "match_settled",
            "match_id": match.id,
            "winner_team_id": match.winner_team_id,
            "profit_pool": summary["profit_pool"],
        },
    )
    await publish_event("events", {"type": "leaderboard_updated"})

    return {"status": "settled", **summary}
