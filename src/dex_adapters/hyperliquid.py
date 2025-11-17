import logging
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from src.dex_adapters.base import DexAdapter
from src.dex_adapters.config import hyperliquid_config as config
from src.models import Side


_logger = logging.getLogger(__name__)


class HyperliquidAdapter(DexAdapter):
    name = "Hyperliquid"

    def __init__(self, base_url: str = config.base_url):
        super().__init__()
        account: LocalAccount = eth_account.Account.from_key(config.private_key)
        self.address = config.address
        self.info = Info(base_url, config.skip_ws)
        self.exchange = Exchange(account, base_url, account_address=self.address)

    async def get_balance(self):
        user_state = self.info.user_state(self.address)
        margin_summary = user_state.get("marginSummary", {})
        balance = float(margin_summary.get("accountValue")) - float(
            margin_summary.get("totalNtlPos")
        )
        return round(balance, 4)

    async def list_positions(self, token: str | None = None):
        positions = self.info.user_state(self.address).get("assetPositions", [])
        if token:
            positions = [
                pos for pos in positions if pos.get("position", {}).get("coin") == token
            ]
        return positions

    async def set_leverage(self, token: str, leverage: int, is_cross: bool = False):
        response = self.exchange.update_leverage(leverage, token, is_cross)
        if response.get("status") == "ok":
            return True
        if response.get("status") == "err":
            response_message = response.get("response", "")
            if "Cross margin is not allowed in for this asset." in response_message:
                return False
        else:
            return False

    async def usd_to_token_amount(self, token: str, usd_amount: float) -> float:
        market_data: dict = self.info.all_mids()
        price = market_data.get(token)
        if price is None:
            raise Exception(
                f"Could not fetch price for token {token} to convert USD amount to token amount."
            )
        token_amount = float(usd_amount) / float(price)
        return round(token_amount, 4)

    async def open_position(
        self,
        token: str,
        side: Side,
        size: float,
        leverage: int = 1,
        slippage: float = 0.01,
        create_order_without_leverage_set: bool = False,
    ):
        """
        Opens a market position.
        :param token: The trading pair/token to open the position on.
        :param side: The side of the position (LONG or SHORT).
        :param size: The size of the position to open in USD.
        :param leverage: The leverage to use for the position.
        :param create_order_without_leverage_set: If True, will attempt to create the order even if leverage setting fails.
        :return: A dictionary with position details including position_id, filled
        """

        # First, set the leverage

        leverage_set = await self.set_leverage(token, leverage, False)
        if not leverage_set and not create_order_without_leverage_set:
            raise Exception(
                f"Could not set leverage to {leverage}x for {token} on Hyperliquid"
            )

        if size < 10:
            raise Exception("Minimum position size on Hyperliquid is $10.")

        is_buy = True if side == Side.LONG else False

        # Convert size from USD to token amount
        size_in_token = await self.usd_to_token_amount(token, size)

        order_result = self.exchange.market_open(
            token, is_buy, size_in_token, None, slippage
        )

        if order_result["status"] == "ok":
            for status in order_result["response"]["data"]["statuses"]:
                try:
                    filled: dict = status["filled"]
                    _logger.info(f"Order filled to open: {filled}")
                    return {
                        "order_id": filled["oid"],
                        "filled_size": filled["totalSz"],
                        "entry_price": filled["avgPx"],
                    }
                except KeyError:
                    _logger.info(f"Error: {status['error']}")
        else:
            raise Exception(f"Failed to open position on Hyperliquid: {order_result}")
        raise Exception("Failed to open position on Hyperliquid for unknown reasons.")

    async def close_position(self, token: str):
        order_result = self.exchange.market_close(token)
        if order_result and order_result["status"] == "ok":
            for status in order_result["response"]["data"]["statuses"]:
                try:
                    filled = status["filled"]
                    _logger.info(f"Order filled to close: {filled}")
                    return {
                        "order_id": filled["oid"],
                        "filled_size": filled["totalSz"],
                        "entry_price": filled["avgPx"],
                    }
                except KeyError:
                    _logger.info(f"Error: {status['error']}")
