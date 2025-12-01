from fundings.base import FundingCrawler, FundingRateData
from typing import List
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class LighterCrawler(FundingCrawler):
    def __init__(self):
        super().__init__()
        self.base_url = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"

    @property
    def exchange_name(self) -> str:
        return "lighter"

    async def get_funding_rates(self) -> List[FundingRateData]:
        # TODO: Implement actual API call to Lighter
        logger.info("Crawling Lighter funding rates...")

        response = requests.get(self.base_url)
        if response.status_code != 200:
            raise Exception(f"Error fetching funding rates: {response.status_code}")
        data = response.json().get("funding_rates")
        if data is None:
            raise Exception("Error fetching funding rates: no data")
        funding_rates = []
        timestamp = datetime.now(timezone.utc)
        for funding_rate in data:
            if funding_rate.get("exchange") != "lighter":
                continue
            funding_rates.append(
                FundingRateData(
                    exchange=self.exchange_name,
                    symbol=funding_rate["symbol"],
                    rate=float(funding_rate["rate"]) * 10000,
                    timestamp=timestamp,
                )
            )
        return funding_rates


if __name__ == "__main__":
    import asyncio

    async def main():
        lighter = LighterCrawler()
        await lighter.get_funding_rates()

    asyncio.run(main())
