from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


def _storage_uri() -> str:
    settings = get_settings()
    if settings.uses_memory_redis:
        return "memory://"
    return settings.redis_url.strip()


limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri())
