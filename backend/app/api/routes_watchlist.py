from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchThesis, Stock, StockScore, WatchlistItem
from app.db.session import get_session
from app.engines.watchlist_change_engine import WATCH_RATINGS, build_watchlist_changes

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Default user for backward-compatible endpoints
_DEFAULT_USER = "anonymous"


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class WatchlistCreate(BaseModel):
    stock_code: str
    note: str = ""
    status: str = "观察"


class WatchlistCreateFromThesis(BaseModel):
    thesis_id: int
    note: str = ""
    priority: str = "B"


class WatchlistUpdate(BaseModel):
    note: str | None = None
    status: str | None = None
    priority: str | None = None


# ---------------------------------------------------------------------------
# Helper: get current user from header (mirrors agent/api.py pattern)
# ---------------------------------------------------------------------------


def _current_user_id(x_alpha_user_id: str | None = Header(default=None)) -> str:
    return x_alpha_user_id or _DEFAULT_USER


# ---------------------------------------------------------------------------
# Helper: convert WatchlistItem to response dict
# ---------------------------------------------------------------------------


def _item_row(item: WatchlistItem, stock: Stock | None = None) -> dict[str, Any]:
    return {
        "id": item.id,
        "stock_code": item.stock_code,
        "note": item.note,
        "status": item.status,
        "user_id": item.user_id,
        "subject_type": item.subject_type,
        "subject_id": item.subject_id,
        "subject_name": item.subject_name,
        "source_thesis_id": item.source_thesis_id,
        "source_report_id": item.source_report_id,
        "reason": item.reason,
        "watch_metrics": _loads_json_list(item.watch_metrics_json),
        "invalidation_conditions": _loads_json_list(item.invalidation_conditions_json),
        "priority": item.priority,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        # Stock info (if applicable)
        "name": stock.name if stock else (item.subject_name if item.subject_name else None),
        "industry": stock.industry_level1 if stock else None,
        "market": stock.market if stock else None,
        "board": stock.board if stock else None,
    }


def _loads_json_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


# ---------------------------------------------------------------------------
# Existing endpoints (backward compatible)
# ---------------------------------------------------------------------------


@router.get("")
def list_watchlist(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.execute(select(WatchlistItem, Stock).join(Stock, Stock.code == WatchlistItem.stock_code)).all()
    return [
        {
            "stock_code": item.stock_code,
            "name": stock.name,
            "industry": stock.industry_level1,
            "note": item.note,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        for item, stock in rows
    ]


@router.get("/changes")
def watchlist_changes(session: Session = Depends(get_session)) -> dict[str, object]:
    score_dates = session.scalars(select(StockScore.trade_date).distinct().order_by(StockScore.trade_date.desc()).limit(2)).all()
    latest_date = score_dates[0] if score_dates else None
    previous_date = score_dates[1] if len(score_dates) > 1 else None
    latest_scores = session.scalars(select(StockScore).where(StockScore.trade_date == latest_date)).all() if latest_date else []
    previous_scores = session.scalars(select(StockScore).where(StockScore.trade_date == previous_date)).all() if previous_date else []
    score_codes = {score.stock_code for score in latest_scores} | {score.stock_code for score in previous_scores}
    stocks = session.scalars(select(Stock).where(Stock.code.in_(score_codes))).all() if score_codes else []
    stocks_by_code = {stock.code: stock for stock in stocks}
    return build_watchlist_changes(
        latest_date=latest_date,
        previous_date=previous_date,
        latest_scores=list(latest_scores),
        previous_scores=list(previous_scores),
        stocks_by_code=stocks_by_code,
    )


@router.get("/timeline")
def watchlist_timeline(
    limit: int = Query(default=20, ge=1, le=120),
    market: str | None = Query(default=None),
    board: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    stocks_query = select(Stock)
    if market and market.upper() != "ALL":
        stocks_query = stocks_query.where(Stock.market == market.upper())
    if board and board.lower() != "all":
        stocks_query = stocks_query.where(Stock.board == board.lower())

    stocks = session.scalars(stocks_query).all()
    stocks_by_code = {stock.code: stock for stock in stocks}
    scoped_codes = set(stocks_by_code)
    if not scoped_codes:
        return {
            "market": market.upper() if market else "ALL",
            "board": board.lower() if board else "all",
            "latest": None,
            "timeline": [],
        }

    score_dates = session.scalars(
        select(StockScore.trade_date)
        .where(StockScore.stock_code.in_(scoped_codes))
        .distinct()
        .order_by(StockScore.trade_date.desc())
        .limit(limit + 1)
    ).all()
    if not score_dates:
        return {
            "market": market.upper() if market else "ALL",
            "board": board.lower() if board else "all",
            "latest": None,
            "timeline": [],
        }

    scores_by_date: dict[object, list[StockScore]] = {}
    for trade_date in score_dates:
        scores_by_date[trade_date] = list(
            session.scalars(
                select(StockScore)
                .where(StockScore.trade_date == trade_date, StockScore.stock_code.in_(scoped_codes))
                .order_by(StockScore.final_score.desc())
            ).all()
        )

    timeline: list[dict[str, object]] = []
    for index, trade_date in enumerate(score_dates[:limit]):
        previous_date = score_dates[index + 1] if index + 1 < len(score_dates) else None
        latest_scores = scores_by_date.get(trade_date, [])
        previous_scores = scores_by_date.get(previous_date, []) if previous_date else []
        changes = build_watchlist_changes(
            latest_date=trade_date,
            previous_date=previous_date,
            latest_scores=latest_scores,
            previous_scores=previous_scores,
            stocks_by_code=stocks_by_code,
        )
        timeline.append(
            {
                "trade_date": trade_date.isoformat(),
                "previous_date": previous_date.isoformat() if previous_date else None,
                "summary": changes["summary"],
                "new_entries": changes["new_entries"],
                "removed_entries": changes["removed_entries"],
                "upgraded": changes["upgraded"],
                "downgraded": changes["downgraded"],
                "score_gainers": changes["score_gainers"],
                "score_losers": changes["score_losers"],
                "watchlist_top": _watchlist_top(latest_scores, stocks_by_code),
            }
        )

    return {
        "market": market.upper() if market else "ALL",
        "board": board.lower() if board else "all",
        "latest": timeline[0] if timeline else None,
        "timeline": timeline,
    }


@router.post("")
def add_watchlist(payload: WatchlistCreate, session: Session = Depends(get_session)) -> dict[str, object]:
    stock = session.scalar(select(Stock).where(Stock.code == payload.stock_code))
    if stock is None:
        raise HTTPException(status_code=404, detail="stock not found")
    item = session.scalar(select(WatchlistItem).where(WatchlistItem.stock_code == payload.stock_code))
    if item is None:
        item = WatchlistItem(
            stock_code=payload.stock_code,
            note=payload.note,
            status=payload.status,
            subject_type="stock",
            subject_id=payload.stock_code,
            subject_name=stock.name,
        )
        session.add(item)
    else:
        item.note = payload.note
        item.status = payload.status
    session.commit()
    return {"stock_code": payload.stock_code, "status": payload.status}


# ---------------------------------------------------------------------------
# New endpoints for thesis-linked observation pool
# ---------------------------------------------------------------------------


def add_thesis_to_watchlist(thesis_id: int, user_id: str | None, db: Session, priority: str = "B") -> WatchlistItem:
    """Create a WatchlistItem from a ResearchThesis.

    Returns the newly created (or existing, if already linked) item.
    """
    thesis = db.get(ResearchThesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")

    # Map subject_id to stock_code for stock-type theses
    stock_code = None
    if thesis.subject_type == "stock" and thesis.subject_id:
        stock_code = thesis.subject_id

    existing = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.source_thesis_id == thesis_id,
        )
    )
    if existing is not None:
        return existing

    item = WatchlistItem(
        stock_code=stock_code,
        user_id=user_id,
        subject_type=thesis.subject_type,
        subject_id=thesis.subject_id,
        subject_name=thesis.subject_name,
        source_thesis_id=thesis.id,
        reason=thesis.thesis_body,
        watch_metrics_json=thesis.key_metrics_json,
        invalidation_conditions_json=thesis.invalidation_conditions_json,
        status="active",
        note="",
        priority=priority,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/items")
def create_watchlist_item(
    payload: WatchlistCreateFromThesis,
    user_id: str = Depends(_current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a watchlist item from a thesis. Adds to the observation pool (观察池)."""
    item = add_thesis_to_watchlist(
        thesis_id=payload.thesis_id,
        user_id=user_id,
        db=session,
        priority=payload.priority,
    )
    if payload.note:
        item.note = payload.note
        session.commit()

    # Attach stock info if applicable
    stock = None
    if item.stock_code:
        stock = session.scalar(select(Stock).where(Stock.code == item.stock_code))

    return {
        "status": "ok",
        "message": "已添加到观察池",
        "item": _item_row(item, stock),
    }


@router.get("/items")
def list_watchlist_items(
    user_id: str | None = Query(default=None, description="Filter by user_id"),
    status: str | None = Query(default=None, description="Filter by status: active/archived/观察 etc."),
    priority: str | None = Query(default=None, description="Filter by priority: S/A/B"),
    subject_type: str | None = Query(default=None, description="Filter by subject_type: stock/industry/theme"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """List observation pool items with optional filters."""
    query = select(WatchlistItem).order_by(WatchlistItem.created_at.desc())

    if user_id:
        query = query.where(WatchlistItem.user_id == user_id)
    if status:
        query = query.where(WatchlistItem.status == status)
    if priority:
        query = query.where(WatchlistItem.priority == priority)
    if subject_type:
        query = query.where(WatchlistItem.subject_type == subject_type)

    items = session.scalars(query).all()

    # Bulk-load stock info
    stock_codes = {i.stock_code for i in items if i.stock_code}
    stocks = session.scalars(select(Stock).where(Stock.code.in_(stock_codes))).all() if stock_codes else []
    stocks_by_code = {s.code: s for s in stocks}

    # Bulk-load thesis summaries
    thesis_ids = {i.source_thesis_id for i in items if i.source_thesis_id}
    theses = (
        session.scalars(select(ResearchThesis).where(ResearchThesis.id.in_(thesis_ids))).all()
        if thesis_ids
        else []
    )
    theses_by_id = {t.id: t for t in theses}

    rows = []
    for item in items:
        row = _item_row(item, stocks_by_code.get(item.stock_code))
        thesis = theses_by_id.get(item.source_thesis_id) if item.source_thesis_id else None
        row["thesis_title"] = thesis.thesis_title if thesis else None
        row["thesis_direction"] = thesis.direction if thesis else None
        row["thesis_status"] = thesis.status if thesis else None
        rows.append(row)

    return {
        "total": len(rows),
        "rows": rows,
    }


@router.get("/items/{item_id}")
def get_watchlist_item(
    item_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Get a single observation pool item with full details."""
    item = session.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="观察池条目未找到")

    stock = None
    if item.stock_code:
        stock = session.scalar(select(Stock).where(Stock.code == item.stock_code))

    row = _item_row(item, stock)

    # Attach thesis summary
    if item.source_thesis_id:
        thesis = session.get(ResearchThesis, item.source_thesis_id)
        if thesis:
            row["thesis"] = {
                "id": thesis.id,
                "thesis_title": thesis.thesis_title,
                "thesis_body": thesis.thesis_body,
                "direction": thesis.direction,
                "confidence": thesis.confidence,
                "status": thesis.status,
                "key_metrics": _loads_json_list(thesis.key_metrics_json),
                "invalidation_conditions": _loads_json_list(thesis.invalidation_conditions_json),
                "created_at": thesis.created_at.isoformat() if thesis.created_at else None,
            }

    return {"item": row}


@router.patch("/items/{item_id}")
def update_watchlist_item(
    item_id: int,
    payload: WatchlistUpdate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update an observation pool item's priority, note, or status."""
    item = session.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="观察池条目未找到")

    if payload.note is not None:
        item.note = payload.note
    if payload.status is not None:
        item.status = payload.status
    if payload.priority is not None:
        item.priority = payload.priority

    session.commit()
    session.refresh(item)

    stock = None
    if item.stock_code:
        stock = session.scalar(select(Stock).where(Stock.code == item.stock_code))

    return {
        "status": "ok",
        "message": "观察池条目已更新",
        "item": _item_row(item, stock),
    }


@router.post("/items/{item_id}/archive")
def archive_watchlist_item(
    item_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Archive an observation pool item (set status to 'archived')."""
    item = session.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="观察池条目未找到")

    item.status = "archived"
    session.commit()
    session.refresh(item)

    return {
        "status": "ok",
        "message": "已归档至历史观察",
        "item": _item_row(item),
    }


@router.get("/summary")
def watchlist_summary(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Summary of the observation pool for the dashboard."""
    all_items = session.scalars(select(WatchlistItem)).all()

    # Active count by priority
    active = [i for i in all_items if i.status == "active"]
    by_priority = {"S": 0, "A": 0, "B": 0}
    for item in active:
        key = item.priority if item.priority in by_priority else "B"
        by_priority[key] += 1

    # Items with upcoming reviews (from thesis review schedule)
    upcoming_reviews = []
    for item in active:
        if item.source_thesis_id:
            from app.db.models import ResearchThesisReview

            pending_reviews = session.scalars(
                select(ResearchThesisReview)
                .where(
                    ResearchThesisReview.thesis_id == item.source_thesis_id,
                    ResearchThesisReview.review_status == "pending",
                )
                .order_by(ResearchThesisReview.scheduled_review_date.asc())
                .limit(1)
            ).all()
            for review in pending_reviews:
                upcoming_reviews.append(
                    {
                        "item_id": item.id,
                        "subject_name": item.subject_name,
                        "subject_type": item.subject_type,
                        "priority": item.priority,
                        "review_id": review.id,
                        "scheduled_review_date": review.scheduled_review_date.isoformat() if review.scheduled_review_date else None,
                        "review_horizon_days": review.review_horizon_days,
                    }
                )

    # Recently archived (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recently_archived = [
        _item_row(i)
        for i in all_items
        if i.status == "archived" and i.updated_at and i.updated_at >= thirty_days_ago
    ]

    return {
        "total_active": len(active),
        "total_archived": sum(1 for i in all_items if i.status == "archived"),
        "by_priority": by_priority,
        "upcoming_reviews": sorted(upcoming_reviews, key=lambda r: r["scheduled_review_date"] or "")[:20],
        "recently_archived": sorted(recently_archived, key=lambda r: r["updated_at"] or "", reverse=True)[:10],
    }


def _watchlist_top(scores: list[StockScore], stocks_by_code: dict[str, Stock], limit: int = 20) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for score in scores:
        if score.rating not in WATCH_RATINGS:
            continue
        stock = stocks_by_code.get(score.stock_code)
        rows.append(
            {
                "code": score.stock_code,
                "name": stock.name if stock else score.stock_code,
                "market": stock.market if stock else "",
                "board": stock.board if stock else "",
                "industry": stock.industry_level1 if stock else "",
                "rating": score.rating,
                "final_score": round(score.final_score, 2),
                "industry_score": round(score.industry_score, 2),
                "company_score": round(score.company_score, 2),
                "trend_score": round(score.trend_score, 2),
                "catalyst_score": round(score.catalyst_score, 2),
                "risk_penalty": round(score.risk_penalty, 2),
            }
        )
    return rows[:limit]
