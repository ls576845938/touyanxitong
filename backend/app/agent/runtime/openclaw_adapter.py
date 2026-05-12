from __future__ import annotations

from typing import Any

from app.agent.runtime.base import AgentRuntimeResult, RuntimeAdapter


class OpenClawRuntimeAdapter(RuntimeAdapter):
    provider_name = "openclaw"

    def run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        # Future version can use OpenClaw as a Gateway that forwards requests to
        # the Alpha Radar Agent API.  The MCP manifest at GET /api/agent/tools/mcp-manifest
        # allows OpenClaw to discover available tools and route tool calls to the
        # corresponding endpoints.  No OpenClaw dependency is imported here.
        raise NotImplementedError("OpenClaw runtime adapter is reserved but not enabled in this MVP.")
