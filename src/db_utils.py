import psycopg2

from src.db_setup import DATABASE_URL


COIN_ID_TO_SYMBOL_CACHE = {}


def get_coins_for_dex(dex_name: str) -> list[tuple]:
    """Get list of coins with open positions on a given DEX."""
    query = """
        SELECT DISTINCT c.id, c.symbol
        FROM funding_rates f
        JOIN coin c ON f.coin_id = c.id
        WHERE f.dex = %s;
    """
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(query, (dex_name,))
    pairs = cur.fetchall()

    cur.close()
    conn.close()
    return pairs


def get_recent_funding_rates(
    dex_name: str, coin_ids: list[int], minutes: int = 5
) -> dict[int, list[dict]]:
    """
    Get recent funding rates for a given DEX and coin.
    Returns a dict mapping of coin id to list of funding rate dicts (sorted by timestamp desc).
    """
    query = """
        SELECT coin_id, dex, funding_rate / 10.0 AS funding_rate, timestamp
        FROM funding_rates
        WHERE dex = %s
          AND coin_id = ANY(%s)
          AND timestamp >= NOW() - INTERVAL '%s minutes';
    """
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(query, (dex_name, coin_ids, minutes))
    rates_tuple = cur.fetchall()

    cur.close()
    conn.close()

    rates = {}
    for rate in rates_tuple:
        rates.setdefault(rate[0], []).append(
            {
                "funding_rate_bps": float(rate[2]),
                "timestamp": rate[3],
            }
        )
    for _, rate_list in rates.items():
        rate_list.sort(key=lambda x: x["timestamp"], reverse=True)

    return rates


def get_arbitrage_opportunities(
    rates_a: dict[int, list[dict]],
    rates_b: dict[int, list[dict]],
    threshold: float = 20.0,
) -> dict:
    """
    Given two dicts of funding rates (from get_recent_funding_rates), find arbitrage opportunities.
    Returns a list of dicts with coin_id, coin_symbol, rate_a, rate_b, arb_diff_bps and where to buy.
    """
    opportunities = {}
    for coin_id in rates_a.keys():
        if coin_id in rates_b:
            latest_rate_a = rates_a[coin_id][0]["funding_rate_bps"]
            latest_rate_b = rates_b[coin_id][0]["funding_rate_bps"]
            arb_diff = latest_rate_a - latest_rate_b
            if not abs(arb_diff) > threshold:
                continue
            symbol = get_symbol_for_coin_id(coin_id)
            opportunities[symbol] = {
                "coin_id": coin_id,
                "coin_symbol": symbol,
                "rate_a_bps": latest_rate_a,
                "rate_b_bps": latest_rate_b,
                "arb_diff_bps": round(arb_diff, 2),
                "buy_on_a_sell_on_b": latest_rate_a < latest_rate_b,
            }
    return opportunities


def get_symbol_for_coin_id(coin_id: int) -> str:
    """Get coin symbol for a given coin id."""
    if coin_id in COIN_ID_TO_SYMBOL_CACHE:
        return COIN_ID_TO_SYMBOL_CACHE[coin_id]
    query = "SELECT symbol FROM coin WHERE id = %s;"
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(query, (coin_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if result:
        COIN_ID_TO_SYMBOL_CACHE[coin_id] = result[0]
    return (
        COIN_ID_TO_SYMBOL_CACHE[coin_id]
        if coin_id in COIN_ID_TO_SYMBOL_CACHE
        else "UNKNOWN"
    )


if __name__ == "__main__":
    lighter_coins = set([c for c, _ in get_coins_for_dex("lighter")])
    hyperliquid_coins = set([c for c, _ in get_coins_for_dex("hyperliquid")])
    common_coins = lighter_coins.intersection(hyperliquid_coins)
    hyperliquid_funding_rates = get_recent_funding_rates(
        "hyperliquid", list(common_coins), minutes=5
    )
    lighter_funding_rates = get_recent_funding_rates(
        "lighter", list(common_coins), minutes=5
    )
    arbitrages = get_arbitrage_opportunities(
        lighter_funding_rates, hyperliquid_funding_rates, 5.0
    )
    print("Arbitrage opportunities between Lighter and Hyperliquid:")
    for coin_symbol, arb in arbitrages.items():
        print(f" - {coin_symbol}: {arb['arb_diff_bps']} bps")
