from models import Side


class DexAdapter:
    """
    Interface - adapter per DEX must implement these methods
    """

    name: str

    def __init__(self):
        pass

    async def get_balance(self) -> float:
        """
        Return available collateral or balance usable for opening positions.
        Implement as async if the DEX API is async, otherwise as sync.
        """
        raise NotImplementedError

    async def list_positions(self, token: str) -> list[dict]:
        """
        Return open positions on this DEX for token.
        Implement as async if the DEX API is async, otherwise as sync.
        """
        raise NotImplementedError

    async def open_position(
        self,
        token: str,
        side: Side,
        size: float,
        leverage: int,
        slippage: float,
        create_order_without_leverage_set: bool = False,
    ) -> dict:
        """
        Open position on DEX. Return dict with position_id and filled_size & entry_price.
        Implement as async if the DEX API is async, otherwise as sync.
        """
        raise NotImplementedError

    async def close_position(self, token: str) -> dict:
        """
        Close all or part of a position. Return dict with closed_size and realized_pnl.
        Implement as async if the DEX API is async, otherwise as sync.
        """
        raise NotImplementedError
