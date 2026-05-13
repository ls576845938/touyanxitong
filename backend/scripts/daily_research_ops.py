"""Daily research operations script.

Runs the complete closed-loop workflow:
  1. Daily pipeline (optional — can be run separately)
  2. Daily report generation (includes thesis extraction + review schedule)
  3. Due thesis reviews
  4. Analytics recomputation
  5. Report quality recomputation

Usage:
    python scripts/daily_research_ops.py [OPTIONS]

Options:
    --date YYYY-MM-DD       Target date (default: today)
    --skip-pipeline         Skip the daily data pipeline
    --skip-report           Skip daily report generation
    --skip-review           Skip thesis review execution
    --skip-analytics        Skip analytics recomputation
    --skip-quality          Skip report quality recomputation
    --dry-run               Print steps without writing anything
    --output-json           Output results as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.models import DailyReport  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.pipeline.daily_pipeline import run_daily_pipeline  # noqa: E402
from app.pipeline.daily_report_job import run_daily_report_job  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run daily research operations (closed-loop workflow).",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Skip the daily data pipeline",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Skip daily report generation",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip thesis review execution",
    )
    parser.add_argument(
        "--skip-analytics",
        action="store_true",
        help="Skip analytics recomputation",
    )
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip report quality recomputation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps without writing anything",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output results as JSON at the end",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(val: str | None) -> date:
    if not val:
        return date.today()
    return date.fromisoformat(val)


def _run_step(
    step_name: str,
    step_label: str,
    dry_run: bool,
    steps: dict,
    warnings: list,
    fn,
) -> str:
    """Execute a single workflow step with error handling.

    Returns the overall status ('success' or 'partial').
    """
    overall = "success"
    print(f"\n--- {step_label} ---")

    if dry_run:
        print(f"  [DRY RUN] Would run: {step_name}")
        steps[step_name] = {"status": "dry_run"}
        return overall

    try:
        t0 = time.time()
        result = fn()
        duration = time.time() - t0
        steps[step_name] = result
        if "duration_seconds" not in steps[step_name]:
            steps[step_name]["duration_seconds"] = round(duration, 1)
        print(f"  Completed in {duration:.1f}s")
    except Exception as exc:
        print(f"  [ERROR] {step_name} failed: {exc}")
        warnings.append(f"{step_name}: {exc}")
        steps[step_name] = {"status": "failed", "error": str(exc)}
        overall = "partial"

    return overall


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    target_date = _parse_date(args.date)

    print("=" * 60)
    print(f"  Daily Research Ops — {target_date}")
    print("=" * 60)

    init_db()

    steps: dict[str, dict] = {}
    warnings: list[str] = []
    overall = "success"

    # ------------------------------------------------------------------
    # Step 1: Daily Pipeline
    # ------------------------------------------------------------------
    if not args.skip_pipeline:

        def _step_pipeline():
            run_daily_pipeline(end_date=target_date)
            return {"status": "completed"}

        step_result = _run_step(
            "pipeline",
            f"Step 1/5: Daily Pipeline ({target_date})",
            args.dry_run,
            steps,
            warnings,
            _step_pipeline,
        )
        if step_result == "partial":
            overall = "partial"

    # ------------------------------------------------------------------
    # Step 2: Daily Report + Theses
    # ------------------------------------------------------------------
    if not args.skip_report:

        def _step_report():
            with SessionLocal() as session:
                report_result = run_daily_report_job(session, report_date=target_date)
                session.commit()
            return {
                "status": "completed",
                "theses_created": report_result.get("daily_reports", 0),
            }

        step_result = _run_step(
            "report",
            f"Step 2/5: Daily Report + Theses ({target_date})",
            args.dry_run,
            steps,
            warnings,
            _step_report,
        )
        if step_result == "partial":
            overall = "partial"

    # ------------------------------------------------------------------
    # Step 3: Due Thesis Reviews
    # ------------------------------------------------------------------
    if not args.skip_review:

        def _step_review():
            from app.engines.thesis_review_engine import run_due_reviews

            with SessionLocal() as session:
                results = run_due_reviews(target_date, session)
                session.commit()
            total = len(results)
            completed = sum(1 for r in results if r.review_status in {"hit", "missed"})
            inconclusive = sum(1 for r in results if r.review_status == "inconclusive")
            invalidated = sum(1 for r in results if r.review_status == "invalidated")
            print(
                f"  Reviewed {total}: {completed} completed, "
                f"{inconclusive} inconclusive, {invalidated} invalidated",
            )
            return {
                "status": "completed",
                "due": total,
                "completed": completed,
                "inconclusive": inconclusive,
                "invalidated": invalidated,
            }

        step_result = _run_step(
            "review",
            f"Step 3/5: Due Thesis Reviews ({target_date})",
            args.dry_run,
            steps,
            warnings,
            _step_review,
        )
        if step_result == "partial":
            overall = "partial"

    # ------------------------------------------------------------------
    # Step 4: Analytics Recomputation
    # ------------------------------------------------------------------
    if not args.skip_analytics:

        def _step_analytics():
            try:
                from app.engines.thesis_analytics_engine import (
                    compute_thesis_analytics,
                )
            except ImportError:
                warnings.append("Analytics: thesis_analytics_engine not available")
                return {"status": "skipped", "reason": "module not available"}

            with SessionLocal() as session:
                snapshot = compute_thesis_analytics(session, snapshot_date=target_date)
                session.commit()

            sample_size = snapshot.sample_size

            # Collect low-sample warnings from the snapshot
            if snapshot.low_sample_warnings_json:
                try:
                    low_warnings = json.loads(snapshot.low_sample_warnings_json)
                    for w in low_warnings:
                        warnings.append(
                            f"Analytics: {w.get('dimension', '?')} "
                            f"bucket '{w.get('group', '?')}' has only "
                            f"{w.get('sample_size', 0)} samples",
                        )
                except (json.JSONDecodeError, TypeError):
                    pass

            print(f"  Analytics computed (sample_size={sample_size})")
            return {
                "status": "completed",
                "sample_size": sample_size,
            }

        step_result = _run_step(
            "analytics",
            f"Step 4/5: Analytics Recomputation ({target_date})",
            args.dry_run,
            steps,
            warnings,
            _step_analytics,
        )
        if step_result == "partial":
            overall = "partial"

    # ------------------------------------------------------------------
    # Step 5: Report Quality Recomputation
    # ------------------------------------------------------------------
    if not args.skip_quality:

        def _step_quality():
            try:
                from app.engines.report_quality_engine import (
                    update_quality_from_reviews,
                )
            except ImportError:
                warnings.append("Quality: report_quality_engine not available")
                return {"status": "skipped", "reason": "module not available"}

            with SessionLocal() as session:
                reports = session.scalars(
                    select(DailyReport).order_by(DailyReport.report_date.desc()),
                ).all()
                updated = 0
                for report in reports:
                    try:
                        update_quality_from_reviews("daily_report", report.id, session)
                        updated += 1
                    except Exception as qe:
                        warnings.append(f"Quality: report #{report.id} failed: {qe}")
                session.commit()

            print(f"  Quality scores updated for {updated} report(s)")
            return {
                "status": "completed",
                "scores_updated": updated,
            }

        step_result = _run_step(
            "quality",
            f"Step 5/5: Report Quality Recomputation ({target_date})",
            args.dry_run,
            steps,
            warnings,
            _step_quality,
        )
        if step_result == "partial":
            overall = "partial"

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    if not args.dry_run:
        title = f"  Overall: {overall}"
    else:
        title = "  DRY RUN — No changes written"

    print()
    print("=" * 60)
    print(title)
    print("=" * 60)

    if warnings:
        print()
        print("Warnings:")
        for w in warnings:
            print(f"  - {w}")

    # JSON final output is always produced when --output-json is set
    if args.output_json:
        output = {
            "date": target_date.isoformat(),
            "steps": steps,
            "warnings": warnings,
            "overall": overall,
        }
        print()
        print(json.dumps(output, ensure_ascii=False, indent=2))

    sys.exit(0 if overall == "success" else 1)


if __name__ == "__main__":
    main()
