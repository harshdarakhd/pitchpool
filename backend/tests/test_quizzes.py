from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import Match, MatchStage, MatchStatus, QuizQuestion, Team, Tournament, TournamentStatus
from app.services.quizzes import COMPLETED_KIND, WINNER_KIND, ensure_match_quizzes, resolve_auto_quiz_answers


async def _open_match(db) -> Match:
    tournament = Tournament(
        cricheroes_id=1,
        slug="t",
        base_url="https://cricheroes.com/tournament/1/t",
        status=TournamentStatus.active,
    )
    db.add(tournament)
    await db.flush()
    team_a = Team(tournament_id=tournament.id, name="Rajwada Royals", short_name="RR")
    team_b = Team(tournament_id=tournament.id, name="Eagles Warriors", short_name="EW")
    db.add_all([team_a, team_b])
    await db.flush()
    start = datetime.now(UTC) + timedelta(days=1)
    match = Match(
        tournament_id=tournament.id,
        cricheroes_match_key="m1",
        stage=MatchStage.league,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        start_time=start,
        bid_deadline=start - timedelta(minutes=15),
        status=MatchStatus.upcoming,
    )
    db.add(match)
    await db.flush()
    return match, team_a, team_b


@pytest.mark.asyncio
async def test_open_match_gets_reusable_quiz_pack(db_session):
    match, team_a, team_b = await _open_match(db_session)
    await ensure_match_quizzes(db_session, match, team_a, team_b)
    await ensure_match_quizzes(db_session, match, team_a, team_b)

    questions = list(
        (await db_session.execute(select(QuizQuestion).where(QuizQuestion.match_id == match.id)))
        .scalars()
        .all()
    )
    assert {q.kind for q in questions} == {WINNER_KIND, COMPLETED_KIND}
    assert len(questions) == 2
    winner = next(q for q in questions if q.kind == WINNER_KIND)
    assert winner.options["A"] == "Rajwada Royals"
    assert winner.options["C"] == "No result / abandoned"


@pytest.mark.asyncio
async def test_completed_import_does_not_get_a_quiz(db_session):
    match, team_a, team_b = await _open_match(db_session)
    match.status = MatchStatus.completed
    await ensure_match_quizzes(db_session, match, team_a, team_b)
    count = (
        await db_session.execute(select(QuizQuestion).where(QuizQuestion.match_id == match.id))
    ).scalars().all()
    assert count == []


@pytest.mark.asyncio
async def test_resolve_sets_correct_options_from_result(db_session):
    match, team_a, team_b = await _open_match(db_session)
    await ensure_match_quizzes(db_session, match, team_a, team_b)
    match.status = MatchStatus.completed
    match.winner_team_id = team_a.id
    await resolve_auto_quiz_answers(db_session, match)

    questions = {
        q.kind: q
        for q in (
            await db_session.execute(select(QuizQuestion).where(QuizQuestion.match_id == match.id))
        )
        .scalars()
        .all()
    }
    assert questions[WINNER_KIND].correct_option == "A"
    assert questions[COMPLETED_KIND].correct_option == "A"
