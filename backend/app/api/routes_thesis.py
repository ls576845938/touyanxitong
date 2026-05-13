from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchThesis, ResearchThesisReview
from app.db.session import get_session

router = APIRouter(prefix="/api/research", tags=["research-thesis"])


@router.get("/theses")
def thesis_list(
    status: str | None = Query(default=None, description="Filter by status: active/hit/missed/invalidated/inconclusive/archived"),
    subject_type: str | None = Query(default=None, description="Filter by subject type: stock/industry/market/theme"),
    source_type: str | None = Query(default=None, description="Filter by source type: daily_report/agent_run/manual"),
    direction: str | None = Query(default=None, description="Filter by direction: positive/negative/neutral/mixed"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    query = select(ResearchThesis).order_by(ResearchThesis.created_at.desc())

    if status:
        query = query.where(ResearchThesis.status == status)
    if subject_type:
        query = query.where(ResearchThesis.subject_type == subject_type)
    if source_type:
        query = query.where(ResearchThesis.source_type == source_type)
    if direction:
        query = query.where(ResearchThesis.direction == direction)

    total = session.scalar(select(ResearchThesis.id).where(query.exists()).limit(1))
    total_count = 1 if total else 0

    rows = session.scalars(query.offset(offset).limit(limit)).all()
    # Get actual total count
    count_query = select(ResearchThesis.id)
    if status:
        count_query = count_query.where(ResearchThesis.status == status)
    if subject_type:
        count_query = count_query.where(ResearchThesis.subject_type == subject_type)
    if source_type:
        count_query = count_query.where(ResearchThesis.source_type == source_type)
    if direction:
        count_query = count_query.where(ResearchThesis.direction == direction)
    actual_total = len(session.scalars(count_query).all())

    return {
        "total": actual_total,
        "limit": limit,
        "offset": offset,
        "rows": [_thesis_row(t) for t in rows],
    }


@router.get("/theses/{thesis_id}")
def thesis_detail(thesis_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    thesis = session.get(ResearchThesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")

    reviews = session.scalars(
        select(ResearchThesisReview)
        .where(ResearchThesisReview.thesis_id == thesis_id)
        .order_by(ResearchThesisReview.scheduled_review_date.asc())
    ).all()

    return {
        "thesis": _thesis_row(thesis),
        "reviews": [_review_row(r) for r in reviews],
    }


def _thesis_row(t: ResearchThesis) -> dict[str, Any]:
    return {
        "id": t.id,
        "source_type": t.source_type,
        "source_id": t.source_id,
        "subject_type": t.subject_type,
        "subject_id": t.subject_id,
        "subject_name": t.subject_name,
        "thesis_title": t.thesis_title,
        "thesis_body": t.thesis_body,
        "direction": t.direction,
        "horizon_days": t.horizon_days,
        "confidence": t.confidence,
        "evidence_refs": _loads_json_list(t.evidence_refs_json),
        "key_metrics": _loads_json_list(t.key_metrics_json),
        "invalidation_conditions": _loads_json_list(t.invalidation_conditions_json),
        "risk_flags": _loads_json_list(t.risk_flags_json),
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _review_row(r: ResearchThesisReview) -> dict[str, Any]:
    return {
        "id": r.id,
        "thesis_id": r.thesis_id,
        "review_horizon_days": r.review_horizon_days,
        "scheduled_review_date": r.scheduled_review_date.isoformat() if r.scheduled_review_date else None,
        "actual_review_date": r.actual_review_date.isoformat() if r.actual_review_date else None,
        "review_status": r.review_status,
        "realized_metrics": _loads_json_object(r.realized_metrics_json),
        "realized_return": r.realized_return,
        "benchmark_return": r.benchmark_return,
        "review_note": r.review_note,
        "evidence_update": _loads_json_object(r.evidence_update_json),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _loads_json_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _loads_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
