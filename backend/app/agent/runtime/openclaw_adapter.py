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
        # TODO: Future version can use OpenClaw as a multi-channel Gateway that
        # forwards requests into Alpha Radar Agent API. No OpenClaw dependency
        # is installed or imported in this MVP.
        raise NotImplementedError("OpenClaw runtime adapter is reserved but not enabled in this MVP.")
