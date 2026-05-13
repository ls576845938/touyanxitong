from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRun,
    DailyReport,
    ReportQualityScore,
    ResearchThesis,
    ResearchThesisReview,
    ScoringFeedbackEvent,
)


def compute_report_quality(source_type: str, source_id: int, db_session: Session) -> ReportQualityScore:
    """Compute a report quality score for a given source (daily_report or agent_run).

    Counts theses linked to the source, evaluates evidence coverage, confidence,
    and guardrail violations. Stores the composite quality score.

    Integration hook: call this after DailyReport generation (daily_report_job.py)
    or after AgentRun completion (orchestrator.py).
    """
    # Validate the source exists
    _resolve_source(source_type, source_id, db_session)

    # Find all theses linked to this source
    theses = _find_linked_theses(source_type, source_id, db_session)
    thesis_count = len(theses)

    # Count evidence refs across all theses
    evidence_count = 0
    total_confidence = 0.0
    guardrail_violation_count = 0
    unavailable_data_count = 0
    thesis_texts: list[str] = []

    for thesis in theses:
        thesis_texts.append(str(thesis.thesis_title or ""))
        thesis_texts.append(str(thesis.thesis_body or ""))
        total_confidence += float(thesis.confidence or 0.0)

        # Count evidence refs
        refs = _safe_json_loads(thesis.evidence_refs_json, [])
        evidence_count += len(refs) if isinstance(refs, list) else 0

        # Count unavailable data flags
        risk_flags = _safe_json_loads(thesis.risk_flags_json, [])
        if isinstance(risk_flags, list):
            unavailable_data_count += sum(
                1 for flag in risk_flags if _flag_indicates_unavailable_data(flag)
            )

    # Check for guardrail violations in thesis text
    guardrail_violation_count = _count_guardrail_violations(thesis_texts)

    avg_confidence = total_confidence / thesis_count if thesis_count > 0 else 0.0

    # Compute composite quality score (conservative when data is sparse)
    quality_score = _compute_quality_score(
        thesis_count=thesis_count,
        evidence_count=evidence_count,
        avg_confidence=avg_confidence,
        guardrail_violation_count=guardrail_violation_count,
        hit_rate_5d=None,
        hit_rate_20d=None,
        hit_rate_60d=None,
    )

    # Upsert the quality score record
    existing = db_session.scalars(
        select(ReportQualityScore).where(
            ReportQualityScore.source_type == source_type,
            ReportQualityScore.source_id == source_id,
        )
    ).first()

    if existing:
        existing.thesis_count = thesis_count
        existing.evidence_count = evidence_count
        existing.avg_confidence = round(avg_confidence, 2)
        existing.guardrail_violation_count = guardrail_violation_count
        existing.unavailable_data_count = unavailable_data_count
        existing.quality_score = round(quality_score, 2)
        result = existing
    else:
        result = ReportQualityScore(
            source_type=source_type,
            source_id=source_id,
            thesis_count=thesis_count,
            evidence_count=evidence_count,
            avg_confidence=round(avg_confidence, 2),
            guardrail_violation_count=guardrail_violation_count,
            unavailable_data_count=unavailable_data_count,
            quality_score=round(quality_score, 2),
        )
        db_session.add(result)

    db_session.commit()
    return result


def update_quality_from_reviews(source_type: str, source_id: int, db_session: Session) -> ReportQualityScore:
    """Update a report quality score with hit rates from completed thesis reviews.

    Finds all theses linked to the source, retrieves completed reviews,
    computes hit rates per horizon (5d, 20d, 60d), and recalculates the
    composite quality score.

    Integration hook: call this after running thesis reviews.
    """
    score_record = db_session.scalars(
        select(ReportQualityScore).where(
            ReportQualityScore.source_type == source_type,
            ReportQualityScore.source_id == source_id,
        )
    ).first()

    if score_record is None:
        # No pre-existing record; compute from scratch
        score_record = compute_report_quality(source_type, source_id, db_session)

    # Find theses linked to this source
    theses = _find_linked_theses(source_type, source_id, db_session)
    thesis_ids = [t.id for t in theses]

    if not thesis_ids:
        return score_record

    # Find all completed reviews for these theses
    reviews = db_session.scalars(
        select(ResearchThesisReview).where(
            ResearchThesisReview.thesis_id.in_(thesis_ids),
            ResearchThesisReview.review_status.in_(["confirmed", "rejected", "partial"]),
        )
    ).all()

    # Compute hit rates per horizon
    horizon_groups: dict[int, list[bool]] = {5: [], 20: [], 60: []}
    for review in reviews:
        horizon = int(review.review_horizon_days or 20)
        if horizon not in horizon_groups:
            # Map unknown horizons to nearest standard bucket
            horizon = _nearest_standard_horizon(horizon)
        # A review is a "hit" if the thesis direction was confirmed
        is_hit = _is_review_hit(review)
        horizon_groups[horizon].append(is_hit)

    hit_rate_5d = _safe_hit_rate(horizon_groups[5])
    hit_rate_20d = _safe_hit_rate(horizon_groups[20])
    hit_rate_60d = _safe_hit_rate(horizon_groups[60])

    # Update the record
    score_record.hit_rate_5d = hit_rate_5d
    score_record.hit_rate_20d = hit_rate_20d
    score_record.hit_rate_60d = hit_rate_60d

    # Recompute quality score incorporating hit rates
    quality_score = _compute_quality_score(
        thesis_count=score_record.thesis_count,
        evidence_count=score_record.evidence_count,
        avg_confidence=score_record.avg_confidence,
        guardrail_violation_count=score_record.guardrail_violation_count,
        hit_rate_5d=hit_rate_5d,
        hit_rate_20d=hit_rate_20d,
        hit_rate_60d=hit_rate_60d,
    )
    score_record.quality_score = round(quality_score, 2)
    db_session.commit()
    return score_record


def create_feedback_event(thesis: ResearchThesis, review: ResearchThesisReview, db_session: Session) -> ScoringFeedbackEvent:
    """Create a scoring feedback event from a thesis review outcome.

    Maps the thesis direction to expected_direction and the review status
    to actual_direction. Does NOT modify scoring engine weights.

    Integration hook: call this after each thesis review completes.
    """
    expected = _map_direction_to_expected(str(thesis.direction or "neutral"))
    actual = _map_review_to_actual(thesis, review)

    signal_name = str(thesis.thesis_title or "")[:64] or f"thesis_{thesis.id}"

    event = ScoringFeedbackEvent(
        thesis_id=thesis.id,
        subject_type=str(thesis.subject_type or "stock")[:16],
        subject_id=str(thesis.subject_id or "")[:32],
        signal_name=signal_name,
        expected_direction=expected,
        actual_direction=actual,
        review_status=str(review.review_status or "pending"),
        confidence=int(float(thesis.confidence or 50.0)),
    )
    db_session.add(event)
    db_session.commit()
    return event


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_source(source_type: str, source_id: int, db_session: Session) -> None:
    """Verify the source record exists; raises ValueError if not."""
    if source_type == "daily_report":
        obj = db_session.get(DailyReport, source_id)
    elif source_type == "agent_run":
        obj = db_session.get(AgentRun, source_id)
    else:
        raise ValueError(f"Unknown source_type: {source_type}")
    if obj is None:
        raise ValueError(f"{source_type} with id={source_id} not found")


def _find_linked_theses(source_type: str, source_id: int, db_session: Session) -> list[ResearchThesis]:
    """Find all ResearchThesis records linked to the given source."""
    results = db_session.scalars(
        select(ResearchThesis).where(
            ResearchThesis.source_type == source_type,
            ResearchThesis.source_id == str(source_id),
        )
    ).all()
    return list(results)


def _compute_quality_score(
    *,
    thesis_count: int,
    evidence_count: int,
    avg_confidence: float,
    guardrail_violation_count: int,
    hit_rate_5d: float | None,
    hit_rate_20d: float | None,
    hit_rate_60d: float | None,
) -> float:
    """Compute a composite report quality score in the range 0-100.

    Formula (normalized to 0-100):
      raw = thesis_count * 10         (max 50)
          + evidence_count * 5         (max 25)
          + avg_confidence * 0.5       (max 50)
          + hit_rate_bonus             (max 30)
          + (0 if violations > 0 else 20)
      quality_score = min(100, raw) / 1.45
    """
    count_component = min(50.0, float(thesis_count) * 10.0)
    evidence_component = min(25.0, float(evidence_count) * 5.0)
    confidence_component = min(50.0, float(avg_confidence) * 0.5)
    guardrail_penalty = 0.0 if guardrail_violation_count > 0 else 20.0

    hit_rate_bonus = 0.0
    if hit_rate_5d is not None:
        hit_rate_bonus += float(hit_rate_5d) * 15.0
    if hit_rate_20d is not None:
        hit_rate_bonus += float(hit_rate_20d) * 10.0
    if hit_rate_60d is not None:
        hit_rate_bonus += float(hit_rate_60d) * 5.0
    hit_rate_bonus = min(30.0, hit_rate_bonus)

    raw = count_component + evidence_component + confidence_component + hit_rate_bonus + guardrail_penalty
    normalized = min(100.0, raw) / 1.45
    return max(0.0, min(100.0, normalized))


def _count_guardrail_violations(texts: list[str]) -> int:
    """Search thesis texts for forbidden terms indicating guardrail violations.

    Returns the total count of distinct violations found.
    """
    forbidden_terms = [
        "guaranteed return",
        "guaranteed profit",
        "sure thing",
        "no risk",
        "risk free",
        "risk-free",
        "zero risk",
        "100% certain",
        "absolutely certain",
        "guaranteed",
        "certain gain",
        "guaranteed upside",
        "no downside",
        "can't lose",
        "100% 确定",
        "100% 保证",
        "保本保收益",
        "无风险",
        "稳赚",
        "一定涨",
        "肯定涨",
        "保证收益",
        "包赚",
    ]

    combined = " ".join(texts).lower()
    violation_count = 0
    for term in forbidden_terms:
        if term.lower() in combined:
            violation_count += 1
    return violation_count


def _flag_indicates_unavailable_data(flag: Any) -> bool:
    """Check if a risk flag indicates unavailable/missing data."""
    if isinstance(flag, str):
        lowered = flag.lower()
        return any(
            keyword in lowered
            for keyword in ["missing", "unavailable", "no data", "data gap", "null", "数据缺失", "无数据"]
        )
    if isinstance(flag, dict):
        text = json.dumps(flag, ensure_ascii=False).lower()
        return any(
            keyword in text
            for keyword in ["missing", "unavailable", "no data", "data gap", "null", "数据缺失", "无数据"]
        )
    return False


def _is_review_hit(review: ResearchThesisReview) -> bool:
    """Determine if a thesis review was a 'hit' (thesis direction was confirmed)."""
    status = str(review.review_status or "").lower()
    if status == "confirmed":
        return True
    if status == "rejected":
        return False
    # Partial: use realized return if available, else not a hit
    if status == "partial":
        realized = review.realized_return
        if realized is not None:
            return float(realized) > 0
        return False  # no return data available, be conservative
    return False


def _nearest_standard_horizon(horizon: int) -> int:
    """Map an unknown horizon to the nearest standard bucket (5, 20, or 60)."""
    standards = [5, 20, 60]
    return min(standards, key=lambda s: abs(s - horizon))


def _safe_hit_rate(results: list[bool]) -> float | None:
    """Compute hit rate as a float 0-1, or None if no data."""
    if not results:
        return None
    return round(sum(1 for r in results if r) / len(results), 4)


def _map_direction_to_expected(direction: str) -> str:
    """Map ResearchThesis direction to expected_direction."""
    mapping = {
        "up": "positive",
        "down": "negative",
        "neutral": "neutral",
    }
    return mapping.get(direction.lower(), "neutral")


def _map_review_to_actual(thesis: ResearchThesis, review: ResearchThesisReview) -> str | None:
    """Map review outcome to actual_direction.

    If review confirmed the thesis direction, actual = expected.
    If review rejected, actual = opposite of expected.
    If partial, check realized_return.
    If pending/missed, return None.
    """
    status = str(review.review_status or "").lower()
    expected = _map_direction_to_expected(str(thesis.direction or "neutral"))

    if status == "confirmed":
        return expected
    if status == "rejected":
        return _opposite_direction(expected)
    if status == "partial":
        realized = review.realized_return
        if realized is not None:
            return "positive" if float(realized) > 0 else "negative" if float(realized) < 0 else "neutral"
        return expected  # partial with no return data: assume thesis direction
    return None  # pending, missed, etc.


def _opposite_direction(direction: str) -> str:
    if direction == "positive":
        return "negative"
    if direction == "negative":
        return "positive"
    return "neutral"


def _safe_json_loads(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return default
