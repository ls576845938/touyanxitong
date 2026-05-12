from __future__ import annotations

import json
from typing import Any, Protocol

import httpx
from loguru import logger

from app.config import settings
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


class OpenAIProvider:
    """Real provider calling OpenAI-compatible API."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url

    def generate_research_report(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            raise
