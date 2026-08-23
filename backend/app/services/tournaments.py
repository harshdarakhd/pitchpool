"""Tournament lifecycle: preview, activation, archive, and active-tournament helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    Bid,
    Match,
    MatchStatus,
    Streak,
    Tournament,
    TournamentStatus,
    User,
)
from app.services.cricheroes.client import fetch_all_match_tabs
from app.services.cricheroes.parser import (
    parse_matches_from_pages,
    parse_teams_from_html,
    parse_tournament_name_from_html,
)

logger = logging.getLogger(__name__)

SYNC_LOCK_KEY = "sync:cricheroes"
# A full three-tab Playwright scrape can exceed five minutes on free hosting.
SYNC_LOCK_TTL_SECONDS = 900

URL_RE = re.compile(
    r"^https://cricheroes\.com/tournament/(\d+)/([a-z0-9-]+)$",
    re.IGNORECASE,
)
ID_RE = re.compile(r"^\d+$")


@dataclass
class TournamentPreview:
    cricheroes_id: int
    slug: str
    base_url: str
    display_name: str
    teams: list[str]
    match_count: int
    status_counts: dict[str, int]
    biddable_count: int
    earliest_start: datetime | None
    latest_start: datetime | None
    # Reuse the verified scrape during activation. This is intentionally not
    # included in the API response and avoids launching Chromium twice.
    pages: list[str] = field(default_factory=list, repr=False)


class OpenBidsError(Exception):
    def __init__(self, open_bid_count: int) -> None:
        self.open_bid_count = open_bid_count
        super().__init__(f"{open_bid_count} open bid(s) on unsettled matches")


def slug_to_display_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def parse_tournament_ref(ref: str) -> tuple[int, str, str]:
    """Resolve a CricHeroes tournament ID or URL to (id, slug, canonical_url)."""
    ref = ref.strip()
    if ID_RE.match(ref):
        settings = get_settings()
        cricheroes_id = int(ref)
        if settings.cricheroes_tournament_id == cricheroes_id and settings.cricheroes_base_url:
            url = settings.cricheroes_base_url.rstrip("/")
            m = URL_RE.match(url)
            if m:
                return cricheroes_id, m.group(2), url
        slug = f"tournament-{cricheroes_id}"
        return cricheroes_id, slug, f"https://cricheroes.com/tournament/{cricheroes_id}/{slug}"

    url = ref.rstrip("/")
    parts = url.split("/")
    if len(parts) > 6 and parts[3] == "tournament":
        url = "/".join(parts[:6])
    m = URL_RE.match(url)
    if not m:
        raise ValueError(
            f"Not a CricHeroes tournament reference: {ref!r}. "
            "Expected a numeric ID or https://cricheroes.com/tournament/<id>/<slug>"
        )
    return int(m.group(1)), m.group(2), url


async def fetch_tournament_preview(ref: str) -> TournamentPreview:
    """Fetch and parse a tournament without writing to the database."""
    cricheroes_id, slug, base_url = parse_tournament_ref(ref)
    pages = await fetch_all_match_tabs(base_url)
    if not pages:
        raise RuntimeError("CricHeroes returned no usable pages (blocked or offline)")

    teams = parse_teams_from_html(pages[0])
    matches = parse_matches_from_pages(pages)
    status_counts: dict[str, int] = {}
    starts: list[datetime] = []
    for item in matches:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
        if item.get("start_time"):
            starts.append(item["start_time"])

    biddable = status_counts.get("upcoming", 0) + status_counts.get("locked", 0)
    return TournamentPreview(
        cricheroes_id=cricheroes_id,
        slug=slug,
        base_url=base_url,
        display_name=parse_tournament_name_from_html(pages[0]) or slug_to_display_name(slug),
        teams=teams,
        match_count=len(matches),
        status_counts=status_counts,
        biddable_count=biddable,
        earliest_start=min(starts) if starts else None,
        latest_start=max(starts) if starts else None,
        pages=pages,
    )


async def get_active_tournament(db: AsyncSession) -> Tournament | None:
    result = await db.execute(
        select(Tournament).where(Tournament.status == TournamentStatus.active).limit(1)
    )
    return result.scalar_one_or_none()


async def require_active_tournament(db: AsyncSession) -> Tournament:
    tournament = await get_active_tournament(db)
    if not tournament:
        raise HTTPException(status_code=503, detail="No active tournament configured")
    return tournament


async def ensure_active_tournament(db: AsyncSession) -> Tournament:
    """Return the active tournament, bootstrapping from env settings when missing."""
    tournament = await get_active_tournament(db)
    if tournament:
        return tournament

    settings = get_settings()
    _, slug, base_url = parse_tournament_ref(str(settings.cricheroes_tournament_id))
    if settings.cricheroes_base_url:
        try:
            _, slug, base_url = parse_tournament_ref(settings.cricheroes_base_url)
        except ValueError:
            pass

    tournament = Tournament(
        cricheroes_id=settings.cricheroes_tournament_id,
        slug=slug,
        base_url=base_url.rstrip("/"),
        display_name=slug_to_display_name(slug),
        status=TournamentStatus.active,
        activated_at=datetime.now(UTC),
    )
    db.add(tournament)
    await db.flush()
    logger.info("Bootstrapped active tournament %s from environment", tournament.base_url)
    return tournament


async def count_open_bids(db: AsyncSession, tournament_id: int) -> int:
    """Bids on matches that are not yet settled in the given tournament."""
    open_statuses = (
        MatchStatus.upcoming,
        MatchStatus.locked,
        MatchStatus.awaiting_result,
    )
    result = await db.execute(
        select(func.count(Bid.id))
        .select_from(Bid)
        .join(Match, Match.id == Bid.match_id)
        .where(Match.tournament_id == tournament_id, Match.status.in_(open_statuses))
    )
    return int(result.scalar() or 0)


async def reset_current_season_state(db: AsyncSession) -> None:
    """Reset points and streaks for a fresh tournament season.

    Season bets remain on archived tournaments; the active tournament API
    scopes bets to the current tournament only.
    """
    users = (await db.execute(select(User))).scalars().all()
    for user in users:
        user.points_balance = user.starting_balance
        user.joined_match_index = 0

    await db.execute(delete(Streak))


async def archive_tournament(
    db: AsyncSession,
    tournament: Tournament,
    *,
    archived_by_user_id: int | None = None,
) -> None:
    tournament.status = TournamentStatus.archived
    tournament.archived_at = datetime.now(UTC)
    tournament.archived_by_user_id = archived_by_user_id
    await db.flush()


async def activate_tournament(
    db: AsyncSession,
    ref: str,
    *,
    admin_user_id: int | None = None,
    confirm_reset: bool = False,
) -> Tournament:
    """Preview-fetch, archive the previous tournament, import fixtures, reset game state."""
    preview = await fetch_tournament_preview(ref)
    current = await get_active_tournament(db)

    if current:
        open_bids = await count_open_bids(db, current.id)
        if open_bids and not confirm_reset:
            raise OpenBidsError(open_bids)
        if current.cricheroes_id == preview.cricheroes_id and current.slug == preview.slug:
            raise HTTPException(status_code=400, detail="Tournament is already active")

    if current:
        await archive_tournament(db, current, archived_by_user_id=admin_user_id)

    tournament = Tournament(
        cricheroes_id=preview.cricheroes_id,
        slug=preview.slug,
        base_url=preview.base_url,
        display_name=preview.display_name,
        status=TournamentStatus.active,
        team_count=len(preview.teams),
        match_count=preview.match_count,
        activated_at=datetime.now(UTC),
        activated_by_user_id=admin_user_id,
    )
    db.add(tournament)
    await db.flush()

    from app.services.cricheroes.sync import sync_cricheroes

    run = await sync_cricheroes(
        db,
        tournament=tournament,
        pages=getattr(preview, "pages", None),
    )
    if run.status != "success":
        raise HTTPException(
            status_code=502,
            detail=f"Tournament import failed: {run.error or 'unknown error'}",
        )

    tournament.last_sync_at = run.finished_at
    tournament.team_count = len(preview.teams)
    tournament.match_count = preview.match_count
    await reset_current_season_state(db)
    await db.flush()
    return tournament


async def list_archived_tournaments(db: AsyncSession) -> list[Tournament]:
    result = await db.execute(
        select(Tournament)
        .where(Tournament.status == TournamentStatus.archived)
        .order_by(Tournament.archived_at.desc())
    )
    return list(result.scalars().all())


async def update_tournament_counts(db: AsyncSession, tournament_id: int) -> None:
    from app.db.models import Team

    team_count = await db.scalar(
        select(func.count()).select_from(Team).where(Team.tournament_id == tournament_id)
    )
    match_count = await db.scalar(
        select(func.count()).select_from(Match).where(Match.tournament_id == tournament_id)
    )
    await db.execute(
        update(Tournament)
        .where(Tournament.id == tournament_id)
        .values(team_count=team_count or 0, match_count=match_count or 0)
    )
