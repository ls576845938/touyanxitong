from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.pipeline.daily_pipeline import run_daily_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AlphaRadar daily research pipeline.")
    parser.add_argument("--markets", default=",".join(settings.enabled_markets), help="Comma-separated markets, e.g. A,US,HK")
    parser.add_argument(
        "--max-stocks-per-market",
        type=int,
        default=settings.max_stocks_per_market,
        help="Limit market data download per market. Use 0 for no limit.",
    )
    parser.add_argument("--stock-codes", default="", help="Comma-separated stock code allowlist for market data.")
    parser.add_argument("--periods", type=int, default=settings.market_data_periods, help="Daily bar periods to request per stock.")
    parser.add_argument("--end-date", default="", help="Optional end date in YYYY-MM-DD.")
    parser.add_argument("--batch-offset", type=int, default=0, help="Per-market offset for batched market data ingestion.")
    return parser.parse_args()


def _tuple_csv(value: str) -> tuple[str, ...] | None:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return items or None


def _date(value: str):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    args = parse_args()
    output = run_daily_pipeline(
        markets=_tuple_csv(args.markets),
        max_stocks_per_market=args.max_stocks_per_market,
        stock_codes=_tuple_csv(args.stock_codes),
        periods=args.periods,
        end_date=_date(args.end_date),
        batch_offset=args.batch_offset,
    )
    logger.info("pipeline completed: {}", output)
    print(output)
