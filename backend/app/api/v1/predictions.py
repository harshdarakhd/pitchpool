from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_admin, get_current_user
from app.db.base import get_db
from app.db.models import Match, QuizAnswer, QuizQuestion, SeasonBet, User
from app.schemas import (
    QuizAnswerRequest,
    QuizCreateRequest,
    QuizQuestionResponse,
    SeasonBetRequest,
    SeasonBetResponse,
)
from app.services.predictions import get_community_picks, place_season_bet, submit_quiz_answer
from app.services.tournaments import get_active_tournament, require_active_tournament
from app.services.scoring import season_cap_for_date
from app.db.models import SeasonCategory

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/quiz/{match_id}", response_model=list[QuizQuestionResponse])
async def get_quiz(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(QuizQuestion).where(QuizQuestion.match_id == match_id))
    questions = list(result.scalars().all())
    out = []
    for q in questions:
        ans_result = await db.execute(
            select(QuizAnswer).where(
                QuizAnswer.question_id == q.id,
                QuizAnswer.user_id == user.id,
            )
        )
        ans = ans_result.scalar_one_or_none()
        out.append(
            QuizQuestionResponse(
                id=q.id,
                match_id=q.match_id,
                text=q.text,
                options=q.options,
                points=q.points,
                locks_at=q.locks_at,
                user_answer=ans.chosen_option if ans else None,
            )
        )
    return out


@router.post("/quiz/answer")
async def answer_quiz(
    body: QuizAnswerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ans = await submit_quiz_answer(db, user, body.question_id, body.chosen_option)
    return {"ok": True, "chosen_option": ans.chosen_option}


@router.get("/season", response_model=list[SeasonBetResponse])
async def my_season_bets(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await require_active_tournament(db)
    result = await db.execute(
        select(SeasonBet).where(
            SeasonBet.user_id == user.id,
            SeasonBet.tournament_id == active.id,
        )
    )
    bets = list(result.scalars().all())
    current_cap = season_cap_for_date()
    return [
        SeasonBetResponse(
            id=b.id,
            category=b.category.value,
            pick=b.pick,
            locked_cap=b.locked_cap,
            placed_at=b.placed_at,
            result=b.result.value,
            payout=b.payout,
            current_cap=current_cap,
        )
        for b in bets
    ]


@router.post("/season", response_model=SeasonBetResponse)
async def create_season_bet(
    body: SeasonBetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bet = await place_season_bet(db, user, body.category, body.pick)
    return SeasonBetResponse(
        id=bet.id,
        category=bet.category.value,
        pick=bet.pick,
        locked_cap=bet.locked_cap,
        placed_at=bet.placed_at,
        result=bet.result.value,
        payout=bet.payout,
        current_cap=season_cap_for_date(),
    )


@router.get("/season/community/{category}")
async def season_community(
    category: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        cat = SeasonCategory(category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid category") from e
    return await get_community_picks(db, cat)


@router.post("/admin/quiz", dependencies=[Depends(get_current_admin)])
async def admin_create_quiz(
    body: QuizCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    active = await require_active_tournament(db)
    result = await db.execute(
        select(Match).where(Match.id == body.match_id, Match.tournament_id == active.id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    q = QuizQuestion(
        match_id=body.match_id,
        text=body.text,
        options=body.options,
        correct_option=body.correct_option,
        points=body.points,
        locks_at=match.bid_deadline,
    )
    db.add(q)
    await db.flush()
    return {"id": q.id}
