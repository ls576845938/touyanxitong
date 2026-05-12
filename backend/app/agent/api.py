from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.guardrails import RISK_DISCLAIMER, sanitize_financial_output
from app.agent.tools.registry import registry
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import (
    AgentArtifactClaim,
    AgentArtifactClaimRef,
    AgentArtifactResponse,
    AgentEventSSE,
    AgentFollowupRequest,
    AgentFollowupResponse,
    AgentRunDetail,
    AgentRunRequest,
    AgentRunResponse,
    AgentSkillCreate,
    AgentSkillResponse,
    AgentStepResponse,
    FollowupMode,
)
from app.agent.skills.registry import system_skill_by_id, system_skill_payloads
from app.db.models import AgentArtifact, AgentFollowup, AgentRun, AgentSkill, AgentStep, AgentToolCall, utcnow
from app.db.session import get_session

router = APIRouter(prefix="/api/agent", tags=["agent"])


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


@router.get("/runs/{run_id}/events")
async def stream_agent_run_events(run_id: int, session: Session = Depends(get_session)) -> StreamingResponse:
    """SSE event stream for an agent run (poll-to-SSE bridge).

    Opens a long-lived SSE connection that replays existing events and polls
    the DB for new steps, tool calls, and artifacts.  For completed runs all
    events are replayed then the connection closes.  For running/pending runs
    the connection stays open, sending heartbeats every 10 seconds.
    """
    _ensure_run(session, run_id)
    return StreamingResponse(
        _event_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/followups", response_model=AgentFollowupResponse, status_code=201)
def create_followup(
    run_id: int,
    payload: AgentFollowupRequest,
    session: Session = Depends(get_session),
) -> AgentFollowupResponse:
    _ensure_run(session, run_id)
    artifact = session.scalars(
        select(AgentArtifact)
        .where(AgentArtifact.run_id == run_id)
        .order_by(AgentArtifact.created_at.desc())
        .limit(1)
    ).first()
    if artifact is None:
        raise HTTPException(status_code=400, detail="该投研报告尚未完成, 无法追问.")

    evidence_refs = _loads_list(artifact.evidence_refs_json)
    answer_md, answer_warnings = _generate_followup_answer(
        message=payload.message,
        mode=str(payload.mode.value) if isinstance(payload.mode, FollowupMode) else str(payload.mode),
        original_title=artifact.title,
        original_content_md=artifact.content_md,
        evidence_refs=evidence_refs,
    )

    saved_artifact_id: int | None = None
    if payload.save_as_artifact:
        note = AgentArtifact(
            run_id=run_id,
            artifact_type="followup_note",
            title=f"追问:{payload.message[:80]}",
            content_md=answer_md,
            content_json=json.dumps({"followup_mode": str(payload.mode)}, ensure_ascii=False),
            evidence_refs_json=json.dumps(evidence_refs, ensure_ascii=False),
        )
        session.add(note)
        session.flush()
        saved_artifact_id = note.id

    followup = AgentFollowup(
        run_id=run_id,
        message=payload.message,
        mode=str(payload.mode.value) if isinstance(payload.mode, FollowupMode) else str(payload.mode),
        answer_md=answer_md,
        evidence_refs_json=json.dumps(evidence_refs, ensure_ascii=False),
        warnings_json=json.dumps(answer_warnings, ensure_ascii=False),
        saved_artifact_id=saved_artifact_id,
    )
    session.add(followup)
    session.commit()
    session.refresh(followup)

    return AgentFollowupResponse(
        run_id=run_id,
        followup_id=followup.id,
        mode=followup.mode,
        answer_md=followup.answer_md,
        evidence_refs=evidence_refs,
        warnings=answer_warnings,
        saved_artifact_id=saved_artifact_id,
        created_at=followup.created_at.isoformat(),
    )


@router.get("/runs/{run_id}/messages", response_model=list[dict[str, Any]])
def get_followup_messages(run_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    _ensure_run(session, run_id)
    rows = session.scalars(
        select(AgentFollowup)
        .where(AgentFollowup.run_id == run_id)
        .order_by(AgentFollowup.created_at, AgentFollowup.id)
    ).all()
    return [
        {
            "message_id": row.id,
            "mode": row.mode,
            "message": row.message,
            "answer_md": row.answer_md,
            "evidence_refs": _loads_list(row.evidence_refs_json),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


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


@router.get("/tools", summary="List all agent tool specs")
def list_tools() -> list[dict[str, Any]]:
    """Return every registered ToolSpec as a list of dictionaries."""
    return [spec.to_dict() for spec in registry.get_all_tools()]


@router.get("/tools/mcp-manifest", summary="MCP-compatible tool manifest")
def get_mcp_manifest() -> dict[str, Any]:
    """Return a standard MCP-ready JSON manifest for tool discovery.

    The manifest follows the MCP protocol shape:
    ``{"protocol": "mcp", "version": "1.0", "serverInfo": ..., "tools": [...]}``
    """
    return registry.get_mcp_manifest()


# ---------------------------------------------------------------------------
# SSE event-stream helpers (poll-to-SSE bridge)
# ---------------------------------------------------------------------------


def _ts(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    return dt.isoformat()


def _mk_sse_event(event: str, run_id: int, payload: dict[str, Any], timestamp: str | None = None) -> dict[str, Any]:
    return {"event": event, "run_id": run_id, "timestamp": timestamp or _ts(None), "payload": payload}


def _format_sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _event_generator(run_id: int) -> AsyncGenerator[str, None]:
    """Poll-to-SSE bridge: long-lived async generator.

    Replays existing steps/tool-calls/artifacts as SSE events, then polls
    every 1.5 seconds for new records.  Sends heartbeats every 10 seconds.
    Closes cleanly when the run reaches a terminal state or the client
    disconnects.
    """
    from app.db.session import SessionLocal
    from app.db.models import AgentStep as _AgentStep, AgentToolCall as _AgentToolCall, AgentArtifact as _AgentArtifact  # noqa: F811

    db = SessionLocal()
    try:
        run = db.get(AgentRun, run_id)
        if run is None:
            yield _format_sse(_mk_sse_event("error", run_id, {"detail": "agent run not found"}))
            return

        last_step_id: int = 0
        last_tc_id: int = 0
        last_art_id: int = 0
        last_known_status: str | None = None
        terminal_sent = False
        last_heartbeat = 0.0

        while True:
            # Refresh run from DB (avoid stale ORM cache)
            db.expire(run)
            run = db.get(AgentRun, run_id)
            status = run.status

            # ----- status transitions -----
            if last_known_status is None:
                # First iteration — replay initial events
                yield _format_sse(_mk_sse_event("run_created", run_id, {"status": status}, timestamp=_ts(run.created_at)))
                if status in ("running", "success", "failed"):
                    yield _format_sse(_mk_sse_event("run_started", run_id, {}))
            elif last_known_status == "pending" and status == "running":
                yield _format_sse(_mk_sse_event("run_started", run_id, {}))
            last_known_status = status

            # ----- poll for new steps -----
            step_rows = db.execute(
                select(_AgentStep)
                .where(_AgentStep.run_id == run_id, _AgentStep.id > last_step_id)
                .order_by(_AgentStep.id)
            ).scalars().all()
            for row in step_rows:
                yield _format_sse(
                    _mk_sse_event(
                        "step_started",
                        run_id,
                        {
                            "id": row.id,
                            "step_name": row.step_name,
                            "agent_role": row.agent_role,
                            "status": row.status,
                            "input": _loads_dict(row.input_json),
                        },
                        timestamp=_ts(row.created_at),
                    )
                )
                yield _format_sse(
                    _mk_sse_event(
                        "step_completed",
                        run_id,
                        {
                            "id": row.id,
                            "step_name": row.step_name,
                            "agent_role": row.agent_role,
                            "status": row.status,
                            "output": _loads_dict(row.output_json),
                            "error_message": row.error_message or "",
                        },
                        timestamp=_ts(row.created_at),
                    )
                )
                last_step_id = row.id

            # ----- poll for new tool calls -----
            tc_rows = db.execute(
                select(_AgentToolCall)
                .where(_AgentToolCall.run_id == run_id, _AgentToolCall.id > last_tc_id)
                .order_by(_AgentToolCall.id)
            ).scalars().all()
            for row in tc_rows:
                yield _format_sse(
                    _mk_sse_event(
                        "tool_call_started",
                        run_id,
                        {
                            "id": row.id,
                            "tool_name": row.tool_name,
                            "input": _loads_dict(row.input_json),
                        },
                        timestamp=_ts(row.created_at),
                    )
                )
                yield _format_sse(
                    _mk_sse_event(
                        "tool_call_completed",
                        run_id,
                        {
                            "id": row.id,
                            "tool_name": row.tool_name,
                            "output": _loads_dict(row.output_json),
                            "latency_ms": row.latency_ms,
                            "success": row.success,
                            "error_message": row.error_message or "",
                        },
                        timestamp=_ts(row.created_at),
                    )
                )
                last_tc_id = row.id

            # ----- poll for new artifacts -----
            art_rows = db.execute(
                select(_AgentArtifact)
                .where(_AgentArtifact.run_id == run_id, _AgentArtifact.id > last_art_id)
                .order_by(_AgentArtifact.id)
            ).scalars().all()
            for row in art_rows:
                yield _format_sse(
                    _mk_sse_event(
                        "artifact_created",
                        run_id,
                        {
                            "id": row.id,
                            "artifact_type": row.artifact_type,
                            "title": row.title,
                        },
                        timestamp=_ts(row.created_at),
                    )
                )
                last_art_id = row.id

            # ----- terminal check -----
            if status in ("success", "failed") and not terminal_sent:
                event_type = "run_completed" if status == "success" else "run_failed"
                yield _format_sse(
                    _mk_sse_event(
                        event_type,
                        run_id,
                        {
                            "status": status,
                            "error_message": run.error_message or "",
                            "completed_at": _ts(run.completed_at),
                        },
                    )
                )
                terminal_sent = True

            if terminal_sent:
                return

            # ----- heartbeat -----
            now = time.monotonic()
            if now - last_heartbeat >= 10:
                yield _format_sse(_mk_sse_event("heartbeat", run_id, {}))
                last_heartbeat = now

            await asyncio.sleep(1.5)

    except asyncio.CancelledError:
        pass  # Client disconnected — clean exit
    except Exception:
        pass  # Swallow unexpected errors to avoid unhandled coroutine warnings
    finally:
        db.close()


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


def _generate_followup_answer(
    message: str,
    mode: str,
    original_title: str,
    original_content_md: str,
    evidence_refs: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Generate a minimal follow-up answer referencing the original report.

    Uses mock-style template generation (no AI call) for MVP 2.1.
    The answer references original evidence refs, goes through guardrails,
    includes RISK_DISCLAIMER, and does not give buy/sell advice.
    """
    answer_lines: list[str] = []
    mode_label = _followup_mode_label(mode)
    answer_lines.append(f"# 追问回答: {mode_label}")
    answer_lines.append("")
    answer_lines.append(f"## 用户问题")
    answer_lines.append(message)
    answer_lines.append("")
    answer_lines.append(f"## 回答")
    answer_lines.append(f"以下基于《{original_title}》的分析整理如下:")

    if mode in ("", "auto", "explain"):
        answer_lines.append("")
        answer_lines.append("根据原有报告内容，针对您的问题梳理关键要点如下：")
        answer_lines.append("- 报告核心逻辑已在原文中展开，此部分为您做重点提取。")
        answer_lines.append("- 如需进一步深入某一方面，可以选择不同的追问模式。")
    elif mode == "expand_risk":
        answer_lines.append("")
        answer_lines.append("以下是针对报告中提及的风险因素展开分析：")
        answer_lines.append("- 报告中涉及的风险因素主要包括行业风险、公司经营风险和估值波动风险。")
        answer_lines.append("- 行业风险：需关注政策变化、技术迭代和竞争格局演变。")
        answer_lines.append("- 公司风险：需验证财务数据真实性、管理层能力和治理结构。")
        answer_lines.append("- 估值风险：当前估值是否已充分反映潜在负面因素。")
    elif mode == "evidence_drilldown":
        answer_lines.append("")
        answer_lines.append("以下是针对报告中引用的证据进行深入分析：")
        answer_lines.append("- 报告引用的证据来源包括结构化数据（行情、财务）和外部来源。")
        answer_lines.append("- 每条证据的置信度已在原文中标注，需结合数据质量门综合判断。")
        answer_lines.append("- 对于低置信度或模拟数据来源，结论仅作为待验证线索。")
    elif mode == "compare":
        answer_lines.append("")
        answer_lines.append("以下是基于报告进行对比分析：")
        answer_lines.append("- 当前报告主要聚焦单一标的/行业，对比分析需要获取多个标的的数据。")
        answer_lines.append("- 建议使用新的研究请求来进行多标的对比分析。")
    elif mode == "generate_checklist":
        answer_lines.append("")
        answer_lines.append("以下是基于报告生成的跟踪检查清单：")
        answer_lines.append("- [ ] 复核报告中的数据来源和置信度标签")
        answer_lines.append("- [ ] 验证关键证据的真实性和时效性")
        answer_lines.append("- [ ] 检查是否存在反证信息未被纳入")
        answer_lines.append("- [ ] 评估数据质量门对结论的影响程度")
        answer_lines.append("- [ ] 确认是否达到独立决策所需的信息充分度")

    if evidence_refs:
        answer_lines.append("")
        answer_lines.append("## 参考来源")
        for ref in evidence_refs[:6]:
            title = ref.get("title") or ref.get("source") or "未命名来源"
            ref_id = ref.get("id") or ""
            answer_lines.append(f"- [{ref_id}] {title}")

    answer_lines.append("")
    raw_answer = "\n".join(answer_lines)

    sanitized, warnings = sanitize_financial_output(raw_answer)
    return sanitized, warnings


def _followup_mode_label(mode: str) -> str:
    labels = {
        "explain": "解释说明",
        "expand_risk": "风险展开",
        "evidence_drilldown": "证据深入",
        "compare": "对比分析",
        "generate_checklist": "生成检查清单",
        "auto": "自动追问",
    }
    return labels.get(mode, "自动追问")
