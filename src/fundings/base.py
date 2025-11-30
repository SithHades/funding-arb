from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FundingRateData:
    exchange: str
    symbol: str
    rate: float
    timestamp: datetime


class FundingCrawler(ABC):
    """
    Abstract base class for funding rate crawlers.
    """

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        pass

    @abstractmethod
    async def get_funding_rates(self) -> List[FundingRateData]:
        """
        Fetch current funding rates from the exchange.
        """
        pass
