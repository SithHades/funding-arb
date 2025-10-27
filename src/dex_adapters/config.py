from hyperliquid.utils.constants import MAINNET_API_URL
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HyperliquidConfig(BaseSettings):
    address: str = Field(..., env="ETHEREUM_ADDRESS", alias="ETHEREUM_ADDRESS")
    private_key: str = Field(
        ...,
        env="HYPERLIQUID_API_WALLET_PK",
        alias="HYPERLIQUID_API_WALLET_PK",
    )
    skip_ws: bool = Field(False, env="HYPERLIQUID_SKIP_WS", alias="HYPERLIQUID_SKIP_WS")
    base_url: str = Field(
        MAINNET_API_URL,
        env="HYPERLIQUID_API_BASE_URL",
        alias="HYPERLIQUID_API_BASE_URL",
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True
    )


class LighterConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True
    )
    base_url: str = Field(
        "https://mainnet.zklighter.elliot.ai",
        env="LIGHTER_API_BASE_URL",
        alias="LIGHTER_API_BASE_URL",
    )
    account_index: int = Field(
        ...,
        env="LIGHTER_API_ACCOUNT_INDEX",
        alias="LIGHTER_API_ACCOUNT_INDEX",
    )
    private_key: str = Field(
        ...,
        env="LIGHTER_API_WALLET_PK",
        alias="LIGHTER_API_WALLET_PK",
    )
    key_index: int = Field(
        ...,
        env="LIGHTER_API_KEY_INDEX",
        alias="LIGHTER_API_KEY_INDEX",
    )
    address: str = Field(
        ...,
        env="ETHEREUM_ADDRESS",
        alias="ETHEREUM_ADDRESS",
    )


hyperliquid_config = HyperliquidConfig()
lighter_config = LighterConfig()
