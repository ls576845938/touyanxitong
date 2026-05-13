"""Tests for ResearchThesisReview model and thesis review engine."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models import DailyBar, Industry, IndustryHeat, ResearchThesis, ResearchThesisReview, Stock, TrendSignal
from app.engines.thesis_review_engine import (
    ThesisReviewResult,
    create_review_schedule,
    run_due_reviews,
    run_thesis_review,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thesis(
    db_session,
    *,
    subject_type="stock",
    subject_id="300308",
    direction="up",
    horizon_days=20,
    confidence=70.0,
) -> ResearchThesis:
    """Create and return a minimal ResearchThesis."""
    thesis = ResearchThesis(
        source_type="daily_report",
        source_id="1",
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name="中际旭创",
        thesis_title="测试观点",
        thesis_body="趋势偏强，持续关注。",
        direction=direction,
        horizon_days=horizon_days,
        confidence=confidence,
    )
    db_session.add(thesis)
    db_session.flush()
    return thesis


def _make_review(db_session, thesis: ResearchThesis, *, horizon_days: int = 20) -> ResearchThesisReview:
    """Create a pending review for *thesis*."""
    review = ResearchThesisReview(
        thesis_id=thesis.id,
        review_horizon_days=horizon_days,
        scheduled_review_date=date(2026, 5, 20),
        review_status="pending",
    )
    db_session.add(review)
    db_session.flush()
    return review


def _make_daily_bar(db_session, stock_code: str, trade_date: date, close: float = 100.0) -> DailyBar:
    """Create a DailyBar row (flushed)."""
    bar = DailyBar(
        stock_code=stock_code,
        trade_date=trade_date,
        open=close * 0.99,
        high=close * 1.02,
        low=close * 0.98,
        close=close,
        pre_close=close * 0.995,
        volume=1_000_000,
        amount=close * 1_000_000,
        pct_chg=0.5,
        source="test",
        source_kind="test",
        source_confidence=1.0,
    )
    db_session.add(bar)
    db_session.flush()
    return bar


def _make_stock(db_session, code: str, industry: str = "AI算力") -> Stock:
    """Create a Stock row (flushed)."""
    stock = Stock(
        code=code,
        name=f"样本_{code}",
        market="A",
        exchange="SZ",
        industry_level1=industry,
        is_active=True,
    )
    db_session.add(stock)
    db_session.flush()
    return stock


def _make_industry(db_session, industry_id: int = 1, name: str = "AI算力") -> Industry:
    """Create an Industry row."""
    ind = Industry(id=industry_id, name=name)
    db_session.add(ind)
    return ind


def _make_industry_heat(db_session, industry_id: int, trade_date: date, heat_score: float = 80.0) -> IndustryHeat:
    """Create an IndustryHeat row (flushed)."""
    ih = IndustryHeat(
        industry_id=industry_id,
        trade_date=trade_date,
        heat_score=heat_score,
        heat_change_7d=2.5,
        heat_change_30d=5.0,
        heat_1d=heat_score,
        heat_7d=heat_score - 2,
        heat_30d=heat_score - 5,
        top_keywords="[]",
        top_articles="[]",
        explanation="热度测试",
    )
    db_session.add(ih)
    db_session.flush()
    return ih


# =============================================================================
# ResearchThesisReview model
# =============================================================================


class TestThesisReviewModel:
    """Test ResearchThesisReview model creation and validation."""

    def test_create_review(self, db_session) -> None:
        """Can create a pending review for a thesis."""
        thesis = _make_thesis(db_session)
        review = _make_review(db_session, thesis)

        assert review.id is not None
        assert review.thesis_id == thesis.id
        assert review.review_status == "pending"
        assert review.scheduled_review_date is not None
        assert review.created_at is not None

    def test_review_status_values(self, db_session) -> None:
        """Review status transitions work correctly."""
        thesis = _make_thesis(db_session)
        review = _make_review(db_session, thesis)

        for status in ("pending", "hit", "missed", "invalidated", "inconclusive"):
            review.review_status = status
            db_session.commit()
            db_session.refresh(review)
            assert review.review_status == status

    def test_review_linked_to_thesis(self, db_session) -> None:
        """Review should be queryable by thesis_id."""
        thesis = _make_thesis(db_session)
        review = _make_review(db_session, thesis)

        # Reviews are loaded via query (not relationship) to avoid registry conflicts
        reviews = list(
            db_session.scalars(
                select(ResearchThesisReview).where(ResearchThesisReview.thesis_id == thesis.id)
            ).all()
        )
        assert len(reviews) == 1
        assert reviews[0].id == review.id

    def test_review_benchmark_return(self, db_session) -> None:
        """Review stores benchmark return correctly."""
        thesis = _make_thesis(db_session)
        review = _make_review(db_session, thesis)
        review.realized_return = 0.05
        review.benchmark_return = 0.03
        db_session.commit()
        db_session.refresh(review)
        assert review.realized_return == 0.05
        assert review.benchmark_return == 0.03


# =============================================================================
# create_review_schedule
# =============================================================================


class TestCreateReviewSchedule:
    """Test create_review_schedule function."""

    def test_create_review_schedule_short_horizon(self, db_session) -> None:
        """Short-horizon thesis (5d) gets only one review."""
        thesis = _make_thesis(db_session, horizon_days=5)
        horizons = create_review_schedule(thesis, db_session)

        assert horizons == [5]

        reviews = list(
            db_session.scalars(
                select(ResearchThesisReview).where(ResearchThesisReview.thesis_id == thesis.id)
            ).all()
        )
        assert len(reviews) == 1
        assert reviews[0].review_horizon_days == 5

    def test_create_review_schedule_medium_horizon(self, db_session) -> None:
        """Medium-horizon thesis (20d) gets 5d and 20d reviews."""
        thesis = _make_thesis(db_session, horizon_days=20)
        horizons = create_review_schedule(thesis, db_session)

        assert horizons == [5, 20]

        reviews = list(
            db_session.scalars(
                select(ResearchThesisReview).where(ResearchThesisReview.thesis_id == thesis.id)
            ).all()
        )
        assert len(reviews) == 2
        horizon_days_list = sorted(r.review_horizon_days for r in reviews)
        assert horizon_days_list == [5, 20]

    def test_create_review_schedule_long_horizon(self, db_session) -> None:
        """Long-horizon thesis (60d) gets 5d, 20d, and 60d reviews."""
        thesis = _make_thesis(db_session, horizon_days=60)
        horizons = create_review_schedule(thesis, db_session)

        assert horizons == [5, 20, 60]

        reviews = list(
            db_session.scalars(
                select(ResearchThesisReview).where(ResearchThesisReview.thesis_id == thesis.id)
            ).all()
        )
        assert len(reviews) == 3
        horizon_days_list = sorted(r.review_horizon_days for r in reviews)
        assert horizon_days_list == [5, 20, 60]

    def test_create_review_schedule_idempotent(self, db_session) -> None:
        """Calling create_review_schedule twice should not create duplicates."""
        thesis = _make_thesis(db_session, horizon_days=20)
        create_review_schedule(thesis, db_session)
        create_review_schedule(thesis, db_session)  # second call

        reviews = list(
            db_session.scalars(
                select(ResearchThesisReview).where(ResearchThesisReview.thesis_id == thesis.id)
            ).all()
        )
        assert len(reviews) == 2  # still 5d and 20d

    def test_review_scheduled_date_from_thesis(self, db_session) -> None:
        """Review scheduled_date should be calculated from thesis created_at."""
        thesis = _make_thesis(db_session, horizon_days=20)
        # Manually set created_at to a known date
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        create_review_schedule(thesis, db_session)

        reviews = list(
            db_session.scalars(
                select(ResearchThesisReview).where(ResearchThesisReview.thesis_id == thesis.id)
            ).all()
        )
        for r in reviews:
            if r.review_horizon_days == 20:
                assert r.scheduled_review_date == date(2026, 5, 21)  # May 1 + 20d
            elif r.review_horizon_days == 5:
                assert r.scheduled_review_date == date(2026, 5, 6)  # May 1 + 5d


# =============================================================================
# run_thesis_review
# =============================================================================


class TestRunThesisReview:
    """Test run_thesis_review function."""

    def test_run_review_insufficient_data(self, db_session) -> None:
        """Should return inconclusive when price data is missing."""
        thesis = _make_thesis(db_session, subject_type="stock", subject_id="NO_DATA")
        review = _make_review(db_session, thesis)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "inconclusive"
        assert "DailyBar data missing" in result.review_note

    def test_run_review_stock_hit(self, db_session) -> None:
        """Positive thesis should hit when stock price rises."""
        stock_code = "300308"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 20), close=110.0)

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up", horizon_days=20)
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "hit"
        assert result.realized_return is not None
        assert result.realized_return > 0

    def test_run_review_stock_miss(self, db_session) -> None:
        """Positive thesis should miss when stock price falls."""
        stock_code = "688235"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 20), close=85.0)

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up", horizon_days=20)
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "missed"
        assert result.realized_return is not None
        assert result.realized_return < 0

    def test_run_review_stock_inconclusive_neutral(self, db_session) -> None:
        """Thesis should be inconclusive when price change is within neutral range."""
        stock_code = "000001"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 20), close=101.0)  # +1%, within neutral

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up", horizon_days=20)
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "inconclusive"
        assert result.realized_return is not None

    def test_run_review_stock_invalidated(self, db_session) -> None:
        """Thesis should be invalidated when direction strongly contradicted."""
        stock_code = "300308"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 20), close=50.0)  # -50%, invalidates

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up", horizon_days=20)
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "invalidated"
        assert result.realized_return is not None
        assert result.realized_return < -0.20

    def test_run_review_invalidation_conditions(self, db_session) -> None:
        """Explicit invalidation conditions in JSON should be checked."""
        stock_code = "300308"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 20), close=90.0)

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up", horizon_days=20)
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        thesis.invalidation_conditions_json = json.dumps(
            [{"type": "return_below", "value": -0.05}]
        )
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "invalidated"
        assert "return_below" in result.review_note

    def test_run_review_industry_hit(self, db_session) -> None:
        """Industry thesis should hit when heat increases."""
        ind = _make_industry(db_session, industry_id=1, name="AI算力")
        _make_industry_heat(db_session, industry_id=1, trade_date=date(2026, 5, 1), heat_score=70.0)
        _make_industry_heat(db_session, industry_id=1, trade_date=date(2026, 5, 20), heat_score=78.0)

        thesis = _make_thesis(db_session, subject_type="industry", subject_id="1", direction="up")
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "hit"
        assert "Heat" in result.review_note

    def test_run_review_industry_miss(self, db_session) -> None:
        """Industry thesis should miss when heat declines significantly."""
        ind = _make_industry(db_session, industry_id=2, name="机器人")
        _make_industry_heat(db_session, industry_id=2, trade_date=date(2026, 5, 1), heat_score=70.0)
        _make_industry_heat(db_session, industry_id=2, trade_date=date(2026, 5, 20), heat_score=55.0)

        thesis = _make_thesis(db_session, subject_type="industry", subject_id="2", direction="up")
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "missed"

    def test_run_review_industry_no_data(self, db_session) -> None:
        """Industry thesis without heat data should be inconclusive."""
        ind = _make_industry(db_session, industry_id=99, name="未知行业")

        thesis = _make_thesis(db_session, subject_type="industry", subject_id="99", direction="up")
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "inconclusive"

    def test_run_review_invalid_subject_type(self, db_session) -> None:
        """Unknown subject type should return inconclusive."""
        thesis = _make_thesis(db_session, subject_type="theme", subject_id="T001")
        review = _make_review(db_session, thesis)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "inconclusive"
        assert "not yet implemented" in result.review_note

    def test_run_review_returns_result_type(self, db_session) -> None:
        """run_thesis_review should return a ThesisReviewResult dataclass."""
        thesis = _make_thesis(db_session, subject_type="theme", subject_id="T001")
        review = _make_review(db_session, thesis)

        result = run_thesis_review(thesis, review, db_session)

        assert isinstance(result, ThesisReviewResult)
        assert result.thesis_id == thesis.id
        assert result.review_horizon_days == review.review_horizon_days
        assert isinstance(result.realized_metrics_json, dict)


# =============================================================================
# run_due_reviews
# =============================================================================


class TestRunDueReviews:
    """Test run_due_reviews batch function."""

    def test_run_due_reviews_no_pending(self, db_session) -> None:
        """No pending reviews should return empty list."""
        results = run_due_reviews(as_of_date=date(2026, 5, 20), db_session=db_session)
        assert results == []

    def test_run_due_reviews_finds_and_runs(self, db_session) -> None:
        """Should find and run all due reviews."""
        stock_code = "300308"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 4, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 15), close=110.0)

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up", horizon_days=20)
        thesis.created_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
        db_session.flush()

        # Create a review that is due
        review = ResearchThesisReview(
            thesis_id=thesis.id,
            review_horizon_days=20,
            scheduled_review_date=date(2026, 5, 15),
            review_status="pending",
        )
        db_session.add(review)
        db_session.flush()

        results = run_due_reviews(as_of_date=date(2026, 5, 20), db_session=db_session)

        assert len(results) >= 1
        # The review object was modified in-memory by run_due_reviews
        assert review.review_status == results[0].review_status
        assert review.review_status != "pending"
        assert review.actual_review_date == date(2026, 5, 20)

    def test_run_due_reviews_skips_future(self, db_session) -> None:
        """Reviews with future scheduled dates should not run."""
        thesis = _make_thesis(db_session, subject_id="300308")
        db_session.flush()

        review = ResearchThesisReview(
            thesis_id=thesis.id,
            review_horizon_days=20,
            scheduled_review_date=date(2027, 1, 1),  # far future
            review_status="pending",
        )
        db_session.add(review)
        db_session.flush()

        results = run_due_reviews(as_of_date=date(2026, 5, 20), db_session=db_session)

        assert len(results) == 0
        db_session.refresh(review)
        assert review.review_status == "pending"  # unchanged

    def test_run_due_reviews_missing_thesis(self, db_session) -> None:
        """Review with missing parent thesis should be marked inconclusive."""
        # Create a review directly without a thesis (simulate orphan)
        review = ResearchThesisReview(
            thesis_id=99999,  # non-existent
            review_horizon_days=20,
            scheduled_review_date=date(2026, 5, 15),
            review_status="pending",
        )
        db_session.add(review)
        db_session.flush()

        results = run_due_reviews(as_of_date=date(2026, 5, 20), db_session=db_session)

        assert len(results) >= 1
        assert results[0].review_status == "inconclusive"
        assert "not found" in results[0].review_note

    def test_run_due_reviews_updates_thesis_status(self, db_session) -> None:
        """Thesis status should update when review completes."""
        stock_code = "300308"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 15), close=50.0)

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up", horizon_days=20)
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = ResearchThesisReview(
            thesis_id=thesis.id,
            review_horizon_days=20,
            scheduled_review_date=date(2026, 5, 15),
            review_status="pending",
        )
        db_session.add(review)
        db_session.flush()

        run_due_reviews(as_of_date=date(2026, 5, 20), db_session=db_session)

        # Thesis status was updated in-memory by run_due_reviews
        assert thesis.status in ("invalidated", "missed")


# =============================================================================
# Conservative review principle
# =============================================================================


class TestConservativeReview:
    """Review engine should prefer inconclusive over wrong calls."""

    def test_review_does_not_fabricate_hit(self, db_session) -> None:
        """Should never return hit when data is truly insufficient."""
        thesis = _make_thesis(db_session, subject_type="stock", subject_id="MISSING")
        review = _make_review(db_session, thesis)

        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status != "hit"

    def test_review_conservative_on_minimal_data(self, db_session) -> None:
        """Even with partial data, if confidence is low, prefer inconclusive."""
        stock_code = "LOW_DATA"
        _make_stock(db_session, stock_code)
        # Only anchor bar, no review bar
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)

        thesis = _make_thesis(db_session, subject_id=stock_code, direction="up")
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        review = _make_review(db_session, thesis)
        review.scheduled_review_date = date(2026, 5, 20)

        result = run_thesis_review(thesis, review, db_session)

        # Should be inconclusive due to missing data
        assert result.review_status == "inconclusive"
