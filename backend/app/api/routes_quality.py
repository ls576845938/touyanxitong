from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ReportQualityScore, ScoringFeedbackEvent
from app.db.session import get_session
from app.engines.report_quality_engine import compute_report_quality, update_quality_from_reviews

router = APIRouter(prefix="/api/research", tags=["report-quality"])


@router.get("/report-quality")
def get_report_quality(
    source_type: str = Query(..., description="daily_report or agent_run"),
    source_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Get a report quality score for a specific source.

    If no score record exists yet, computes and persists it on-demand.
    """
    if source_type not in ("daily_report", "agent_run"):
        raise HTTPException(status_code=400, detail="source_type must be daily_report or agent_run")

    record = session.scalars(
        select(ReportQualityScore).where(
            ReportQualityScore.source_type == source_type,
            ReportQualityScore.source_id == source_id,
        )
    ).first()

    if record is None:
        try:
            record = compute_report_quality(source_type, source_id, session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    return _quality_score_payload(record)


@router.post("/report-quality/compute")
def trigger_compute_report_quality(
    source_type: str = Query(..., description="daily_report or agent_run"),
    source_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Force (re)compute report quality score for a source."""
    if source_type not in ("daily_report", "agent_run"):
        raise HTTPException(status_code=400, detail="source_type must be daily_report or agent_run")
    try:
        record = compute_report_quality(source_type, source_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _quality_score_payload(record)


@router.post("/report-quality/update-reviews")
def trigger_update_quality_from_reviews(
    source_type: str = Query(..., description="daily_report or agent_run"),
    source_id: int = Query(..., ge=1),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Update report quality score with hit rates from completed reviews."""
    if source_type not in ("daily_report", "agent_run"):
        raise HTTPException(status_code=400, detail="source_type must be daily_report or agent_run")
    try:
        record = update_quality_from_reviews(source_type, source_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _quality_score_payload(record)


@router.get("/feedback-events")
def get_feedback_events(
    subject_type: str | None = Query(default=None, description="stock / industry / market / theme"),
    subject_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None, description="Filter by review_status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """List scoring feedback events with optional filters."""
    query = select(ScoringFeedbackEvent).order_by(ScoringFeedbackEvent.created_at.desc())

    if subject_type:
        query = query.where(ScoringFeedbackEvent.subject_type == subject_type)
    if subject_id:
        query = query.where(ScoringFeedbackEvent.subject_id == subject_id)
    if review_status:
        query = query.where(ScoringFeedbackEvent.review_status == review_status)

    total = session.scalar(select(func.count(ScoringFeedbackEvent.id)).select_from(query.subquery()))
    rows = session.scalars(query.offset(offset).limit(limit)).all()

    return {
        "total": total or 0,
        "offset": offset,
        "limit": limit,
        "rows": [_feedback_event_payload(e) for e in rows],
    }


@router.get("/quality-summary")
def get_quality_summary(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Summary of recent report quality scores."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    records = session.scalars(
        select(ReportQualityScore)
        .where(ReportQualityScore.created_at >= cutoff)
        .order_by(ReportQualityScore.created_at.desc())
        .limit(limit)
    ).all()

    scores = [r.quality_score for r in records if r.quality_score is not None]
    thesis_counts = [r.thesis_count for r in records]

    # Aggregate counts by source type
    counts_by_source: dict[str, int] = {}
    for r in records:
        counts_by_source[r.source_type] = counts_by_source.get(r.source_type, 0) + 1

    # Recent feedback events count
    feedback_count = session.scalar(
        select(func.count(ScoringFeedbackEvent.id)).where(ScoringFeedbackEvent.created_at >= cutoff)
    )

    return {
        "window_days": days,
        "record_count": len(records),
        "scores_by_source": counts_by_source,
        "average_quality_score": round(sum(scores) / len(scores), 2) if scores else None,
        "min_quality_score": round(min(scores), 2) if scores else None,
        "max_quality_score": round(max(scores), 2) if scores else None,
        "total_thesis_count": sum(thesis_counts) if thesis_counts else 0,
        "recent_feedback_event_count": feedback_count or 0,
        "rows": [_quality_score_payload(r) for r in records],
    }


# ---------------------------------------------------------------------------
# Payload serializers
# ---------------------------------------------------------------------------

def _quality_score_payload(record: ReportQualityScore) -> dict[str, object]:
    return {
        "id": record.id,
        "source_type": record.source_type,
        "source_id": record.source_id,
        "thesis_count": record.thesis_count,
        "evidence_count": record.evidence_count,
        "avg_confidence": record.avg_confidence,
        "hit_rate_5d": record.hit_rate_5d,
        "hit_rate_20d": record.hit_rate_20d,
        "hit_rate_60d": record.hit_rate_60d,
        "unavailable_data_count": record.unavailable_data_count,
        "guardrail_violation_count": record.guardrail_violation_count,
        "quality_score": record.quality_score,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _feedback_event_payload(event: ScoringFeedbackEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "thesis_id": event.thesis_id,
        "subject_type": event.subject_type,
        "subject_id": event.subject_id,
        "signal_name": event.signal_name,
        "expected_direction": event.expected_direction,
        "actual_direction": event.actual_direction,
        "review_status": event.review_status,
        "confidence": event.confidence,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
