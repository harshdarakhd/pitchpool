from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.cookies import clear_auth_cookies, get_refresh_token_from_request, set_auth_cookies
from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    verify_token_type,
)
from app.db.base import get_db
from app.db.models import Match, MatchStatus, RefreshToken, Streak, User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.scoring import compute_late_join_balance

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
@limiter.limit("10/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    completed = await db.execute(
        select(func.count()).select_from(Match).where(Match.status == MatchStatus.completed)
    )
    completed_count = completed.scalar() or 0
    starting = compute_late_join_balance(completed_count)

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        points_balance=starting,
        starting_balance=starting,
        joined_match_index=completed_count,
    )
    db.add(user)
    await db.flush()
    db.add(Streak(user_id=user.id, current=0, best=0))
    await db.flush()
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access = create_access_token(str(user.id), {"role": user.role.value})
    refresh, jti = create_refresh_token(str(user.id))
    expires = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_expire_days)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires))
    user.refresh_token_jti = jti
    set_auth_cookies(response, access, refresh)
    return TokenResponse(access_token=access)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = get_refresh_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = decode_token(token)
        if not verify_token_type(payload, "refresh"):
            raise HTTPException(status_code=401, detail="Invalid token")
        jti = payload["jti"]
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    rt = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti, RefreshToken.revoked == False))
    stored = rt.scalar_one_or_none()
    if not stored or stored.user_id != user_id:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    stored.revoked = True
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()
    access = create_access_token(str(user.id), {"role": user.role.value})
    new_refresh, new_jti = create_refresh_token(str(user.id))
    expires = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_expire_days)
    db.add(RefreshToken(jti=new_jti, user_id=user.id, expires_at=expires))
    user.refresh_token_jti = new_jti
    set_auth_cookies(response, access, new_refresh)
    return TokenResponse(access_token=access)


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = get_refresh_token_from_request(request)
    if token:
        try:
            payload = decode_token(token)
            jti = payload.get("jti")
            if jti:
                rt = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
                stored = rt.scalar_one_or_none()
                if stored:
                    stored.revoked = True
        except JWTError:
            pass
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
