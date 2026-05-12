from __future__ import annotations

from typing import Any

from app.agent.runtime.base import AgentRuntimeResult, RuntimeAdapter


class HermesRuntimeAdapter(RuntimeAdapter):
    provider_name = "hermes"

    def run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        # TODO: Future version can connect to a Hermes sidecar through MCP/HTTP
        # tools. Keep Alpha Radar business code behind this adapter boundary.
        raise NotImplementedError("Hermes runtime adapter is reserved but not enabled in this MVP.")
