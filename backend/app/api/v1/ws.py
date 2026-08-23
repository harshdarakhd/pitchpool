import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.cookies import ACCESS_COOKIE
from app.core.origin import origin_allowed
from app.core.redis import get_redis
from app.core.security import decode_token, verify_token_type

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

_listener_task: asyncio.Task | None = None


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[str, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, channel: str = "global") -> None:
        await ws.accept()
        self.active.setdefault(channel, set()).add(ws)

    def disconnect(self, ws: WebSocket, channel: str = "global") -> None:
        if channel in self.active:
            self.active[channel].discard(ws)

    async def broadcast(self, message: dict[str, Any], channel: str = "global") -> None:
        dead: list[WebSocket] = []
        for ws in self.active.get(channel, set()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)


manager = ConnectionManager()


async def redis_listener() -> None:
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("events")
    async for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        try:
            payload = json.loads(msg["data"])
            await manager.broadcast(payload)
            match_id = payload.get("match_id")
            if match_id:
                await manager.broadcast(payload, f"match:{match_id}")
        except Exception:
            logger.exception("Failed to broadcast event")


def start_redis_listener() -> asyncio.Task:
    global _listener_task
    if _listener_task is None or _listener_task.done():
        _listener_task = asyncio.create_task(redis_listener())
    return _listener_task


def _access_token_from_ws(ws: WebSocket) -> str | None:
    token = ws.cookies.get(ACCESS_COOKIE)
    if token:
        return token
    # Dev/backward compat: optional query token (not required in production UI).
    return ws.query_params.get("token")


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if not origin_allowed(ws):
        await ws.close(code=1008, reason="Origin not allowed")
        return

    token = _access_token_from_ws(ws)
    if not token:
        await ws.close(code=4001, reason="Authentication required")
        return
    try:
        payload = decode_token(token)
        if not verify_token_type(payload, "access"):
            await ws.close(code=4001, reason="Invalid token")
            return
    except JWTError:
        await ws.close(code=4001, reason="Invalid token")
        return

    start_redis_listener()
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(ws)
