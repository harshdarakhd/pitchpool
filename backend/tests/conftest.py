"""Shared async test database and HTTP client fixtures."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.redis import reset_redis_client
from app.db.models import Base


def _rebuild_db_engine() -> None:
    """Point SQLAlchemy at the in-memory test database."""
    import app.db.base as db_base

    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    db_base.engine = create_async_engine(
        settings.database_url,
        echo=settings.sql_echo,
        connect_args=connect_args,
    )
    db_base.AsyncSessionLocal = async_sessionmaker(
        db_base.engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Ensure tests never load production validation defaults from a real .env."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "memory://")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-unit-tests-only-32chars")
    monkeypatch.setenv("ENABLE_INPROCESS_SCHEDULER", "false")
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret-value")
    get_settings.cache_clear()
    reset_redis_client()
    _rebuild_db_engine()
    yield
    get_settings.cache_clear()
    reset_redis_client()


@pytest.fixture
async def db_session():
    from app.db.base import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def trusted_origin() -> dict[str, str]:
    return {"Origin": "http://localhost:5173"}
