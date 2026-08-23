"""Redis client — in-memory fallback allowed only outside production."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None


class _MemoryPubSub:
    def __init__(self, store: "_MemoryRedis") -> None:
        self._store = store
        self._queues: list[asyncio.Queue] = []

    async def subscribe(self, channel: str) -> None:
        q: asyncio.Queue = asyncio.Queue()
        self._store.subscribers.setdefault(channel, []).append(q)
        self._queues.append(q)

    async def listen(self):
        yield {"type": "subscribe", "data": None}
        queues = list(self._queues)
        while True:
            for q in queues:
                try:
                    msg = q.get_nowait()
                    yield msg
                except asyncio.QueueEmpty:
                    pass
            await asyncio.sleep(0.05)


class _MemoryRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.subscribers: dict[str, list[asyncio.Queue]] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)

    async def publish(self, channel: str, message: str) -> int:
        subs = self.subscribers.get(channel, [])
        for q in subs:
            await q.put({"type": "message", "data": message})
        return len(subs)

    async def ping(self) -> bool:
        return True

    def pubsub(self) -> _MemoryPubSub:
        return _MemoryPubSub(self)


async def get_redis() -> Any:
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    url = settings.redis_url.strip()
    if settings.uses_memory_redis:
        if settings.is_production:
            raise RuntimeError("In-memory Redis is not allowed in production")
        logger.warning("Using in-memory Redis (development only)")
        _client = _MemoryRedis()
        return _client

    import redis.asyncio as redis

    client = redis.from_url(url, decode_responses=True)
    await client.ping()
    _client = client
    return _client


async def check_redis() -> bool:
    try:
        r = await get_redis()
        if hasattr(r, "ping"):
            await r.ping()
            return True
    except Exception:
        logger.exception("Redis readiness check failed")
    return False


def reset_redis_client() -> None:
    """Clear cached client (tests)."""
    global _client
    _client = None


async def publish_event(channel: str, payload: dict[str, Any]) -> None:
    r = await get_redis()
    await r.publish(channel, json.dumps(payload))


async def cache_get(key: str) -> str | None:
    r = await get_redis()
    return await r.get(key)


async def cache_set(key: str, value: str, ttl: int = 60) -> None:
    r = await get_redis()
    await r.set(key, value, ex=ttl)


async def acquire_lock(key: str, ttl: int = 120) -> bool:
    r = await get_redis()
    return bool(await r.set(key, "1", nx=True, ex=ttl))


async def release_lock(key: str) -> None:
    r = await get_redis()
    await r.delete(key)
