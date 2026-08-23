"""bootstrap_admin script tests."""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_password
from app.db.models import User, UserRole
from scripts.bootstrap_admin import bootstrap_admin


@pytest.fixture(autouse=True)
def _bind_bootstrap_to_test_db(monkeypatch, _test_env):
    import app.db.base as db_base
    import scripts.bootstrap_admin as bootstrap_module

    monkeypatch.setattr(bootstrap_module, "engine", db_base.engine)
    monkeypatch.setattr(bootstrap_module, "AsyncSessionLocal", db_base.AsyncSessionLocal)


class TestBootstrapAdmin:
    @pytest.mark.asyncio
    async def test_creates_admin_from_env(self, monkeypatch, db_session):
        monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@bootstrap.local")
        monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "securepass123")
        get_settings.cache_clear()

        code = await bootstrap_admin()
        assert code == 0

        result = await db_session.execute(select(User).where(User.email == "admin@bootstrap.local"))
        user = result.scalar_one()
        assert user.role == UserRole.admin
        assert verify_password("securepass123", user.password_hash)

    @pytest.mark.asyncio
    async def test_idempotent_second_run(self, monkeypatch, db_session):
        monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin2@bootstrap.local")
        monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "securepass123")
        get_settings.cache_clear()

        assert await bootstrap_admin() == 0
        assert await bootstrap_admin() == 0

    @pytest.mark.asyncio
    async def test_missing_env_returns_error(self, monkeypatch, db_session):
        monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "")
        monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        get_settings.cache_clear()

        code = await bootstrap_admin()
        assert code == 1
