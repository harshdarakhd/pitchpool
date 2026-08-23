"""Tests for tournament parsing, preview, activation, and scoping."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import (
    Bid,
    Match,
    MatchStage,
    MatchStatus,
    Team,
    Tournament,
    TournamentStatus,
    User,
    UserRole,
)
from app.services.tournaments import (
    OpenBidsError,
    activate_tournament,
    count_open_bids,
    ensure_active_tournament,
    fetch_tournament_preview,
    get_active_tournament,
    parse_tournament_ref,
)
SAMPLE_URL = (
    "https://cricheroes.com/tournament/1691351/"
    "maheshwari-tennis-premier-league-season-4-2026"
)
SAMPLE_HTML = """
<html><head>
<script type="application/ld+json">{"@type":"SportsEvent","name":"Team Alpha vs Team Beta"}</script>
</head><body></body></html>
"""


def _sample_match(status: str = "upcoming", key: str = "m1") -> dict:
    start = datetime.now(UTC) + timedelta(days=1)
    return {
        "cricheroes_match_key": key,
        "team_a_name": "Team Alpha",
        "team_b_name": "Team Beta",
        "stage": "league",
        "stage_label": "League Matches",
        "venue": "Test Ground",
        "start_time": start,
        "status": status,
        "winner_name": None,
        "result_raw": None,
    }


class TestParseTournamentRef:
    def test_parses_canonical_url(self):
        tid, slug, url = parse_tournament_ref(SAMPLE_URL)
        assert tid == 1691351
        assert slug == "maheshwari-tennis-premier-league-season-4-2026"
        assert url == SAMPLE_URL

    def test_trims_deep_link_to_root(self):
        deep = SAMPLE_URL + "/matches/past-matches"
        tid, slug, url = parse_tournament_ref(deep)
        assert tid == 1691351
        assert url == SAMPLE_URL

    def test_parses_numeric_id(self):
        get_settings.cache_clear()
        tid, slug, url = parse_tournament_ref("1691351")
        assert tid == 1691351
        assert "1691351" in url

    def test_rejects_invalid_ref(self):
        with pytest.raises(ValueError):
            parse_tournament_ref("not-a-tournament")


class TestPreview:
    @pytest.mark.asyncio
    async def test_preview_does_not_write(self, db_session):
        with (
            patch(
                "app.services.tournaments.fetch_all_match_tabs",
                new=AsyncMock(return_value=[SAMPLE_HTML]),
            ),
            patch(
                "app.services.tournaments.parse_teams_from_html",
                return_value=["Team Alpha", "Team Beta"],
            ),
            patch(
                "app.services.tournaments.parse_matches_from_pages",
                return_value=[_sample_match("upcoming"), _sample_match("completed", "m2")],
            ),
        ):
            preview = await fetch_tournament_preview(SAMPLE_URL)

        assert preview.match_count == 2
        assert preview.biddable_count == 1
        assert preview.status_counts["upcoming"] == 1

        tournaments = (await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Tournament)
        )).scalars().all()
        assert tournaments == []


class TestActivation:
    async def _seed_user(self, db) -> User:
        user = User(
            email="admin@test.local",
            password_hash=hash_password("secret12345"),
            display_name="Admin",
            role=UserRole.admin,
            points_balance=3000,
            starting_balance=5000,
        )
        db.add(user)
        await db.flush()
        return user

    async def _seed_active_fixture(self, db, tournament: Tournament) -> Match:
        team_a = Team(tournament_id=tournament.id, name="Team Alpha", short_name="TA")
        team_b = Team(tournament_id=tournament.id, name="Team Beta", short_name="TB")
        db.add_all([team_a, team_b])
        await db.flush()
        match = Match(
            tournament_id=tournament.id,
            cricheroes_match_key="old-1",
            stage=MatchStage.league,
            team_a_id=team_a.id,
            team_b_id=team_b.id,
            start_time=datetime.now(UTC) + timedelta(days=1),
            bid_deadline=datetime.now(UTC) + timedelta(hours=20),
            status=MatchStatus.upcoming,
        )
        db.add(match)
        await db.flush()
        return match

    @pytest.mark.asyncio
    async def test_bootstrap_from_env_when_missing(self, db_session):
        get_settings.cache_clear()
        tournament = await ensure_active_tournament(db_session)
        assert tournament.status == TournamentStatus.active
        assert tournament.cricheroes_id == get_settings().cricheroes_tournament_id

    @pytest.mark.asyncio
    async def test_open_bids_block_without_confirmation(self, db_session):
        admin = await self._seed_user(db_session)
        current = Tournament(
            cricheroes_id=111,
            slug="old-season",
            base_url="https://cricheroes.com/tournament/111/old-season",
            display_name="Old Season",
            status=TournamentStatus.active,
        )
        db_session.add(current)
        await db_session.flush()

        match = await self._seed_active_fixture(db_session, current)
        db_session.add(Bid(user_id=admin.id, match_id=match.id, team_id=match.team_a_id, amount=100))
        await db_session.flush()

        assert await count_open_bids(db_session, current.id) == 1

        with (
            patch(
                "app.services.tournaments.fetch_tournament_preview",
                new=AsyncMock(
                    return_value=type(
                        "P",
                        (),
                        {
                            "cricheroes_id": 222,
                            "slug": "new-season",
                            "base_url": "https://cricheroes.com/tournament/222/new-season",
                            "display_name": "New Season",
                            "teams": ["A", "B"],
                            "match_count": 1,
                        },
                    )()
                ),
            ),
            pytest.raises(OpenBidsError),
        ):
            await activate_tournament(
                db_session,
                "https://cricheroes.com/tournament/222/new-season",
                admin_user_id=admin.id,
                confirm_reset=False,
            )

    @pytest.mark.asyncio
    async def test_activation_archives_previous_and_resets_points(self, db_session):
        admin = await self._seed_user(db_session)
        current = Tournament(
            cricheroes_id=111,
            slug="old-season",
            base_url="https://cricheroes.com/tournament/111/old-season",
            display_name="Old Season",
            status=TournamentStatus.active,
        )
        db_session.add(current)
        await db_session.flush()

        preview = type(
            "P",
            (),
            {
                "cricheroes_id": 222,
                "slug": "new-season",
                "base_url": "https://cricheroes.com/tournament/222/new-season",
                "display_name": "New Season",
                "teams": ["Team Alpha", "Team Beta"],
                "match_count": 1,
            },
        )()

        mock_run = type(
            "R",
            (),
            {"status": "success", "finished_at": datetime.now(UTC), "matches_seen": 1, "matches_updated": 1},
        )()

        with (
            patch("app.services.tournaments.fetch_tournament_preview", new=AsyncMock(return_value=preview)),
            patch("app.services.cricheroes.sync.sync_cricheroes", new=AsyncMock(return_value=mock_run)),
        ):
            new_t = await activate_tournament(
                db_session,
                "https://cricheroes.com/tournament/222/new-season",
                admin_user_id=admin.id,
                confirm_reset=True,
            )

        await db_session.refresh(current)
        assert current.status == TournamentStatus.archived
        assert new_t.status == TournamentStatus.active
        assert admin.points_balance == admin.starting_balance

    @pytest.mark.asyncio
    async def test_only_one_active_tournament(self, db_session):
        t1 = Tournament(
            cricheroes_id=1,
            slug="a",
            base_url="https://cricheroes.com/tournament/1/a",
            status=TournamentStatus.active,
        )
        db_session.add(t1)
        await db_session.flush()

        active = await get_active_tournament(db_session)
        assert active is not None
        assert active.id == t1.id


class TestMatchOverrideValidation:
    @pytest.mark.asyncio
    async def test_winner_must_be_match_team(self, db_session):
        from app.api.v1.admin import override_match
        from app.schemas import AdminMatchOverride

        admin = User(
            email="admin2@test.local",
            password_hash="x",
            display_name="Admin",
            role=UserRole.admin,
        )
        tournament = Tournament(
            cricheroes_id=1,
            slug="t",
            base_url="https://cricheroes.com/tournament/1/t",
            status=TournamentStatus.active,
        )
        db_session.add_all([admin, tournament])
        await db_session.flush()

        team_a = Team(tournament_id=tournament.id, name="A", short_name="A")
        team_b = Team(tournament_id=tournament.id, name="B", short_name="B")
        outsider = Team(tournament_id=tournament.id, name="C", short_name="C")
        db_session.add_all([team_a, team_b, outsider])
        await db_session.flush()

        match = Match(
            tournament_id=tournament.id,
            stage=MatchStage.league,
            team_a_id=team_a.id,
            team_b_id=team_b.id,
            start_time=datetime.now(UTC),
            bid_deadline=datetime.now(UTC),
            status=MatchStatus.awaiting_result,
        )
        db_session.add(match)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await override_match(
                match.id,
                AdminMatchOverride(winner_team_id=outsider.id, status="completed"),
                db_session,
                admin,
            )
        assert exc.value.status_code == 400
