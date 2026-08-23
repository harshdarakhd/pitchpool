"""Ledger and balance helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Transaction, TransactionType, User


async def apply_transaction(
    db: AsyncSession,
    user: User,
    delta: int,
    tx_type: TransactionType,
    *,
    match_id: int | None = None,
    tournament_id: int | None = None,
    description: str | None = None,
) -> Transaction:
    new_balance = max(0, user.points_balance + delta)
    user.points_balance = new_balance
    tx = Transaction(
        user_id=user.id,
        tournament_id=tournament_id,
        match_id=match_id,
        type=tx_type,
        delta=delta,
        balance_after=new_balance,
        description=description,
    )
    db.add(tx)
    return tx


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
