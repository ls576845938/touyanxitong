"""API routes for human annotation feedback on research theses.

Annotations are HUMAN feedback only -- they do NOT modify thesis.review_status
or thesis.status. They are stored separately for analytics and review purposes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ResearchThesis, ResearchThesisAnnotation
from app.db.session import get_session

router = APIRouter(prefix="/api/research", tags=["research-annotations"])

VALID_LABELS = frozenset({
    "accurate",
    "inaccurate",
    "evidence_weak",
    "too_vague",
    "useful",
    "not_useful",
    "unclear",
})


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AnnotationCreate(BaseModel):
    label: str = Field(..., description="Annotation label")
    user_id: str | None = Field(default=None, description="Optional user identifier")
    rating: int | None = Field(default=None, ge=1, le=5, description="Rating 1-5")
    note: str | None = Field(default=None, description="Free-text note")


# ---------------------------------------------------------------------------
# POST /api/research/theses/{thesis_id}/annotations
# ---------------------------------------------------------------------------


@router.post("/theses/{thesis_id}/annotations", status_code=201)
def create_annotation(
    thesis_id: int,
    body: AnnotationCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    thesis = session.get(ResearchThesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")

    if body.label not in VALID_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid label '{body.label}'. Must be one of: {', '.join(sorted(VALID_LABELS))}",
        )

    annotation = ResearchThesisAnnotation(
        thesis_id=thesis_id,
        user_id=body.user_id,
        label=body.label,
        rating=body.rating,
        note=body.note,
    )
    session.add(annotation)
    session.commit()
    session.refresh(annotation)

    return _annotation_payload(annotation)


# ---------------------------------------------------------------------------
# GET /api/research/theses/{thesis_id}/annotations
# ---------------------------------------------------------------------------


@router.get("/theses/{thesis_id}/annotations")
def list_thesis_annotations(
    thesis_id: int,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    thesis = session.get(ResearchThesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")

    annotations = session.scalars(
        select(ResearchThesisAnnotation)
        .where(ResearchThesisAnnotation.thesis_id == thesis_id)
        .order_by(ResearchThesisAnnotation.created_at.desc())
    ).all()

    return [_annotation_payload(a) for a in annotations]


# ---------------------------------------------------------------------------
# GET /api/research/annotations
# ---------------------------------------------------------------------------


@router.get("/annotations")
def filtered_annotations(
    label: str | None = Query(default=None, description="Filter by label"),
    user_id: str | None = Query(default=None, description="Filter by user_id"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = (
        select(ResearchThesisAnnotation)
        .order_by(ResearchThesisAnnotation.created_at.desc())
    )

    if label is not None:
        query = query.where(ResearchThesisAnnotation.label == label)
    if user_id is not None:
        query = query.where(ResearchThesisAnnotation.user_id == user_id)

    total = session.scalar(
        select(func.count(ResearchThesisAnnotation.id)).where(query.exists())
    )

    rows = session.scalars(query.offset(offset).limit(limit)).all()

    return {
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "rows": [_annotation_with_thesis_payload(a, session) for a in rows],
    }


# ---------------------------------------------------------------------------
# GET /api/research/annotations/summary
# ---------------------------------------------------------------------------


@router.get("/annotations/summary")
def annotations_summary(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    total = session.scalar(
        select(func.count(ResearchThesisAnnotation.id))
    ) or 0

    # Counts by label
    label_counts_raw = session.execute(
        select(
            ResearchThesisAnnotation.label,
            func.count(ResearchThesisAnnotation.id),
        ).group_by(ResearchThesisAnnotation.label)
    ).all()

    by_label: dict[str, int] = {}
    for label, count in label_counts_raw:
        by_label[str(label)] = count

    useful_count = by_label.get("useful", 0)
    evidence_weak_count = by_label.get("evidence_weak", 0)
    too_vague_count = by_label.get("too_vague", 0)

    return {
        "total": total,
        "useful_rate": round(useful_count / total, 4) if total > 0 else 0.0,
        "evidence_weak_rate": round(evidence_weak_count / total, 4) if total > 0 else 0.0,
        "too_vague_rate": round(too_vague_count / total, 4) if total > 0 else 0.0,
        "by_label": by_label,
    }


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _annotation_payload(a: ResearchThesisAnnotation) -> dict[str, Any]:
    return {
        "id": a.id,
        "thesis_id": a.thesis_id,
        "user_id": a.user_id,
        "label": a.label,
        "rating": a.rating,
        "note": a.note,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _annotation_with_thesis_payload(
    a: ResearchThesisAnnotation,
    session: Session,
) -> dict[str, Any]:
    thesis = session.get(ResearchThesis, a.thesis_id)
    thesis_summary = None
    if thesis is not None:
        thesis_summary = {
            "id": thesis.id,
            "subject_type": thesis.subject_type,
            "subject_id": thesis.subject_id,
            "subject_name": thesis.subject_name,
            "thesis_title": thesis.thesis_title,
            "direction": thesis.direction,
            "status": thesis.status,
        }

    return {
        "id": a.id,
        "thesis_id": a.thesis_id,
        "user_id": a.user_id,
        "label": a.label,
        "rating": a.rating,
        "note": a.note,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "thesis": thesis_summary,
    }
