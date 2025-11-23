from datetime import datetime
from enum import Enum
from sqlalchemy import String, Float, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.database.base import Base


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ArbitragePosition(Base):
    __tablename__ = "arbitrage_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    entry_arb_diff_bps: Mapped[float] = mapped_column(Float, nullable=False)
    entry_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[PositionStatus] = mapped_column(
        String, default=PositionStatus.OPEN, nullable=False
    )
    unfavorable_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    long_dex: Mapped[str] = mapped_column(String, nullable=False)
    short_dex: Mapped[str] = mapped_column(String, nullable=False)
    size_usd: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self):
        return (
            f"<ArbitragePosition(id={self.id}, symbol='{self.symbol}', "
            f"status='{self.status}', size_usd={self.size_usd})>"
        )
