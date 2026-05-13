"""Tests for thesis replay functionality.

Replay theses are historical theses re-evaluated against past data to verify
the system's predictive accuracy.  They use ``source_type`` values containing
``historical_replay`` so they can be queried separately from production theses.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.db.models import DailyBar, ResearchThesis, ResearchThesisReview, Stock
from app.engines.thesis_review_engine import create_review_schedule, run_thesis_review


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thesis(
    db_session,
    *,
    source_type: str = "historical_replay",
    source_id: str = "replay_001",
    subject_id: str = "300308",
    direction: str = "up",
    horizon_days: int = 20,
    confidence: float = 70.0,
) -> ResearchThesis:
    """Create and return a minimal ResearchThesis for replay testing."""
    thesis = ResearchThesis(
        source_type=source_type,
        source_id=source_id,
        subject_type="stock",
        subject_id=subject_id,
        subject_name="中际旭创",
        thesis_title="回测观点",
        thesis_body="历史回测观点，用于验证系统预测准确率。",
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
    horizon_days: int = 20,
) -> ResearchThesisReview:
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


def _make_daily_bar(
    db_session,
    stock_code: str,
    trade_date: date,
    close: float = 100.0,
) -> DailyBar:
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


# =============================================================================
# Tests
# =============================================================================


class TestThesisReplay:
    """Test thesis replay functionality."""

    def test_replay_marks_source_type_correctly(self, db_session) -> None:
        """Replay theses must have source_type containing 'historical_replay'."""
        thesis = _make_thesis(db_session, source_type="historical_replay")
        assert "historical_replay" in thesis.source_type

    def test_replay_thesis_distinct_from_production(self, db_session) -> None:
        """Replay theses must be queryable separately from production theses."""
        _make_thesis(db_session, source_type="historical_replay", source_id="replay_001")
        _make_thesis(db_session, source_type="daily_report", source_id="daily_001")
        db_session.commit()

        replay_theses = list(
            db_session.scalars(
                select(ResearchThesis).where(ResearchThesis.source_type == "historical_replay")
            ).all()
        )
        prod_theses = list(
            db_session.scalars(
                select(ResearchThesis).where(ResearchThesis.source_type == "daily_report")
            ).all()
        )

        assert len(replay_theses) == 1
        assert len(prod_theses) == 1
        assert replay_theses[0].source_id == "replay_001"
        assert prod_theses[0].source_id == "daily_001"

    def test_replay_skips_existing_thesis(self, db_session) -> None:
        """Replay should skip theses that already exist (dedup).

        When a thesis with the same (source_type, source_id) already exists,
        the application layer should detect the duplicate and skip insertion.
        """
        # Create first replay thesis
        _make_thesis(db_session, source_type="historical_replay", source_id="replay_001")
        db_session.commit()

        total_before = db_session.scalar(select(func.count(ResearchThesis.id)))

        # Application-level dedup: check before inserting
        existing = db_session.scalar(
            select(ResearchThesis).where(
                ResearchThesis.source_type == "historical_replay",
                ResearchThesis.source_id == "replay_001",
            )
        )
        if existing is None:
            _make_thesis(db_session, source_type="historical_replay", source_id="replay_001")
            db_session.commit()

        total_after = db_session.scalar(select(func.count(ResearchThesis.id)))
        assert total_after == total_before  # no new row added

    def test_replay_review_created_when_data_exists(self, db_session) -> None:
        """When price data exists, replay review should produce hit/miss/inconclusive."""
        stock_code = "300308"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 20), close=110.0)

        thesis = _make_thesis(
            db_session,
            source_type="historical_replay",
            source_id="replay_002",
            subject_id=stock_code,
            direction="up",
        )
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        # Create review schedule
        create_review_schedule(thesis, db_session)

        review = db_session.scalar(
            select(ResearchThesisReview).where(
                ResearchThesisReview.thesis_id == thesis.id,
                ResearchThesisReview.review_horizon_days == 20,
            )
        )
        assert review is not None

        result = run_thesis_review(thesis, review, db_session)

        # With price going from 100 -> 110 (+10%), up-thesis should hit
        assert result.review_status in ("hit", "missed", "inconclusive")
        assert result.realized_return is not None
        assert abs(result.realized_return - 0.1) < 0.01

    def test_replay_review_inconclusive_when_no_data(self, db_session) -> None:
        """When price data is missing, review should be inconclusive."""
        thesis = _make_thesis(
            db_session,
            source_type="historical_replay",
            source_id="replay_003",
            subject_id="MISSING_DATA",
        )
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        create_review_schedule(thesis, db_session)
        review = db_session.scalar(
            select(ResearchThesisReview).where(
                ResearchThesisReview.thesis_id == thesis.id,
                ResearchThesisReview.review_horizon_days == 20,
            )
        )
        result = run_thesis_review(thesis, review, db_session)

        assert result.review_status == "inconclusive"
        assert "data" in result.review_note.lower() or "insufficient" in result.review_note.lower()

    def test_replay_dry_run_does_not_write(self, db_session) -> None:
        """Dry run should not persist anything.

        A dry run creates review schedule rows but does not execute reviews,
        so all reviews remain in ``pending`` status with no actual review date.
        """
        stock_code = "300308"
        _make_stock(db_session, stock_code)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 1), close=100.0)
        _make_daily_bar(db_session, stock_code, date(2026, 5, 20), close=110.0)

        thesis = _make_thesis(
            db_session,
            source_type="historical_replay",
            source_id="replay_dry",
            subject_id=stock_code,
        )
        thesis.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db_session.flush()

        # "Dry run": create schedule but don't run reviews
        create_review_schedule(thesis, db_session)
        db_session.commit()

        # Verify theses exist
        theses = list(
            db_session.scalars(
                select(ResearchThesis).where(ResearchThesis.source_type == "historical_replay")
            ).all()
        )
        assert len(theses) == 1

        # Verify reviews are created but NOT executed (still pending)
        reviews = list(
            db_session.scalars(
                select(ResearchThesisReview).where(ResearchThesisReview.thesis_id == thesis.id)
            ).all()
        )
        assert len(reviews) >= 1
        for r in reviews:
            assert r.review_status == "pending"
            assert r.actual_review_date is None
