"""Sync CricHeroes tournament data into local DB."""

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Match, MatchPool, MatchStage, MatchStatus, SyncRun, Team, Tournament
from app.services.cricheroes.client import fetch_all_match_tabs
from app.services.cricheroes.parser import parse_matches_from_pages, parse_teams_from_html
from app.services.settlement import settle_match
from app.services.tournaments import ensure_active_tournament, update_tournament_counts

logger = logging.getLogger(__name__)

_STOPWORDS = {"xi", "the", "of"}


def _short_name(name: str) -> str:
    """Build a 2-4 char abbreviation, e.g. 'Markup Ultimate Warriors' -> 'MUW'."""
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    initials = [w[0] for w in words if w.lower() not in _STOPWORDS and w[0].isalnum()]
    if len(initials) >= 2:
        return "".join(initials[:4]).upper()
    compact = re.sub(r"[^A-Za-z0-9]", "", name)
    return (compact[:4] or "TBD").upper()


async def _get_or_create_team(db: AsyncSession, tournament_id: int, name: str) -> Team:
    result = await db.execute(
        select(Team).where(Team.tournament_id == tournament_id, Team.name == name)
    )
    team = result.scalar_one_or_none()
    if team:
        return team

    short = _short_name(name)
    existing = await db.execute(
        select(Team.short_name).where(Team.tournament_id == tournament_id)
    )
    taken = {s for (s,) in existing.all()}
    if short in taken:
        base = short
        for i in range(2, 100):
            candidate = f"{base[:3]}{i}"
            if candidate not in taken:
                short = candidate
                break

    team = Team(tournament_id=tournament_id, name=name, short_name=short)
    db.add(team)
    await db.flush()
    return team


async def sync_cricheroes(
    db: AsyncSession,
    *,
    tournament: Tournament | None = None,
    pages: list[str] | None = None,
) -> SyncRun:
    tournament = tournament or await ensure_active_tournament(db)
    base_url = tournament.base_url

    run = SyncRun(status="running", tournament_id=tournament.id)
    db.add(run)
    await db.flush()

    try:
        pages = pages or await fetch_all_match_tabs(base_url)
        if not pages:
            raise RuntimeError("CricHeroes returned no usable pages (blocked or offline)")

        for name in parse_teams_from_html(pages[0]):
            await _get_or_create_team(db, tournament.id, name)

        parsed = parse_matches_from_pages(pages)
        run.matches_seen = len(parsed)
        updated = 0

        settings = get_settings()
        bid_deadline_minutes = settings.bid_deadline_minutes

        status_map = {
            "completed": MatchStatus.completed,
            "upcoming": MatchStatus.upcoming,
            "locked": MatchStatus.locked,
            "no_result": MatchStatus.no_result,
        }

        for item in parsed:
            if not item.get("start_time"):
                logger.warning(
                    "Skipping CricHeroes match %s: no parsable date",
                    item.get("cricheroes_match_key"),
                )
                continue

            team_a = await _get_or_create_team(db, tournament.id, item["team_a_name"])
            team_b = await _get_or_create_team(db, tournament.id, item["team_b_name"])

            result = await db.execute(
                select(Match).where(
                    Match.tournament_id == tournament.id,
                    Match.cricheroes_match_key == item["cricheroes_match_key"],
                )
            )
            match = result.scalar_one_or_none()

            start_time = item["start_time"]
            bid_deadline = start_time - timedelta(minutes=bid_deadline_minutes)
            status = status_map.get(item["status"], MatchStatus.upcoming)

            winner_id = None
            if item.get("winner_name"):
                name = item["winner_name"]
                if name == team_a.name:
                    winner_id = team_a.id
                elif name == team_b.name:
                    winner_id = team_b.id
                else:
                    w_result = await db.execute(
                        select(Team).where(Team.tournament_id == tournament.id, Team.name == name)
                    )
                    winner = w_result.scalar_one_or_none()
                    winner_id = winner.id if winner else None
                    if winner_id is None:
                        logger.warning(
                            "Winner %r not in match %s (%s vs %s)",
                            name,
                            item["cricheroes_match_key"],
                            team_a.name,
                            team_b.name,
                        )

            if match:
                if match.manual_override:
                    continue
                old_status = match.status
                match.stage = MatchStage(item.get("stage", "league"))
                match.stage_label = item.get("stage_label")
                match.venue = item.get("venue")
                match.start_time = start_time
                match.bid_deadline = bid_deadline
                match.status = status
                match.result_raw = item.get("result_raw")
                if winner_id:
                    match.winner_team_id = winner_id
                if (
                    old_status != MatchStatus.completed
                    and status == MatchStatus.completed
                    and winner_id
                ):
                    await settle_match(db, match)
                updated += 1
            else:
                match = Match(
                    tournament_id=tournament.id,
                    cricheroes_match_key=item["cricheroes_match_key"],
                    stage=MatchStage(item.get("stage", "league")),
                    stage_label=item.get("stage_label"),
                    team_a_id=team_a.id,
                    team_b_id=team_b.id,
                    venue=item.get("venue"),
                    start_time=start_time,
                    bid_deadline=bid_deadline,
                    status=status,
                    winner_team_id=winner_id,
                    result_raw=item.get("result_raw"),
                )
                if status in (MatchStatus.completed, MatchStatus.no_result):
                    match.settled_at = datetime.now(UTC)

                db.add(match)
                await db.flush()
                db.add(MatchPool(match_id=match.id, team_id=team_a.id))
                db.add(MatchPool(match_id=match.id, team_id=team_b.id))
                updated += 1

        run.matches_updated = updated
        run.status = "success"
        tournament.last_sync_at = datetime.now(UTC)
        await update_tournament_counts(db, tournament.id)
    except Exception as e:
        logger.exception("Sync failed")
        run.status = "failed"
        run.error = str(e)
    finally:
        run.finished_at = datetime.now(UTC)
        await db.flush()

    return run
