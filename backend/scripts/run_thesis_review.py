"""Enhanced thesis review runner with CLI options.

Usage:
    python scripts/run_thesis_review.py [OPTIONS]
    python scripts/run_thesis_review.py [YYYY-MM-DD]             (legacy)

Options:
    --due-only          Only review theses with scheduled_review_date <= today (default)
    --all-pending        Review ALL pending reviews regardless of date
    --horizon 5,20,60    Only review for specific horizons
    --start-date YYYY-MM-DD  Filter by scheduled_review_date >= start
    --end-date YYYY-MM-DD    Filter by scheduled_review_date <= end
    --dry-run            Print what would be done, don't write
    --limit N            Max reviews to process (default: no limit)
    --output-json        Output results as JSON instead of text
    --subject-type stock|industry  Only review specific subject type
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.db.models import ResearchThesis, ResearchThesisReview  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.engines.thesis_review_engine import (  # noqa: E402
    ThesisReviewResult,
    run_due_reviews,
    run_thesis_review,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run due thesis reviews for the Alpha Radar research system.",
    )
    parser.add_argument(
        "date",
        nargs="?",
        type=str,
        default=None,
        help="As-of date YYYY-MM-DD (default: today)",
    )

    # Filter options
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Review ALL pending reviews regardless of scheduled date "
        "(default: due-only, i.e. scheduled_review_date <= today)",
    )
    parser.add_argument(
        "--horizon",
        type=str,
        default=None,
        help="Only review for specific horizons, comma-separated (e.g. 5,20,60)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Filter by scheduled_review_date >= YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Filter by scheduled_review_date <= YYYY-MM-DD",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without writing anything",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of reviews to process (0 = no limit)",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output results as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--subject-type",
        type=str,
        default=None,
        choices=["stock", "industry"],
        help="Only review theses of a specific subject type",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    return date.fromisoformat(val)


def _parse_horizons(val: str | None) -> list[int] | None:
    if not val:
        return None
    return [int(x.strip()) for x in val.split(",") if x.strip()]


def _persist_review(
    db_session,
    review: ResearchThesisReview,
    thesis: ResearchThesis,
    result: ThesisReviewResult,
    review_date: date,
) -> None:
    """Persist a single review result to the database session."""
    review.review_status = result.review_status
    review.actual_review_date = review_date
    review.realized_return = result.realized_return
    review.benchmark_return = result.benchmark_return
    review.realized_metrics_json = json.dumps(
        result.realized_metrics_json, ensure_ascii=False,
    )
    review.review_note = result.review_note
    review.evidence_update_json = json.dumps(
        result.evidence_update_json, ensure_ascii=False,
    )
    review.created_at = datetime.now(timezone.utc)
    _update_thesis_status(thesis, result.review_status)


def _update_thesis_status(thesis: ResearchThesis, review_status: str) -> None:
    """Adjust thesis.status after a review completes."""
    if review_status == "invalidated":
        thesis.status = "invalidated"
    elif review_status == "missed":
        if thesis.status not in {"invalidated", "completed"}:
            thesis.status = "missed"
    elif review_status == "hit":
        if thesis.status == "active":
            thesis.status = "validated"


def _query_due_count(db_session, as_of_date: date) -> int:
    """Count pending reviews due on or before *as_of_date*."""
    return (
        db_session.scalar(
            select(func.count(ResearchThesisReview.id)).where(
                ResearchThesisReview.review_status == "pending",
                ResearchThesisReview.scheduled_review_date <= as_of_date,
            ),
        )
        or 0
    )


def _query_review_pairs(
    db_session,
    as_of_date: date,
    all_pending: bool,
    horizons: list[int] | None,
    start_date: date | None,
    end_date: date | None,
    subject_type: str | None,
    limit: int,
) -> list[tuple[ResearchThesisReview, ResearchThesis]]:
    """Query reviews with custom filters, returning ``(review, thesis)`` pairs."""
    query = (
        select(ResearchThesisReview, ResearchThesis)
        .join(ResearchThesis, ResearchThesisReview.thesis_id == ResearchThesis.id)
        .where(ResearchThesisReview.review_status == "pending")
    )

    if not all_pending:
        query = query.where(ResearchThesisReview.scheduled_review_date <= as_of_date)

    if start_date is not None:
        query = query.where(ResearchThesisReview.scheduled_review_date >= start_date)
    if end_date is not None:
        query = query.where(ResearchThesisReview.scheduled_review_date <= end_date)
    if subject_type is not None:
        query = query.where(ResearchThesis.subject_type == subject_type)
    if horizons is not None:
        query = query.where(ResearchThesisReview.review_horizon_days.in_(horizons))

    query = query.order_by(ResearchThesisReview.scheduled_review_date)
    if limit > 0:
        query = query.limit(limit)

    rows = db_session.execute(query).all()
    return [(row[0], row[1]) for row in rows]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    init_db()

    as_of_date = _parse_date(args.date) or date.today()
    horizons = _parse_horizons(args.horizon)
    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)
    limit = args.limit if args.limit > 0 else 0

    # Fast path: use simple run_due_reviews() when no custom filters are active
    use_fast_path = (
        not args.all_pending
        and horizons is None
        and start_date is None
        and end_date is None
        and args.subject_type is None
        and limit <= 0
    )

    db = SessionLocal()
    t0 = time.time()

    try:
        # ------------------------------------------------------------------
        # Dry-run mode
        # ------------------------------------------------------------------
        if args.dry_run:
            if use_fast_path:
                count = _query_due_count(db, as_of_date)
                print(
                    f"[DRY RUN] Would run run_due_reviews("
                    f"as_of_date={as_of_date.isoformat()}) — "
                    f"{count} pending review(s) due",
                )
            else:
                pairs = _query_review_pairs(
                    db,
                    as_of_date,
                    args.all_pending,
                    horizons,
                    start_date,
                    end_date,
                    args.subject_type,
                    limit,
                )
                print(
                    f"[DRY RUN] Would review {len(pairs)} thesis "
                    f"review(s) with custom filters",
                )
                for review, thesis in pairs:
                    print(
                        f"  [DRY RUN] Thesis #{review.thesis_id} "
                        f"(horizon={review.review_horizon_days}d, "
                        f"scheduled={review.scheduled_review_date}, "
                        f"type={thesis.subject_type})",
                    )
            db.close()
            return

        # ------------------------------------------------------------------
        # Execute reviews
        # ------------------------------------------------------------------
        if use_fast_path:
            results = run_due_reviews(as_of_date, db)
            db.commit()
        else:
            pairs = _query_review_pairs(
                db,
                as_of_date,
                args.all_pending,
                horizons,
                start_date,
                end_date,
                args.subject_type,
                limit,
            )
            results: list[ThesisReviewResult] = []
            for review, thesis in pairs:
                try:
                    result = run_thesis_review(thesis, review, db)
                except Exception as exc:
                    result = ThesisReviewResult(
                        thesis_id=review.thesis_id,
                        review_horizon_days=review.review_horizon_days,
                        scheduled_review_date=review.scheduled_review_date,
                        review_status="inconclusive",
                        realized_return=None,
                        benchmark_return=None,
                        realized_metrics_json={},
                        review_note=f"Review engine error: {exc}",
                        evidence_update_json={},
                    )
                _persist_review(db, review, thesis, result, as_of_date)
                results.append(result)
            db.commit()

        elapsed = time.time() - t0

        # ------------------------------------------------------------------
        # Output
        # ------------------------------------------------------------------
        if args.output_json:
            output = {
                "date": as_of_date.isoformat(),
                "total_reviewed": len(results),
                "hits": sum(1 for r in results if r.review_status == "hit"),
                "missed": sum(1 for r in results if r.review_status == "missed"),
                "invalidated": sum(
                    1 for r in results if r.review_status == "invalidated"
                ),
                "inconclusive": sum(
                    1 for r in results if r.review_status == "inconclusive"
                ),
                "elapsed_seconds": round(elapsed, 2),
            }
            print(json.dumps(output, ensure_ascii=False))
        else:
            hits = sum(1 for r in results if r.review_status == "hit")
            missed = sum(1 for r in results if r.review_status == "missed")
            invalidated = sum(
                1 for r in results if r.review_status == "invalidated"
            )
            inconclusive = sum(
                1 for r in results if r.review_status == "inconclusive"
            )
            print(f"Reviewed {len(results)} theses in {elapsed:.1f}s:")
            print(f"  Hits: {hits}")
            print(f"  Missed: {missed}")
            print(f"  Invalidated: {invalidated}")
            print(f"  Inconclusive: {inconclusive}")
            for r in results:
                print(
                    f"  Thesis #{r.thesis_id}: {r.review_status} "
                    f"(horizon={r.review_horizon_days}d)",
                )

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
