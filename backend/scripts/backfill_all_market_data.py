from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.pipeline.daily_report_job import run_daily_report_job  # noqa: E402
from app.pipeline.evidence_chain_job import run_evidence_chain_job  # noqa: E402
from app.pipeline.backfill_manifest import (  # noqa: E402
    DEFAULT_BACKFILL_MANIFEST_PATH,
    build_backfill_manifest,
    load_backfill_manifest,
    save_backfill_manifest,
)
from app.pipeline.industry_heat_job import run_industry_heat_job  # noqa: E402
from app.pipeline.ingestion_task_service import _client_for_source, priority_candidates  # noqa: E402
from app.pipeline.market_data_job import run_market_data_job  # noqa: E402
from app.pipeline.sector_industry_mapping_job import run_sector_industry_mapping_job  # noqa: E402
from app.pipeline.tenbagger_score_job import run_tenbagger_score_job  # noqa: E402
from app.pipeline.trend_signal_job import run_trend_signal_job  # noqa: E402


DEFAULT_STATUS_PATH = DEFAULT_BACKFILL_MANIFEST_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resumeable full-market daily bar backfill for A/HK/US.")
    parser.add_argument("--markets", default=",".join(settings.enabled_markets), help="Comma-separated markets: A,US,HK")
    parser.add_argument("--source", default="auto", help="auto, mock, yahoo, akshare, tencent, baostock, or optional paid-token providers/chain")
    parser.add_argument("--periods", type=int, default=settings.market_data_periods)
    parser.add_argument("--batch-limit", type=int, default=50, help="Symbols per market batch.")
    parser.add_argument("--max-batches", type=int, default=0, help="0 means keep running until no candidates remain.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Small pause between provider batches.")
    parser.add_argument("--min-complete-ratio", type=float, default=0.95, help="Treat a symbol as covered once bars >= periods * ratio.")
    parser.add_argument("--max-attempts-per-symbol", type=int, default=2)
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--skip-research", action="store_true", help="Do not recompute heat/trend/score/evidence/report at the end.")
    parser.add_argument("--dry-run", action="store_true", help="Show the next candidate batches without downloading bars.")
    return parser.parse_args()


def _tuple_csv(value: str) -> tuple[str, ...]:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    return tuple(item for item in items if item in {"A", "US", "HK"}) or ("A", "US", "HK")


def _candidate_codes(session, market: str, limit: int, periods: int, complete_bars: int, attempts: dict[str, int], max_attempts: int) -> tuple[str, ...]:
    rows = priority_candidates(session, market=market, limit=max(limit * 3, limit), periods=periods)
    codes: list[str] = []
    for row in rows:
        code = str(row["code"])
        if int(row["bars_count"] or 0) >= complete_bars:
            continue
        if attempts.get(code, 0) >= max_attempts:
            continue
        codes.append(code)
        if len(codes) >= limit:
            break
    return tuple(codes)


def _research_refresh(session) -> dict[str, object]:
    return {
        "sector_industry_mapping": run_sector_industry_mapping_job(session, markets=("A",)),
        "industry_heat": run_industry_heat_job(session),
        "trend_signal": run_trend_signal_job(session),
        "tenbagger_score": run_tenbagger_score_job(session),
        "evidence_chain": run_evidence_chain_job(session),
        "daily_report": run_daily_report_job(session),
    }


if __name__ == "__main__":
    args = parse_args()
    markets = _tuple_csv(args.markets)
    batch_limit = max(1, min(int(args.batch_limit), 200))
    max_batches = max(0, int(args.max_batches))
    complete_bars = max(1, int(args.periods * max(0.5, min(float(args.min_complete_ratio), 1.0))))
    status_path = Path(args.status_path)
    status = load_backfill_manifest(status_path)
    resume = status.get("resume") if isinstance(status.get("resume"), dict) else {}
    raw_attempts = dict(status.get("attempts", {}) or resume.get("attempts", {}))
    attempts: dict[str, int] = {str(key): int(value) for key, value in raw_attempts.items()}
    totals = dict(status.get("totals", {}))
    totals.setdefault("batches", 0)
    totals.setdefault("inserted", 0)
    totals.setdefault("updated", 0)
    totals.setdefault("failed_symbols", 0)
    totals.setdefault("processed_symbols", 0)

    init_db()
    client = _client_for_source(args.source)
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "full-market backfill started markets={} source={} periods={} complete_bars={} batch_limit={}",
        markets,
        args.source,
        args.periods,
        complete_bars,
        batch_limit,
    )
    with SessionLocal() as session:
        batches_run = 0
        while True:
            made_progress = False
            for market in markets:
                codes = _candidate_codes(session, market, batch_limit, args.periods, complete_bars, attempts, args.max_attempts_per_symbol)
                if not codes:
                    continue
                made_progress = True
                if args.dry_run:
                    logger.info("dry-run market={} codes={}", market, codes)
                    continue
                logger.info("backfill batch market={} symbols={}", market, len(codes))
                result = run_market_data_job(
                    session,
                    markets=(market,),
                    stock_codes=codes,
                    max_stocks_per_market=len(codes),
                    periods=args.periods,
                    client=client,
                )
                for code in codes:
                    attempts[code] = attempts.get(code, 0) + 1
                totals["batches"] = int(totals["batches"]) + 1
                totals["inserted"] = int(totals["inserted"]) + int(result["inserted"])
                totals["updated"] = int(totals["updated"]) + int(result["updated"])
                totals["failed_symbols"] = int(totals["failed_symbols"]) + int(result["missing_stocks"])
                totals["processed_symbols"] = int(totals["processed_symbols"]) + int(result["stocks_processed"])
                batches_run += 1
                last_batch = {"market": market, "codes": codes, "result": result}
                save_backfill_manifest(
                    status_path,
                    build_backfill_manifest(
                        session,
                        status="running",
                        started_at=str(status.get("started_at") or started_at),
                        markets=markets,
                        source=args.source,
                        periods=args.periods,
                        complete_bars=complete_bars,
                        totals=totals,
                        last_batch=last_batch,
                        attempts=attempts,
                    ),
                )
                if max_batches and batches_run >= max_batches:
                    made_progress = False
                    break
                if args.sleep_seconds > 0:
                    time.sleep(args.sleep_seconds)
            if args.dry_run or not made_progress or (max_batches and batches_run >= max_batches):
                break

        research = {} if args.skip_research or args.dry_run else _research_refresh(session)
        final_payload = build_backfill_manifest(
            session,
            status="completed" if not args.dry_run else "dry_run",
            started_at=str(status.get("started_at") or started_at),
            finished_at=datetime.now(timezone.utc).isoformat(),
            markets=markets,
            source=args.source,
            periods=args.periods,
            complete_bars=complete_bars,
            totals=totals,
            attempts=attempts,
        )
        final_payload["research"] = research
        save_backfill_manifest(status_path, final_payload)
    logger.info("full-market backfill finished: {}", final_payload)
    print(json.dumps({key: value for key, value in final_payload.items() if key != "resume"}, ensure_ascii=False, indent=2, default=str))
