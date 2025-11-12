from contextlib import contextmanager
from datetime import datetime, timezone
import os
import uuid
import dotenv
import redis
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


dotenv.load_dotenv()
Base = declarative_base()


# ---------- Models ----------
class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True)
    dex_name = Column(String, nullable=False)
    coin = Column(String, nullable=False)
    side = Column(String, nullable=False)  # LONG or SHORT
    size = Column(Numeric, nullable=False)  # notional size
    entry_price = Column(Numeric)
    leverage = Column(Numeric)
    collateral = Column(Numeric)
    position_id_on_dex = Column(String)  # DEX returned id
    status = Column(String, nullable=False, default="OPEN")
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )


class ArbRun(Base):
    __tablename__ = "arb_runs"
    id = Column(Integer, primary_key=True)
    long_pos_id = Column(Integer, ForeignKey("positions.id"))
    short_pos_id = Column(Integer, ForeignKey("positions.id"))
    open_at = Column(DateTime)
    close_at = Column(DateTime)
    status = Column(String, default="OPEN")


# ---------- Setup DB & Redis ----------
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://user:pass@localhost:5432/arbdb"
)
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL)


@contextmanager
def redis_lock(key: str, ttl=10):
    lock_key = f"lock:{key}"
    token = str(uuid.uuid4())
    got = redis_client.set(lock_key, token, nx=True, ex=ttl)
    try:
        if not got:
            raise RuntimeError(f"Failed to acquire lock {key}")
        yield
    finally:
        # release only if token matches
        val = redis_client.get(lock_key)
        # val may be bytes, str, or something else (type stubs can vary), so handle bytes and str explicitly
        if isinstance(val, (bytes, bytearray)):
            val_decoded = val.decode()
        elif isinstance(val, str):
            val_decoded = val
        else:
            val_decoded = None
        if val_decoded == token:
            redis_client.delete(lock_key)
