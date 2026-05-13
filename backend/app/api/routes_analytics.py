"""API routes for thesis review analytics snapshots."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import ThesisReviewAnalyticsSnapshot
from app.db.session import get_session
from app.engines.thesis_analytics_engine import compute_thesis_analytics, get_latest_analytics

router = APIRouter(prefix="/api/research", tags=["research-thesis-analytics"])


# ---------------------------------------------------------------------------
# GET /api/research/thesis-analytics
# ---------------------------------------------------------------------------


@router.get("/thesis-analytics")
def get_thesis_analytics(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return the most recent analytics snapshot.

    Returns a 404 if no snapshot has been computed yet.
    """
    snapshot = get_latest_analytics(session)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="No analytics snapshot available. POST /api/research/thesis-analytics/recompute to create one.",
        )
    return _snapshot_payload(snapshot)


# ---------------------------------------------------------------------------
# POST /api/research/thesis-analytics/recompute
# ---------------------------------------------------------------------------


@router.post("/thesis-analytics/recompute")
def recompute_thesis_analytics(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Recompute thesis analytics from all completed reviews and persist a new snapshot."""
    snapshot_date = date.today()
    snapshot = compute_thesis_analytics(session, snapshot_date=snapshot_date)
    session.commit()
    return _snapshot_payload(snapshot)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _snapshot_payload(s: ThesisReviewAnalyticsSnapshot) -> dict[str, Any]:
    return {
        "id": s.id,
        "snapshot_date": s.snapshot_date.isoformat(),
        "sample_size": s.sample_size,
        "hit_count": s.hit_count,
        "missed_count": s.missed_count,
        "invalidated_count": s.invalidated_count,
        "inconclusive_count": s.inconclusive_count,
        "hit_rate": s.hit_rate,
        "miss_rate": s.miss_rate,
        "inconclusive_rate": s.inconclusive_rate,
        "by_subject_type": _load_json(s.by_subject_type_json),
        "by_direction": _load_json(s.by_direction_json),
        "by_horizon": _load_json(s.by_horizon_json),
        "by_confidence_bucket": _load_json(s.by_confidence_bucket_json),
        "by_evidence_type": _load_json(s.by_evidence_type_json),
        "by_source_type": _load_json(s.by_source_type_json),
        "calibration_report": _load_json(s.calibration_report_json),
        "low_sample_warnings": _load_json(s.low_sample_warnings_json),
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _load_json(raw: str) -> Any:
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}
