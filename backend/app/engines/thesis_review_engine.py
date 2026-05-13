"""Thesis review engine: schedule and execute post-hoc thesis verification.

This module provides:
- create_review_schedule: auto-create pending review rows when a thesis is saved.
- run_thesis_review: perform a single review (stock / industry / market / theme).
- run_due_reviews: batch-process all reviews whose scheduled date has arrived.

Review logic is intentionally conservative -- prefer inconclusive over a wrong
hit/miss call when data is insufficient.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyBar, IndustryHeat, ResearchThesis, ResearchThesisReview, TrendSignal


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThesisReviewResult:
    thesis_id: int
    review_horizon_days: int
    scheduled_review_date: date
    review_status: str  # hit / missed / invalidated / inconclusive
    realized_return: float | None
    benchmark_return: float | None
    realized_metrics_json: dict
    review_note: str
    evidence_update_json: dict


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def create_review_schedule(thesis: ResearchThesis, db_session: Session) -> list[int]:
    """Create pending reviews for *thesis* if they do not already exist.

    Always creates a review at ``thesis.horizon_days``.  Also creates 5d and
    20d reviews when the overall horizon is longer.  Returns the sorted list
    of horizon days that now have a pending review row.
    """
    horizons: set[int] = {thesis.horizon_days}
    if thesis.horizon_days > 5:
        horizons.add(5)
    if thesis.horizon_days > 20:
        horizons.add(20)

    sorted_horizons = sorted(horizons)

    for horizon in sorted_horizons:
        scheduled_date = _scheduled_review_date(thesis, horizon)
        existing = db_session.scalar(
            select(ResearchThesisReview).where(
                ResearchThesisReview.thesis_id == thesis.id,
                ResearchThesisReview.review_horizon_days == horizon,
            )
        )
        if existing is None:
            db_session.add(
                ResearchThesisReview(
                    thesis_id=thesis.id,
                    review_horizon_days=horizon,
                    scheduled_review_date=scheduled_date,
                    review_status="pending",
                )
            )

    return sorted_horizons


def _scheduled_review_date(thesis: ResearchThesis, horizon_days: int) -> date:
    """Calculate the calendar-date review deadline for *horizon_days*.

    The base anchor is thesis.created_at (or today if not available).
    """
    anchor = thesis.created_at.date() if thesis.created_at else date.today()
    return anchor + timedelta(days=horizon_days)


# ---------------------------------------------------------------------------
# Single thesis review
# ---------------------------------------------------------------------------


def run_thesis_review(
    thesis: ResearchThesis,
    review: ResearchThesisReview,
    db_session: Session,
) -> ThesisReviewResult:
    """Execute the review *review* against *thesis* and return the outcome.

    Dispatches to a subject-type-specific handler.  Subjects whose data model
    is not fully covered always return ``inconclusive``.
    """
    subject_type = str(thesis.subject_type or "").lower()

    if subject_type == "stock":
        return _review_stock_thesis(thesis, review, db_session)

    if subject_type == "industry":
        return _review_industry_thesis(thesis, review, db_session)

    return _review_unknown(thesis, review)


# ---------------------------------------------------------------------------
# Subject-type handlers
# ---------------------------------------------------------------------------


def _review_stock_thesis(
    thesis: ResearchThesis,
    review: ResearchThesisReview,
    db_session: Session,
) -> ThesisReviewResult:
    """Review a stock-level thesis using DailyBar prices."""
    stock_code = thesis.subject_id

    # Fetch anchor price (date of thesis creation)
    anchor_date = thesis.created_at.date() if thesis.created_at else date.today()
    anchor_bar = _closest_daily_bar(db_session, stock_code, anchor_date)
    # Fetch review price (scheduled review date)
    review_bar = _closest_daily_bar(db_session, stock_code, review.scheduled_review_date)

    result_builder = _ResultBuilder(thesis, review)

    if anchor_bar is None or review_bar is None:
        return result_builder.inconclusive("DailyBar data missing for stock thesis review.")

    anchor_close = float(anchor_bar.close or 0.0)
    review_close = float(review_bar.close or 0.0)
    if anchor_close <= 0 or review_close <= 0:
        return result_builder.inconclusive("Invalid price data (zero or negative close) for stock thesis review.")

    realized_return = (review_close - anchor_close) / anchor_close

    # Benchmark: average return of all stocks with DailyBar data over same period
    benchmark_return = _compute_benchmark_return(db_session, stock_code, anchor_close, review_bar, anchor_date, review.scheduled_review_date)

    # Check invalidation conditions
    invalidated, invalidation_note = _check_invalidation_conditions(thesis, realized_return)
    if invalidated:
        return result_builder.invalidated(
            note=invalidation_note,
            realized_return=round(realized_return, 6),
            benchmark_return=benchmark_return,
        )

    # Determine hit / missed / inconclusive based on direction
    status, note = _classify_outcome(
        direction=str(thesis.direction or "up"),
        realized_return=realized_return,
        horizon_days=review.review_horizon_days,
    )

    return result_builder.build(
        status=status,
        note=note,
        realized_return=round(realized_return, 6),
        benchmark_return=benchmark_return,
        realized_metrics={"stock_code": stock_code, "anchor_close": anchor_close, "review_close": review_close},
    )


def _review_industry_thesis(
    thesis: ResearchThesis,
    review: ResearchThesisReview,
    db_session: Session,
) -> ThesisReviewResult:
    """Review an industry-level thesis using IndustryHeat and TrendSignal."""
    result_builder = _ResultBuilder(thesis, review)

    # Attempt to parse industry id from subject_id
    industry_id = _parse_int(thesis.subject_id)
    if not industry_id:
        return result_builder.inconclusive("Industry subject_id is not a valid integer id.")

    anchor_date = thesis.created_at.date() if thesis.created_at else date.today()
    review_date = review.scheduled_review_date

    # Fetch heat at anchor and review dates
    anchor_heat = _closest_industry_heat(db_session, industry_id, anchor_date)
    review_heat = _closest_industry_heat(db_session, industry_id, review_date)

    metrics: dict[str, Any] = {}
    notes: list[str] = []

    if anchor_heat and review_heat:
        heat_change_7d = float(review_heat.heat_change_7d or 0.0)
        heat_change_30d = float(review_heat.heat_change_30d or 0.0)
        heat_change = float(review_heat.heat_score or 0.0) - float(anchor_heat.heat_score or 0.0)
        metrics["heat_change"] = round(heat_change, 4)
        metrics["heat_change_7d"] = round(heat_change_7d, 4)
        metrics["heat_change_30d"] = round(heat_change_30d, 4)
        notes.append(f"Heat score changed by {heat_change:+.4f}.")

        # Check trend signals for related stocks
        trend_signals = _recent_trend_signals(db_session, review_date, limit=10)
        avg_trend_score = 0.0
        if trend_signals:
            avg_trend_score = sum(float(s.trend_score or 0.0) for s in trend_signals) / len(trend_signals)
            metrics["avg_trend_score"] = round(avg_trend_score, 4)
            notes.append(f"Average trend score among top stocks: {avg_trend_score:.2f}.")

        # Simple direction check based on heat change
        direction = str(thesis.direction or "up").lower()
        if direction == "up" and heat_change > 2.0:
            status = "hit"
            notes.append("Industry heat increased, thesis direction confirmed.")
        elif direction == "down" and heat_change < -2.0:
            status = "hit"
            notes.append("Industry heat decreased, thesis direction confirmed.")
        elif direction == "up" and heat_change < -5.0:
            status = "missed"
            notes.append("Industry heat declined significantly despite up-thesis.")
        elif direction == "down" and heat_change > 5.0:
            status = "missed"
            notes.append("Industry heat increased significantly despite down-thesis.")
        else:
            status = "inconclusive"
            notes.append("Heat change insufficient to confirm or contradict thesis direction.")
    else:
        return result_builder.inconclusive("IndustryHeat data insufficient for review.")

    return result_builder.build(
        status=status,
        note="; ".join(notes),
        realized_return=None,
        benchmark_return=None,
        realized_metrics=metrics,
    )


def _review_unknown(
    thesis: ResearchThesis,
    review: ResearchThesisReview,
) -> ThesisReviewResult:
    """Fallback for unsupported subject types -- always inconclusive."""
    return _ResultBuilder(thesis, review).inconclusive(
        f"Subject type '{thesis.subject_type}' review is not yet implemented; "
        "insufficient data for a conclusive result."
    )


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------


def run_due_reviews(as_of_date: date, db_session: Session) -> list[ThesisReviewResult]:
    """Find and execute all pending reviews whose scheduled date has arrived.

    Updates both the ``ResearchThesisReview`` rows and the parent
    ``ResearchThesis`` status accordingly.  Returns the list of results.
    """
    pending_reviews = list(
        db_session.scalars(
            select(ResearchThesisReview)
            .where(
                ResearchThesisReview.review_status == "pending",
                ResearchThesisReview.scheduled_review_date <= as_of_date,
            )
            .order_by(ResearchThesisReview.scheduled_review_date)
        ).all()
    )

    thesis_ids = {r.thesis_id for r in pending_reviews}
    thesis_map: dict[int, ResearchThesis] = {}
    if thesis_ids:
        rows = db_session.scalars(
            select(ResearchThesis).where(ResearchThesis.id.in_(thesis_ids))
        ).all()
        thesis_map = {t.id: t for t in rows}

    results: list[ThesisReviewResult] = []
    now_utc = datetime.now(timezone.utc)

    for review in pending_reviews:
        thesis = thesis_map.get(review.thesis_id)
        if thesis is None:
            review.review_status = "inconclusive"
            review.actual_review_date = as_of_date
            review.review_note = "Parent thesis not found."
            results.append(
                ThesisReviewResult(
                    thesis_id=review.thesis_id,
                    review_horizon_days=review.review_horizon_days,
                    scheduled_review_date=review.scheduled_review_date,
                    review_status="inconclusive",
                    realized_return=None,
                    benchmark_return=None,
                    realized_metrics_json={},
                    review_note="Parent thesis not found.",
                    evidence_update_json={},
                )
            )
            continue

        try:
            result = run_thesis_review(thesis, review, db_session)
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

        # Persist the review outcome
        review.review_status = result.review_status
        review.actual_review_date = as_of_date
        review.realized_return = result.realized_return
        review.benchmark_return = result.benchmark_return
        review.realized_metrics_json = json.dumps(result.realized_metrics_json, ensure_ascii=False)
        review.review_note = result.review_note
        review.evidence_update_json = json.dumps(result.evidence_update_json, ensure_ascii=False)
        review.created_at = now_utc

        # Update thesis status based on review outcome
        _update_thesis_status(thesis, result.review_status, db_session)

        results.append(result)

    return results


def _update_thesis_status(
    thesis: ResearchThesis,
    review_status: str,
    db_session: Session,
) -> None:
    """Adjust thesis.status after a review completes."""
    if review_status == "invalidated":
        thesis.status = "invalidated"
    elif review_status == "missed":
        # Only downgrade if not already a terminal status
        if thesis.status not in {"invalidated", "completed"}:
            thesis.status = "missed"
    elif review_status == "hit":
        if thesis.status == "active":
            thesis.status = "validated"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _closest_daily_bar(
    db_session: Session,
    stock_code: str,
    target_date: date,
) -> Any | None:
    """Return the DailyBar closest to *target_date* (looking backward up to 10 days)."""
    for offset in range(11):
        candidate = target_date - timedelta(days=offset)
        bar = db_session.scalar(
            select(DailyBar)
            .where(
                DailyBar.stock_code == stock_code,
                DailyBar.trade_date == candidate,
            )
            .order_by(DailyBar.trade_date.desc())
            .limit(1)
        )
        if bar is not None:
            return bar
    # Try looking forward (data date may be slightly after candidate)
    for offset in range(1, 6):
        candidate = target_date + timedelta(days=offset)
        bar = db_session.scalar(
            select(DailyBar)
            .where(
                DailyBar.stock_code == stock_code,
                DailyBar.trade_date == candidate,
            )
            .order_by(DailyBar.trade_date.desc())
            .limit(1)
        )
        if bar is not None:
            return bar
    return None


def _compute_benchmark_return(
    db_session: Session,
    stock_code: str,
    anchor_close: float,
    review_bar: Any,
    anchor_date: date,
    review_date: date,
) -> float | None:
    """Estimate a market/industry benchmark return for comparison.

    Uses the industry average return (all stocks that have DailyBar data at
    both anchor and review dates).  Returns ``None`` if not enough peers are
    available.
    """
    try:
        # Identify the industry of the stock
        from app.db.models import Stock

        stock = db_session.scalar(select(Stock).where(Stock.code == stock_code))
        if stock is None or not stock.industry_level1:
            return None

        industry = str(stock.industry_level1)
        peers = list(
            db_session.scalars(
                select(Stock.code).where(
                    Stock.industry_level1 == industry,
                    Stock.code != stock_code,
                    Stock.is_active == True,  # noqa: E712
                )
                .limit(30)
            ).all()
        )
        if not peers:
            return None

        returns: list[float] = []
        for peer_code in peers:
            anchor = _closest_daily_bar(db_session, peer_code, anchor_date)
            review = _closest_daily_bar(db_session, peer_code, review_date)
            if anchor is None or review is None:
                continue
            a_close = float(anchor.close or 0.0)
            r_close = float(review.close or 0.0)
            if a_close > 0 and r_close > 0:
                returns.append((r_close - a_close) / a_close)
        if returns:
            return round(sum(returns) / len(returns), 6)
    except Exception:
        pass
    return None


def _closest_industry_heat(
    db_session: Session,
    industry_id: int,
    target_date: date,
) -> Any | None:
    """Return the IndustryHeat row closest to *target_date*."""
    for offset in range(11):
        candidate = target_date - timedelta(days=offset)
        heat = db_session.scalar(
            select(IndustryHeat).where(
                IndustryHeat.industry_id == industry_id,
                IndustryHeat.trade_date == candidate,
            )
        )
        if heat is not None:
            return heat
    return None


def _recent_trend_signals(
    db_session: Session,
    as_of_date: date,
    limit: int = 10,
) -> list[Any]:
    """Return the most recent TrendSignal rows (best trend scores) as of *as_of_date*."""
    return list(
        db_session.scalars(
            select(TrendSignal)
            .where(TrendSignal.trade_date <= as_of_date)
            .order_by(TrendSignal.trade_date.desc(), TrendSignal.trend_score.desc())
            .limit(limit)
        ).all()
    )


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _check_invalidation_conditions(
    thesis: ResearchThesis,
    realized_return: float,
) -> tuple[bool, str]:
    """Check if any invalidation condition is triggered by *realized_return*.

    Supports simple conditions encoded as dicts with ``type`` and ``value``,
    as well as a basic default: if return is worse than -20% for an "up"
    thesis (or > +20% for a "down" thesis) and no other conditions override,
    the thesis is considered potentially invalidated.
    """
    raw = thesis.invalidation_conditions_json
    if not raw:
        return False, ""
    try:
        conditions = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return False, ""

    if not isinstance(conditions, list):
        conditions = [conditions]

    direction = str(thesis.direction or "up").lower()

    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        cond_type = str(cond.get("type", "")).lower()
        cond_value = _number(cond.get("value"))

        if cond_type == "return_below" and cond_value is not None:
            if realized_return < cond_value:
                return True, f"Invalidation condition 'return_below {cond_value}' triggered (realized={realized_return:.4f})."

        if cond_type == "return_above" and cond_value is not None:
            if realized_return > cond_value:
                return True, f"Invalidation condition 'return_above {cond_value}' triggered (realized={realized_return:.4f})."

    # Default fallback: large counter-directional move
    if direction == "up" and realized_return < -0.20:
        return True, f"Default invalidation: stock declined {realized_return:.1%} against up-thesis."
    if direction == "down" and realized_return > 0.25:
        return True, f"Default invalidation: stock rose {realized_return:.1%} against down-thesis."

    return False, ""


def _classify_outcome(
    direction: str,
    realized_return: float,
    horizon_days: int,
) -> tuple[str, str]:
    """Classify a review outcome given *direction* and *realized_return*.

    Thresholds scale with sqrt(horizon_days / 5) so that short-horizon reviews
    require smaller moves while long-horizon reviews allow more room.
    Returns ``(status, note)``.
    """
    scale = math.sqrt(max(horizon_days, 5) / 5.0)
    hit_threshold = 0.02 * scale  # min positive move to call "hit"
    miss_threshold = 0.05 * scale  # min counter move to call "missed"

    direction = direction.lower()

    if direction == "up":
        if realized_return >= hit_threshold:
            return "hit", f"Realized return {realized_return:+.4f} aligns with up-thesis."
        if realized_return <= -miss_threshold:
            return "missed", f"Realized return {realized_return:+.4f} contradicts up-thesis."
        return "inconclusive", f"Realized return {realized_return:+.4f} within neutral range (hit≥{hit_threshold:.4f}, miss≤{-miss_threshold:.4f})."

    if direction == "down":
        if realized_return <= -hit_threshold:
            return "hit", f"Realized return {realized_return:+.4f} aligns with down-thesis."
        if realized_return >= miss_threshold:
            return "missed", f"Realized return {realized_return:+.4f} contradicts down-thesis."
        return "inconclusive", f"Realized return {realized_return:+.4f} within neutral range."

    return "inconclusive", f"Unrecognized direction '{direction}'; cannot classify."


# ---------------------------------------------------------------------------
# Result builder helper
# ---------------------------------------------------------------------------


class _ResultBuilder:
    """Fluent helper for building ``ThesisReviewResult`` instances."""

    def __init__(self, thesis: ResearchThesis, review: ResearchThesisReview) -> None:
        self._thesis = thesis
        self._review = review

    def inconclusive(self, note: str) -> ThesisReviewResult:
        return self.build(
            status="inconclusive",
            note=note,
            realized_return=None,
            benchmark_return=None,
            realized_metrics={},
        )

    def invalidated(
        self,
        note: str,
        realized_return: float | None = None,
        benchmark_return: float | None = None,
    ) -> ThesisReviewResult:
        return self.build(
            status="invalidated",
            note=note,
            realized_return=realized_return,
            benchmark_return=benchmark_return,
            realized_metrics={},
        )

    def build(
        self,
        status: str,
        note: str,
        realized_return: float | None,
        benchmark_return: float | None,
        realized_metrics: dict[str, Any] | None = None,
    ) -> ThesisReviewResult:
        return ThesisReviewResult(
            thesis_id=self._thesis.id,
            review_horizon_days=self._review.review_horizon_days,
            scheduled_review_date=self._review.scheduled_review_date,
            review_status=status,
            realized_return=realized_return,
            benchmark_return=benchmark_return,
            realized_metrics_json=realized_metrics or {},
            review_note=note,
            evidence_update_json={},
        )


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
