import asyncio
import lighter
from src.dex_adapters.base import DexAdapter
from src.dex_adapters.config import lighter_config as config
from src.models import Side


class LighterAdapter(DexAdapter):
    name = "Lighter"

    def __init__(self):
        super().__init__()
        self.api_client = lighter.ApiClient(
            configuration=lighter.Configuration(host=config.base_url)
        )
        self.account_api = lighter.AccountApi(self.api_client)
        self.signer_client = lighter.SignerClient(
            url=config.base_url,
            private_key=config.private_key,
            account_index=config.account_index,
            api_key_index=config.key_index,
        )
        self.funding_api = lighter.FundingApi(self.api_client)
        self._token_market_id: dict[str, int] | None = None
        self._token_market_lock: asyncio.Lock = asyncio.Lock()

    async def close(self):
        await self.api_client.close()
        await self.signer_client.close()

    async def generate_market_id_map(self) -> dict[str, int]:
        market_id_map = {}
        response = await self.funding_api.funding_rates()
        for funding_rate in response.funding_rates:
            market_id_map[funding_rate.symbol] = funding_rate.market_id
        return market_id_map

    async def _ensure_market_map(self) -> dict[str, int]:
        """Ensure the token -> market_id map is loaded and cached.

        Uses double-checked locking so multiple concurrent callers share the same
        initialization and we only perform the async network call once.
        """
        if self._token_market_id is None:
            async with self._token_market_lock:
                if self._token_market_id is None:
                    self._token_market_id = await self.generate_market_id_map()
        return self._token_market_id

    async def get_market_id(self, token: str) -> int | None:
        mapping = await self._ensure_market_map()
        return mapping.get(token)

    async def get_balance(self) -> float:
        response: lighter.DetailedAccounts = await self.account_api.account(
            by="l1_address", value=config.address
        )
        balance = response.accounts[0].available_balance
        return round(float(balance), 6)

    async def list_positions(self, token: str | None) -> list[dict]:
        response: lighter.DetailedAccounts = await self.account_api.account(
            by="l1_address", value=config.address
        )
        positions = []
        for position in response.accounts[0].positions:
            if isinstance(position, lighter.AccountPosition):
                if float(position.position) > 0:
                    positions.append(position.model_dump())
        if token:
            positions = [pos for pos in positions if pos.get("symbol") == token]
        return positions

    async def set_leverage(self, token: str, leverage: int) -> bool:
        # todo find market_id from token symbol
        market_id = await self.get_market_id(token)
        if market_id is None:
            return False
        _, _, err = await self.signer_client.update_leverage(
            market_id, self.signer_client.CROSS_MARGIN_MODE, int(leverage)
        )

        if err is not None:
            return False
        return True

    async def open_position(
        self,
        token: str,
        side: Side,
        size: float,
        leverage: int,
        slippage: float,
        create_order_without_leverage_set: bool = False,
    ) -> dict:
        raise NotImplementedError("open_position not implemented")

    async def close_position(self, token: str) -> bool:
        raise NotImplementedError("close_position not implemented")
