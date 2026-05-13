"""Tests for thesis review analytics computation.

Verifies that ``compute_thesis_analytics`` produces correct per-dimension
breakdowns, calibration analysis, and low-sample warnings, and that snapshots
are persisted and retrievable.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import ResearchThesis, ResearchThesisReview, ThesisReviewAnalyticsSnapshot
from app.engines.thesis_analytics_engine import compute_thesis_analytics, get_latest_analytics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thesis(
    db_session,
    *,
    subject_type: str = "stock",
    subject_id: str = "300308",
    direction: str = "up",
    horizon_days: int = 20,
    confidence: float = 70.0,
    source_type: str = "daily_report",
) -> ResearchThesis:
    """Create and return a minimal ResearchThesis."""
    thesis = ResearchThesis(
        source_type=source_type,
        source_id="1",
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name="样本",
        thesis_title="测试观点",
        thesis_body="趋势偏强，持续关注。",
        direction=direction,
        horizon_days=horizon_days,
        confidence=confidence,
    )
    db_session.add(thesis)
    db_session.flush()
    return thesis


def _make_review(
    db_session,
    thesis: ResearchThesis,
    *,
    status: str = "hit",
    horizon_days: int = 20,
) -> ResearchThesisReview:
    """Create a completed review for *thesis*."""
    review = ResearchThesisReview(
        thesis_id=thesis.id,
        review_horizon_days=horizon_days,
        scheduled_review_date=date(2026, 5, 20),
        review_status=status,
        actual_review_date=date(2026, 5, 20),
        realized_return=0.05 if status == "hit" else -0.05 if status == "missed" else None,
    )
    db_session.add(review)
    db_session.flush()
    return review


# =============================================================================
# Tests
# =============================================================================


class TestThesisAnalytics:
    """Test thesis analytics computation."""

    def test_compute_analytics_empty(self, db_session) -> None:
        """Computing analytics with no reviews should return zeros, not crash."""
        snapshot = compute_thesis_analytics(db_session, snapshot_date=date(2026, 5, 20))

        assert snapshot.sample_size == 0
        assert snapshot.hit_count == 0
        assert snapshot.missed_count == 0
        assert snapshot.inconclusive_count == 0
        assert snapshot.invalidated_count == 0
        assert snapshot.hit_rate is None
        assert snapshot.miss_rate is None
        assert snapshot.inconclusive_rate is None

    def test_compute_analytics_with_reviews(self, db_session) -> None:
        """With review data, should compute correct hit/miss/inconclusive rates."""
        t1 = _make_thesis(db_session)
        _make_review(db_session, t1, status="hit")
        t2 = _make_thesis(db_session, subject_id="688235")
        _make_review(db_session, t2, status="hit")
        t3 = _make_thesis(db_session, subject_id="000001")
        _make_review(db_session, t3, status="missed")
        db_session.flush()

        snapshot = compute_thesis_analytics(db_session, snapshot_date=date(2026, 5, 20))

        assert snapshot.sample_size == 3
        assert snapshot.hit_count == 2
        assert snapshot.missed_count == 1
        assert pytest.approx(snapshot.hit_rate, abs=1e-4) == 2 / 3

    def test_analytics_by_subject_type(self, db_session) -> None:
        """Should group stats by subject_type."""
        t1 = _make_thesis(db_session, subject_type="stock")
        _make_review(db_session, t1, status="hit")
        t2 = _make_thesis(db_session, subject_type="industry", subject_id="1")
        _make_review(db_session, t2, status="missed")
        db_session.flush()

        snapshot = compute_thesis_analytics(db_session, snapshot_date=date(2026, 5, 20))

        by_subject = json.loads(snapshot.by_subject_type_json)
        assert "stock" in by_subject
        assert "industry" in by_subject
        assert by_subject["stock"]["hit_count"] == 1
        assert by_subject["industry"]["miss_count"] == 1

    def test_analytics_by_confidence_bucket(self, db_session) -> None:
        """Should bucket confidence levels correctly.

        Confidence values fall into predefined buckets: 0-40, 40-60, 60-75,
        75-90, 90-100.
        """
        t1 = _make_thesis(db_session, confidence=35.0)  # bucket 0-40
        _make_review(db_session, t1, status="hit")
        t2 = _make_thesis(db_session, subject_id="688235", confidence=80.0)  # bucket 75-90
        _make_review(db_session, t2, status="hit")
        db_session.flush()

        snapshot = compute_thesis_analytics(db_session, snapshot_date=date(2026, 5, 20))

        by_bucket = json.loads(snapshot.by_confidence_bucket_json)
        assert "0-40" in by_bucket
        assert "75-90" in by_bucket

    def test_calibration_gap_overconfident(self, db_session) -> None:
        """When confidence > actual hit rate, calibration_gap should be positive."""
        for i in range(5):
            t = _make_thesis(db_session, subject_id=f"T{i:04d}", confidence=95.0)
            _make_review(db_session, t, status="missed")
            db_session.flush()

        snapshot = compute_thesis_analytics(db_session, snapshot_date=date(2026, 5, 20))

        calib = json.loads(snapshot.calibration_report_json)
        assert "90-100" in calib
        gap = calib["90-100"]["calibration_gap"]
        # Midpoint is 0.95, actual hit rate is 0.0 => gap = 0.95
        assert gap is not None
        assert gap > 0

    def test_low_sample_warning(self, db_session) -> None:
        """Groups with < 10 samples should have low_sample_warning."""
        t = _make_thesis(db_session, subject_type="stock")
        _make_review(db_session, t, status="hit")
        db_session.flush()

        snapshot = compute_thesis_analytics(db_session, snapshot_date=date(2026, 5, 20))

        warnings = json.loads(snapshot.low_sample_warnings_json)
        assert len(warnings) >= 1
        for w in warnings:
            assert w["sample_size"] < 10

    def test_analytics_snapshot_persisted(self, db_session) -> None:
        """Snapshot should be saved to DB and retrievable."""
        t = _make_thesis(db_session)
        _make_review(db_session, t, status="hit")
        db_session.flush()

        compute_thesis_analytics(db_session, snapshot_date=date(2026, 5, 20))

        latest = get_latest_analytics(db_session)
        assert latest is not None
        assert latest.sample_size == 1
        assert latest.hit_count == 1
        assert latest.snapshot_date == date(2026, 5, 20)
