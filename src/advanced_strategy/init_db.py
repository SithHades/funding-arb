#!/usr/bin/env python3
"""Initialize the database tables and optionally seed test data.

Usage examples:

  # create tables using the DATABASE_URL in env
  python3 src/init_db.py

  # create tables and seed sample rows (uses DATABASE_URL env unless --database-url provided)
  python3 src/init_db.py --seed

  # override the database URL for a one-off run (useful for sqlite file):
  python3 src/init_db.py --database-url sqlite:///./test_init.db --seed

The script will import the project's DB configuration from `src.db_setup` and call
Base.metadata.create_all(engine). When seeding, it inserts a couple of sample
Position rows and an ArbRun linking them.
"""

from __future__ import annotations

import argparse
import importlib
import os
from decimal import Decimal
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(
        description="Initialize DB and optionally seed test data"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Insert small set of test rows after creating tables",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Optional database URL to use for this run (overrides DATABASE_URL env var)",
    )
    args = parser.parse_args()

    if args.database_url:
        # set env var then reload module to ensure engine is recreated with the new URL
        os.environ["DATABASE_URL"] = args.database_url

    # import here so that DATABASE_URL can be swapped before import if requested
    import src.db_setup as db_setup

    # if user passed --database-url after import, reload to pick it up
    if args.database_url:
        importlib.reload(db_setup)

    Base = db_setup.Base
    engine = db_setup.engine
    Session = db_setup.Session
    Position = db_setup.Position
    ArbRun = db_setup.ArbRun

    print(f"Using database engine {engine}")

    print("Creating tables from Base metadata...")
    Base.metadata.create_all(engine)
    print("Tables created (if they did not already exist).")

    if args.seed:
        print("Seeding sample data...")
        session = Session()
        try:
            now = datetime.now(timezone.utc)
            p1 = Position(
                dex_name="mock",
                coin="BTC",
                side="LONG",
                size=Decimal("0.1"),
                entry_price=Decimal("50000"),
                leverage=Decimal("2"),
                collateral=Decimal("2500"),
                position_id_on_dex="mock-1",
                status="OPEN",
                created_at=now,
                updated_at=now,
            )
            p2 = Position(
                dex_name="mock",
                coin="BTC",
                side="SHORT",
                size=Decimal("0.1"),
                entry_price=Decimal("50010"),
                leverage=Decimal("2"),
                collateral=Decimal("2500"),
                position_id_on_dex="mock-2",
                status="OPEN",
                created_at=now,
                updated_at=now,
            )
            session.add_all([p1, p2])
            session.commit()

            run = ArbRun(
                long_pos_id=p1.id, short_pos_id=p2.id, open_at=now, status="OPEN"
            )
            session.add(run)
            session.commit()

            print("Seed data inserted:")
            print(f"  Position 1 id={p1.id}")
            print(f"  Position 2 id={p2.id}")
            print(f"  ArbRun id={run.id}")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


if __name__ == "__main__":
    main()
