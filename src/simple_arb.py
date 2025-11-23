import asyncio
import decimal
import logging
import time

from src.db_utils import (
    get_arbitrage_opportunities,
    get_coins_for_dex,
    get_recent_funding_rates,
)
from src.dex_adapters.base import DexAdapter
from src.dex_adapters.hyperliquid import HyperliquidAdapter
from src.dex_adapters.lighter_adapter import LighterAdapter
from src.models import Side
from src.database.session import init_models, AsyncSessionLocal
from src.database import repository
from datetime import datetime


logging.basicConfig(
    level=logging.INFO,  # or DEBUG for more detail
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

_logger = logging.getLogger("SimpleArb")


THRESHOLD = 10  # in bps
GRACE_PERIOD = 120  # seconds to wait before closing an arb when it becomes unfavorable


def decimalize(v):
    return decimal.Decimal(v)


async def compute_trade_size(
    long_adapter: DexAdapter, short_adapter: DexAdapter, config_fraction=0.5
):
    """
    Determine size to open based on smaller available balance.
    config_fraction (0..1) of available balance to use.
    Supports both sync and async adapters.
    """
    bal_long = decimalize(await long_adapter.get_balance())
    bal_short = decimalize(await short_adapter.get_balance())
    usable = min(bal_long, bal_short) * decimalize(config_fraction)
    return usable


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
        return size
    except Exception as e:
        _logger.info(f"Error entering arbitrage: {e}")
        await exit_arb(coin_symbol, lighter, hyperliquid)
        return 0.0


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
    await init_models()
    lighter = LighterAdapter()
    hyperliquid = HyperliquidAdapter()

    current_arb_coin = ""
    entered_arb = 0.0
    arb_unfavorable_since: float | None = None
    current_position_id = None

    async with AsyncSessionLocal() as session:
        positions = await repository.get_open_positions(session)
        if positions:
            if len(positions) > 1:
                _logger.warning(
                    f"Found {len(positions)} open positions, but simple_arb only supports one. Using the first one."
                )
            pos = positions[0]
            current_arb_coin = pos.symbol
            entered_arb = pos.entry_arb_diff_bps
            current_position_id = pos.id
            if pos.unfavorable_since:
                arb_unfavorable_since = pos.unfavorable_since.timestamp()
            _logger.info(f"Resumed position on {current_arb_coin} from DB.")
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

            # Determine if the current arbitrage has become unfavorable.
            now = time.time()
            unfavorable_reason = None
            if not arbitrages:
                # no arbitrage opportunities at all
                if current_arb_coin:
                    unfavorable_reason = "no_arbitrages"
            elif current_arb_coin:
                # check direction change (only if entered_arb was set previously)
                if best_arb_coin == current_arb_coin:
                    if entered_arb != 0 and best_arb != 0:
                        try:
                            if (entered_arb / abs(entered_arb)) * (
                                best_arb / abs(best_arb)
                            ) < 0:
                                unfavorable_reason = "direction_change"
                        except Exception:
                            # be conservative: if something odd happens, mark unfavorable
                            unfavorable_reason = "direction_change"
                else:
                    # current coin no longer present in arbitrages meaning below threshold
                    if current_arb_coin not in arbitrages.keys():
                        unfavorable_reason = "current_missing"

            # If unfavorable, start or check grace period timer
            if unfavorable_reason:
                if arb_unfavorable_since is None:
                    arb_unfavorable_since = now
                    if current_position_id:
                        async with AsyncSessionLocal() as session:
                            await repository.update_unfavorable_since(
                                session,
                                current_position_id,
                                datetime.fromtimestamp(now),
                            )
                    _logger.info(
                        f"Arbitrage for {current_arb_coin} became unfavorable ({unfavorable_reason}). Starting grace period of {GRACE_PERIOD}s."
                    )
                else:
                    elapsed = now - arb_unfavorable_since
                    if elapsed >= GRACE_PERIOD:
                        _logger.info(
                            f"Grace period expired ({GRACE_PERIOD}s). Exiting arb for {current_arb_coin} due to {unfavorable_reason}."
                        )
                        await exit_arb(current_arb_coin, lighter, hyperliquid)
                        if current_position_id:
                            async with AsyncSessionLocal() as session:
                                await repository.close_position(
                                    session, current_position_id
                                )
                            current_position_id = None
                        current_arb_coin = ""
                        arb_unfavorable_since = None

                        # TODO check if actually exited successfully

                        # after exiting, if there are arbitrages, enter the best available
                        if arbitrages:
                            _logger.info(
                                f"Entering a better arbitrage on {best_arb_coin} with arb diff {best_arb} bps."
                            )
                            lighter_long = (
                                arbitrages[best_arb_coin]["buy_on_a_sell_on_b"]
                                and lighter_first
                            )
                            size = await enter_arb(
                                best_arb_coin, lighter_long, lighter, hyperliquid
                            )
                            current_arb_coin = best_arb_coin
                            entered_arb = abs(arbitrages[best_arb_coin]["arb_diff_bps"])
                            if size > 0:
                                async with AsyncSessionLocal() as session:
                                    pos = await repository.create_position(
                                        session,
                                        best_arb_coin,
                                        entered_arb,
                                        "lighter" if lighter_long else "hyperliquid",
                                        "hyperliquid" if lighter_long else "lighter",
                                        size,
                                    )
                                    current_position_id = pos.id
                        else:
                            _logger.info("No arbitrage opportunities found after exit.")
                    else:
                        remaining = GRACE_PERIOD - elapsed
                        _logger.info(
                            f"Unfavorable condition '{unfavorable_reason}' for {current_arb_coin}. Will exit if it persists for {remaining:.0f}s more."
                        )
                        # wait a short while before re-evaluating
                        await asyncio.sleep(30)
                        continue
            else:
                # everything looks fine again; reset the grace timer
                if arb_unfavorable_since is not None:
                    arb_unfavorable_since = None
                    if current_position_id:
                        async with AsyncSessionLocal() as session:
                            await repository.update_unfavorable_since(
                                session, current_position_id, None
                            )

            # If we don't have an active arb, try to enter the best one
            if not current_arb_coin:
                if arbitrages:
                    lighter_long = (
                        arbitrages[best_arb_coin]["buy_on_a_sell_on_b"]
                        and lighter_first
                    )
                    _logger.info(
                        f"Entering arbitrage on {best_arb_coin} with arb diff {best_arb} bps."
                    )
                    size = await enter_arb(
                        best_arb_coin, lighter_long, lighter, hyperliquid
                    )
                    current_arb_coin = best_arb_coin
                    entered_arb = abs(arbitrages[best_arb_coin]["arb_diff_bps"])
                    if size > 0:
                        async with AsyncSessionLocal() as session:
                            pos = await repository.create_position(
                                session,
                                best_arb_coin,
                                entered_arb,
                                "lighter" if lighter_long else "hyperliquid",
                                "hyperliquid" if lighter_long else "lighter",
                                size,
                            )
                            current_position_id = pos.id
                else:
                    _logger.info("No arbitrage opportunities found.")
                    await asyncio.sleep(30)
                    continue
            else:
                # continuing the existing arbitrage
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
