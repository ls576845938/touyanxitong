from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.pipeline.stock_universe_job import run_stock_universe_job  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover and upsert full-market security master data.")
    parser.add_argument("--markets", default=",".join(settings.enabled_markets), help="Comma-separated markets: A,US,HK")
    return parser.parse_args()


def _tuple_csv(value: str) -> tuple[str, ...] | None:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return items or None


if __name__ == "__main__":
    args = parse_args()
    init_db()
    with SessionLocal() as session:
        output = run_stock_universe_job(session, markets=_tuple_csv(args.markets))
    logger.info("universe discovery completed: {}", output)
    print(output)
