import os
import dotenv

dotenv.load_dotenv()


class Config:
    DATABASE_URL = os.environ.get(
        "APP_DATABASE_URL", "postgresql://user:pass@localhost:5432/arbdb"
    )
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Celery Configuration
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_TIMEZONE = "UTC"


config = Config()
