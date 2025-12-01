import os
from typing import Literal, Union
import dotenv
from hyperliquid.utils.constants import MAINNET_API_URL
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


dotenv.load_dotenv()


class HyperliquidConfig(BaseSettings):
    address: str = Field(..., alias="ETHEREUM_ADDRESS")
    private_key: str = Field(
        ...,
        alias="HYPERLIQUID_API_WALLET_PK",
    )
    skip_ws: bool = Field(False, alias="HYPERLIQUID_SKIP_WS")
    base_url: str = Field(
        MAINNET_API_URL,
        alias="HYPERLIQUID_API_BASE_URL",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        env_prefix="",
    )


lighter_map = {
    "test": {
        "base_url": "https://testnet.zklighter.elliot.ai",
        "account_index": "LIGHTER_API_TESTNET_ACCOUNT_INDEX",
        "private_key": "LIGHTER_API_WALLET_TESTNET_PRIVATE_KEY",
        "key_index": "LIGHTER_API_TESTNET_API_KEY_INDEX",
    },
    "main": {
        "base_url": "https://mainnet.zklighter.elliot.ai",
        "account_index": "LIGHTER_API_ACCOUNT_INDEX",
        "private_key": "LIGHTER_API_WALLET_PK",
        "key_index": "LIGHTER_API_KEY_INDEX",
    },
}


class LighterConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        env_prefix="",
    )

    mode: Union[Literal["test"], Literal["main"]] = Field(
        "main", alias="LIGHTER_API_MODE"
    )

    # base_url is directly replaced from lighter_map
    base_url: str | None = Field(None)

    # These are loaded dynamically later based on mode
    account_index: int | None = None
    private_key: str | None = None
    key_index: int | None = None

    address: str = Field(..., alias="ETHEREUM_ADDRESS")

    @model_validator(mode="after")
    def load_dynamic_envs(cls, values):
        mode = values.mode
        config = lighter_map[mode]

        # Always set the base_url from the map
        values.base_url = config["base_url"]

        # For the rest, use environment variables defined by the map
        for field, env_name in [
            ("account_index", config["account_index"]),
            ("private_key", config["private_key"]),
            ("key_index", config["key_index"]),
        ]:
            if getattr(values, field) is None:
                env_val = os.getenv(env_name)
                if env_val is not None and field in ["account_index", "key_index"]:
                    env_val = int(env_val)
                if env_val is None:
                    raise ValueError(
                        f"Missing required environment variable: {env_name} for mode '{mode}'"
                    )
                setattr(values, field, env_val)

        return values


class ExtendedConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        env_prefix="",
    )
    private_key: str = Field(..., alias="EXTENDED_STARK_KEY_PRIVATE")
    public_key: str = Field(..., alias="EXTENDED_STARK_KEY_PUBLIC")
    api_key: str = Field(..., alias="EXTENDED_API_KEY")
    vault_id: str = Field(..., alias="EXTENDED_VAULT_NUMBER")


hyperliquid_config = HyperliquidConfig()  # type: ignore
lighter_config = LighterConfig()  # type: ignore
extended_config = ExtendedConfig()  # type: ignore
