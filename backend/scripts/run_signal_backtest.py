from __future__ import annotations

import argparse
from datetime import date

from app.db.session import SessionLocal, init_db
from app.pipeline.backtest_job import run_signal_backtest_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AlphaRadar signal calibration backtest.")
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=None)
    parser.add_argument("--horizon-days", type=int, default=120)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--market", default=None)
    parser.add_argument("--board", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    with SessionLocal() as session:
        result = run_signal_backtest_job(
            session,
            as_of_date=args.as_of_date,
            horizon_days=args.horizon_days,
            min_score=args.min_score,
            market=args.market,
            board=args.board,
        )
    print(result)


if __name__ == "__main__":
    main()
