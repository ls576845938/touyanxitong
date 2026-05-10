from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db.models import DailyBar, Stock  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.pipeline.daily_report_job import run_daily_report_job  # noqa: E402
from app.pipeline.evidence_chain_job import run_evidence_chain_job  # noqa: E402
from app.pipeline.ingestion_task_service import _client_for_source  # noqa: E402
from app.pipeline.market_data_job import run_market_data_job  # noqa: E402
from app.pipeline.tenbagger_score_job import run_tenbagger_score_job  # noqa: E402
from app.pipeline.trend_signal_job import run_trend_signal_job  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update already-covered daily bars and refresh research outputs.")
    parser.add_argument("--markets", default=",".join(settings.enabled_markets), help="Comma-separated markets: A,US,HK")
    parser.add_argument("--source", default="auto", help="auto, mock, or a provider/chain such as yahoo,akshare")
    parser.add_argument("--periods", type=int, default=30, help="Recent daily bars to refresh for covered symbols.")
    parser.add_argument("--max-symbols", type=int, default=0, help="Optional safety cap. 0 means all covered symbols.")
    return parser.parse_args()


def _tuple_csv(value: str) -> tuple[str, ...]:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return items or ("A", "US", "HK")


def _covered_codes(session, markets: tuple[str, ...], max_symbols: int) -> tuple[str, ...]:
    covered = select(DailyBar.stock_code).distinct().subquery()
    query = (
        select(Stock.code)
        .join(covered, covered.c.stock_code == Stock.code)
        .where(
            Stock.market.in_(markets),
            Stock.is_active.is_(True),
            Stock.listing_status == "listed",
            Stock.asset_type == "equity",
        )
        .order_by(Stock.market, Stock.board, Stock.code)
    )
    if max_symbols > 0:
        query = query.limit(max_symbols)
    return tuple(session.scalars(query).all())


if __name__ == "__main__":
    args = parse_args()
    markets = _tuple_csv(args.markets)
    init_db()
    with SessionLocal() as session:
        codes = _covered_codes(session, markets, max(0, args.max_symbols))
        if not codes:
            raise SystemExit("no covered symbols found; run a backfill batch first")
        logger.info("daily update symbols={} markets={} periods={}", len(codes), markets, args.periods)
        output = {
            "market_data": run_market_data_job(
                session,
                markets=markets,
                stock_codes=codes,
                max_stocks_per_market=0,
                periods=args.periods,
                client=_client_for_source(args.source),
            ),
            "trend_signal": run_trend_signal_job(session),
            "tenbagger_score": run_tenbagger_score_job(session),
            "evidence_chain": run_evidence_chain_job(session),
            "daily_report": run_daily_report_job(session),
        }
    logger.info("daily update completed: {}", output)
    print(output)
