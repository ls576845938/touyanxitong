"""Thesis review analytics engine: compute predictive-power statistics.

Answers the question: does the system's research thesis signal actually predict
outcomes?  Produces per-dimensional breakdowns, calibration curves, and flags
groups with insufficient sample sizes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchThesis, ResearchThesisReview, ThesisReviewAnalyticsSnapshot

# ---------------------------------------------------------------------------
# Confidence-bucket definitions
# ---------------------------------------------------------------------------

CONFIDENCE_BUCKETS: list[tuple[str, float, float]] = [
    ("0-40", 0.0, 40.0),
    ("40-60", 40.0, 60.0),
    ("60-75", 60.0, 75.0),
    ("75-90", 75.0, 90.0),
    ("90-100", 90.0, 100.0),
]

BUCKET_MIDPOINTS: dict[str, float] = {
    "0-40": 20.0,
    "40-60": 50.0,
    "60-75": 67.5,
    "75-90": 82.5,
    "90-100": 95.0,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_thesis_analytics(
    db_session: Session,
    snapshot_date: date | None = None,
) -> ThesisReviewAnalyticsSnapshot:
    """Compute a fresh analytics snapshot from all completed thesis reviews.

    Queries every ``ResearchThesisReview`` whose ``review_status != 'pending'``,
    groups results along multiple dimensions, computes calibration, and persists
    the snapshot to the database.
    """
    snapshot_date = snapshot_date or date.today()

    # Load all non-pending reviews together with their parent theses
    reviews = list(
        db_session.scalars(
            select(ResearchThesisReview).where(
                ResearchThesisReview.review_status != "pending"
            )
        ).all()
    )

    thesis_ids = {r.thesis_id for r in reviews}
    thesis_map: dict[int, ResearchThesis] = {}
    if thesis_ids:
        theses = list(
            db_session.scalars(
                select(ResearchThesis).where(ResearchThesis.id.in_(thesis_ids))
            ).all()
        )
        thesis_map = {t.id: t for t in theses}

    # Build enriched list (skip orphaned reviews)
    enriched: list[dict[str, Any]] = []
    for r in reviews:
        t = thesis_map.get(r.thesis_id)
        if t is None:
            continue
        enriched.append({"review": r, "thesis": t})

    total = len(enriched)
    hit_count = _count_status(enriched, "hit")
    missed_count = _count_status(enriched, "missed")
    invalidated_count = _count_status(enriched, "invalidated")
    inconclusive_count = _count_status(enriched, "inconclusive")

    hit_rate = _safe_rate(hit_count, total)
    miss_rate = _safe_rate(missed_count, total)
    inconclusive_rate = _safe_rate(inconclusive_count, total)

    # Dimension breakdowns
    by_subject_type = _group_by(enriched, lambda e: str(e["thesis"].subject_type or "unknown"))
    by_direction = _group_by(enriched, lambda e: str(e["thesis"].direction or "unknown"))
    by_horizon = _group_by(enriched, lambda e: str(e["review"].review_horizon_days))
    by_confidence_bucket = _group_by(enriched, lambda e: _confidence_bucket(e["thesis"].confidence))
    by_source_type = _group_by(enriched, lambda e: str(e["thesis"].source_type or "unknown"))
    by_evidence_type = _group_by_evidence_type(enriched)

    # Calibration analysis
    calibration_report = _compute_calibration(by_confidence_bucket)

    # Low-sample warnings
    low_sample_warnings = _gather_low_sample_warnings(
        subject_type=by_subject_type,
        direction=by_direction,
        horizon=by_horizon,
        confidence_bucket=by_confidence_bucket,
        source_type=by_source_type,
        evidence_type=by_evidence_type,
    )

    snapshot = ThesisReviewAnalyticsSnapshot(
        snapshot_date=snapshot_date,
        sample_size=total,
        hit_count=hit_count,
        missed_count=missed_count,
        invalidated_count=invalidated_count,
        inconclusive_count=inconclusive_count,
        hit_rate=hit_rate,
        miss_rate=miss_rate,
        inconclusive_rate=inconclusive_rate,
        by_subject_type_json=json.dumps(by_subject_type, ensure_ascii=False),
        by_direction_json=json.dumps(by_direction, ensure_ascii=False),
        by_horizon_json=json.dumps(by_horizon, ensure_ascii=False),
        by_confidence_bucket_json=json.dumps(by_confidence_bucket, ensure_ascii=False),
        by_evidence_type_json=json.dumps(by_evidence_type, ensure_ascii=False),
        by_source_type_json=json.dumps(by_source_type, ensure_ascii=False),
        calibration_report_json=json.dumps(calibration_report, ensure_ascii=False),
        low_sample_warnings_json=json.dumps(low_sample_warnings, ensure_ascii=False),
    )

    db_session.add(snapshot)
    db_session.flush()
    return snapshot


def get_latest_analytics(
    db_session: Session,
) -> ThesisReviewAnalyticsSnapshot | None:
    """Return the most recent analytics snapshot, or ``None`` if none exist."""
    return db_session.scalar(
        select(ThesisReviewAnalyticsSnapshot)
        .order_by(ThesisReviewAnalyticsSnapshot.snapshot_date.desc())
        .limit(1)
    )


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _count_status(enriched: list[dict[str, Any]], status: str) -> int:
    return sum(1 for e in enriched if e["review"].review_status == status)


# ---------------------------------------------------------------------------
# Confidence bucket helper
# ---------------------------------------------------------------------------


def _confidence_bucket(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    for label, low, high in CONFIDENCE_BUCKETS:
        if low <= confidence < high:
            return label
    # 100.0 exactly falls into the last bucket
    if confidence == 100.0:
        return "90-100"
    return "unknown"


# ---------------------------------------------------------------------------
# Dimension groupers
# ---------------------------------------------------------------------------


def _compute_group_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-group aggregate statistics."""
    n = len(items)
    hits = sum(1 for e in items if e["review"].review_status == "hit")
    misses = sum(1 for e in items if e["review"].review_status == "missed")
    invalidated = sum(1 for e in items if e["review"].review_status == "invalidated")
    inconcl = sum(1 for e in items if e["review"].review_status == "inconclusive")
    return {
        "sample_size": n,
        "hit_count": hits,
        "miss_count": misses,
        "invalidated_count": invalidated,
        "inconclusive_count": inconcl,
        "hit_rate": _safe_rate(hits, n),
        "miss_rate": _safe_rate(misses, n),
        "inconclusive_rate": _safe_rate(inconcl, n),
    }


def _group_by(
    enriched: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """Group enriched reviews by a string key and compute per-group stats."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in enriched:
        key = key_fn(e)
        groups.setdefault(key, []).append(e)

    result: dict[str, Any] = {}
    for key in sorted(groups):
        result[key] = _compute_group_stats(groups[key])
    return result


def _extract_evidence_types(thesis: ResearchThesis) -> list[str]:
    """Parse evidence type tags from a thesis's evidence_refs_json.

    Expects a JSON array where each element is either a string or a dict with a
    ``type`` (or ``evidence_type``) key.  Returns a sorted unique list.
    """
    raw = thesis.evidence_refs_json
    if not raw:
        return []
    try:
        refs = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(refs, list):
        return []

    types: set[str] = set()
    for ref in refs:
        if isinstance(ref, dict):
            t = ref.get("type") or ref.get("evidence_type") or ""
        elif isinstance(ref, str):
            t = ref
        else:
            continue
        cleaned = str(t).strip()
        if cleaned:
            types.add(cleaned)
    return sorted(types)


def _group_by_evidence_type(enriched: list[dict[str, Any]]) -> dict[str, Any]:
    """Group enriched reviews by their thesis's evidence types.

    A single thesis may reference multiple evidence types; it contributes to
    every matching group.  When no types can be parsed the review lands in the
    ``"unknown"`` bucket.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in enriched:
        types = _extract_evidence_types(e["thesis"])
        if not types:
            types = ["unknown"]
        for t in types:
            groups.setdefault(t, []).append(e)

    result: dict[str, Any] = {}
    for key in sorted(groups):
        result[key] = _compute_group_stats(groups[key])
    return result


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def _compute_calibration(by_confidence_bucket: dict[str, Any]) -> dict[str, Any]:
    """Compute calibration curve from the confidence-bucket breakdown.

    For each non-unknown bucket the *midpoint* (in fraction, 0-1) is compared
    against the actual hit rate.  A positive *calibration_gap* means the system
    is overconfident (predicted better than actual).
    """
    report: dict[str, Any] = {}
    for bucket, stats in by_confidence_bucket.items():
        if bucket == "unknown":
            continue
        midpoint = BUCKET_MIDPOINTS.get(bucket)
        if midpoint is None:
            continue
        actual_hit_rate = stats["hit_rate"]
        if actual_hit_rate is not None:
            midpoint_fraction = midpoint / 100.0
            gap = round(midpoint_fraction - actual_hit_rate, 4)
        else:
            gap = None
        report[bucket] = {
            "sample_size": stats["sample_size"],
            "midpoint": midpoint,
            "midpoint_fraction": midpoint / 100.0 if midpoint else None,
            "actual_hit_rate": actual_hit_rate,
            "calibration_gap": gap,
        }
    return report


# ---------------------------------------------------------------------------
# Low-sample warnings
# ---------------------------------------------------------------------------

_WARNING_THRESHOLD = 10


def _gather_low_sample_warnings(**dimensions: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect every dimension group whose sample size is below threshold."""
    warnings: list[dict[str, Any]] = []
    for dimension_name, groups in dimensions.items():
        for group_key, stats in groups.items():
            if stats["sample_size"] < _WARNING_THRESHOLD:
                warnings.append({
                    "dimension": dimension_name,
                    "group": group_key,
                    "sample_size": stats["sample_size"],
                })
    return warnings
