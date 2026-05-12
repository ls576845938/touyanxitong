from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentRuntimeResult:
    title: str
    summary: str
    content_md: str
    content_json: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRuntimeChunk:
    type: str  # "token_delta" | "final" | "error"
    delta: str = ""  # incremental token text
    content: str = ""  # full content (for "final")
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeAdapter(ABC):
    provider_name = "base"

    @abstractmethod
    def run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        raise NotImplementedError

    @abstractmethod
    async def stream_run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
        on_event: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> AgentRuntimeResult:
        """Streaming version of run(). Yields AgentRuntimeChunk events via on_event callback.

        on_event receives (event_type, payload_dict) for each chunk.
        Returns the final AgentRuntimeResult with complete content.
        """
        raise NotImplementedError
