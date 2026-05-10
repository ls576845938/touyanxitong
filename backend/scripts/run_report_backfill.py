from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.pipeline.daily_pipeline import run_daily_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill AlphaRadar daily pipeline over a date range.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--markets", default=",".join(settings.enabled_markets), help="Comma-separated markets, e.g. A,US,HK")
    parser.add_argument("--max-stocks-per-market", type=int, default=settings.max_stocks_per_market)
    parser.add_argument("--periods", type=int, default=settings.market_data_periods)
    parser.add_argument("--batch-offset", type=int, default=0)
    parser.add_argument("--include-weekends", action="store_true")
    return parser.parse_args()


def _date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _tuple_csv(value: str) -> tuple[str, ...] | None:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return items or None


def _dates(start_text: str, end_text: str, include_weekends: bool):
    current = _date(start_text)
    end = _date(end_text)
    while current <= end:
        if include_weekends or current.weekday() < 5:
            yield current
        current += timedelta(days=1)


if __name__ == "__main__":
    args = parse_args()
    outputs = {}
    for day in _dates(args.start_date, args.end_date, args.include_weekends):
        logger.info("backfill pipeline date={}", day.isoformat())
        outputs[day.isoformat()] = run_daily_pipeline(
            markets=_tuple_csv(args.markets),
            max_stocks_per_market=args.max_stocks_per_market,
            periods=args.periods,
            end_date=day,
            batch_offset=args.batch_offset,
        )
    logger.info("backfill completed: {}", list(outputs))
    print(outputs)
