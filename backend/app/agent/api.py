from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.guardrails import RISK_DISCLAIMER
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import (
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


@router.post("/runs", response_model=AgentRunResponse)
def create_agent_run(payload: AgentRunRequest, session: Session = Depends(get_session)) -> AgentRunResponse:
    return AgentOrchestrator(session).run(payload)


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
    return AgentArtifactResponse(
        id=row.id,
        run_id=row.run_id,
        artifact_type=row.artifact_type,
        title=row.title,
        content_md=row.content_md,
        content_json=_loads_dict(row.content_json),
        evidence_refs=[item for item in _loads_list(row.evidence_refs_json) if isinstance(item, dict)],
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
