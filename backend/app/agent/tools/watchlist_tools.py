from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchThesis, Stock, WatchlistItem


def add_to_watchlist(thesis_id: int, user_id: str | None = None, priority: str = "B", db: Session | None = None) -> dict[str, Any]:
    """Add a thesis to the observation pool (watchlist/观察池).

    Loads the thesis and creates a WatchlistItem with reason,
    watch_metrics, and invalidation_conditions copied from the thesis.

    Args:
        thesis_id: ID of the ResearchThesis to add.
        user_id: Optional user identifier for user isolation.
        priority: Priority level (S/A/B), defaults to B.
        db: SQLAlchemy session. If None, creates a new one.

    Returns:
        dict with status and the created watchlist item data, or error.
    """
    from app.db.session import SessionLocal

    own_session = db is None
    session: Session = db or SessionLocal()

    try:
        thesis = session.get(ResearchThesis, thesis_id)
        if thesis is None:
            return {"status": "error", "message": f"Thesis #{thesis_id} not found"}

        # Check if already in watchlist
        existing = session.scalar(
            select(WatchlistItem).where(WatchlistItem.source_thesis_id == thesis_id)
        )
        if existing is not None:
            return {
                "status": "ok",
                "message": "该研报论点已在观察池中",
                "item": _item_row(existing, session),
            }

        # Map subject_id to stock_code for stock-type theses
        stock_code = None
        if thesis.subject_type == "stock" and thesis.subject_id:
            stock_code = thesis.subject_id

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
        session.add(item)
        session.commit()
        session.refresh(item)

        return {
            "status": "ok",
            "message": f"已添加 {thesis.subject_name} 至观察池（优先级: {priority}）",
            "item": _item_row(item, session),
        }
    except Exception as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        if own_session:
            session.close()


def _item_row(item: WatchlistItem, session: Session) -> dict[str, Any]:
    stock = None
    if item.stock_code:
        stock = session.scalar(select(Stock).where(Stock.code == item.stock_code))

    import json

    def _loads_list(raw: str) -> list[Any]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    return {
        "id": item.id,
        "stock_code": item.stock_code,
        "subject_type": item.subject_type,
        "subject_id": item.subject_id,
        "subject_name": item.subject_name,
        "source_thesis_id": item.source_thesis_id,
        "status": item.status,
        "priority": item.priority,
        "reason": item.reason,
        "watch_metrics": _loads_list(item.watch_metrics_json),
        "invalidation_conditions": _loads_list(item.invalidation_conditions_json),
        "name": stock.name if stock else item.subject_name,
        "industry": stock.industry_level1 if stock else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
