from __future__ import annotations

from typing import Any, Protocol

from app.config import settings
from app.llm.openai_provider import OpenAIProvider
from app.llm.schemas import EvidenceChainSchema


class LLMProvider(Protocol):
    def generate_research_report(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        ...


class RuleBasedLLMProvider:
    """Safe local provider used by the MVP when no external LLM is configured."""

    def generate_research_report(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        # Simple heuristic to return something structured from the prompts
        return {
            "title": "Deterministic Research Report",
            "summary": "This is a deterministic fallback report.",
            "content_md": "## Fallback\nNo real LLM configured.",
            "content_json": {"claims": [], "evidence_refs": []}
        }


__all__ = ["LLMProvider", "OpenAIProvider", "RuleBasedLLMProvider"]
