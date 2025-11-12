import asyncio
from datetime import datetime, timezone
from decimal import Decimal, getcontext
import os
from typing import Optional

import dotenv
from sqlalchemy import text
from src.db_setup import redis_lock, engine
from src.dex_adapters.hyperliquid import HyperliquidAdapter
from src.dex_adapters.lighter_adapter import LighterAdapter
from src.advanced_strategy.position_management import close_positions, open_positions


dotenv.load_dotenv()


EMA_ALPHA = float(os.environ.get("EMA_ALPHA", "0.15"))  # how fast EMA adapts
EMA_MINUTES = int(
    os.environ.get("EMA_MINUTES", "60")
)  # fallback window to fetch if no EMA state
ESTIMATED_SWITCH_COST = Decimal(os.environ.get("ESTIMATED_SWITCH_COST", "0.0025"))
# estimated fractional cost (e.g., 0.0025 = 0.25% of notional). This covers slippage/spread/imbalance cost.
MIN_PROFIT_BUFFER = Decimal(os.environ.get("MIN_PROFIT_BUFFER", "0.0005"))
# minimum extra expected funding spread (fraction) beyond switch cost to perform a swap

POLL_INTERVAL = int(
    os.environ.get("POLL_INTERVAL", "60")
)  # seconds between arb decisions
COINS = os.environ.get("COINS", "BTC,ETH,SOL").split(",")


# ---------- Utilities ----------
getcontext().prec = 28


def fetch_recent_rates_from_db(
    dex_name: str, coin: str, minutes: int
) -> list[tuple[datetime, Decimal]]:
    """
    Query last `minutes` entries (by timestamp) for given dex/coin. Return list of (ts, rate).
    Assumes table funding_rates(dex_name, coin, funding_rate, timestamp).
    """
    with engine.connect() as conn:
        q = text("""
            SELECT timestamp, funding_rate
            FROM funding_rates
            WHERE dex_name = :dex AND coin = :coin
              AND timestamp >= (now() AT TIME ZONE 'utc') - (:mins || ' minutes')::interval
            ORDER BY timestamp ASC
        """)
        rows = conn.execute(
            q, {"dex": dex_name, "coin": coin, "mins": minutes}
        ).fetchall()
    return [(r[0], Decimal(str(r[1]))) for r in rows]


def ema_from_series(series: list[Decimal], alpha: float) -> Optional[Decimal]:
    if not series:
        return None
    ema = series[0]
    for value in series[1:]:
        ema = (Decimal(str(alpha)) * value) + (
            (Decimal("1") - Decimal(str(alpha))) * ema
        )
    return ema


def expected_rate(
    dex_name: str,
    coin: str,
    lookback_minutes: int = EMA_MINUTES,
    alpha: float = EMA_ALPHA,
) -> Decimal:
    """
    Compute expected funding rate for next hour using EMA of recent minute samples.
    Returns Decimal. If no data, returns Decimal('0').
    """
    rows = fetch_recent_rates_from_db(dex_name, coin, lookback_minutes)
    if not rows:
        return Decimal("0")
    series = [r for (_, r) in rows]
    ema = ema_from_series(series, alpha)
    return ema if ema is not None else Decimal("0")


# ---------- Position / arb run helpers ----------
def get_open_arbruns() -> list[dict]:
    """
    Query arb_runs joined with positions to find currently OPEN arb runs.
    We'll use direct SQL for brevity.
    Return list of dicts: {id, coin, long_dex, short_dex, long_pos_id, short_pos_id, open_at}
    """
    with engine.connect() as conn:
        q = text("""
            SELECT
              ar.id as arb_id,
              p_long.dex_name as long_dex,
              p_short.dex_name as short_dex,
              p_long.coin as coin,
              ar.long_pos_id,
              ar.short_pos_id,
              ar.open_at
            FROM arb_runs ar
            JOIN positions p_long ON ar.long_pos_id = p_long.id
            JOIN positions p_short ON ar.short_pos_id = p_short.id
            WHERE ar.status = 'OPEN'
        """)
        rows = conn.execute(q).fetchall()
    result = []
    for r in rows:
        result.append(
            {
                "arb_id": r[0],
                "long_dex": r[1],
                "short_dex": r[2],
                "coin": r[3],
                "long_pos_id": r[4],
                "short_pos_id": r[5],
                "open_at": r[6],
            }
        )
    return result


# ---------- Decision logic ----------
def score_pair(long_dex_name: str, short_dex_name: str, coin: str) -> Decimal:
    """
    Return expected funding spread (LONG funding - SHORT funding) for next hour.
    The higher the value, the better long_dex receives funding vs short_dex paying.
    """
    r_long = expected_rate(long_dex_name, coin)
    r_short = expected_rate(short_dex_name, coin)
    return r_long - r_short


def pick_best_pair(
    coins: list[str], dex_names: list[str]
) -> tuple[Optional[tuple[str, str, str]], Decimal]:
    """
    For all coin x dex pair combinations (long, short) return best (long, short, coin) and its score.
    """
    best = None
    best_score = Decimal("-Inf")
    for coin in coins:
        for i in range(len(dex_names)):
            for j in range(len(dex_names)):
                if i == j:
                    continue
                long = dex_names[i]
                short = dex_names[j]
                sc = score_pair(long, short, coin)
                if sc is None:
                    continue
                if sc > best_score:
                    best_score = sc
                    best = (long, short, coin)
    return best, best_score


async def decide_and_act(lighter_adapter, hyper_adapter):
    """
    Main decision routine. Called periodically.
    """
    dex_map = {lighter_adapter.name: lighter_adapter, hyper_adapter.name: hyper_adapter}
    dex_names = list(dex_map.keys())

    with redis_lock("arb:decision", ttl=55):
        open_runs = get_open_arbruns()

        # evaluate best available opportunity now
        candidate, candidate_score = pick_best_pair(COINS, dex_names)

        # convert candidate score to Decimal safely
        candidate_score = (
            Decimal(candidate_score)
            if candidate_score not in (None, Decimal("-Inf"))
            else Decimal("-999")
        )

        # If no open run, consider opening best candidate if above threshold
        if not open_runs:
            if candidate is None:
                print(f"{datetime.now(timezone.utc)}: No candidate found.")
                return
            # decision: check if expected spread > switch cost + buffer
            if candidate_score > (ESTIMATED_SWITCH_COST + MIN_PROFIT_BUFFER):
                long_name, short_name, coin = candidate
                print(
                    f"{datetime.now(timezone.utc)}: Opening new arb on {coin}: LONG {long_name} / SHORT {short_name} (score={candidate_score})"
                )
                long_adapter = dex_map[long_name]
                short_adapter = dex_map[short_name]
                await open_positions(long_adapter, short_adapter, coin)
            else:
                print(
                    f"{datetime.now(timezone.utc)}: Best candidate score {candidate_score} insufficient to open (need {ESTIMATED_SWITCH_COST + MIN_PROFIT_BUFFER})."
                )
            return

        # There exist open arbs. Evaluate each and possibly replace
        # For simplicity we evaluate each open arb individually comparing it to the global best.
        for run in open_runs:
            coin = run["coin"]
            current_long = run["long_dex"]
            current_short = run["short_dex"]
            current_score = score_pair(current_long, current_short, coin)
            current_score = Decimal(current_score)
            print(
                f"{datetime.now(timezone.utc)}: Open arb {run['arb_id']} on {coin} (LONG {current_long} / SHORT {current_short}) score={current_score}"
            )

            # If the global best is the same coin and same pair, nothing to do
            if candidate and (
                candidate[2] == coin
                and candidate[0] == current_long
                and candidate[1] == current_short
            ):
                print("Candidate equals current open arb. Hold.")
                continue

            # If there is a better candidate on any coin
            # We compare candidate_score (best overall) vs current_score. If candidate_score sufficiently better, replace.
            if candidate and candidate_score > (
                current_score + ESTIMATED_SWITCH_COST + MIN_PROFIT_BUFFER
            ):
                # Replace: close current arb and open candidate
                print(
                    f"{datetime.now(timezone.utc)}: Replacing arb {run['arb_id']} on {coin} (score {current_score}) with candidate {candidate} (score {candidate_score})"
                )
                # Close current run
                try:
                    long_adapter_cur = dex_map[current_long]
                    short_adapter_cur = dex_map[current_short]
                    await close_positions(
                        long_adapter_cur,
                        short_adapter_cur,
                        coin,
                        arb_run_id=run["arb_id"],
                    )
                except Exception as e:
                    print(
                        f"Error closing existing arb {run['arb_id']}: {e}. Aborting this replace attempt."
                    )
                    continue

                # Open candidate
                long_adapter = dex_map[candidate[0]]
                short_adapter = dex_map[candidate[1]]
                try:
                    await open_positions(long_adapter, short_adapter, candidate[2])
                except Exception as e:
                    print(
                        f"Error opening candidate arb {candidate}: {e}. You might be left unhedged — check logs."
                    )
                # After one replace, break to let locks/reconciliation catch up next loop
                break
            else:
                print(
                    f"Holding arb {run['arb_id']}. Candidate not sufficiently better (candidate_score={candidate_score}, current_score={current_score})"
                )


# ---------- Backtesting helper to estimate switch cost ----------
def backtest_switch_cost(
    dex_a: str, dex_b: str, coin: str, window_hours: int = 24
) -> Decimal:
    """
    A simple estimator for the expected cost of switching between two DEXs for a given coin.
    Idea: compute the average instantaneous change in spread when we 'simulate' switching:
      - for each minute t, compute spread_t = r_a(t) - r_b(t)
      - compute delta = abs(spread_{t+1} - spread_t) or focus on moments when we would have switched
    Use the median or mean of abs changes as a proxy for spread/slippage cost per hour.
    This is a heuristic; you should refine with real trade PnL logs.
    """
    minutes = window_hours * 60
    # fetch aligned time series for both dexes (last minutes)
    rows_a = fetch_recent_rates_from_db(dex_a, coin, minutes)
    rows_b = fetch_recent_rates_from_db(dex_b, coin, minutes)
    # align on timestamps by minute (simple approach)
    rate_map_a = {r[0].replace(second=0, microsecond=0): r[1] for r in rows_a}
    rate_map_b = {r[0].replace(second=0, microsecond=0): r[1] for r in rows_b}
    timestamps = sorted(set(rate_map_a.keys()) & set(rate_map_b.keys()))
    if len(timestamps) < 2:
        return Decimal("0")
    spreads = [rate_map_a[t] - rate_map_b[t] for t in timestamps]
    abs_deltas = [abs(spreads[i + 1] - spreads[i]) for i in range(len(spreads) - 1)]
    # use median of abs deltas as representative per-minute switching volatility
    abs_deltas_sorted = sorted(abs_deltas)
    median = abs_deltas_sorted[len(abs_deltas_sorted) // 2]
    # scale the median to an hourly-equivalent switching cost (because funding pays hourly)
    # conservative multiply by 60 (worst-case instant change across an hour)
    estimated = median * Decimal(60)
    print(
        f"Backtest: median per-minute abs spread delta={median}, hourly-scaled estimated switch cost={estimated}"
    )
    return estimated


# ---------- Main loop ----------
async def run_loop():
    # initialize adapters
    lighter_adapter = LighterAdapter()  # adapt constructor as needed
    hyper_adapter = HyperliquidAdapter()

    print("Starting arb manager main loop...")
    while True:
        try:
            await decide_and_act(lighter_adapter, hyper_adapter)
        except Exception as e:
            print(f"Decision loop error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    # Example usage:
    # 1) estimate switching cost from history (optional)
    # print("Estimating switch cost from history...")
    # est = backtest_switch_cost("lighter", "hyperliquid", "BTC", window_hours=72)
    # print("Historically estimated switch cost:", est)

    asyncio.run(run_loop())
