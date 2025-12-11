from decimal import Decimal
from typing import Any
from x10.perpetual.accounts import StarkPerpetualAccount
from x10.perpetual.configuration import MAINNET_CONFIG
from x10.perpetual.order_object import create_order_object
from x10.perpetual.orders import OrderSide
from x10.perpetual.trading_client import PerpetualTradingClient


from src.dex_adapters.base import DexAdapter
from src.dex_adapters.config import extended_config as config
from src.models import ExtendedPosition, Side


async def build_markets_cache(trading_client: PerpetualTradingClient):
    markets = await trading_client.markets_info.get_markets()
    assert markets.data is not None
    return {m.name: m for m in markets.data if m.active}


class ExtendedAdapter(DexAdapter):
    name = "ExtendedAdapter"

    def __init__(self):
        super().__init__()
        self.stark_account = StarkPerpetualAccount(
            vault=config.vault_id,
            api_key=config.api_key,
            private_key=config.private_key,
            public_key=config.public_key,
        )
        self.trading_client = PerpetualTradingClient(MAINNET_CONFIG, self.stark_account)
        self.markets_cache = None

    async def close(self):
        """Close the trading client."""
        await self.trading_client.close()

    def market_name(self, token: str) -> str:
        """Get market name for a given token."""
        return f"{token}-USD"

    async def get_market(self, market_name: str):
        """Gets the market model object for a given market name."""
        if self.markets_cache is None:
            self.markets_cache = await build_markets_cache(self.trading_client)
        return self.markets_cache.get(market_name)

    async def get_balance(self) -> Any:
        """Get available balance for trading."""
        balance_response_wrapped = await self.trading_client.account.get_balance()
        balance_response = balance_response_wrapped.data
        if not balance_response:
            return 0.0
        return float(balance_response.available_for_trade)

    async def list_positions(self, token: str | None) -> list[ExtendedPosition]:
        """
        Return open positions on this DEX for token.
        Implement as async if the DEX API is async, otherwise as sync.
        """
        positions_response_wrapped = await self.trading_client.account.get_positions(
            market_names=[self.market_name(token)] if token else None
        )
        if not positions_response_wrapped.data:
            return []
        positions_response = [
            {
                "position_id": pos.id,
                "token": pos.market.split("-")[0],
                "side": Side.LONG if pos.side == OrderSide.BUY else Side.SHORT,
                "size": float(abs(pos.size)),
                "entry_price": float(pos.open_price),
                "unrealized_pnl": float(pos.unrealised_pnl),
                "realized_pnl": float(pos.realised_pnl),
                "mark_price": float(pos.mark_price),
            }
            for pos in positions_response_wrapped.data
        ]

        return [ExtendedPosition.model_validate(pos) for pos in positions_response]

    async def get_price(self, token: str, side: Side) -> float:
        wrapped_orderbook = (
            await self.trading_client.markets_info.get_orderbook_snapshot(
                market_name=self.market_name(token)
            )
        )
        orderbook = wrapped_orderbook.data
        if orderbook:
            if side == Side.LONG:
                return float(orderbook.bid[0].price)
            else:
                return float(orderbook.ask[0].price)
        else:
            wrapped_market_stats = (
                await self.trading_client.markets_info.get_market_statistics(
                    market_name=self.market_name(token)
                )
            )
            market_stats = wrapped_market_stats.data
            if not market_stats:
                raise ValueError(
                    f"Market stats for {self.market_name(token)} not found"
                )
            if side == Side.LONG:
                return float(market_stats.bid_price)
            else:
                return float(market_stats.ask_price)

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
        await self.trading_client.account.update_leverage(
            self.market_name(token), Decimal(leverage)
        )

        market = await self.get_market(self.market_name(token))
        if not market:
            raise ValueError(f"Market {self.market_name(token)} not found")
        price = Decimal(await self.get_price(token, side))
        order = create_order_object(
            account=self.stark_account,
            market=market,
            amount_of_synthetic=Decimal(size),
            price=price,
            side=OrderSide.BUY if side == Side.LONG else OrderSide.SELL,
            starknet_domain=MAINNET_CONFIG.starknet_domain,
        )
        response = await self.trading_client.orders.place_order(order)
        if not response.data:
            raise Exception("Failed to open position: No response from trading client")
        return {
            "position_id": response.data.id,
            "filled_size": float(size),
            "entry_price": float(price),
        }

    async def close_position(self, token: str) -> dict:
        """
        Close all or part of a position. Return dict with closed_size and realized_pnl.
        Implement as async if the DEX API is async, otherwise as sync.
        """
        open_position = await self.list_positions(token)
        if not open_position:
            raise Exception(f"No open position found for token {token}")
        position = open_position[0]
        side = OrderSide.SELL if position.side == Side.LONG else OrderSide.BUY
        price = await self.get_price(
            token, Side.SHORT if position.side == Side.LONG else Side.LONG
        )
        market = await self.get_market(self.market_name(token))
        if not market:
            raise ValueError(f"Market {self.market_name(token)} not found")
        order = create_order_object(
            account=self.stark_account,
            market=market,
            amount_of_synthetic=Decimal(abs(position.size)),
            price=Decimal(price),
            side=side,
            starknet_domain=MAINNET_CONFIG.starknet_domain,
        )
        response = await self.trading_client.orders.place_order(order)
        if not response.data:
            raise Exception("Failed to close position: No response from trading client")
        return {
            "position_id": response.data.id,
            "filled_size": float(abs(position.size)),
            "price": float(price),
        }
