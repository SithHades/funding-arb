from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import ArbitragePosition, PositionStatus


async def get_open_positions(session: AsyncSession) -> list[ArbitragePosition]:
    """
    Fetch all currently open positions.
    """
    stmt = select(ArbitragePosition).where(
        ArbitragePosition.status == PositionStatus.OPEN
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_position(
    session: AsyncSession,
    symbol: str,
    entry_arb_diff_bps: float,
    long_dex: str,
    short_dex: str,
    size_usd: float,
) -> ArbitragePosition:
    """
    Create a new open position.
    """
    new_pos = ArbitragePosition(
        symbol=symbol,
        entry_arb_diff_bps=entry_arb_diff_bps,
        long_dex=long_dex,
        short_dex=short_dex,
        size_usd=size_usd,
        status=PositionStatus.OPEN,
        entry_timestamp=datetime.utcnow(),
    )
    session.add(new_pos)
    await session.commit()
    await session.refresh(new_pos)
    return new_pos


async def close_position(session: AsyncSession, position_id: int):
    """
    Mark a position as CLOSED.
    """
    stmt = (
        update(ArbitragePosition)
        .where(ArbitragePosition.id == position_id)
        .values(status=PositionStatus.CLOSED)
    )
    await session.execute(stmt)
    await session.commit()


async def update_unfavorable_since(
    session: AsyncSession, position_id: int, timestamp: datetime | None
):
    """
    Update the unfavorable_since timestamp.
    """
    stmt = (
        update(ArbitragePosition)
        .where(ArbitragePosition.id == position_id)
        .values(unfavorable_since=timestamp)
    )
    await session.execute(stmt)
    await session.commit()
