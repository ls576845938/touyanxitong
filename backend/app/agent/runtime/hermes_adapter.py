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
        # Future version can connect to a Hermes sidecar via MCP/HTTP tools using
        # the ToolSpec registry (app.agent.tools.registry).  The MCP manifest is
        # available at GET /api/agent/tools/mcp-manifest so the sidecar can
        # discover and invoke Alpha Radar data tools without importing any Hermes
        # dependency in this codebase.
        raise NotImplementedError("Hermes runtime adapter is reserved but not enabled in this MVP.")
