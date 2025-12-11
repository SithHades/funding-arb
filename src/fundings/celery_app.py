from celery import Celery
from fundings.config import config

app = Celery(
    "fundings",
    broker=config.CELERY_BROKER_URL,
    backend=config.CELERY_RESULT_BACKEND,
    include=["fundings.tasks"],
)

app.conf.update(
    timezone=config.CELERY_TIMEZONE,
    enable_utc=True,
)

# Schedule tasks
app.conf.beat_schedule = {
    "crawl-lighter-every-minute": {
        "task": "fundings.tasks.crawl_exchange",
        "schedule": 60.0,  # 1 minute
        "args": ("lighter",),
    },
    "crawl-hyperliquid-every-minute": {
        "task": "fundings.tasks.crawl_exchange",
        "schedule": 60.0,  # 1 minute
        "args": ("hyperliquid",),
    },
}
