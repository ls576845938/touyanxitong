from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.evaluation.golden_cases import GOLDEN_CASES
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import AgentRunRequest
from app.db.models import AgentArtifact, ResearchThesis, ResearchThesisReview

# ---------------------------------------------------------------------------
# Legacy runner (unchanged) — validates task_type, required_phrases,
# forbidden_phrases only.
# ---------------------------------------------------------------------------


def replay_golden_cases(session: Session) -> list[dict[str, object]]:
    orchestrator = AgentOrchestrator(session)
    results = []
    for case in GOLDEN_CASES:
        response = orchestrator.run(AgentRunRequest(user_prompt=str(case["prompt"])))
        artifact = session.get(AgentArtifact, response.artifact_id) if response.artifact_id else None
        content = artifact.content_md if artifact else ""

        reasons = []
        if response.selected_task_type != case["expected_task_type"]:
            reasons.append(f"Expected task type {case['expected_task_type']}, got {response.selected_task_type}")

        for phrase in case.get("required_phrases", []):
            if phrase not in content:
                reasons.append(f"Missing required phrase: {phrase}")

        for phrase in case.get("forbidden_phrases", []):
            if phrase in content:
                reasons.append(f"Found forbidden phrase: {phrase}")

        results.append(
            {
                "prompt": case["prompt"],
                "status": response.status,
                "selected_task_type": response.selected_task_type,
                "passed": len(reasons) == 0,
                "reasons": reasons,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Thesis-quality evaluation  (MVP 3.0)
# ---------------------------------------------------------------------------


@dataclass
class ThesisQualityResult:
    """Per-case result of thesis-quality validation."""

    case_index: int
    task_type_correct: bool
    thesis_count: int
    thesis_count_ok: bool
    evidence_ok: bool
    invalidation_ok: bool
    horizon_ok: bool
    confidence_ok: bool
    forbidden_ok: bool
    risk_flags_ok: bool
    uncertainty_ok: bool
    review_schedule_ok: bool = True
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def _load_json_field(record: Any, field_name: str) -> Any:
    """Safely deserialize a JSON text column from an ORM record."""
    raw = getattr(record, field_name, "")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
    return raw or []


def _check_thesis_quality(
    case: dict[str, Any],
    case_index: int,
    artifact: AgentArtifact | None,
    session: Session,
) -> ThesisQualityResult:
    """Run thesis-quality checks against the artifact and persisted theses.

    All quality checks are *optional* — they only fire when the corresponding
    key exists in the case dict.
    """
    failures: list[str] = []

    # --- task type correctness (always checked) ---
    task_type_correct = True  # Callers fill this; we only check thesis fields here.

    # --- gather theses from DB via thesis_ids_json ---
    thesis_ids: list[int] = []
    if artifact is not None:
        thesis_ids_raw = _load_json_field(artifact, "thesis_ids_json")
        if isinstance(thesis_ids_raw, list):
            thesis_ids = [int(t) for t in thesis_ids_raw if t]
    thesis_records: list[ResearchThesis] = []
    if thesis_ids:
        stmt = select(ResearchThesis).where(ResearchThesis.id.in_(thesis_ids))
        thesis_records = list(session.execute(stmt).scalars().all())

    thesis_count = len(thesis_records)

    content_md = artifact.content_md if artifact else ""

    # --- 1. min_thesis_count ---
    min_count = case.get("min_thesis_count")
    if min_count is not None:
        if thesis_count < min_count:
            failures.append(
                f"Expected at least {min_count} thesis/teses, got {thesis_count}"
            )
        thesis_count_ok = thesis_count >= min_count
    else:
        thesis_count_ok = True

    # --- 2. require_evidence_refs ---
    if case.get("require_evidence_refs"):
        all_have_evidence = True
        for t in thesis_records:
            ev_refs = _load_json_field(t, "evidence_refs_json")
            if not ev_refs:
                all_have_evidence = False
                failures.append(
                    f"Thesis #{t.id} ('{t.thesis_title[:60]}') has no evidence refs"
                )
        if thesis_count == 0:
            evidence_ok = True  # no theses → no thesis-level evidence failure
        else:
            evidence_ok = all_have_evidence
            if not all_have_evidence:
                pass  # specific failures already added above
    else:
        evidence_ok = True

    # --- 3. require_invalidation ---
    if case.get("require_invalidation"):
        all_have_invalidation = True
        for t in thesis_records:
            invalidation = _load_json_field(t, "invalidation_conditions_json")
            if not invalidation:
                all_have_invalidation = False
                failures.append(
                    f"Thesis #{t.id} ('{t.thesis_title[:60]}') has no invalidation conditions"
                )
        if thesis_count == 0:
            invalidation_ok = True
        else:
            invalidation_ok = all_have_invalidation
    else:
        invalidation_ok = True

    # --- 4. require_horizon ---
    if case.get("require_horizon"):
        all_have_horizon = True
        for t in thesis_records:
            if not t.horizon_days or t.horizon_days <= 0:
                all_have_horizon = False
                failures.append(
                    f"Thesis #{t.id} ('{t.thesis_title[:60]}') has no horizon_days"
                )
        if thesis_count == 0:
            horizon_ok = True
        else:
            horizon_ok = all_have_horizon
    else:
        horizon_ok = True

    # --- 5. require_confidence / max_confidence ---
    confidence_ok = True
    if case.get("require_confidence"):
        all_have_confidence = True
        for t in thesis_records:
            if t.confidence is None or t.confidence <= 0:
                all_have_confidence = False
                failures.append(
                    f"Thesis #{t.id} ('{t.thesis_title[:60]}') has no confidence"
                )
        if thesis_count > 0 and not all_have_confidence:
            confidence_ok = False

    max_conf = case.get("max_confidence")
    if max_conf is not None:
        for t in thesis_records:
            if t.confidence and t.confidence > max_conf:
                confidence_ok = False
                failures.append(
                    f"Thesis #{t.id} ('{t.thesis_title[:60]}') confidence={t.confidence} "
                    f"exceeds max allowed {max_conf}"
                )

    # --- 6. forbidden_phrases (re-checked against thesis text) ---
    forbidden_ok = True
    for phrase in case.get("forbidden_phrases", []):
        if phrase in content_md:
            forbidden_ok = False
            failures.append(f"Found forbidden phrase in content: '{phrase}'")
        # Also check thesis bodies
        for t in thesis_records:
            if phrase in (t.thesis_body or "") or phrase in (t.thesis_title or ""):
                forbidden_ok = False
                failures.append(
                    f"Found forbidden phrase '{phrase}' in thesis #{t.id}"
                )

    # --- 7. require_risk_flags ---
    risk_flags_ok = True
    if case.get("require_risk_flags"):
        if "风险" not in content_md:
            risk_flags_ok = False
            failures.append("Content does not mention 风险 (risk)")
        # Check if any thesis has risk_flags
        if thesis_records:
            any_risk = False
            for t in thesis_records:
                rfs = _load_json_field(t, "risk_flags_json")
                if rfs:
                    any_risk = True
                    break
            if not any_risk:
                risk_flags_ok = False
                failures.append("No thesis has risk flags")
    else:
        risk_flags_ok = True

    # --- 8. require_uncertainty ---
    uncertainty_ok = True
    if case.get("require_uncertainty"):
        if "不确定" not in content_md and "风险" not in content_md:
            uncertainty_ok = False
            failures.append("Content does not mention uncertainty/risk (不确定/风险)")
        # Also check claim-level uncertainty from content_json
        if artifact is not None:
            cj = _load_json_field(artifact, "content_json")
            if isinstance(cj, dict):
                claims = cj.get("claims", [])
                if claims:
                    any_uncertainty = False
                    for cl in claims:
                        if cl.get("uncertainty", "").strip():
                            any_uncertainty = True
                            break
                    if not any_uncertainty and thesis_count > 0:
                        uncertainty_ok = False
                        failures.append(
                            "Claims lack uncertainty field — expected uncertainty expressions"
                        )
    else:
        uncertainty_ok = True

    # --- 9. require_review_schedule ---
    if case.get("require_review_schedule"):
        all_have_schedule = True
        for t in thesis_records:
            sched_count = session.scalar(
                select(func.count(ResearchThesisReview.id)).where(
                    ResearchThesisReview.thesis_id == t.id
                )
            )
            if sched_count == 0:
                all_have_schedule = False
                failures.append(
                    f"Thesis #{t.id} ('{t.thesis_title[:60]}') has no review schedule"
                )
        if thesis_count == 0:
            review_schedule_ok = True
        else:
            review_schedule_ok = all_have_schedule
    else:
        review_schedule_ok = True

    return ThesisQualityResult(
        case_index=case_index,
        task_type_correct=True,  # filled by caller below
        thesis_count=thesis_count,
        thesis_count_ok=thesis_count_ok,
        evidence_ok=evidence_ok,
        invalidation_ok=invalidation_ok,
        horizon_ok=horizon_ok,
        confidence_ok=confidence_ok,
        forbidden_ok=forbidden_ok,
        risk_flags_ok=risk_flags_ok,
        uncertainty_ok=uncertainty_ok,
        review_schedule_ok=review_schedule_ok,
        failures=failures,
    )


def run_all_golden_cases_with_thesis_quality(
    session: Session,
) -> list[ThesisQualityResult]:
    """Run every golden case through the agent and validate thesis quality.

    Returns one ``ThesisQualityResult`` per case.
    """
    orchestrator = AgentOrchestrator(session)
    results: list[ThesisQualityResult] = []

    for idx, case in enumerate(GOLDEN_CASES):
        response = orchestrator.run(AgentRunRequest(user_prompt=str(case["prompt"])))
        artifact = (
            session.get(AgentArtifact, response.artifact_id) if response.artifact_id else None
        )

        # --- base checks (task type, required phrases, forbidden phrases) ---
        task_type_correct = response.selected_task_type == case["expected_task_type"]
        content = artifact.content_md if artifact else ""

        base_failures: list[str] = []
        if not task_type_correct:
            base_failures.append(
                f"Expected task type {case['expected_task_type']}, got {response.selected_task_type}"
            )

        for phrase in case.get("required_phrases", []):
            if phrase not in content:
                base_failures.append(f"Missing required phrase: {phrase}")

        # --- thesis quality checks ---
        quality_result = _check_thesis_quality(case, idx, artifact, session)

        # Merge base failures into quality result
        quality_result.task_type_correct = task_type_correct
        quality_result.failures.extend(base_failures)

        results.append(quality_result)

    return results
