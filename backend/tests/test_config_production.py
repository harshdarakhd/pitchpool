"""Production config validation tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


class TestProductionConfigValidation:
    def _prod_settings(self, **overrides) -> Settings:
        base = {
            "environment": "production",
            "secret_key": "a" * 32,
            "database_url": "postgresql+asyncpg://user:pass@localhost/db",
            "redis_url": "redis://localhost:6379/0",
            "cron_secret": "cron-secret-min-16-ch",
            "cors_origins": "https://pitchpool.example.com",
        }
        base.update(overrides)
        return Settings(**base)

    def test_valid_production_config(self):
        s = self._prod_settings()
        assert s.is_production

    def test_rejects_default_secret(self):
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._prod_settings(secret_key="dev-secret-change-in-production")

    def test_rejects_short_secret(self):
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._prod_settings(secret_key="tooshort")

    def test_rejects_sqlite(self):
        with pytest.raises(ValidationError, match="DATABASE_URL"):
            self._prod_settings(database_url="sqlite+aiosqlite:///./pitchpool.db")

    def test_rejects_memory_redis(self):
        with pytest.raises(ValidationError, match="REDIS_URL"):
            self._prod_settings(redis_url="memory://")

    def test_rejects_missing_cron_secret(self):
        with pytest.raises(ValidationError, match="CRON_SECRET"):
            self._prod_settings(cron_secret="")

    def test_development_allows_defaults(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
        s = Settings()
        assert s.database_url.startswith("sqlite")
        assert s.uses_memory_redis
