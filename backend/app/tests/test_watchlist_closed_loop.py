"""Tests for watchlist closed loop integration (thesis -> watchlist)."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models import ResearchThesis, WatchlistItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thesis(
    db_session,
    *,
    subject_id: str = "300308",
    subject_name: str = "中际旭创",
    direction: str = "positive",
) -> ResearchThesis:
    """Create a minimal thesis for watchlist testing."""
    thesis = ResearchThesis(
        source_type="daily_report",
        source_id="1",
        subject_type="stock",
        subject_id=subject_id,
        subject_name=subject_name,
        thesis_title=f"{subject_name}趋势偏强测试",
        thesis_body=f"{subject_name}当前趋势偏强，持续关注进一步确认。",
        direction=direction,
        horizon_days=20,
        confidence=70.0,
        evidence_refs_json=json.dumps(
            [{"source": "stock_score", "code": subject_id, "final_score": 82.0}]
        ),
        key_metrics_json=json.dumps(
            [{"name": "综合评分", "value": 82.0}]
        ),
        invalidation_conditions_json=json.dumps(
            [f"{subject_name}股价跌破20日均线"]
        ),
        risk_flags_json=json.dumps(
            ["个股评分仅为研究线索，不构成投资建议"]
        ),
    )
    db_session.add(thesis)
    db_session.flush()
    return thesis


def _make_watchlist_item(
    db_session,
    thesis: ResearchThesis,
    *,
    user_id: str = "user_a",
    reason: str | None = None,
) -> WatchlistItem:
    """Create a watchlist item derived from a thesis."""
    item = WatchlistItem(
        stock_code=thesis.subject_id,
        subject_type=thesis.subject_type,
        subject_id=thesis.subject_id,
        subject_name=thesis.subject_name,
        source_thesis_id=thesis.id,
        user_id=user_id,
        reason=reason or f"根据研报观点关注{thesis.subject_name}",
        watch_metrics_json=thesis.key_metrics_json,
        invalidation_conditions_json=thesis.invalidation_conditions_json,
        note=thesis.thesis_body,
        status="观察",
        priority="B",
    )
    db_session.add(item)
    db_session.flush()
    return item


# =============================================================================
# Watchlist integration tests
# =============================================================================


class TestWatchlistClosedLoop:
    """Test watchlist closed-loop integration with theses."""

    def test_add_thesis_to_watchlist(self, db_session) -> None:
        """Should create watchlist item from thesis with relevant fields."""
        thesis = _make_thesis(db_session)
        item = _make_watchlist_item(db_session, thesis)

        assert item.id is not None
        assert item.stock_code == "300308"
        assert item.subject_type == "stock"
        assert item.subject_name == "中际旭创"
        assert item.source_thesis_id == thesis.id
        assert item.status == "观察"
        assert item.priority == "B"

    def test_watchlist_item_has_reason(self, db_session) -> None:
        """Watchlist item must have a reason (not empty)."""
        thesis = _make_thesis(db_session)
        item = _make_watchlist_item(db_session, thesis, reason="根据研报观点关注中际旭创，趋势偏强")

        assert item.reason is not None
        assert len(item.reason) > 0
        assert "趋势偏强" in item.reason or "关注" in item.reason

    def test_watchlist_item_has_invalidation(self, db_session) -> None:
        """Watchlist item should carry invalidation conditions from thesis."""
        thesis = _make_thesis(db_session)
        item = _make_watchlist_item(db_session, thesis)

        invalidation = json.loads(item.invalidation_conditions_json)
        assert len(invalidation) >= 1
        assert "跌破20日均线" in invalidation[0]

    def test_watchlist_metrics_from_thesis(self, db_session) -> None:
        """Watchlist item should carry watch_metrics from thesis."""
        thesis = _make_thesis(db_session)
        item = _make_watchlist_item(db_session, thesis)

        metrics = json.loads(item.watch_metrics_json)
        assert len(metrics) >= 1
        assert metrics[0]["name"] == "综合评分"
        assert metrics[0]["value"] == 82.0

    def test_user_isolation(self, db_session) -> None:
        """Different users should see different watchlists."""
        thesis = _make_thesis(db_session, subject_id="300308", subject_name="中际旭创")

        # Create items for two users referencing the same thesis
        item_a = _make_watchlist_item(db_session, thesis, user_id="user_a")
        item_b = _make_watchlist_item(db_session, thesis, user_id="user_b")

        # Query as user_a
        user_a_items = list(
            db_session.scalars(
                select(WatchlistItem).where(WatchlistItem.user_id == "user_a")
            ).all()
        )
        assert len(user_a_items) == 1
        assert user_a_items[0].id == item_a.id

        # Query as user_b
        user_b_items = list(
            db_session.scalars(
                select(WatchlistItem).where(WatchlistItem.user_id == "user_b")
            ).all()
        )
        assert len(user_b_items) == 1
        assert user_b_items[0].id == item_b.id

        # Users should not see each other's items
        user_a_ids = {i.id for i in user_a_items}
        user_b_ids = {i.id for i in user_b_items}
        assert user_a_ids.isdisjoint(user_b_ids)

    def test_user_isolation_multiple_items(self, db_session) -> None:
        """One user's watchlist should not include other user's items."""
        thesis_a = _make_thesis(db_session, subject_id="300308", subject_name="中际旭创")
        thesis_b = _make_thesis(db_session, subject_id="688235", subject_name="样本B")

        _make_watchlist_item(db_session, thesis_a, user_id="user_a")
        _make_watchlist_item(db_session, thesis_b, user_id="user_b")

        items_a = list(
            db_session.scalars(
                select(WatchlistItem).where(WatchlistItem.user_id == "user_a")
            ).all()
        )
        for item in items_a:
            assert item.user_id == "user_a"
            assert item.stock_code == "300308"

    def test_archive_item(self, db_session) -> None:
        """Should be able to archive a watchlist item."""
        thesis = _make_thesis(db_session)
        item = _make_watchlist_item(db_session, thesis)

        # Archive by setting status
        item.status = "已归档"
        db_session.commit()
        db_session.refresh(item)

        assert item.status == "已归档"

    def test_archive_does_not_delete(self, db_session) -> None:
        """Archived watchlist items should remain in DB."""
        thesis = _make_thesis(db_session)
        item = _make_watchlist_item(db_session, thesis)

        item_id = item.id
        item.status = "已归档"
        db_session.commit()

        # Should still be queryable
        archived = db_session.get(WatchlistItem, item_id)
        assert archived is not None
        assert archived.status == "已归档"

    def test_unique_constraint_subject_user(self, db_session) -> None:
        """Cannot have duplicate watchlist entries for same subject+user."""
        thesis = _make_thesis(db_session)

        _make_watchlist_item(db_session, thesis, user_id="user_a")

        # Second item for same user+subject should raise
        duplicate = WatchlistItem(
            stock_code="300308",
            subject_type="stock",
            subject_id="300308",
            user_id="user_a",
            reason="重复",
        )
        db_session.add(duplicate)
        with pytest.raises(Exception):
            db_session.commit()

    def test_no_buy_sell_language(self, db_session) -> None:
        """Watchlist should use observation language, not buy/sell."""
        thesis = _make_thesis(db_session)
        item = _make_watchlist_item(db_session, thesis)

        # Check all text fields for forbidden language
        text_fields = [
            str(item.reason or ""),
            str(item.note or ""),
            str(item.status or ""),
        ]
        combined = " ".join(text_fields)
        forbidden = ["买入", "卖出"]
        for term in forbidden:
            assert term not in combined, (
                f"Forbidden term '{term}' found in watchlist item fields"
            )

    def test_watchlist_default_status(self, db_session) -> None:
        """Watchlist item should have a default status."""
        item = WatchlistItem(
            stock_code="300308",
            subject_type="stock",
            subject_id="300308",
            user_id="user_a",
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)

        assert item.status == "观察"
        assert item.priority == "B"

    def test_watchlist_reason_default_null(self, db_session) -> None:
        """Watchlist reason can default to None (nullable)."""
        item = WatchlistItem(
            stock_code="688235",
            subject_type="stock",
            subject_id="688235",
            user_id="user_c",
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)

        assert item.reason is None  # nullable


class TestWatchlistChangeEngine:
    """Test watchlist change detection engine."""

    def test_build_watchlist_changes_new(self, db_session) -> None:
        """build_watchlist_changes should detect new watch entries."""
        from app.engines.watchlist_change_engine import build_watchlist_changes

        class ScoreRow:
            def __init__(self, code: str, rating: str, score: float):
                self.stock_code = code
                self.rating = rating
                self.final_score = score

        scores = [
            ScoreRow("300308", "强观察", 85.0),
            ScoreRow("688235", "观察", 65.0),
        ]
        stocks_by_code = {
            "300308": type("s", (), {"name": "中际旭创", "industry_level1": "AI算力"})(),
            "688235": type("s", (), {"name": "样本B", "industry_level1": "半导体"})(),
        }

        # First snapshot (no previous)
        result = build_watchlist_changes(
            latest_date=date(2026, 5, 13),
            previous_date=None,
            latest_scores=scores,
            previous_scores=[],
            stocks_by_code=stocks_by_code,
        )

        assert result["summary"]["new_count"] == 2
        assert result["summary"]["latest_watch_count"] == 2

    def test_build_watchlist_changes_removed(self, db_session) -> None:
        """build_watchlist_changes should detect removed watch entries."""
        from app.engines.watchlist_change_engine import build_watchlist_changes

        class ScoreRow:
            def __init__(self, code: str, rating: str, score: float):
                self.stock_code = code
                self.rating = rating
                self.final_score = score

        latest = [ScoreRow("300308", "强观察", 82.0)]
        previous = [
            ScoreRow("300308", "强观察", 80.0),
            ScoreRow("688235", "观察", 60.0),
        ]
        stocks_by_code = {
            "300308": type("s", (), {"name": "中际旭创", "industry_level1": "AI算力"})(),
            "688235": type("s", (), {"name": "样本B", "industry_level1": "半导体"})(),
        }

        result = build_watchlist_changes(
            latest_date=date(2026, 5, 13),
            previous_date=date(2026, 5, 12),
            latest_scores=latest,
            previous_scores=previous,
            stocks_by_code=stocks_by_code,
        )

        assert result["summary"]["removed_count"] == 1
        removed_codes = [e["code"] for e in result["removed_entries"]]
        assert "688235" in removed_codes
