"""Auth cookies, CSRF/origin guard, cron, readiness, and WebSocket auth."""

import pytest
from httpx import AsyncClient
from jose import jwt

from app.core.config import get_settings
from app.core.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.core.security import ALGORITHM, create_access_token
from app.core.security import hash_password
from app.db.models import Streak, User, UserRole


async def _create_user(db_session, email: str = "user@test.local", password: str = "password12345") -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Test User",
        points_balance=5000,
        starting_balance=5000,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(Streak(user_id=user.id, current=0, best=0))
    await db_session.flush()
    return user


class TestAuthCookies:
    @pytest.mark.asyncio
    async def test_login_sets_httponly_cookies(self, client: AsyncClient, db_session, monkeypatch, trusted_origin):
        from app.db.base import get_db
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        await _create_user(db_session, "cookie@test.local")

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "cookie@test.local", "password": "password12345"},
            headers=trusted_origin,
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()
        cookies = resp.cookies
        assert ACCESS_COOKIE in cookies
        assert REFRESH_COOKIE in cookies
        set_cookie = resp.headers.get_list("set-cookie")
        assert any("httponly" in c.lower() for c in set_cookie)
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_me_works_from_access_cookie(self, client: AsyncClient, db_session, monkeypatch):
        from app.db.base import get_db
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        user = await _create_user(db_session, "me-cookie@test.local")

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "me-cookie@test.local", "password": "password12345"},
            headers={"Origin": "http://localhost:5173"},
        )
        client.cookies.update(login.cookies)

        me = await client.get("/api/v1/auth/me", headers={"Origin": "http://localhost:5173"})
        assert me.status_code == 200
        assert me.json()["email"] == user.email
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_me_still_accepts_authorization_header(self, client: AsyncClient, db_session):
        from app.db.base import get_db
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        user = await _create_user(db_session, "bearer@test.local")
        token = create_access_token(str(user.id), {"role": user.role.value})

        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}", "Origin": "http://localhost:5173"},
        )
        assert me.status_code == 200
        app.dependency_overrides.clear()


class TestOriginGuard:
    @pytest.mark.asyncio
    async def test_blocks_mutation_with_untrusted_origin(self, client: AsyncClient, db_session):
        from app.db.base import get_db
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override

        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "blocked@test.local", "password": "password12345", "display_name": "Blocked"},
            headers={"Origin": "https://evil.example.com"},
        )
        assert resp.status_code == 403
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_allows_mutation_with_trusted_origin(self, client: AsyncClient, db_session, trusted_origin):
        from app.db.base import get_db
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override

        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "allowed@test.local", "password": "password12345", "display_name": "Allowed"},
            headers=trusted_origin,
        )
        assert resp.status_code == 200
        app.dependency_overrides.clear()


class TestCronSync:
    @pytest.mark.asyncio
    async def test_rejects_missing_secret(self, client: AsyncClient):
        resp = await client.post("/internal/cron/sync")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_wrong_secret(self, client: AsyncClient):
        resp = await client.post("/internal/cron/sync", headers={"X-Cron-Secret": "wrong"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_accepts_valid_secret(self, client: AsyncClient, db_session, monkeypatch):
        from app.db.base import get_db
        from app.main import app
        from app.services.cricheroes import sync as sync_mod

        async def _override():
            yield db_session

        async def _fake_sync(db, **kwargs):
            from datetime import UTC, datetime
            from app.db.models import SyncRun, Tournament, TournamentStatus

            t = Tournament(
                cricheroes_id=1,
                slug="t",
                base_url="https://cricheroes.com/tournament/1/t",
                status=TournamentStatus.active,
            )
            db.add(t)
            await db.flush()
            run = SyncRun(status="success", tournament_id=t.id, finished_at=datetime.now(UTC))
            db.add(run)
            await db.flush()
            return run

        app.dependency_overrides[get_db] = _override
        monkeypatch.setattr(sync_mod, "sync_cricheroes", _fake_sync)

        resp = await client.post(
            "/internal/cron/sync",
            headers={"X-Cron-Secret": get_settings().cron_secret},
        )
        assert resp.status_code == 200
        app.dependency_overrides.clear()


class TestCronImport:
    @pytest.mark.asyncio
    async def test_rejects_missing_secret(self, client: AsyncClient):
        resp = await client.post("/internal/cron/import", json={"matches": []})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_imports_pushed_matches(self, client: AsyncClient, db_session):
        from sqlalchemy import select

        from app.db.base import get_db
        from app.db.models import Match, MatchStatus
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        try:
            resp = await client.post(
                "/internal/cron/import",
                headers={"X-Cron-Secret": get_settings().cron_secret},
                json={
                    "teams": ["Rajwada Royals", "Eagles Warriors"],
                    "matches": [
                        {
                            "cricheroes_match_key": "26120123",
                            "team_a_name": "Rajwada Royals",
                            "team_b_name": "Eagles Warriors",
                            "start_time": "2026-07-13T08:00:00+00:00",
                            "status": "completed",
                            "winner_name": "Rajwada Royals",
                            "venue": "Pune",
                        }
                    ],
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "success"
            assert body["matches_updated"] == 1

            match = (
                await db_session.execute(
                    select(Match).where(Match.cricheroes_match_key == "26120123")
                )
            ).scalar_one()
            assert match.status == MatchStatus.completed
            assert match.winner_team_id is not None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_rejects_mismatched_tournament(self, client: AsyncClient, db_session):
        from app.db.base import get_db
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        try:
            resp = await client.post(
                "/internal/cron/import",
                headers={"X-Cron-Secret": get_settings().cron_secret},
                json={"cricheroes_id": 999999, "teams": [], "matches": []},
            )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()


class TestReady:
    @pytest.mark.asyncio
    async def test_ready_ok(self, client: AsyncClient, db_session, monkeypatch):
        from app.db.base import get_db
        from app.main import app

        async def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override

        resp = await client.get("/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["redis"] == "ok"
        app.dependency_overrides.clear()


class TestWebSocketAuth:
    @pytest.mark.asyncio
    async def test_ws_rejects_missing_auth(self):
        from app.main import app
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with pytest.raises(Exception):
                with tc.websocket_connect("/ws", headers={"Origin": "http://localhost:5173"}):
                    pass

    @pytest.mark.asyncio
    async def test_ws_accepts_cookie_auth(self, db_session):
        from app.main import app

        user = await _create_user(db_session, "ws@test.local")
        settings = get_settings()
        token = jwt.encode(
            {"sub": str(user.id), "type": "access", "exp": 9999999999},
            settings.secret_key,
            algorithm=ALGORITHM,
        )

        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            tc.cookies.set(ACCESS_COOKIE, token)
            with tc.websocket_connect("/ws", headers={"Origin": "http://localhost:5173"}) as ws:
                ws.send_text("ping")
                assert ws.receive_text() == "pong"

    @pytest.mark.asyncio
    async def test_ws_rejects_bad_origin(self):
        from app.main import app
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with pytest.raises(Exception):
                with tc.websocket_connect("/ws", headers={"Origin": "https://evil.example.com"}):
                    pass
