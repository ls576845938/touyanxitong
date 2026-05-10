from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.pipeline.industry_mapping_job import run_industry_mapping_job  # noqa: E402
from app.pipeline.sector_industry_mapping_job import run_sector_industry_mapping_job  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AlphaRadar industry mapping v1.")
    parser.add_argument("--markets", default="", help="Comma-separated markets, e.g. A,US,HK. Empty means all stocks.")
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--with-sector-source", action="store_true", help="Use free A-share sector constituents before rule mapping.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _tuple_csv(value: str) -> tuple[str, ...] | None:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return items or None


if __name__ == "__main__":
    args = parse_args()
    init_db()
    with SessionLocal() as session:
        if args.with_sector_source:
            print(run_sector_industry_mapping_job(session, markets=("A",), dry_run=args.dry_run))
        result = run_industry_mapping_job(
            session,
            markets=_tuple_csv(args.markets),
            min_confidence=args.min_confidence,
            dry_run=args.dry_run,
        )
    print(result)
