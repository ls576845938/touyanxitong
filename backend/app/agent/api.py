from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.guardrails import RISK_DISCLAIMER
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import (
    AgentArtifactClaim,
    AgentArtifactClaimRef,
    AgentArtifactResponse,
    AgentRunDetail,
    AgentRunRequest,
    AgentRunResponse,
    AgentSkillCreate,
    AgentSkillResponse,
    AgentStepResponse,
)
from app.agent.skills.registry import system_skill_by_id, system_skill_payloads
from app.db.models import AgentArtifact, AgentRun, AgentSkill, AgentStep
from app.db.session import get_session

router = APIRouter(prefix="/api/agent", tags=["agent"])


from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException


@router.post("/runs", response_model=AgentRunResponse, status_code=202)
def create_agent_run(
    payload: AgentRunRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    orchestrator = AgentOrchestrator(session)
    # Create the run record first
    run_id = orchestrator.create_run_record(payload)
    # Schedule the execution in the background
    background_tasks.add_task(orchestrator.execute_async, run_id, payload)
    
    # Return initial status
    return AgentRunResponse(
        run_id=run_id,
        status="pending",
        selected_task_type=payload.task_type or AgentTaskType.AUTO,
        report_title="正在排队...",
        summary="您的投研请求已进入后台处理队列，请稍后通过轮询获取结果。",
    )


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
def get_agent_run(run_id: int, session: Session = Depends(get_session)) -> AgentRunDetail:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent run not found")
    latest_artifact = session.scalars(
        select(AgentArtifact).where(AgentArtifact.run_id == run_id).order_by(AgentArtifact.created_at.desc()).limit(1)
    ).first()
    return AgentRunDetail(
        id=run.id,
        user_id=run.user_id,
        task_type=run.task_type,
        user_prompt=run.user_prompt,
        runtime_provider=run.runtime_provider,
        status=run.status,
        selected_symbols=_loads_list(run.selected_symbols_json),
        selected_industries=_loads_list(run.selected_industries_json),
        created_at=run.created_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        error_message=run.error_message,
        latest_artifact=_artifact_payload(latest_artifact) if latest_artifact else None,
    )


@router.get("/runs/{run_id}/steps", response_model=list[AgentStepResponse])
def get_agent_run_steps(run_id: int, session: Session = Depends(get_session)) -> list[AgentStepResponse]:
    _ensure_run(session, run_id)
    rows = session.scalars(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.created_at, AgentStep.id)).all()
    return [
        AgentStepResponse(
            id=row.id,
            run_id=row.run_id,
            step_name=row.step_name,
            agent_role=row.agent_role,
            status=row.status,
            input_json=_loads_dict(row.input_json),
            output_json=_loads_dict(row.output_json),
            error_message=row.error_message,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


@router.get("/runs/{run_id}/artifacts", response_model=list[AgentArtifactResponse])
def get_agent_run_artifacts(run_id: int, session: Session = Depends(get_session)) -> list[AgentArtifactResponse]:
    _ensure_run(session, run_id)
    rows = session.scalars(select(AgentArtifact).where(AgentArtifact.run_id == run_id).order_by(AgentArtifact.created_at, AgentArtifact.id)).all()
    return [_artifact_payload(row) for row in rows]


@router.post("/skills", response_model=AgentSkillResponse)
def create_agent_skill(payload: AgentSkillCreate, session: Session = Depends(get_session)) -> AgentSkillResponse:
    skill = AgentSkill(
        name=payload.name,
        description=payload.description,
        skill_type=str(payload.skill_type),
        skill_md=payload.skill_md,
        skill_config_json=json.dumps(payload.skill_config, ensure_ascii=False),
        owner_user_id=payload.owner_user_id,
        is_system=payload.is_system,
    )
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return _skill_payload(skill)


@router.get("/skills", response_model=list[AgentSkillResponse])
def list_agent_skills(session: Session = Depends(get_session)) -> list[AgentSkillResponse]:
    system_rows = [AgentSkillResponse(**payload) for payload in system_skill_payloads()]
    custom_rows = [
        _skill_payload(row)
        for row in session.scalars(select(AgentSkill).order_by(AgentSkill.is_system.desc(), AgentSkill.created_at.desc())).all()
    ]
    return system_rows + custom_rows


@router.get("/skills/{skill_id}", response_model=AgentSkillResponse)
def get_agent_skill(skill_id: str, session: Session = Depends(get_session)) -> AgentSkillResponse:
    system_skill = system_skill_by_id(skill_id)
    if system_skill is not None:
        payload = next(item for item in system_skill_payloads() if item["id"] == skill_id)
        return AgentSkillResponse(**payload)
    try:
        numeric_id = int(skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="agent skill not found") from exc
    skill = session.get(AgentSkill, numeric_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="agent skill not found")
    return _skill_payload(skill)


def _ensure_run(session: Session, run_id: int) -> None:
    if session.get(AgentRun, run_id) is None:
        raise HTTPException(status_code=404, detail="agent run not found")


def _artifact_payload(row: AgentArtifact) -> AgentArtifactResponse:
    content_json = _loads_dict(row.content_json)
    evidence_refs = [item for item in _loads_list(row.evidence_refs_json) if isinstance(item, dict)]
    claims = _artifact_claims(content_json)
    claim_refs = _artifact_claim_refs(claims, evidence_refs)
    if claims:
        content_json = {**content_json, "claims": [claim.model_dump() for claim in claims]}
    return AgentArtifactResponse(
        id=row.id,
        run_id=row.run_id,
        artifact_type=row.artifact_type,
        title=row.title,
        content_md=row.content_md,
        content_json=content_json,
        evidence_refs=evidence_refs,
        claims=claims,
        claim_refs=claim_refs,
        risk_disclaimer=RISK_DISCLAIMER,
        created_at=row.created_at.isoformat(),
    )


def _skill_payload(row: AgentSkill) -> AgentSkillResponse:
    return AgentSkillResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        skill_type=row.skill_type,
        skill_md=row.skill_md,
        skill_config=_loads_dict(row.skill_config_json),
        owner_user_id=row.owner_user_id,
        is_system=row.is_system,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


def _loads_list(raw: str | None) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _loads_dict(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _artifact_claims(content_json: dict[str, Any]) -> list[AgentArtifactClaim]:
    rows = content_json.get("claims")
    if not isinstance(rows, list):
        return []
    claims: list[AgentArtifactClaim] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        claims.append(
            AgentArtifactClaim(
                id=str(row.get("id") or f"C{index}"),
                section=str(row.get("section") or "未命名章节"),
                text=str(row.get("text") or ""),
                evidence_ref_ids=[str(item) for item in row.get("evidence_ref_ids", []) if item],
                source_tools=[str(item) for item in row.get("source_tools", []) if item],
                confidence=str(row.get("confidence") or "low"),
                uncertainty=str(row.get("uncertainty") or ""),
                user_prompt=str(row.get("user_prompt") or ""),
            )
        )
    return claims


def _artifact_claim_refs(claims: list[AgentArtifactClaim], evidence_refs: list[dict[str, Any]]) -> list[AgentArtifactClaimRef]:
    refs_by_id = {str(item.get("id")): item for item in evidence_refs if item.get("id")}
    return [
        AgentArtifactClaimRef(
            claim_id=claim.id,
            evidence_ref_ids=claim.evidence_ref_ids,
            evidence_refs=[refs_by_id[ref_id] for ref_id in claim.evidence_ref_ids if ref_id in refs_by_id],
            source_tools=claim.source_tools,
            missing_evidence_ref_ids=[ref_id for ref_id in claim.evidence_ref_ids if ref_id not in refs_by_id],
            has_evidence=bool(claim.evidence_ref_ids) and all(ref_id in refs_by_id for ref_id in claim.evidence_ref_ids),
        )
        for claim in claims
    ]
