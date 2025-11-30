import asyncio
from celery import shared_task
from fundings.crawlers.lighter_crawler import LighterCrawler
from fundings.crawlers.hyperliquid_crawler import HyperliquidCrawler
from fundings.db import db
import logging

logger = logging.getLogger(__name__)

CRAWLERS = {
    "lighter": LighterCrawler(),
    "hyperliquid": HyperliquidCrawler(),
}


@shared_task
def crawl_exchange(exchange_name: str):
    crawler = CRAWLERS.get(exchange_name)
    if not crawler:
        logger.error(f"No crawler found for exchange: {exchange_name}")
        return

    try:
        # Run async crawler in sync Celery task
        rates = asyncio.run(crawler.get_funding_rates())
        db.save_funding_rates(rates)
        logger.info(f"Successfully crawled {exchange_name}")
    except Exception as e:
        logger.error(f"Error crawling {exchange_name}: {e}")
