from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.pipeline.ingestion_task_service import enqueue_ingestion_backfill, run_ingestion_queue  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Queue and optionally run full-market daily bar backfill tasks.")
    parser.add_argument("--markets", default=",".join(settings.enabled_markets), help="Comma-separated markets: A,US,HK")
    parser.add_argument("--board", default="all", help="A-share board filter: all,main,chinext,star,bse")
    parser.add_argument("--source", default=settings.market_data_source, help="auto, mock, or a provider/chain such as tushare,tencent,akshare")
    parser.add_argument("--batches-per-market", type=int, default=3)
    parser.add_argument("--batch-limit", type=int, default=20)
    parser.add_argument("--periods", type=int, default=settings.market_data_periods)
    parser.add_argument("--run", action="store_true", help="Run queued tasks after enqueueing. Default only queues.")
    parser.add_argument("--max-tasks", type=int, default=3, help="Maximum tasks to run when --run is set.")
    parser.add_argument("--worker-id", default=None, help="Optional stable worker id for queue lease ownership.")
    return parser.parse_args()


def _tuple_csv(value: str) -> tuple[str, ...]:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return items or ("A", "US", "HK")


if __name__ == "__main__":
    args = parse_args()
    init_db()
    with SessionLocal() as session:
        queued = enqueue_ingestion_backfill(
            session,
            markets=_tuple_csv(args.markets),
            board=args.board,
            source=args.source,
            batches_per_market=args.batches_per_market,
            batch_limit=args.batch_limit,
            periods=args.periods,
        )
        logger.info("market data backfill queued: {}", queued)
        print(queued)
        if args.run:
            result = run_ingestion_queue(session, max_tasks=args.max_tasks, worker_id=args.worker_id)
            logger.info("market data backfill queue run: {}", result)
            print(result)
