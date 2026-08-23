"""One-time admin bootstrap from environment variables.

Usage:
    BOOTSTRAP_ADMIN_EMAIL=admin@example.com \\
    BOOTSTRAP_ADMIN_PASSWORD='strong-password' \\
    python -m scripts.bootstrap_admin
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import AsyncSessionLocal, engine
from app.db.models import Base, Streak, User, UserRole


async def bootstrap_admin() -> int:
    settings = get_settings()
    email = settings.bootstrap_admin_email.strip().lower()
    password = settings.bootstrap_admin_password

    if not email or not password:
        print("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD", file=sys.stderr)
        return 1

    if len(password) < 8:
        print("BOOTSTRAP_ADMIN_PASSWORD must be at least 8 characters", file=sys.stderr)
        return 1

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        user = existing.scalar_one_or_none()
        if user:
            if user.role != UserRole.admin:
                user.role = UserRole.admin
                await db.commit()
                print(f"Promoted existing user to admin: {email}")
            else:
                print(f"Admin already exists: {email}")
            return 0

        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name="Admin",
            role=UserRole.admin,
            points_balance=settings.starting_points,
            starting_balance=settings.starting_points,
        )
        db.add(user)
        await db.flush()
        db.add(Streak(user_id=user.id, current=0, best=0))
        await db.commit()
        print(f"Created admin user: {email}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(bootstrap_admin()))


if __name__ == "__main__":
    main()
