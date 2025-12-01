from pydantic_settings.main import SettingsConfigDict
from pydantic.fields import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_database_url: str = Field(
        "postgresql+asyncpg://user:pass@localhost:5432/arbdb", alias="APP_DATABASE_URL"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        env_prefix="",
    )


settings = Settings()
