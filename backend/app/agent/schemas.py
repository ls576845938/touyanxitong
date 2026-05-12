from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentTaskType(StrEnum):
    STOCK_DEEP_RESEARCH = "stock_deep_research"
    INDUSTRY_CHAIN_RADAR = "industry_chain_radar"
    TREND_POOL_SCAN = "trend_pool_scan"
    TENBAGGER_CANDIDATE = "tenbagger_candidate"
    DAILY_MARKET_BRIEF = "daily_market_brief"
    AUTO = "auto"


class AgentRunRequest(BaseModel):
    user_prompt: str = Field(min_length=1, max_length=4000)
    task_type: AgentTaskType | None = AgentTaskType.AUTO
    symbols: list[str] | None = None
    industry_keywords: list[str] | None = None
    risk_preference: str | None = None
    time_window: str | None = None
    save_as_skill: bool = False
    user_id: str | None = None


class AgentRunResponse(BaseModel):
    run_id: int
    status: str
    selected_task_type: AgentTaskType
    report_title: str
    summary: str
    artifact_id: int | None = None
    warnings: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    step_name: str
    agent_role: str
    status: str
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""


class AgentStepResponse(AgentStep):
    id: int
    run_id: int
    created_at: str


class AgentArtifact(BaseModel):
    artifact_type: str
    title: str
    content_md: str
    content_json: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    claims: list["AgentArtifactClaim"] = Field(default_factory=list)
    claim_refs: list["AgentArtifactClaimRef"] = Field(default_factory=list)
    risk_disclaimer: str


class AgentArtifactResponse(AgentArtifact):
    id: int
    run_id: int
    created_at: str


class AgentToolCallResponse(BaseModel):
    id: int
    run_id: int
    tool_name: str
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
    success: bool
    error_message: str
    created_at: str


class AgentEventSSE(BaseModel):
    """SSE event payload for the /events streaming endpoint."""

    event: str
    run_id: int
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentArtifactClaim(BaseModel):
    id: str
    section: str
    text: str
    evidence_ref_ids: list[str] = Field(default_factory=list)
    source_tools: list[str] = Field(default_factory=list)
    confidence: str = "low"
    uncertainty: str = ""
    user_prompt: str = ""


class AgentArtifactClaimRef(BaseModel):
    claim_id: str
    evidence_ref_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_tools: list[str] = Field(default_factory=list)
    missing_evidence_ref_ids: list[str] = Field(default_factory=list)
    has_evidence: bool = False


class AgentRunDetail(BaseModel):
    id: int
    user_id: str | None = None
    task_type: AgentTaskType
    user_prompt: str
    runtime_provider: str
    status: str
    selected_symbols: list[str] = Field(default_factory=list)
    selected_industries: list[str] = Field(default_factory=list)
    created_at: str
    completed_at: str | None = None
    error_message: str = ""
    latest_artifact: AgentArtifactResponse | None = None


class FollowupMode(StrEnum):
    EXPLAIN = "explain"
    EXPAND_RISK = "expand_risk"
    EVIDENCE_DRILLDOWN = "evidence_drilldown"
    COMPARE = "compare"
    GENERATE_CHECKLIST = "generate_checklist"
    AUTO = "auto"


class AgentFollowupRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: FollowupMode = FollowupMode.AUTO
    save_as_artifact: bool = False


class AgentFollowupResponse(BaseModel):
    run_id: int
    followup_id: int
    mode: str
    answer_md: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    saved_artifact_id: int | None = None
    created_at: str


class AgentSkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    skill_type: AgentTaskType | str = AgentTaskType.AUTO
    skill_md: str = ""
    skill_config: dict[str, Any] = Field(default_factory=dict)
    owner_user_id: str | None = None
    is_system: bool = False


class AgentSkillResponse(BaseModel):
    id: int | str
    name: str
    description: str
    skill_type: str
    skill_md: str
    skill_config: dict[str, Any] = Field(default_factory=dict)
    owner_user_id: str | None = None
    is_system: bool
    created_at: str | None = None
    updated_at: str | None = None
