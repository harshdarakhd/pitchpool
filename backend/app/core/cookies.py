"""HttpOnly auth cookie helpers for same-origin deployment."""

from fastapi import Request, Response

from app.core.config import get_settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    common = {
        "httponly": True,
        "samesite": settings.cookie_samesite,
        "secure": settings.cookie_secure_flag,
        "path": "/",
    }
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **common,
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(
            key=name,
            path="/",
            secure=settings.cookie_secure_flag,
            samesite=settings.cookie_samesite,
        )


def get_access_token_from_request(request: Request) -> str | None:
    return request.cookies.get(ACCESS_COOKIE)


def get_refresh_token_from_request(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)
