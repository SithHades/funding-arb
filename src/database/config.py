import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_DATABASE_URL: str = os.environ.get(
        "APP_DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/arbdb"
    )


settings = Settings()
