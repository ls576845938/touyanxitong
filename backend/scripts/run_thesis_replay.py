"""Historical Thesis Replay (Sub-task A for MVP 3.1).

Run the daily report pipeline over a historical date range, then
evaluate thesis outcomes using post-hoc price/heat data.

Usage:
    python -m backend.scripts.run_thesis_replay --start-date YYYY-MM-DD --end-date YYYY-MM-DD
    python -m backend.scripts.run_thesis_replay --start-date 2024-01-01 --end-date 2024-03-31 --reset-replay
    python -m backend.scripts.run_thesis_replay --start-date 2024-01-01 --end-date 2024-01-31 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import DailyReport, ResearchThesis, ResearchThesisReview  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.engines.thesis_review_engine import run_thesis_review, _update_thesis_status  # noqa: E402
from app.pipeline.daily_report_job import run_daily_report_job  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Historical Thesis Replay: run daily report pipeline over a date range and evaluate thesis outcomes."
    )
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--mode",
        default="daily_report",
        choices=["daily_report", "agent_cases", "both"],
        help="Replay mode (default: daily_report). agent_cases is a placeholder.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing to DB.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max theses per date (default: 10).",
    )
    parser.add_argument(
        "--reset-replay",
        action="store_true",
        help=(
            "Remove previous replay data (source_type LIKE 'historical_replay_%%') "
            "before starting."
        ),
    )
    parser.add_argument(
        "--review-horizons",
        default="5,20,60",
        help="Comma-separated review horizon days (default: 5,20,60).",
    )
    parser.add_argument(
        "--as-of-date",
        default=None,
        help=(
            "YYYY-MM-DD review cutoff date (default: today). "
            "Reviews with scheduled_review_date <= this are executed immediately."
        ),
    )
    parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="Process weekend dates too (default: weekdays only).",
    )
    return parser.parse_args()


def _date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _dates(start: date, end: date, include_weekends: bool):
    """Yield each calendar day in [start, end], optionally filtering weekends."""
    current = start
    while current <= end:
        if include_weekends or current.weekday() < 5:
            yield current
        current += timedelta(days=1)


# ---------------------------------------------------------------------------
# Summary counters
# ---------------------------------------------------------------------------


def _fresh_stats() -> dict[str, int]:
    return {
        "dates_processed": 0,
        "dates_skipped": 0,
        "dates_failed": 0,
        "theses_generated": 0,
        "reviews_created": 0,
        "reviews_hit": 0,
        "reviews_missed": 0,
        "reviews_invalidated": 0,
        "reviews_inconclusive": 0,
        "reviews_no_price_data": 0,
    }


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def _clean_replay_data(db: Any, dry_run: bool = False) -> None:
    """Delete all theses with source_type LIKE 'historical_replay_%' and their reviews."""
    thesis_ids = list(
        db.scalars(
            select(ResearchThesis.id).where(
                ResearchThesis.source_type.like("historical_replay_%")
            )
        ).all()
    )
    if not thesis_ids:
        logger.info("No previous replay data found.")
        return

    review_count = db.scalar(
        select(func.count(ResearchThesisReview.id)).where(
            ResearchThesisReview.thesis_id.in_(thesis_ids)
        )
    )

    if dry_run:
        logger.info("[DRY RUN] Would delete {} reviews and {} theses", review_count or 0, len(thesis_ids))
        return

    # Delete reviews first (FK constraint), then theses
    db.query(ResearchThesisReview).filter(
        ResearchThesisReview.thesis_id.in_(thesis_ids)
    ).delete(synchronize_session=False)
    db.query(ResearchThesis).filter(
        ResearchThesis.id.in_(thesis_ids)
    ).delete(synchronize_session=False)
    db.commit()
    logger.info("Removed {} reviews and {} theses", review_count or 0, len(thesis_ids))


# ---------------------------------------------------------------------------
# Per-date processing
# ---------------------------------------------------------------------------


def _process_date(
    db: Any,
    day: date,
    horizons: list[int],
    as_of_date: date,
    limit: int,
    stats: dict,
) -> None:
    """Run daily report for *day*, create reviews, and execute due ones.

    Uses ORM-style operations throughout for consistency with the rest of
    the codebase (thesis_review_engine, daily_report_job, etc.).
    """
    # -- dedup: skip if historical_replay theses already exist for this date --
    start_of_day = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end_of_day = start_of_day + timedelta(days=1)
    existing_id = db.scalar(
        select(ResearchThesis.id)
        .where(
            ResearchThesis.source_type == "historical_replay_daily_report",
            ResearchThesis.created_at >= start_of_day,
            ResearchThesis.created_at < end_of_day,
        )
        .limit(1)
    )
    if existing_id is not None:
        logger.info("Skipping {} (theses already exist for this date)", day)
        stats["dates_skipped"] += 1
        return

    # -- run daily report job with replay overrides --
    result = run_daily_report_job(
        db,
        report_date=day,
        thesis_source_type="historical_replay_daily_report",
        thesis_created_date=day,
        skip_review_schedule=True,
        thesis_limit=limit,
    )
    stats["dates_processed"] += 1
    effective_date_str = result.get("report_date", day.isoformat())
    effective_date = _date(effective_date_str)

    # -- fetch theses via DailyReport (the source_id was backfilled by the job) --
    daily_report = db.scalar(
        select(DailyReport).where(DailyReport.report_date == effective_date)
    )
    thesis_ids: list[int] = []
    if daily_report:
        raw = daily_report.thesis_ids_json or "[]"
        try:
            thesis_ids = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            thesis_ids = []
    theses: list[ResearchThesis] = []
    if thesis_ids:
        theses = list(
            db.scalars(
                select(ResearchThesis).where(ResearchThesis.id.in_(thesis_ids))
            ).all()
        )
    stats["theses_generated"] += len(theses)

    # -- create reviews for each thesis, run if due --
    for thesis in theses:
        thesis_anchor = thesis.created_at.date() if thesis.created_at else effective_date
        for horizon in horizons:
            review_date = thesis_anchor + timedelta(days=horizon)

            # Check for existing review (duplicate run protection)
            existing_review = db.scalar(
                select(ResearchThesisReview).where(
                    ResearchThesisReview.thesis_id == thesis.id,
                    ResearchThesisReview.review_horizon_days == horizon,
                )
            )
            if existing_review is not None:
                continue

            # Create a new pending review
            review = ResearchThesisReview(
                thesis_id=thesis.id,
                review_horizon_days=horizon,
                scheduled_review_date=review_date,
                review_status="pending",
            )
            db.add(review)
            db.flush()
            stats["reviews_created"] += 1

            # Run the review immediately if the scheduled date has arrived
            if review_date <= as_of_date:
                _run_single_review(db, thesis, review, stats)

    db.commit()


def _run_single_review(
    db: Any,
    thesis: ResearchThesis,
    review: ResearchThesisReview,
    stats: dict,
) -> None:
    """Execute a single thesis review and persist the outcome on ORM objects."""
    try:
        result = run_thesis_review(thesis, review, db)
    except Exception as exc:
        logger.warning("Review error for thesis #{} horizon={}d: {}", thesis.id, review.review_horizon_days, exc)
        stats["reviews_inconclusive"] += 1
        return

    # Persist outcome on ORM objects (tracked by session, committed in _process_date)
    review.review_status = result.review_status
    review.actual_review_date = date.today()
    review.realized_return = result.realized_return
    review.benchmark_return = result.benchmark_return
    review.realized_metrics_json = json.dumps(result.realized_metrics_json, ensure_ascii=False)
    review.review_note = result.review_note
    review.evidence_update_json = json.dumps(result.evidence_update_json, ensure_ascii=False)

    # Update parent thesis status based on outcome
    _update_thesis_status(thesis, result.review_status, db)

    # Tally
    if result.review_status == "hit":
        stats["reviews_hit"] += 1
    elif result.review_status == "missed":
        stats["reviews_missed"] += 1
    elif result.review_status == "invalidated":
        stats["reviews_invalidated"] += 1
    elif _is_no_price_data(result):
        stats["reviews_no_price_data"] += 1
        stats["reviews_inconclusive"] += 1
    else:
        stats["reviews_inconclusive"] += 1


def _is_no_price_data(result: Any) -> bool:
    """Check if the review was inconclusive due to missing price data."""
    note = (result.review_note or "").lower()
    return (
        "dailybar data missing" in note
        or "invalid price data" in note
        or "industryheat data insufficient" in note
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _print_summary(stats: dict) -> None:
    print("\nReplay Summary:")
    print(f"  Dates processed: {stats['dates_processed']}")
    if stats["dates_skipped"]:
        print(f"  Dates skipped (duplicates): {stats['dates_skipped']}")
    if stats["dates_failed"]:
        print(f"  Dates failed: {stats['dates_failed']}")
    print(f"  Theses generated: {stats['theses_generated']}")
    print(f"  Reviews created: {stats['reviews_created']}")
    print(f"  Reviews completed (hit): {stats['reviews_hit']}")
    print(f"  Reviews completed (missed): {stats['reviews_missed']}")
    print(f"  Reviews completed (invalidated): {stats['reviews_invalidated']}")
    print(f"  Reviews completed (inconclusive): {stats['reviews_inconclusive']}")
    print(f"  Skipped (no price data): {stats['reviews_no_price_data']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    start_date = _date(args.start_date)
    end_date = _date(args.end_date)
    as_of_date = _date(args.as_of_date) if args.as_of_date else date.today()
    horizons = sorted({int(h.strip()) for h in args.review_horizons.split(",") if h.strip()})

    init_db()
    db = SessionLocal()

    stats = _fresh_stats()

    try:
        # -- reset --
        if args.reset_replay:
            _clean_replay_data(db, dry_run=args.dry_run)

        # -- mode dispatch --
        if args.mode in ("daily_report", "both"):
            _run_daily_report_mode(
                db, start_date, end_date, horizons, as_of_date, args.limit, args.dry_run, args.include_weekends, stats
            )

        if args.mode in ("agent_cases", "both"):
            logger.warning("agent_cases mode is not yet implemented in Sub-task A; skipping.")

        # -- summary --
        if not args.dry_run:
            _print_summary(stats)
        else:
            logger.info("[DRY RUN] Would process ~{} dates", stats["dates_processed"])

    except Exception as exc:
        logger.error("Replay failed: {}", exc)
        db.rollback()
        raise
    finally:
        db.close()


def _run_daily_report_mode(
    db: Any,
    start_date: date,
    end_date: date,
    horizons: list[int],
    as_of_date: date,
    limit: int,
    dry_run: bool,
    include_weekends: bool,
    stats: dict,
) -> None:
    """Iterate over trading days calling daily report + review creation."""
    for day in _dates(start_date, end_date, include_weekends):
        if dry_run:
            logger.info("[DRY RUN] Would process date: {} (limit={}, horizons={})", day, limit, horizons)
            stats["dates_processed"] += 1
            continue

        try:
            _process_date(
                db=db,
                day=day,
                horizons=horizons,
                as_of_date=as_of_date,
                limit=limit,
                stats=stats,
            )
        except Exception as exc:
            logger.error("Failed to process date {}: {}", day, exc)
            db.rollback()
            stats["dates_failed"] += 1
            continue


if __name__ == "__main__":
    main()
