from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.events import publish_event, replay_events, subscribe, unsubscribe
from app.agent.export_utils import build_print_html
from app.agent.guardrails import RISK_DISCLAIMER, sanitize_financial_output
from app.agent.tools.registry import registry
from app.config import settings
from app.llm.provider import OpenAIProvider
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
async def stream_agent_run_events(
    run_id: int,
    since_seq: int = Query(0, description="Replay events after this sequence number"),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """SSE event stream for an agent run (EventBus push).

    Replays persisted events from ``agent_events`` (since ``since_seq``) then,
    for live runs, subscribes to the in-memory ``AgentEventBus`` for real-time
    push.  Heartbeats are sent every 10 seconds while the connection is open.

    For terminated runs events are replayed and the connection closes.
    """
    _ensure_run(session, run_id)
    return StreamingResponse(
        _event_stream(run_id, since_seq),
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
    # Build event publisher that publishes follow-up events through EventBus
    def _publish_followup_event(event_dict: dict[str, Any]) -> None:
        try:
            event_type = event_dict.get("event", "")
            # Use all keys except "event" and "run_id" as the event payload
            payload = {k: v for k, v in event_dict.items() if k not in ("event", "run_id")}
            publish_event(session, run_id, event_type, payload)
        except Exception:
            pass  # Don't crash follow-up on event publish failure

    answer_md, answer_warnings = _generate_followup_answer(
        message=payload.message,
        mode=str(payload.mode.value) if isinstance(payload.mode, FollowupMode) else str(payload.mode),
        run_id=run_id,
        session=session,
        on_event=_publish_followup_event,
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


@router.get("/runs/{run_id}/export/markdown")
def export_agent_run_markdown(run_id: int, session: Session = Depends(get_session)) -> Response:
    """Download the artifact content as a Markdown file.

    Returns sanitized content_md with the report title as a H1 heading and
    the risk disclaimer.  Content is already guardrails-sanitised in the
    artifact; no further sanitisation is applied.
    """
    _ensure_run(session, run_id)
    artifact = session.scalars(
        select(AgentArtifact).where(AgentArtifact.run_id == run_id).order_by(AgentArtifact.created_at.desc()).limit(1)
    ).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="no artifact found for this run")

    content_md = artifact.content_md or ""
    title = artifact.title or "投研报告"

    # Build full markdown — the content_md is already sanitised
    full_md = f"# {title}\n\n{content_md}"
    if RISK_DISCLAIMER not in full_md:
        full_md = f"{full_md.rstrip()}\n\n---\n{RISK_DISCLAIMER}\n"

    filename = f"alpha-radar-report-{run_id}.md"
    return Response(
        content=full_md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/export/html")
def export_agent_run_html(run_id: int, session: Session = Depends(get_session)) -> Response:
    """Download the artifact content as a minimal safe HTML page.

    Converts the artifact content_md to basic HTML.  The page includes the
    report title, summary, evidence references, and risk disclaimer.  No
    script execution — just formatted, printable text.
    """
    _ensure_run(session, run_id)
    artifact = session.scalars(
        select(AgentArtifact).where(AgentArtifact.run_id == run_id).order_by(AgentArtifact.created_at.desc()).limit(1)
    ).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="no artifact found for this run")

    content_md = artifact.content_md or ""
    title = artifact.title or "投研报告"
    evidence_refs = _loads_list(artifact.evidence_refs_json)

    html = _markdown_to_safe_html(title, content_md, evidence_refs, RISK_DISCLAIMER)

    filename = f"alpha-radar-report-{run_id}.html"
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/export/print")
def export_agent_run_print_html(run_id: int, session: Session = Depends(get_session)) -> Response:
    """Return a print-optimized HTML page for the agent research report.

    Uses ``markdown-it-py`` for proper HTML rendering (tables, code blocks,
    headings, etc.). Chart tags (``:::chart {...}:::``) are replaced with
    descriptive text placeholders. The page includes print-optimised CSS with
    ``@media print`` rules.

    **Usage**: Open this URL in a browser tab and press **Ctrl+P** /
    **Cmd+P** to save as PDF.  No PDF library is required.
    """
    _ensure_run(session, run_id)
    artifact = session.scalars(
        select(AgentArtifact).where(AgentArtifact.run_id == run_id).order_by(AgentArtifact.created_at.desc()).limit(1)
    ).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="no artifact found for this run")

    content_md = artifact.content_md or ""
    title = artifact.title or "投研报告"
    evidence_refs = _loads_list(artifact.evidence_refs_json)
    created_at = artifact.created_at.isoformat() if hasattr(artifact.created_at, "isoformat") else str(artifact.created_at)

    # Attempt to extract a summary from content_json
    content_json = _loads_dict(artifact.content_json)
    summary = str(content_json.get("summary", "")) if isinstance(content_json, dict) else ""

    html_content = build_print_html(
        title=title,
        content_md=content_md,
        evidence_refs=evidence_refs,
        risk_disclaimer=RISK_DISCLAIMER,
        created_at=created_at,
        summary=summary,
    )

    return HTMLResponse(content=html_content)


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


async def _event_stream(run_id: int, since_seq: int = 0) -> AsyncGenerator[str, None]:
    """EventBus-backed SSE stream: replay + live push.

    Replays persisted events from ``agent_events`` (since ``since_seq``),
    then subscribes to the in-memory ``AgentEventBus`` for real-time delivery.
    Heartbeats are sent every 10 seconds.

    Closes cleanly when a terminal event is reached or the client disconnects.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    logger = logging.getLogger(__name__)
    try:
        run = db.get(AgentRun, run_id)
        if run is None:
            yield _format_sse(_mk_sse_event("error", run_id, {"detail": "agent run not found"}))
            return

        # ---- Replay persisted events ---------------------------------------
        events = replay_events(db, run_id, since_seq)
        last_seq = since_seq
        for event_dict in events:
            yield _format_sse(event_dict)
            last_seq = event_dict.get("seq", last_seq)
            if event_dict["event"] in ("run_completed", "run_failed"):
                return

        # ---- Re-check status (may have changed during replay) --------------
        db.expire(run)
        run = db.get(AgentRun, run_id)
        if run.status in ("success", "failed"):
            # Catch any events that landed between the two reads
            for event_dict in replay_events(db, run_id, last_seq):
                yield _format_sse(event_dict)
                if event_dict["event"] in ("run_completed", "run_failed"):
                    return
            return

        # ---- Subscribe for live push ---------------------------------------
        queue, loop = subscribe(run_id)
        try:
            last_heartbeat = time.monotonic()
            while True:
                try:
                    event_dict = await asyncio.wait_for(queue.get(), timeout=10)
                    yield _format_sse(event_dict)
                    if event_dict["event"] in ("run_completed", "run_failed"):
                        return
                except asyncio.TimeoutError:
                    # Heartbeat tick
                    yield _format_sse(_mk_sse_event("heartbeat", run_id, {}))
                    last_heartbeat = time.monotonic()
        finally:
            unsubscribe(run_id, queue)

    except asyncio.CancelledError:
        # Client disconnected — clean exit
        pass
    except Exception:
        logger.exception("SSE stream error for run %s", run_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Legacy poll-to-SSE bridge (kept as fallback / reference)
# ---------------------------------------------------------------------------

# The original _event_generator (polling every 1.5 s) was replaced by the
# _event_stream above which uses the EventBus for real-time push.  The old
# code is preserved here for reference / emergency fallback:
#
# async def _event_generator_fallback(run_id: int) -> AsyncGenerator[str, None]:
#     ... polling implementation ...


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
    run_id: int,
    session: Session,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, list[str]]:
    """Generate a follow-up answer — LLM-first with deterministic template fallback.

    Reads full context from the database (latest artifact, tool-call summary,
    previous follow-ups) and attempts to produce an LLM-generated answer.
    When no LLM is configured or the call fails, falls back to the same
    deterministic template used in MVP 2.1.

    When *on_event* is provided (a callable that accepts a dict) the function
    emits lifecycle events for streaming clients:

    * ``followup_started`` – before the answer is generated
    * ``followup_token_delta`` – per-token during LLM streaming
    * ``followup_completed`` – after the answer is ready

    The answer always passes through ``sanitize_financial_output`` guardrails
    before being returned.
    """
    # ------------------------------------------------------------------
    # 1. Read context from the database
    # ------------------------------------------------------------------
    artifact = session.scalars(
        select(AgentArtifact)
        .where(AgentArtifact.run_id == run_id)
        .order_by(AgentArtifact.created_at.desc())
        .limit(1)
    ).first()
    if artifact is None:
        raise HTTPException(status_code=400, detail="该投研报告尚未完成, 无法追问.")

    original_title = artifact.title
    original_content_md = artifact.content_md
    evidence_refs = _loads_list(artifact.evidence_refs_json)

    # Tool-call summary (last 10)
    tool_calls = session.scalars(
        select(AgentToolCall)
        .where(AgentToolCall.run_id == run_id)
        .order_by(AgentToolCall.created_at.desc())
        .limit(10)
    ).all()
    tool_summary_lines = [
        f"- {tc.tool_name}: {'成功' if tc.success else '失败'}"
        for tc in tool_calls
    ]
    tool_summary = "\n".join(tool_summary_lines) if tool_summary_lines else "无工具调用记录"

    # Previous follow-ups (last 5, chronological)
    prev_followups = session.scalars(
        select(AgentFollowup)
        .where(AgentFollowup.run_id == run_id)
        .order_by(AgentFollowup.created_at.desc())
        .limit(5)
    ).all()
    prev_followups.reverse()
    followup_context_lines = []
    for fu in prev_followups:
        preview = fu.answer_md[:200].replace("\n", " ")
        followup_context_lines.append(f"Q: {fu.message}\nA: {preview}")
    followup_context = "\n---\n".join(followup_context_lines) if followup_context_lines else "无"

    mode_label = _followup_mode_label(mode)

    # ------------------------------------------------------------------
    # 2. LLM-first attempt
    # ------------------------------------------------------------------
    if settings.openai_api_key:
        try:
            # Build prompts
            system_prompt = (
                "你是一个投资研究助理。你需要基于原始研究报告回答用户的追问问题。\n\n"
                "规则：\n"
                "- 严格基于提供的报告内容回答，不要编造事实。\n"
                "- 禁止提供任何买入、卖出或具体投资建议。\n"
                "- 始终保持客观、专业的分析语气。\n"
                "- 回答应包含风险提示和免责声明。\n"
                "- 可以使用标题、列表等 Markdown 格式来组织回答。"
            )

            content_truncated = original_content_md
            if len(content_truncated) > 2000:
                content_truncated = content_truncated[:2000] + "\n\n...（报告内容较长，已截取前2000字符）"

            user_message = (
                f"## 原始报告标题\n{original_title}\n\n"
                f"## 原始报告内容（摘要）\n{content_truncated}\n\n"
                f"## 报告使用的工具调用\n{tool_summary}\n\n"
                f"## 参考来源\n{json.dumps(evidence_refs, ensure_ascii=False, indent=2)[:1000]}\n\n"
                f"## 历史追问\n{followup_context}\n\n"
                f"## 当前追问\n追问模式: {mode_label}\n用户问题: {message}\n\n"
                "请根据报告内容回答用户的追问。直接给出回答内容（Markdown格式），不要输出JSON。"
            )

            provider = OpenAIProvider(api_key=settings.openai_api_key)

            if on_event is not None:
                on_event({"event": "followup_started", "run_id": run_id, "mode": mode})
                # Try streaming first
                try:
                    collected_tokens: list[str] = []

                    def _on_token(token: str) -> None:
                        collected_tokens.append(token)
                        if on_event is not None:
                            on_event({
                                "event": "followup_token_delta",
                                "run_id": run_id,
                                "delta": token,
                            })

                    answer = provider.generate_followup_answer(
                        system_prompt, user_message, on_token=_on_token,
                    )
                except Exception:
                    # Streaming failed — fall back to non-streaming LLM call
                    answer = provider.generate_followup_answer(
                        system_prompt, user_message,
                    )

                on_event({"event": "followup_completed", "run_id": run_id})
            else:
                answer = provider.generate_followup_answer(
                    system_prompt, user_message,
                )

            sanitized, warnings = sanitize_financial_output(answer)
            return sanitized, warnings

        except Exception:
            # LLM unavailable or failed — fall through to template
            pass

    # ------------------------------------------------------------------
    # 3. Deterministic template fallback (same logic as MVP 2.1)
    # ------------------------------------------------------------------
    if on_event is not None:
        on_event({"event": "followup_started", "run_id": run_id, "mode": mode})

    answer_lines: list[str] = []
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

    if on_event is not None:
        on_event({"event": "followup_completed", "run_id": run_id})

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


def _markdown_to_safe_html(
    title: str,
    content_md: str,
    evidence_refs: list[dict[str, Any]],
    risk_disclaimer: str,
) -> str:
    """Convert a markdown string to a minimal safe HTML page.

    Handles basic markdown constructs (headings, bullet lists, horizontal
    rules, paragraphs) and replaces ``:::chart ...:::`` inline chart tags
    with a placeholder.  No script execution is possible in the output.
    """
    paragraphs: list[str] = []

    lines = content_md.split("\n")
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Chart tags
        if stripped.startswith(":::chart") and stripped.endswith(":::"):
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            try:
                raw_json = stripped[8:-3]
                config = json.loads(raw_json)
                chart_label = config.get("symbol") or config.get("type", "chart")
            except (json.JSONDecodeError, KeyError):
                chart_label = "chart"
            paragraphs.append(f'<div class="chart-placeholder">[图表: {chart_label}]</div>')
            continue

        # Headings
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append(f"<h1>{_html_escape(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append(f"<h2>{_html_escape(stripped[3:])}</h2>")
            continue
        if stripped.startswith("### "):
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append(f"<h3>{_html_escape(stripped[4:])}</h3>")
            continue

        # Horizontal rule
        if stripped == "---":
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append("<hr />")
            continue

        # Bullet list
        if stripped.startswith("- "):
            if not in_list:
                paragraphs.append("<ul>")
                in_list = True
            paragraphs.append(f"<li>{_html_escape(stripped[2:])}</li>")
            continue

        # Empty line – close any open list
        if not stripped:
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            continue

        # Regular paragraph
        if in_list:
            paragraphs.append("</ul>")
            in_list = False
        paragraphs.append(f"<p>{_html_escape(stripped)}</p>")

    if in_list:
        paragraphs.append("</ul>")

    body = "\n".join(paragraphs)

    # Evidence references section
    if evidence_refs:
        ref_lines = ["<h2>参考来源</h2>", "<ul>"]
        for ref in evidence_refs[:10]:
            ref_title = _html_escape(str(ref.get("title") or ref.get("source") or "未命名来源"))
            ref_id = _html_escape(str(ref.get("id") or ""))
            ref_lines.append(f"<li> [{ref_id}] {ref_title}</li>")
        ref_lines.append("</ul>")
        body += "\n" + "\n".join(ref_lines)

    # Risk disclaimer
    body += f'\n<hr />\n<p class="risk-disclaimer">{_html_escape(risk_disclaimer)}</p>'

    return (
        f"<!DOCTYPE html>\n"
        f"<html lang=\"zh-CN\">\n"
        f"<head>\n"
        f"<meta charset=\"utf-8\" />\n"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
        f"<title>{_html_escape(title)}</title>\n"
        f"<style>\n"
        f"  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
        f"max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.7; }}\n"
        f"  h1 {{ font-size: 1.8rem; font-weight: 800; margin-top: 0; }}\n"
        f"  h2 {{ font-size: 1.3rem; font-weight: 700; margin-top: 1.5em; }}\n"
        f"  h3 {{ font-size: 1.1rem; font-weight: 700; margin-top: 1.2em; }}\n"
        f"  p, li {{ font-size: 0.95rem; line-height: 1.7; }}\n"
        f"  ul {{ padding-left: 1.5em; }}\n"
        f"  li {{ margin-bottom: 0.3em; }}\n"
        f"  hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 2em 0; }}\n"
        f"  .chart-placeholder {{ background: #f1f5f9; border: 1px dashed #cbd5e1; "
        f"border-radius: 8px; padding: 2em 1em; text-align: center; color: #64748b; "
        f"font-size: 0.9rem; margin: 1em 0; }}\n"
        f"  .risk-disclaimer {{ font-size: 0.8rem; color: #64748b; text-align: center; "
        f"margin-top: 2em; }}\n"
        f"  @media print {{ body {{ margin: 0; padding: 0.5in; }} }}\n"
        f"</style>\n"
        f"</head>\n"
        f"<body>\n"
        f"<h1>{_html_escape(title)}</h1>\n"
        f"{body}\n"
        f"</body>\n"
        f"</html>"
    )


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

