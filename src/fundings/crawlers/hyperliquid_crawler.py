from hyperliquid.info import Info

from fundings.base import FundingCrawler, FundingRateData
from dex_adapters.config import hyperliquid_config as config
from typing import List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class HyperliquidCrawler(FundingCrawler):
    def __init__(self):
        super().__init__()
        self.info = Info(config.base_url, True)

    @property
    def exchange_name(self) -> str:
        return "hyperliquid"

    async def get_funding_rates(self) -> List[FundingRateData]:
        # TODO: Implement actual API call to Hyperliquid
        logger.info("Crawling Hyperliquid funding rates...")
        timestamp = datetime.now(timezone.utc)
        meta_and_asset_ctxs = self.info.meta_and_asset_ctxs()
        metas = meta_and_asset_ctxs[0].get("universe", [])
        assets = meta_and_asset_ctxs[1]
        if not metas or not assets:
            return []
        if not isinstance(metas, list) or not isinstance(assets, list):
            return []
        if not len(metas) == len(assets):
            return []
        funding_rates = []
        for meta, asset in zip(metas, assets):
            if not isinstance(meta, dict) or not isinstance(asset, dict):
                continue
            funding = asset.get("funding_rate")
            if not isinstance(funding, float):
                continue
            funding_in_bps = funding * 10000
            name = meta.get("name")
            if not isinstance(name, str):
                continue
            name = name.upper()
            funding_rates.append(
                FundingRateData(
                    exchange=self.exchange_name,
                    symbol=name,
                    rate=funding_in_bps,
                    timestamp=timestamp,
                )
            )
        return funding_rates


if __name__ == "__main__":
    import asyncio

    crawler = HyperliquidCrawler()
    asyncio.run(crawler.get_funding_rates())
