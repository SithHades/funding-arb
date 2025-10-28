import asyncio
from decimal import ROUND_DOWN, Decimal
import time
import lighter
from src.dex_adapters.base import DexAdapter
from src.dex_adapters.config import lighter_config as config
from src.dex_adapters.utils import to_base_amount_int
from src.models import Side


class LighterAdapter(DexAdapter):
    name = "Lighter"

    def __init__(self):
        super().__init__()
        self.api_client = lighter.ApiClient(
            configuration=lighter.Configuration(host=config.base_url)
        )
        self.account_api = lighter.AccountApi(self.api_client)
        self.signer_client = lighter.SignerClient(
            url=config.base_url,
            private_key=config.private_key,
            account_index=config.account_index,
            api_key_index=config.key_index,
        )
        self.funding_api = lighter.FundingApi(self.api_client)
        self.candlestick_api = lighter.CandlestickApi(self.api_client)
        self.orderbook_api = lighter.OrderApi(self.api_client)
        self._token_market_id: dict[str, int] | None = None
        self._token_market_lock: asyncio.Lock = asyncio.Lock()

    async def close(self):
        await self.api_client.close()
        await self.signer_client.close()

    async def generate_market_id_map(self) -> dict[str, int]:
        market_id_map = {}
        response = await self.funding_api.funding_rates()
        for funding_rate in response.funding_rates:
            market_id_map[funding_rate.symbol] = funding_rate.market_id
        return market_id_map

    async def _ensure_market_map(self) -> dict[str, int]:
        """Ensure the token -> market_id map is loaded and cached.

        Uses double-checked locking so multiple concurrent callers share the same
        initialization and we only perform the async network call once.
        """
        if self._token_market_id is None:
            async with self._token_market_lock:
                if self._token_market_id is None:
                    self._token_market_id = await self.generate_market_id_map()
        return self._token_market_id

    async def get_market_id(self, token: str) -> int | None:
        mapping = await self._ensure_market_map()
        return mapping.get(token)

    async def get_balance(self) -> float:
        response: lighter.DetailedAccounts = await self.account_api.account(
            by="l1_address", value=config.address
        )
        balance = response.accounts[0].available_balance
        return round(float(balance), 6)

    async def list_positions(self, token: str | None) -> list[dict]:
        response: lighter.DetailedAccounts = await self.account_api.account(
            by="l1_address", value=config.address
        )
        positions = []
        for position in response.accounts[0].positions:
            if isinstance(position, lighter.AccountPosition):
                if float(position.position) > 0:
                    positions.append(position.model_dump())
        if token:
            positions = [pos for pos in positions if pos.get("symbol") == token]
        return positions

    async def set_leverage(self, token: str, leverage: int) -> bool:
        # todo find market_id from token symbol
        market_id = await self.get_market_id(token)
        if market_id is None:
            return False
        _, _, err = await self.signer_client.update_leverage(
            market_id, self.signer_client.CROSS_MARGIN_MODE, int(leverage)
        )

        if err is not None:
            raise Exception(f"Error setting leverage: {err}")
        return True

    def get_client_order_index(self) -> int:
        # Client order index must be unique per user.
        # Using timestamp in milliseconds for simplicity.
        return int(time.time() * 1000)

    async def get_market_index(self, token: str) -> int:
        market_index = await self.get_market_id(token)
        if market_index is None:
            raise Exception(f"Could not find market ID for token {token}")
        return market_index

    async def calculate_amount_and_avg_execution_price(
        self, is_ask: bool, size: float, market_index: int
    ) -> tuple[int, float]:
        response = await self.orderbook_api.order_book_details(market_id=market_index)
        if response.code != 200:
            raise Exception(
                f"Could not fetch order book for market ID {market_index}, code {response.code}"
            )
        if len(response.order_book_details) == 0:
            raise Exception(f"Could not fetch order book for market ID {market_index}")

        orderbook: lighter.OrderBookDetail = response.order_book_details[0]
        asset_price = (
            Decimal(str(orderbook.last_trade_price))
            if orderbook.last_trade_price
            else None
        )
        if not asset_price or asset_price == 0:
            raise Exception(
                "Cannot compute base amount because last_trade_price is unavailable/zero."
            )

        # Convert USD size to base token amount (size_usd is USD value you want to trade)
        size_usd_dec = Decimal(str(size))
        base_amount_tokens = size_usd_dec / asset_price

        # enforce min_base_amount
        min_base_amount = (
            Decimal(str(orderbook.min_base_amount))
            if orderbook.min_base_amount
            else Decimal("0")
        )
        if base_amount_tokens < min_base_amount:
            raise Exception(
                f"Requested base amount {base_amount_tokens} < market min_base_amount {min_base_amount}"
            )

        # Convert to integer units expected by API
        size_decimals = getattr(
            orderbook, "supported_size_decimals", getattr(orderbook, "size_decimals", 0)
        )
        scale = 10 ** int(size_decimals)
        base_amount_int = to_base_amount_int(base_amount_tokens, size_decimals)

        # sanity: ensure base_amount_int >= scaled min
        if base_amount_int < int(
            (min_base_amount * Decimal(scale)).to_integral_value(rounding=ROUND_DOWN)
        ):
            raise Exception(
                "Converted base_amount is below market minimum after scaling."
            )

        last_price = Decimal(str(orderbook.last_trade_price))
        if last_price <= 0:
            raise Exception("Invalid last trade price")

        if is_ask:
            avg_execution_price = last_price * Decimal("0.975")  # Sell slightly below
        else:
            avg_execution_price = last_price * Decimal("1.025")  # Buy slightly above

        avg_execution_price = avg_execution_price.quantize(
            Decimal(f"1e-{orderbook.supported_price_decimals}")
        )
        return (
            base_amount_int,
            float(avg_execution_price),
            last_price,
            base_amount_tokens,
        )

    async def open_position(
        self,
        token: str,
        side: Side,
        size: float,
        leverage: int,
        slippage: float = 0.01,
        create_order_without_leverage_set: bool = False,
    ) -> dict:
        """
        Opens a market position.
        :param token: The trading pair/token to open the position on.
        :param side: The side of the position (LONG or SHORT).
        :param size: The size of the position to open in USD.
        :param leverage: The leverage to use for the position.
        :param create_order_without_leverage_set: If True, will attempt to create the order even if leverage setting fails.
        :return: A dictionary with position details including position_id, filled
        """
        leverage_set = await self.set_leverage(token, leverage)
        if not leverage_set and not create_order_without_leverage_set:
            raise Exception(
                f"Could not set leverage to {leverage}x for {token} on Lighter"
            )

        market_index = await self.get_market_index(token)
        client_order_index = self.get_client_order_index()
        is_ask = True if side == Side.SHORT else False

        (
            base_amount_int,
            avg_execution_price,
            last_price,
            base_amount_tokens,
        ) = await self.calculate_amount_and_avg_execution_price(is_ask, size)

        order, hash, err = await self.signer_client.create_market_order(
            market_index=int(market_index),
            client_order_index=client_order_index,  # This needs to be a user-unique int value.
            base_amount=base_amount_int,
            avg_execution_price=avg_execution_price,  # has to be within 5% of last_trade_price we want this to be a market order.
            is_ask=is_ask,
            reduce_only=False,
        )
        if err is not None:
            raise Exception(f"Error creating market order: {err}")
        try:
            fill_price = order.price
        except AttributeError:
            fill_price = last_price
        return {
            "order_id": client_order_index,
            "filled_size": float(base_amount_tokens * fill_price),
            "entry_price": fill_price,
        }

    async def close_position(self, token: str) -> bool:
        pass
