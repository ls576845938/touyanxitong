"""Tests for report quality scoring."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models import DailyReport, ReportQualityScore, ResearchThesis, ResearchThesisReview, ScoringFeedbackEvent
from app.engines.report_quality_engine import (
    compute_report_quality,
    create_feedback_event,
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
    *,
    subject_type: str = "stock",
    subject_id: str = "300308",
    confidence: float = 70.0,
    evidence_refs: list | None = None,
    risk_flags: list | None = None,
) -> ResearchThesis:
    """Create a ResearchThesis row."""
    thesis = ResearchThesis(
        source_type=source_type,
        source_id=source_id,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name="样本",
        thesis_title="测试观点",
        thesis_body="趋势偏强，持续关注。",
        direction="up",
        horizon_days=20,
        confidence=confidence,
        evidence_refs_json=json.dumps(evidence_refs or [], ensure_ascii=False),
        risk_flags_json=json.dumps(risk_flags or [], ensure_ascii=False),
    )
    db_session.add(thesis)
    db_session.flush()
    return thesis


def _make_review(
    db_session,
    thesis: ResearchThesis,
    *,
    status: str = "hit",
    realized_return: float | None = None,
    horizon_days: int = 20,
) -> ResearchThesisReview:
    """Create a completed review."""
    review = ResearchThesisReview(
        thesis_id=thesis.id,
        review_horizon_days=horizon_days,
        scheduled_review_date=date(2026, 5, 20),
        review_status=status,
        realized_return=realized_return,
        actual_review_date=date(2026, 5, 20),
    )
    db_session.add(review)
    db_session.flush()
    return review


# =============================================================================
# ReportQualityScore model
# =============================================================================


class TestReportQualityModel:
    """Test ReportQualityScore model creation."""

    def test_create_quality_score(self, db_session) -> None:
        """Can create a report quality score record."""
        score = ReportQualityScore(
            source_type="daily_report",
            source_id=1,
            thesis_count=3,
            evidence_count=5,
            avg_confidence=70.0,
            quality_score=65.0,
        )
        db_session.add(score)
        db_session.commit()
        db_session.refresh(score)

        assert score.id is not None
        assert score.source_type == "daily_report"
        assert score.source_id == 1
        assert score.thesis_count == 3
        assert score.evidence_count == 5
        assert score.avg_confidence == 70.0
        assert score.quality_score == 65.0
        assert score.created_at is not None

    def test_unique_source_constraint(self, db_session) -> None:
        """Cannot create duplicate quality scores for same source."""
        score1 = ReportQualityScore(
            source_type="daily_report",
            source_id=1,
            thesis_count=3,
            quality_score=65.0,
        )
        db_session.add(score1)
        db_session.commit()

        score2 = ReportQualityScore(
            source_type="daily_report",
            source_id=1,
            thesis_count=5,
            quality_score=80.0,
        )
        db_session.add(score2)
        with pytest.raises(Exception):
            db_session.commit()

    def test_quality_score_defaults(self, db_session) -> None:
        """Quality score should default to 0."""
        score = ReportQualityScore(
            source_type="daily_report",
            source_id=99,
        )
        db_session.add(score)
        db_session.commit()
        db_session.refresh(score)

        assert score.quality_score == 0.0
        assert score.thesis_count == 0
        assert score.evidence_count == 0
        assert score.avg_confidence == 0.0
        assert score.guardrail_violation_count == 0
        assert score.unavailable_data_count == 0


# =============================================================================
# compute_report_quality
# =============================================================================


class TestComputeReportQuality:
    """Test compute_report_quality function."""

    def test_compute_quality_from_theses(self, db_session) -> None:
        """Should compute quality score from thesis count and evidence."""
        report = _make_daily_report(db_session)
        _make_thesis(
            db_session,
            source_type="daily_report",
            source_id=str(report.id),
            subject_id="300308",
            confidence=80.0,
            evidence_refs=[{"source": "industry_heat", "heat_score": 82.0}],
        )
        _make_thesis(
            db_session,
            source_type="daily_report",
            source_id=str(report.id),
            subject_id="688235",
            confidence=70.0,
            evidence_refs=[{"source": "industry_heat", "heat_score": 75.0}],
        )

        result = compute_report_quality("daily_report", report.id, db_session)

        assert result.quality_score > 0
        assert result.thesis_count == 2
        assert result.evidence_count == 2
        assert result.avg_confidence > 0

    def test_quality_score_range(self, db_session) -> None:
        """Quality score should be 0-100."""
        # No theses -> low quality
        report = _make_daily_report(db_session)
        result = compute_report_quality("daily_report", report.id, db_session)
        assert 0 <= result.quality_score <= 100

        # Many theses with evidence -> higher quality
        report2 = _make_daily_report(db_session, report_date=date(2026, 5, 14))
        for i in range(5):
            _make_thesis(
                db_session,
                source_type="daily_report",
                source_id=str(report2.id),
                subject_id=f"T{i:04d}",
                confidence=90.0,
                evidence_refs=[{"source": "industry_heat", "heat_score": 80.0 + i}],
            )
        result2 = compute_report_quality("daily_report", report2.id, db_session)
        assert 0 <= result2.quality_score <= 100

    def test_quality_no_theses(self, db_session) -> None:
        """Report with no theses should have low but valid quality score."""
        report = _make_daily_report(db_session)
        result = compute_report_quality("daily_report", report.id, db_session)
        assert result.quality_score >= 0
        assert result.thesis_count == 0

    def test_guardrail_violation_penalty(self, db_session) -> None:
        """Reports with guardrail violations in thesis text should have lower quality."""
        report = _make_daily_report(db_session)

        # Thesis with guardrail-violating text
        thesis = ResearchThesis(
            source_type="daily_report",
            source_id=str(report.id),
            subject_type="stock",
            subject_id="BAD",
            subject_name="违规",
            thesis_title="100% 确定",
            thesis_body="无风险稳赚的机会。",
            direction="up",
            evidence_refs_json="[]",
        )
        db_session.add(thesis)
        db_session.flush()

        result = compute_report_quality("daily_report", report.id, db_session)

        assert result.guardrail_violation_count >= 1
        assert result.quality_score <= 70  # penalized

    def test_quality_more_evidence_higher_score(self, db_session) -> None:
        """More theses and evidence should result in a higher quality score."""
        # Low-evidence report
        report_low = _make_daily_report(db_session, report_date=date(2026, 5, 13))
        _make_thesis(
            db_session,
            source_type="daily_report",
            source_id=str(report_low.id),
            subject_id="T001",
            confidence=50.0,
            evidence_refs=[],
        )
        result_low = compute_report_quality("daily_report", report_low.id, db_session)

        # High-evidence report
        report_high = _make_daily_report(db_session, report_date=date(2026, 5, 14))
        for i in range(4):
            _make_thesis(
                db_session,
                source_type="daily_report",
                source_id=str(report_high.id),
                subject_id=f"T{i:04d}",
                confidence=90.0,
                evidence_refs=[{"source": "test", "score": 80.0 + i} for _ in range(3)],
            )
        result_high = compute_report_quality("daily_report", report_high.id, db_session)

        assert result_high.quality_score > result_low.quality_score


# =============================================================================
# update_quality_from_reviews
# =============================================================================


class TestUpdateQualityFromReviews:
    """Test update_quality_from_reviews function."""

    def test_update_quality_from_reviews(self, db_session) -> None:
        """Should update hit rates when reviews are completed."""
        report = _make_daily_report(db_session)
        thesis = _make_thesis(
            db_session,
            source_type="daily_report",
            source_id=str(report.id),
            subject_id="300308",
        )

        # Compute initial quality
        initial = compute_report_quality("daily_report", report.id, db_session)

        # Add completed reviews with different horizon days
        _make_review(db_session, thesis, status="confirmed", realized_return=0.05, horizon_days=5)
        _make_review(db_session, thesis, status="confirmed", realized_return=0.03, horizon_days=20)

        # Update with review data
        updated = update_quality_from_reviews("daily_report", report.id, db_session)

        assert updated.hit_rate_5d is not None or updated.hit_rate_20d is not None

    def test_update_quality_nonexistent_source(self, db_session) -> None:
        """Should handle missing source gracefully."""
        with pytest.raises(Exception):
            compute_report_quality("daily_report", 99999, db_session)

    def test_update_quality_empty_source(self, db_session) -> None:
        """Source with no theses should still get a quality score."""
        report = _make_daily_report(db_session)
        result = compute_report_quality("daily_report", report.id, db_session)
        assert result is not None


# =============================================================================
# create_feedback_event
# =============================================================================


class TestCreateFeedbackEvent:
    """Test create_feedback_event function."""

    def test_create_feedback_event(self, db_session) -> None:
        """Should create a scoring feedback event from a thesis review."""
        thesis = ResearchThesis(
            source_type="daily_report",
            source_id="1",
            subject_type="stock",
            subject_id="300308",
            subject_name="中际旭创",
            thesis_title="趋势偏强测试",
            thesis_body="趋势偏强。",
            direction="up",
            confidence=75.0,
        )
        db_session.add(thesis)
        db_session.flush()

        review = ResearchThesisReview(
            thesis_id=thesis.id,
            review_horizon_days=20,
            scheduled_review_date=date(2026, 5, 15),
            review_status="confirmed",
            realized_return=0.05,
        )
        db_session.add(review)
        db_session.flush()

        event = create_feedback_event(thesis, review, db_session)

        assert event.id is not None
        assert event.thesis_id == thesis.id
        assert event.subject_type == "stock"
        assert event.subject_id == "300308"
        assert event.signal_name is not None
        assert event.expected_direction == "positive"
        assert event.review_status == "confirmed"
        assert event.confidence == 75

    def test_create_feedback_event_rejected(self, db_session) -> None:
        """Rejected review should map to opposite direction."""
        thesis = ResearchThesis(
            source_type="daily_report",
            source_id="1",
            subject_type="stock",
            subject_id="300308",
            subject_name="中际旭创",
            thesis_title="趋势偏强测试",
            thesis_body="趋势偏强。",
            direction="up",
            confidence=60.0,
        )
        db_session.add(thesis)
        db_session.flush()

        review = ResearchThesisReview(
            thesis_id=thesis.id,
            review_horizon_days=20,
            scheduled_review_date=date(2026, 5, 15),
            review_status="rejected",
        )
        db_session.add(review)
        db_session.flush()

        event = create_feedback_event(thesis, review, db_session)

        assert event.expected_direction == "positive"
        assert event.actual_direction == "negative"


# =============================================================================
# Scoring weights immutability
# =============================================================================


class TestScoringWeightsImmutability:
    """Scoring engine weights should NOT be modified by quality feedback."""

    def test_no_auto_weight_modification(self, db_session) -> None:
        """Quality feedback should not modify scoring engine module state.

        This test verifies that compute_report_quality / create_feedback_event
        do NOT mutate any global tunables in the scoring engine module.
        """
        import app.engines.tenbagger_score_engine as sc

        # Capture initial module-level attributes (filtered to relevant ones)
        initial_dir = {k: v for k, v in vars(sc).items() if not k.startswith("_")}

        # Run quality feedback operations
        report = _make_daily_report(db_session)
        thesis = _make_thesis(
            db_session,
            source_type="daily_report",
            source_id=str(report.id),
            subject_id="300308",
        )
        compute_report_quality("daily_report", report.id, db_session)

        review = _make_review(db_session, thesis, status="confirmed", realized_return=0.05)
        create_feedback_event(thesis, review, db_session)

        # Verify module state unchanged
        current_dir = {k: v for k, v in vars(sc).items() if not k.startswith("_")}
        for key in initial_dir:
            # Skip built-in types and functions -- only check non-callable attributes
            # that look like tunable values
            if key not in current_dir:
                continue
            initial_val = initial_dir[key]
            current_val = current_dir[key]
            if type(initial_val) in (int, float, str, bool, type(None)):
                assert initial_val == current_val, (
                    f"Scoring engine tunable '{key}' was modified from {initial_val!r} to {current_val!r}"
                )
