import asyncio
import logging

from src.db_utils import (
    get_arbitrage_opportunities,
    get_coins_for_dex,
    get_recent_funding_rates,
)
from src.dex_adapters.hyperliquid import HyperliquidAdapter
from src.dex_adapters.lighter_adapter import LighterAdapter
from src.models import Side
from src.advanced_strategy.position_management import compute_trade_size


logging.basicConfig(
    level=logging.INFO,  # or DEBUG for more detail
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

_logger = logging.getLogger(__name__)


THRESHOLD = 10  # in bps


async def enter_arb(
    coin_symbol: str,
    lighter_long: bool,
    lighter: LighterAdapter,
    hyperliquid: HyperliquidAdapter,
):
    size = await compute_trade_size(lighter, hyperliquid, 0.5)

    size = round(float(size), 2)

    lighter_open = lighter.open_position(
        coin_symbol, Side.LONG if lighter_long else Side.SHORT, size, 1, 0.045
    )
    hyperliquid_open = hyperliquid.open_position(
        coin_symbol, Side.SHORT if lighter_long else Side.LONG, size, 1, 0.02
    )
    try:
        _logger.info(f"Opening arb positions on {coin_symbol} with size {size}.")
        _ = await asyncio.gather(lighter_open, hyperliquid_open)
    except Exception as e:
        _logger.info(f"Error entering arbitrage: {e}")
        await exit_arb(coin_symbol, lighter, hyperliquid)


async def exit_arb(
    coin_symbol: str, lighter: LighterAdapter, hyperliquid: HyperliquidAdapter
):
    lighter_close = lighter.close_position(coin_symbol, slippage=0.02)
    hyperliquid_close = hyperliquid.close_position(coin_symbol)
    try:
        await asyncio.gather(lighter_close, hyperliquid_close)
    except Exception as e:
        _logger.info(f"Error exiting arbitrage: {e}")


def get_best_arbitrage_coin(arbitrages: dict) -> tuple[str, float]:
    """From a list of arbitrages, return the coin symbol with the highest arb_diff_bps."""
    best_coin = ""
    best_diff = 0.0
    for arb in arbitrages.values():
        if abs(arb["arb_diff_bps"]) > best_diff:
            best_diff = abs(arb["arb_diff_bps"])
            best_coin = arb["coin_symbol"]
    return best_coin, best_diff


async def main():
    lighter = LighterAdapter()
    hyperliquid = HyperliquidAdapter()
    current_arb_coin = ""
    entered_arb = 0.0
    lighter_coins = set([c for c, _ in get_coins_for_dex("lighter")])
    hyperliquid_coins = set([c for c, _ in get_coins_for_dex("hyperliquid")])
    lighter_first = True
    common_coins = lighter_coins.intersection(hyperliquid_coins)
    try:
        while True:
            hyperliquid_funding_rates = get_recent_funding_rates(
                "hyperliquid", list(common_coins), minutes=5
            )
            lighter_funding_rates = get_recent_funding_rates(
                "lighter", list(common_coins), minutes=5
            )
            arbitrages = get_arbitrage_opportunities(
                lighter_funding_rates, hyperliquid_funding_rates, 5.0
            )
            best_arb_coin, best_arb = get_best_arbitrage_coin(arbitrages)
            if not arbitrages:
                if current_arb_coin:
                    _logger.info(
                        f"Current arb coin {current_arb_coin} no longer has an opportunity. Exiting arb."
                    )
                    await exit_arb(current_arb_coin, lighter, hyperliquid)
                    current_arb_coin = ""
                _logger.info("No arbitrage opportunities found.")
                await asyncio.sleep(30)
                continue
            if best_arb_coin == current_arb_coin and current_arb_coin:
                if (entered_arb / abs(entered_arb)) * (best_arb / abs(best_arb)) < 0:
                    _logger.info(
                        f"Arbitrage direction changed for {current_arb_coin}. Last arb diff was {entered_arb} bps, now {best_arb} bps. Exiting arb."
                    )
                    await exit_arb(current_arb_coin, lighter, hyperliquid)
            if not current_arb_coin:
                lighter_long = (
                    arbitrages[best_arb_coin]["buy_on_a_sell_on_b"] and lighter_first
                )
                await enter_arb(best_arb_coin, lighter_long, lighter, hyperliquid)
                _logger.info(
                    f"Entering arbitrage on {best_arb_coin} with arb diff {best_arb} bps."
                )
                current_arb_coin = best_arb_coin
                entered_arb = arbitrages[best_arb_coin]["arb_diff_bps"]
            else:
                if current_arb_coin not in arbitrages.keys():
                    _logger.info(
                        f"Current arb coin {current_arb_coin} no longer has an opportunity. Exiting arb."
                    )
                    await exit_arb(current_arb_coin, lighter, hyperliquid)
                    lighter_long = (
                        arbitrages[best_arb_coin]["buy_on_a_sell_on_b"]
                        and lighter_first
                    )
                    await enter_arb(best_arb_coin, lighter_long, lighter, hyperliquid)
                    current_arb_coin = best_arb_coin
                    entered_arb = arbitrages[best_arb_coin]["arb_diff_bps"]
                else:
                    _logger.info(
                        f"Continuing arbitrage on {current_arb_coin} with arb diff {best_arb} bps."
                    )

            await asyncio.sleep(30)

    except KeyboardInterrupt:
        _logger.info("Exiting...")
    finally:
        await lighter.close()


if __name__ == "__main__":
    asyncio.run(main())
