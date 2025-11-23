from models import Side


class MockAdapter:
    name = "MockAdapter"

    def __init__(self):
        self.balance = 10000.0
        self.positions = []
        self.leverage = {}
        self.orders = []

    def get_balance(self):
        return self.balance

    def list_positions(self, token: str | None = None):
        if token:
            return [p for p in self.positions if p.get("token") == token]
        return self.positions.copy()

    def set_leverage(self, token: str, leverage: int, is_cross: bool = False):
        self.leverage[token] = leverage
        return True

    def usd_to_token_amount(self, token: str, usd_amount: float) -> float:
        # Mock: 1 token = $10
        return round(usd_amount / 10, 4)

    def open_position(
        self,
        token: str,
        side: Side,
        size: float,
        leverage: int = 1,
        slippage: float = 0.01,
        create_order_without_leverage_set: bool = False,
    ):
        if size < 1:
            raise Exception("Minimum position size is $1.")
        self.set_leverage(token, leverage)
        size_in_token = self.usd_to_token_amount(token, size)
        position = {
            "order_id": len(self.orders) + 1,
            "token": token,
            "side": side,
            "filled_size": size_in_token,
            "entry_price": 10.0,
        }
        self.positions.append(position)
        self.orders.append(position)
        return position

    def close_position(self, token: str):
        closed = [p for p in self.positions if p.get("token") == token]
        self.positions = [p for p in self.positions if p.get("token") != token]
        return {"orders": closed, "success": True}

    def get_orders(self, token: str | None = None, market_id: int | None = None):
        if token:
            return [o for o in self.orders if o.get("token") == token]
        return self.orders.copy()


class AsyncMockAdapter:
    name = "AsyncMockAdapter"

    def __init__(self):
        self.balance = 10000.0
        self.positions = []
        self.leverage = {}
        self.orders = []

    async def get_balance(self):
        return self.balance

    async def list_positions(self, token: str | None = None):
        if token:
            return [p for p in self.positions if p.get("token") == token]
        return self.positions.copy()

    async def set_leverage(self, token: str, leverage: int, is_cross: bool = False):
        self.leverage[token] = leverage
        return True

    async def usd_to_token_amount(self, token: str, usd_amount: float) -> float:
        # Mock: 1 token = $10
        return round(usd_amount / 10, 4)

    async def open_position(
        self,
        token: str,
        side: Side,
        size: float,
        leverage: int = 1,
        slippage: float = 0.01,
        create_order_without_leverage_set: bool = False,
    ):
        if size < 1:
            raise Exception("Minimum position size is $1.")
        await self.set_leverage(token, leverage)
        size_in_token = await self.usd_to_token_amount(token, size)
        position = {
            "order_id": len(self.orders) + 1,
            "token": token,
            "side": side,
            "filled_size": size_in_token,
            "entry_price": 10.0,
        }
        self.positions.append(position)
        self.orders.append(position)
        return position

    async def close_position(self, token: str):
        closed = [p for p in self.positions if p.get("token") == token]
        self.positions = [p for p in self.positions if p.get("token") != token]
        return {"orders": closed, "success": True}

    async def get_orders(self, token: str | None = None, market_id: int | None = None):
        if token:
            return [o for o in self.orders if o.get("token") == token]
        return self.orders.copy()
