from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceChainSchema(BaseModel):
    summary: str = ""
    industry_logic: str = ""
    company_logic: str = ""
    trend_logic: str = ""
    catalyst_logic: str = ""
    risk_summary: str = ""
    watch_reason: str = ""
    questions_to_verify: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, str]] = Field(default_factory=list)
