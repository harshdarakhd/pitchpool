"""Same-origin guards for mutating API requests and WebSocket connections."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import Settings, get_settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT_PREFIXES = (
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/internal/",
)


def _origin_from_referer(referer: str) -> str | None:
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def origin_allowed(request: Request | WebSocket, settings: Settings | None = None) -> bool:
    """Return True when the request appears to come from a trusted same-origin client."""
    settings = settings or get_settings()
    allowed = settings.cors_origin_list
    if not allowed:
        return settings.environment == "development"

    origin = request.headers.get("origin")
    if origin and origin in allowed:
        return True

    referer = request.headers.get("referer", "")
    if referer:
        ref_origin = _origin_from_referer(referer)
        if ref_origin and ref_origin in allowed:
            return True

    if not origin and not referer:
        host = request.headers.get("host", "")
        for item in allowed:
            if urlparse(item).netloc == host:
                return True

    return False


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """Reject cross-site mutating API calls unless Origin/Referer matches CORS_ORIGINS."""

    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        settings = get_settings()
        if settings.environment == "development" and not settings.cors_origin_list:
            return await call_next(request)

        if origin_allowed(request, settings):
            return await call_next(request)

        return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
