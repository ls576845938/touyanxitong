"""API routes for thesis review scheduling and execution."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchThesis, ResearchThesisReview
from app.db.session import get_session
from app.engines.thesis_review_engine import create_review_schedule, run_due_reviews, run_thesis_review

router = APIRouter(prefix="/api/research/theses", tags=["research-theses"])


# ---------------------------------------------------------------------------
# GET /api/research/theses/{thesis_id}/reviews
# ---------------------------------------------------------------------------


@router.get("/{thesis_id}/reviews")
def list_thesis_reviews(
    thesis_id: int,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    thesis = session.get(ResearchThesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")

    reviews = session.scalars(
        select(ResearchThesisReview)
        .where(ResearchThesisReview.thesis_id == thesis_id)
        .order_by(ResearchThesisReview.scheduled_review_date)
    ).all()

    return [_review_payload(r) for r in reviews]


# ---------------------------------------------------------------------------
# POST /api/research/theses/{thesis_id}/review
# ---------------------------------------------------------------------------


@router.post("/{thesis_id}/review")
def trigger_thesis_review(
    thesis_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    thesis = session.get(ResearchThesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")

    # Find the next pending review, or the latest review if all are done
    review = session.scalar(
        select(ResearchThesisReview)
        .where(
            ResearchThesisReview.thesis_id == thesis_id,
            ResearchThesisReview.review_status == "pending",
        )
        .order_by(ResearchThesisReview.scheduled_review_date)
        .limit(1)
    )

    if review is None:
        raise HTTPException(status_code=400, detail="No pending reviews for this thesis")

    as_of_date = date.today()
    result = run_thesis_review(thesis, review, session)

    # Persist
    review.review_status = result.review_status
    review.actual_review_date = as_of_date
    review.realized_return = result.realized_return
    review.benchmark_return = result.benchmark_return
    review.realized_metrics_json = json.dumps(result.realized_metrics_json, ensure_ascii=False)
    review.review_note = result.review_note
    review.evidence_update_json = json.dumps(result.evidence_update_json, ensure_ascii=False)

    # Update thesis status
    if result.review_status == "invalidated":
        thesis.status = "invalidated"
    elif result.review_status == "missed" and thesis.status not in {"invalidated", "completed"}:
        thesis.status = "missed"
    elif result.review_status == "hit" and thesis.status == "active":
        thesis.status = "validated"

    session.commit()

    return {
        "thesis_id": result.thesis_id,
        "review_horizon_days": result.review_horizon_days,
        "scheduled_review_date": result.scheduled_review_date.isoformat(),
        "review_status": result.review_status,
        "realized_return": result.realized_return,
        "benchmark_return": result.benchmark_return,
        "realized_metrics_json": result.realized_metrics_json,
        "review_note": result.review_note,
    }


# ---------------------------------------------------------------------------
# POST /api/research/theses/review-due
# ---------------------------------------------------------------------------


@router.post("/review-due")
def trigger_due_reviews(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    as_of_date = date.today()
    results = run_due_reviews(as_of_date, session)
    session.commit()
    summary = _summarize_results(results)
    return {
        "as_of_date": as_of_date.isoformat(),
        "total_reviewed": len(results),
        "summary": summary,
        "results": [_result_summary(r) for r in results],
    }


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _review_payload(review: ResearchThesisReview) -> dict[str, Any]:
    return {
        "id": review.id,
        "thesis_id": review.thesis_id,
        "review_horizon_days": review.review_horizon_days,
        "scheduled_review_date": review.scheduled_review_date.isoformat(),
        "actual_review_date": review.actual_review_date.isoformat() if review.actual_review_date else None,
        "review_status": review.review_status,
        "realized_metrics_json": _load_json(review.realized_metrics_json),
        "realized_return": review.realized_return,
        "benchmark_return": review.benchmark_return,
        "review_note": review.review_note,
        "evidence_update_json": _load_json(review.evidence_update_json),
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


def _result_summary(r: Any) -> dict[str, Any]:
    return {
        "thesis_id": r.thesis_id,
        "review_horizon_days": r.review_horizon_days,
        "scheduled_review_date": r.scheduled_review_date.isoformat() if hasattr(r.scheduled_review_date, "isoformat") else str(r.scheduled_review_date),
        "review_status": r.review_status,
        "realized_return": r.realized_return,
        "benchmark_return": r.benchmark_return,
        "review_note": r.review_note,
    }


def _summarize_results(results: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        status = r.review_status
        counts[status] = counts.get(status, 0) + 1
    return counts


def _load_json(raw: str) -> Any:
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}
