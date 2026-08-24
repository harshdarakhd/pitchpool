"""Reusable per-match quizzes that score themselves from the fixture result."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Match, MatchStatus, QuizQuestion, Team

WINNER_KIND = "winner"
COMPLETED_KIND = "completed"


def _winner_options(team_a: Team, team_b: Team) -> dict[str, str]:
    return {
        "A": team_a.name,
        "B": team_b.name,
        "C": "No result / abandoned",
    }


async def ensure_match_quizzes(
    db: AsyncSession,
    match: Match,
    team_a: Team,
    team_b: Team,
) -> None:
    """Attach the standard quiz pack to an upcoming match if it has none.

    Historical fixtures are imported already finished, so they are skipped —
    there is nothing left for users to answer.
    """
    if match.status not in (MatchStatus.upcoming, MatchStatus.locked):
        return

    existing = await db.execute(select(QuizQuestion.id).where(QuizQuestion.match_id == match.id))
    if existing.first() is not None:
        return

    locks_at = match.bid_deadline
    db.add(
        QuizQuestion(
            match_id=match.id,
            kind=WINNER_KIND,
            text=f"Who will win {team_a.name} vs {team_b.name}?",
            options=_winner_options(team_a, team_b),
            correct_option=None,
            points=100,
            locks_at=locks_at,
        )
    )
    db.add(
        QuizQuestion(
            match_id=match.id,
            kind=COMPLETED_KIND,
            text="Will this match produce a winner (not abandoned / no result)?",
            options={"A": "Yes", "B": "No"},
            correct_option=None,
            points=100,
            locks_at=locks_at,
        )
    )
    await db.flush()


async def resolve_auto_quiz_answers(db: AsyncSession, match: Match) -> None:
    """Fill in correct options from the match result before scoring."""
    if match.team_a is None or match.team_b is None:
        loaded = await db.execute(
            select(Match)
            .where(Match.id == match.id)
            .options(selectinload(Match.team_a), selectinload(Match.team_b))
        )
        match = loaded.scalar_one()

    result = await db.execute(select(QuizQuestion).where(QuizQuestion.match_id == match.id))
    for question in result.scalars().all():
        if question.kind == WINNER_KIND:
            if match.status == MatchStatus.no_result:
                question.correct_option = "C"
            elif match.winner_team_id == match.team_a_id:
                question.correct_option = "A"
            elif match.winner_team_id == match.team_b_id:
                question.correct_option = "B"
        elif question.kind == COMPLETED_KIND:
            question.correct_option = "B" if match.status == MatchStatus.no_result else "A"
    await db.flush()
