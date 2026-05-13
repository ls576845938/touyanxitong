"""Tests for report quality time-series tracking.

Verifies that quality scores can be computed before and after reviews, that
multiple reports at different dates create a queryable time series, and that
hit rates are never fabricated when no review data exists.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db.models import DailyReport, ReportQualityScore, ResearchThesis, ResearchThesisReview
from app.engines.report_quality_engine import (
    compute_report_quality,
    update_quality_from_reviews,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_daily_report(db_session, report_date: date = date(2026, 5, 13)) -> DailyReport:
    """Create a DailyReport row."""
    report = DailyReport(
        report_date=report_date,
        title="测试报告",
        market_summary="市场偏强",
        top_industries="[]",
        top_trend_stocks="[]",
        risk_alerts="[]",
        full_markdown="",
    )
    db_session.add(report)
    db_session.flush()
    return report


def _make_thesis(
    db_session,
    source_type: str = "daily_report",
    source_id: str = "1",
    **kw,
) -> ResearchThesis:
    """Create a ResearchThesis row."""
    thesis = ResearchThesis(
        source_type=source_type,
        source_id=source_id,
        subject_type="stock",
        subject_id="300308",
        subject_name="样本",
        thesis_title="测试观点",
        thesis_body="趋势偏强，持续关注。",
        direction="up",
        horizon_days=20,
        confidence=70.0,
        **kw,
    )
    db_session.add(thesis)
    db_session.flush()
    return thesis


def _make_review(
    db_session,
    thesis: ResearchThesis,
    *,
    status: str = "confirmed",
    horizon_days: int = 20,
    realized_return: float = 0.05,
) -> ResearchThesisReview:
    """Create a completed review for *thesis*."""
    review = ResearchThesisReview(
        thesis_id=thesis.id,
        review_horizon_days=horizon_days,
        scheduled_review_date=date(2026, 5, 20),
        review_status=status,
        actual_review_date=date(2026, 5, 20),
        realized_return=realized_return,
    )
    db_session.add(review)
    db_session.flush()
    return review


# =============================================================================
# Tests
# =============================================================================


class TestReportQualityTimeseries:
    """Test report quality time-series tracking."""

    def test_pre_review_quality_score(self, db_session) -> None:
        """Quality score before reviews should not have hit rates."""
        report = _make_daily_report(db_session)
        _make_thesis(db_session, source_id=str(report.id))

        score = compute_report_quality("daily_report", report.id, db_session)

        assert score.hit_rate_5d is None
        assert score.hit_rate_20d is None
        assert score.hit_rate_60d is None
        assert score.quality_score >= 0

    def test_post_review_quality_score(self, db_session) -> None:
        """Quality score after reviews should have hit rates."""
        report = _make_daily_report(db_session)
        thesis = _make_thesis(db_session, source_id=str(report.id))
        db_session.commit()

        # Initial quality (no reviews yet)
        pre = compute_report_quality("daily_report", report.id, db_session)
        assert pre.hit_rate_5d is None

        # Add reviews and update
        _make_review(db_session, thesis, status="confirmed", realized_return=0.05, horizon_days=5)
        _make_review(db_session, thesis, status="confirmed", realized_return=0.03, horizon_days=20)
        db_session.commit()

        updated = update_quality_from_reviews("daily_report", report.id, db_session)

        # After update, at least one horizon bucket should have a rate
        assert updated.hit_rate_5d is not None or updated.hit_rate_20d is not None

    def test_quality_timeseries_multiple_dates(self, db_session) -> None:
        """Multiple reports at different dates create a queryable time series."""
        # Report on day 1
        report1 = _make_daily_report(db_session, report_date=date(2026, 5, 10))
        _make_thesis(db_session, source_id=str(report1.id))
        score1 = compute_report_quality("daily_report", report1.id, db_session)

        # Report on day 2
        report2 = _make_daily_report(db_session, report_date=date(2026, 5, 11))
        _make_thesis(db_session, source_id=str(report2.id))
        score2 = compute_report_quality("daily_report", report2.id, db_session)

        # Both scores should be persisted and individually queryable
        all_scores = list(
            db_session.scalars(
                select(ReportQualityScore).order_by(ReportQualityScore.id)
            ).all()
        )
        assert len(all_scores) == 2
        assert all_scores[0].source_id == report1.id
        assert all_scores[1].source_id == report2.id

    def test_quality_timeseries_filtering(self, db_session) -> None:
        """Should be able to filter by source_type and source_id."""
        report1 = _make_daily_report(db_session, report_date=date(2026, 5, 13))
        report2 = _make_daily_report(db_session, report_date=date(2026, 5, 14))
        _make_thesis(db_session, source_id=str(report1.id))
        _make_thesis(db_session, source_id=str(report2.id))

        compute_report_quality("daily_report", report1.id, db_session)
        compute_report_quality("daily_report", report2.id, db_session)

        # Filter by source_type
        daily_scores = list(
            db_session.scalars(
                select(ReportQualityScore).where(
                    ReportQualityScore.source_type == "daily_report"
                ).order_by(ReportQualityScore.id)
            ).all()
        )
        assert len(daily_scores) == 2

        # Filter by source_id
        score = db_session.scalar(
            select(ReportQualityScore).where(
                ReportQualityScore.source_type == "daily_report",
                ReportQualityScore.source_id == report1.id,
            )
        )
        assert score is not None
        assert score.source_id == report1.id

    def test_no_fabricated_hit_rate(self, db_session) -> None:
        """When no reviews exist, hit rates must be None, never 0.0."""
        report = _make_daily_report(db_session)
        _make_thesis(db_session, source_id=str(report.id))

        score = compute_report_quality("daily_report", report.id, db_session)

        # Without reviews, hit rates must be None (not 0.0)
        assert score.hit_rate_5d is None
        assert score.hit_rate_20d is None
        assert score.hit_rate_60d is None
