from __future__ import annotations

from typing import Protocol

from app.llm.schemas import EvidenceChainSchema


class LLMProvider(Protocol):
    def generate_evidence_summary(self, payload: dict[str, object]) -> EvidenceChainSchema:
        ...


class RuleBasedLLMProvider:
    """Safe local provider used by the MVP when no external LLM is configured."""

    def generate_evidence_summary(self, payload: dict[str, object]) -> EvidenceChainSchema:
        return EvidenceChainSchema(
            summary=str(payload.get("summary", "当前证据不足，不能形成有效观察结论。")),
            industry_logic=str(payload.get("industry_logic", "")),
            company_logic=str(payload.get("company_logic", "")),
            trend_logic=str(payload.get("trend_logic", "")),
            catalyst_logic=str(payload.get("catalyst_logic", "")),
            risk_summary=str(payload.get("risk_summary", "")),
            watch_reason=str(payload.get("watch_reason", "进入观察池需要继续验证产业、财务、趋势和风险证据。")),
            questions_to_verify=list(payload.get("questions_to_verify", [])),
            source_refs=list(payload.get("source_refs", [])),
        )
