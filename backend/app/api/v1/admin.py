from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_admin, get_current_user
from app.core.rate_limit import limiter
from app.core.redis import acquire_lock, flag_sync_requested, release_lock
from app.db.base import get_db
from app.db.models import Match, MatchStatus, SyncRun, Tournament, User
from app.schemas import (
    AdminMatchOverride,
    MatchSummary,
    SyncRunResponse,
    TeamResponse,
    TournamentActivateRequest,
    TournamentActivateResponse,
    TournamentPreviewRequest,
    TournamentPreviewResponse,
    TournamentResponse,
)
from app.services.cricheroes.sync import sync_cricheroes
from app.services.settlement import settle_match
from app.services.tournaments import (
    OpenBidsError,
    SYNC_LOCK_KEY,
    SYNC_LOCK_TTL_SECONDS,
    activate_tournament,
    fetch_tournament_preview,
    get_active_tournament,
    list_archived_tournaments,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _tournament_response(t: Tournament) -> TournamentResponse:
    return TournamentResponse.model_validate(t)


@router.get("/tournaments/current", response_model=TournamentResponse | None)
async def current_tournament(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    tournament = await get_active_tournament(db)
    return _tournament_response(tournament) if tournament else None


@router.post("/tournaments/preview", response_model=TournamentPreviewResponse)
@limiter.limit("10/minute")
async def preview_tournament(
    request: Request,
    body: TournamentPreviewRequest,
    admin: User = Depends(get_current_admin),
):
    try:
        preview = await fetch_tournament_preview(body.ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return TournamentPreviewResponse(
        cricheroes_id=preview.cricheroes_id,
        slug=preview.slug,
        base_url=preview.base_url,
        display_name=preview.display_name,
        teams=preview.teams,
        match_count=preview.match_count,
        status_counts=preview.status_counts,
        biddable_count=preview.biddable_count,
        earliest_start=preview.earliest_start,
        latest_start=preview.latest_start,
    )


@router.post("/tournaments/activate", response_model=TournamentActivateResponse)
@limiter.limit("5/minute")
async def activate_tournament_endpoint(
    request: Request,
    body: TournamentActivateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if not await acquire_lock(SYNC_LOCK_KEY, ttl=SYNC_LOCK_TTL_SECONDS):
        raise HTTPException(status_code=409, detail="Tournament switch or sync already running")
    try:
        try:
            tournament = await activate_tournament(
                db,
                body.ref,
                admin_user_id=admin.id,
                confirm_reset=body.confirm_reset,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except OpenBidsError as e:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Open bids exist on the current tournament",
                    "open_bid_count": e.open_bid_count,
                    "requires_confirmation": True,
                },
            ) from e
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        run = (
            await db.execute(
                select(SyncRun)
                .where(SyncRun.tournament_id == tournament.id)
                .order_by(SyncRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one()

        return TournamentActivateResponse(
            tournament=_tournament_response(tournament),
            sync_status=run.status,
            matches_seen=run.matches_seen,
            matches_updated=run.matches_updated,
        )
    finally:
        await release_lock(SYNC_LOCK_KEY)


@router.get("/tournaments/archives", response_model=list[TournamentResponse])
async def archived_tournaments(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    archives = await list_archived_tournaments(db)
    return [_tournament_response(t) for t in archives]


@router.get("/tournaments/history", response_model=list[TournamentResponse])
async def tournament_history(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(Tournament).order_by(Tournament.created_at.desc()))
    return [_tournament_response(t) for t in result.scalars().all()]


@router.post("/sync", response_model=SyncRunResponse)
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if not await acquire_lock(SYNC_LOCK_KEY, ttl=SYNC_LOCK_TTL_SECONDS):
        raise HTTPException(status_code=409, detail="Sync already running")
    try:
        run = await sync_cricheroes(db)
        return run
    finally:
        await release_lock(SYNC_LOCK_KEY)


@router.post("/sync/request")
async def request_home_sync(admin: User = Depends(get_current_admin)):
    """Ask the home-PC agent to scrape CricHeroes. The Render host cannot."""
    await flag_sync_requested()
    return {
        "ok": True,
        "message": "Sync requested. Matches appear after your PC agent finishes scraping.",
    }


@router.get("/sync/runs", response_model=list[SyncRunResponse])
async def sync_runs(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    active = await get_active_tournament(db)
    q = select(SyncRun).order_by(SyncRun.started_at.desc()).limit(20)
    if active:
        q = q.where(SyncRun.tournament_id == active.id)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.patch("/matches/{match_id}")
async def override_match(
    match_id: int,
    body: AdminMatchOverride,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    active = await get_active_tournament(db)
    if not active:
        raise HTTPException(status_code=503, detail="No active tournament configured")

    result = await db.execute(
        select(Match)
        .where(Match.id == match_id, Match.tournament_id == active.id)
        .options(selectinload(Match.team_a), selectinload(Match.team_b), selectinload(Match.winner_team))
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if body.winner_team_id is not None and body.winner_team_id not in (
        match.team_a_id,
        match.team_b_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="Winner must be one of the two teams in this match",
        )

    match.manual_override = True
    if body.status:
        match.status = MatchStatus(body.status)
    if body.winner_team_id:
        match.winner_team_id = body.winner_team_id
    if body.result_raw:
        match.result_raw = body.result_raw

    if match.winner_team_id and match.status == MatchStatus.completed:
        await settle_match(db, match)

    return MatchSummary(
        id=match.id,
        stage=match.stage.value,
        status=match.status.value,
        venue=match.venue,
        start_time=match.start_time,
        bid_deadline=match.bid_deadline,
        multiplier=match.multiplier,
        team_a=TeamResponse.model_validate(match.team_a),
        team_b=TeamResponse.model_validate(match.team_b),
        winner_team=TeamResponse.model_validate(match.winner_team) if match.winner_team else None,
        result_raw=match.result_raw,
    )
