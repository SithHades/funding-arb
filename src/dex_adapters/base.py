from src.models import Side


class DexAdapter:
    """
    Interface - adapter per DEX must implement these methods
    """

    name: str

    def __init__(self):
        pass

    def get_balance(self) -> float:
        """
        return available collateral or balance usable for opening positions
        """
        raise NotImplementedError

    def list_positions(self, token: str) -> list[dict]:
        """
        return open positions on this DEX for token
        """
        raise NotImplementedError

    def open_position(
        self,
        token: str,
        side: Side,
        size: float,
        leverage: int,
        slippage: float,
        create_order_without_leverage_set: bool = False,
    ) -> dict:
        """
        open position on DEX. Return dict with position_id and filled_size & entry_price
        """
        raise NotImplementedError

    def close_position(self, token: str) -> dict:
        """
        close all or part of a position. Return dict with closed_size and realized_pnl
        """
        raise NotImplementedError
