from datetime import datetime, timezone
import decimal
from typing import Optional

from src.db_setup import ArbRun, Position, Session, redis_lock
from src.dex_adapters.base import DexAdapter
from src.models import Side
import inspect


def decimalize(v):
    return decimal.Decimal(v)


async def compute_trade_size(
    long_adapter: DexAdapter, short_adapter: DexAdapter, coin: str, config_fraction=0.5
):
    """
    Determine size to open based on smaller available balance.
    config_fraction (0..1) of available balance to use.
    Supports both sync and async adapters.
    """
    if inspect.iscoroutinefunction(long_adapter.get_balance):
        bal_long = decimalize(await long_adapter.get_balance(coin))
    else:
        bal_long = decimalize(long_adapter.get_balance(coin))
    if inspect.iscoroutinefunction(short_adapter.get_balance):
        bal_short = decimalize(await short_adapter.get_balance(coin))
    else:
        bal_short = decimalize(short_adapter.get_balance(coin))
    usable = min(bal_long, bal_short) * decimalize(config_fraction)
    return usable


async def open_positions(
    long_adapter: DexAdapter,
    short_adapter: DexAdapter,
    coin: str,
    leverage=1,
    fraction=0.5,
):
    """
    Opens matching long and short positions on two DEXs. Supports both sync and async adapters.
    """
    key = f"open:{coin}:{long_adapter.name}:{short_adapter.name}"
    with redis_lock(key, ttl=30):
        session = Session()
        leverage = int(leverage)
        try:
            size = await compute_trade_size(
                long_adapter, short_adapter, coin, config_fraction=fraction
            )
            if size <= 0:
                raise RuntimeError("Computed size is zero")
            size = float(size)
            # Open long
            long_res = await long_adapter.open_position(coin, Side.LONG, size, leverage)
            # Open short
            short_res = await short_adapter.open_position(
                coin, Side.SHORT, size, leverage
            )

            # Persist positions
            long_pos = Position(
                dex_name=long_adapter.name,
                coin=coin,
                side=Side.LONG.value,
                size=size,
                entry_price=decimalize(long_res.get("entry_price", 0)),
                leverage=leverage,
                position_id_on_dex=long_res["position_id"],
                status="OPEN",
            )
            short_pos = Position(
                dex_name=short_adapter.name,
                coin=coin,
                side=Side.SHORT.value,
                size=size,
                entry_price=decimalize(short_res.get("entry_price", 0)),
                leverage=leverage,
                position_id_on_dex=short_res["position_id"],
                status="OPEN",
            )
            session.add(long_pos)
            session.add(short_pos)
            session.commit()

            # link in arb_runs
            run = ArbRun(
                long_pos_id=long_pos.id,
                short_pos_id=short_pos.id,
                open_at=datetime.now(timezone.utc),
                status="OPEN",
            )
            session.add(run)
            session.commit()
            return {
                "arb_run_id": run.id,
                "long_pos_id": long_pos.id,
                "short_pos_id": short_pos.id,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


async def close_positions(
    long_adapter: DexAdapter,
    short_adapter: DexAdapter,
    coin: str,
    arb_run_id: Optional[int] = None,
):
    """
    Close the two legs of an arb (identified by arb_run_id if provided) but account for overlapping positions.
    If arb_run_id is not provided, this will attempt to close the latest matching open arb between these two.
    Supports both sync and async adapters.
    """
    key = f"close:{coin}:{long_adapter.name}:{short_adapter.name}"
    with redis_lock(key, ttl=30):
        session = Session()
        try:
            # Find arb run
            if arb_run_id:
                run = session.query(ArbRun).filter(ArbRun.id == arb_run_id).one()
            else:
                run = (
                    session.query(ArbRun)
                    .filter(ArbRun.status == "OPEN")
                    .order_by(ArbRun.open_at.desc())
                    .first()
                )
            if not run:
                raise RuntimeError("No open arb run found")

            long_pos = session.query(Position).get(run.long_pos_id)
            short_pos = session.query(Position).get(run.short_pos_id)
            if not long_pos or not short_pos:
                raise RuntimeError("Missing positions")

            # Close long leg on long_adapter (partial allowed)
            res_long_close = await long_adapter.close_position(coin)

            long_pos.status = "CLOSED"
            long_pos.size = decimalize(long_pos.size)
            long_pos.updated_at = datetime.now(timezone.utc)
            session.add(long_pos)

            # Close short leg on short_adapter
            res_short_close = await short_adapter.close_position(coin)

            short_pos.status = "CLOSED"
            short_pos.updated_at = datetime.now(timezone.utc)
            session.add(short_pos)

            run.close_at = datetime.now(timezone.utc)
            run.status = "CLOSED"
            session.add(run)
            session.commit()
            return {
                "run_id": run.id,
                "long_closed": res_long_close,
                "short_closed": res_short_close,
            }

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
