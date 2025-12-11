from enum import Enum

from pydantic import BaseModel


class Side(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Position(BaseModel):
    position_id: str
    token: str
    side: Side
    size: float
    entry_price: float
    unrealized_pnl: float
    realized_pnl: float


class ExtendedPosition(Position):
    mark_price: float
