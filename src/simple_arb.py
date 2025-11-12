import asyncio

from src.db_utils import (
    get_arbitrage_opportunities,
    get_coins_for_dex,
    get_recent_funding_rates,
)
from src.dex_adapters.hyperliquid import HyperliquidAdapter
from src.dex_adapters.lighter_adapter import LighterAdapter
from src.models import Side
from src.advanced_strategy.position_management import compute_trade_size


THRESHOLD = 10  # in bps


LIGHTER = LighterAdapter()
HYPERLIQUID = HyperliquidAdapter()


async def enter_arb(coin_symbol: str, lighter_long: bool):
    size = await compute_trade_size(LIGHTER, HYPERLIQUID, 0.5)

    lighter_open = LIGHTER.open_position(
        coin_symbol, Side.LONG if lighter_long else Side.SHORT, float(size), 1, 0.01
    )
    hyperliquid_open = HYPERLIQUID.open_position(
        coin_symbol, Side.SHORT if lighter_long else Side.LONG, float(size), 1, 0.01
    )
    try:
        _ = await asyncio.gather(lighter_open, hyperliquid_open)
    except Exception as e:
        print(f"Error entering arbitrage: {e}")
        await exit_arb(coin_symbol)


async def exit_arb(coin_symbol: str):
    await LIGHTER.close_position(coin_symbol, slippage=0.02)
    await HYPERLIQUID.close_position(coin_symbol)


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
                lighter_funding_rates, hyperliquid_funding_rates, 10.0
            )
            best_arb_coin, best_arb = get_best_arbitrage_coin(arbitrages)
            if not arbitrages:
                if current_arb_coin:
                    print(
                        f"Current arb coin {current_arb_coin} no longer has an opportunity. Exiting arb."
                    )
                    await exit_arb(current_arb_coin)
                    current_arb_coin = ""
                print("No arbitrage opportunities found.")
                await asyncio.sleep(30)
                continue
            if best_arb_coin == current_arb_coin and current_arb_coin:
                if (entered_arb / abs(entered_arb)) * (best_arb / abs(best_arb)) < 0:
                    print(
                        f"Arbitrage direction changed for {current_arb_coin}. Exiting arb."
                    )
                    await exit_arb(current_arb_coin)
            if not current_arb_coin:
                lighter_long = (
                    arbitrages[best_arb_coin]["buy_on_a_sell_on_b"] and lighter_first
                )
                await enter_arb(best_arb_coin, lighter_long)
                current_arb_coin = best_arb_coin
                entered_arb = arbitrages[best_arb_coin]["arb_diff_bps"]
            else:
                if current_arb_coin not in [arb["coin_symbol"] for arb in arbitrages]:
                    print(
                        f"Current arb coin {current_arb_coin} no longer has an opportunity. Exiting arb."
                    )
                    await exit_arb(current_arb_coin)
                    lighter_long = (
                        arbitrages[best_arb_coin]["buy_on_a_sell_on_b"]
                        and lighter_first
                    )
                    await enter_arb(best_arb_coin, lighter_long)
                    current_arb_coin = best_arb_coin
                    entered_arb = arbitrages[best_arb_coin]["arb_diff_bps"]

            await asyncio.sleep(30)

    except KeyboardInterrupt:
        print("Exiting...")
        await LIGHTER.close()


if __name__ == "__main__":
    asyncio.run(main())
