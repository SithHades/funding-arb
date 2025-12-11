import psycopg2
from psycopg2.extras import execute_values
from fundings.config import config
from fundings.base import FundingRateData
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.conn_url = config.DATABASE_URL
        self._coin_cache: Dict[str, int] = {}

    def get_connection(self):
        return psycopg2.connect(self.conn_url)

    def _get_coin_id(self, cursor, symbol: str) -> Optional[int]:
        if symbol in self._coin_cache:
            return self._coin_cache[symbol]

        cursor.execute("SELECT id FROM coin WHERE symbol = %s", (symbol,))
        result = cursor.fetchone()
        if result:
            self._coin_cache[symbol] = result[0]
            return result[0]
        return None

    def save_funding_rates(self, rates: List[FundingRateData]):
        if not rates:
            return

        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Prepare data for insertion
                values = []
                for rate in rates:
                    coin_id = self._get_coin_id(cur, rate.symbol)
                    if coin_id:
                        values.append(
                            (coin_id, rate.exchange, rate.rate, rate.timestamp)
                        )
                    else:
                        logger.warning(f"Coin not found for symbol: {rate.symbol}")

                if values:
                    query = """
                        INSERT INTO funding_rates (coin_id, dex, funding_rate, timestamp)
                        VALUES %s
                    """
                    execute_values(cur, query, values)
                    conn.commit()
                    logger.info(
                        f"Saved {len(values)} funding rates for {rates[0].exchange if rates else 'unknown'}"
                    )
        except Exception as e:
            logger.error(f"Error saving funding rates: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()


db = Database()
