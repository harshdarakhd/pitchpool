import os
from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_SECRETS = frozenset(
    {
        "dev-secret-change-in-production",
        "change-me-in-production-use-openssl-rand-hex-32",
    }
)
_MEMORY_REDIS = frozenset({"", "memory://", "memory"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./pitchpool.db"
    redis_url: str = "memory://"
    secret_key: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cricheroes_tournament_id: int = 1691351
    cricheroes_base_url: str = (
        "https://cricheroes.com/tournament/1691351/"
        "maheshwari-tennis-premier-league-season-4-2026"
    )
    environment: str = "development"
    sql_echo: bool = False
    starting_points: int = 5000
    late_join_penalty_per_match: int = 100
    late_join_floor: int = 500
    bid_deadline_minutes: int = 15

    cron_secret: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    sync_stale_minutes: int = 10
    enable_inprocess_scheduler: bool = True
    cookie_samesite: str = "lax"
    cookie_secure: bool | None = None

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = value.strip().strip('"').strip("'")
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://") and "+asyncpg" not in value.split("://", 1)[0]:
            value = "postgresql+asyncpg://" + value[len("postgresql://") :]
        return value

    def async_engine_url_and_args(self) -> tuple[str, dict]:
        """asyncpg rejects libpq query args such as sslmode=require."""
        url = self.database_url
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            return url, connect_args

        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.pop("sslmode", None)
        query.pop("channel_binding", None)
        cleaned = urlunparse(parsed._replace(query=urlencode(query)))
        connect_args["ssl"] = True
        return cleaned, connect_args

    @field_validator("redis_url")
    @classmethod
    def normalize_redis_url(cls, value: str) -> str:
        value = value.strip().strip('"').strip("'")
        if value.startswith("redis://") and "upstash.io" in value:
            value = "rediss://" + value[len("redis://") :]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        for key in ("RENDER_EXTERNAL_URL", "RENDER_EXTERNAL_HOSTNAME"):
            raw = os.environ.get(key, "").strip().rstrip("/")
            if not raw:
                continue
            if key == "RENDER_EXTERNAL_HOSTNAME" and not raw.startswith("http"):
                raw = f"https://{raw}"
            if raw not in origins:
                origins.append(raw)
        return origins

    @property
    def cookie_secure_flag(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production

    @property
    def uses_memory_redis(self) -> bool:
        return self.redis_url.strip().lower() in _MEMORY_REDIS

    @model_validator(mode="after")
    def validate_production_config(self) -> Self:
        if not self.is_production:
            return self

        if self.secret_key in _FORBIDDEN_SECRETS or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be a strong random value (>=32 chars) in production"
            )

        if self.database_url.startswith("sqlite"):
            raise ValueError("DATABASE_URL must be PostgreSQL (or other server DB) in production")

        if self.uses_memory_redis:
            raise ValueError("REDIS_URL must point to a real Redis instance in production")

        if not self.cron_secret or len(self.cron_secret) < 16:
            raise ValueError("CRON_SECRET must be set (>=16 chars) in production")

        if not self.cors_origin_list:
            raise ValueError(
                "CORS_ORIGINS must list at least one trusted origin in production "
                "(or rely on RENDER_EXTERNAL_URL, which Render sets automatically)"
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
