from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from app.agent.runtime.base import AgentRuntimeResult, RuntimeAdapter

# ---------------------------------------------------------------------------
# Hermes sidecar configuration
# ---------------------------------------------------------------------------
# HERMES_ENDPOINT – when set, the adapter forwards requests to an external
#   Hermes service via HTTP.  The endpoint should be the base URL of the
#   Hermes server (e.g. http://hermes:8000).
# HERMES_ENABLED  – gate used by the provider-selection layer.  The adapter
#   itself does not check this flag; it can be selected regardless.
HERMES_ENDPOINT = os.getenv("HERMES_ENDPOINT", "")
HERMES_ENABLED = os.getenv("HERMES_ENABLED", "false").lower() == "true"


class HermesRuntimeAdapter(RuntimeAdapter):
    """Runtime adapter that follows the Hermes sidecar pattern.

    What makes this "Hermes" vs other adapters:

    1. Tool discovery via MCP manifest (``ToolRegistry.get_mcp_manifest()``).
    2. Structured tool calling with an MCP-compatible request/response format.
    3. Can be configured with ``HERMES_ENDPOINT`` to forward to an external
       Hermes service via HTTP.
    4. When no external endpoint is configured: acts as a local sidecar that
       delegates to ``RealRuntimeAdapter`` (LLM) with ``MockRuntimeAdapter``
       fallback, enriched with the MCP tool manifest.

    No external Hermes SDK or package is imported.
    """

    provider_name = "hermes"

    def __init__(self) -> None:
        from app.agent.tools.registry import registry

        self._manifest = registry.get_mcp_manifest()
        self._tool_specs = registry.get_all_tools()
        self._endpoint = HERMES_ENDPOINT

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        """Process a research request via the Hermes sidecar pattern.

        * If ``HERMES_ENDPOINT`` is configured: forward the request to the
          external Hermes service via HTTP.
        * Otherwise: run locally as a sidecar, enriching the context with
          the MCP tool manifest and delegating to ``RealRuntimeAdapter``
          (LLM) with automatic ``MockRuntimeAdapter`` fallback.
        """
        if self._endpoint:
            return self._forward_run(prompt, context, tools, skill_template)
        return self._local_sidecar_run(prompt, context, tools, skill_template)

    async def stream_run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
        on_event: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> AgentRuntimeResult:
        """Streaming version of :meth:`run`.

        * If ``HERMES_ENDPOINT`` is configured: stream from the external
          Hermes service via HTTP SSE.
        * Otherwise: delegate to ``RealRuntimeAdapter.stream_run()`` with
          automatic fallback.
        """
        if self._endpoint:
            return await self._forward_stream_run(
                prompt, context, tools, skill_template, on_event=on_event
            )
        return await self._local_sidecar_stream_run(
            prompt, context, tools, skill_template, on_event=on_event
        )

    # ------------------------------------------------------------------
    # Context enrichment  (the "Hermes" differentiator)
    # ------------------------------------------------------------------

    def _enrich_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Inject MCP tool manifest and sidecar marker into the context dict.

        Downstream adapters (``RealRuntimeAdapter`` / ``MockRuntimeAdapter``)
        can inspect these fields to discover available tools and adjust their
        report-generation behaviour.
        """
        return {
            **context,
            "_hermes_manifest": self._manifest,
            "_hermes_sidecar": True,
        }

    # ------------------------------------------------------------------
    # Local sidecar mode
    # ------------------------------------------------------------------

    def _local_sidecar_run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        """Run locally: enrich context with MCP manifest, then delegate.

        The ``RealRuntimeAdapter`` checks whether ``settings.openai_api_key``
        is available and falls back to ``MockRuntimeAdapter`` if not — so
        the Hermes sidecar inherits that fallback chain automatically.
        """
        enriched = self._enrich_context(context)
        from app.agent.runtime.real_adapter import RealRuntimeAdapter

        return RealRuntimeAdapter().run(prompt, enriched, tools, skill_template)

    async def _local_sidecar_stream_run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
        on_event: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> AgentRuntimeResult:
        """Streaming version of local sidecar run."""
        enriched = self._enrich_context(context)
        from app.agent.runtime.real_adapter import RealRuntimeAdapter

        return await RealRuntimeAdapter().stream_run(
            prompt, enriched, tools, skill_template, on_event=on_event
        )

    # ------------------------------------------------------------------
    # External Hermes endpoint mode  (HTTP forwarding)
    # ------------------------------------------------------------------

    def _forward_run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> AgentRuntimeResult:
        """Forward the run request to an external Hermes service via HTTP.

        The payload includes the full MCP tool manifest so the remote Hermes
        can discover available tools without any out-of-band configuration.
        """
        import httpx

        payload = self._build_payload(prompt, context, tools, skill_template)
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{self._endpoint.rstrip('/')}/api/hermes/run",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
            return self._parse_response(data)
        except Exception as exc:
            return self._fallback_on_error(prompt, context, tools, skill_template, exc)

    async def _forward_stream_run(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
        on_event: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> AgentRuntimeResult:
        """Forward the stream run request to an external Hermes service.

        Expects a newline-delimited JSON stream (each line is a
        ``AgentRuntimeChunk``-compatible event).  Supports the event types
        ``token_delta``, ``final``, and ``error``.
        """
        import httpx

        payload = self._build_payload(prompt, context, tools, skill_template)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._endpoint.rstrip('/')}/api/hermes/run",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()

                    full_content: list[str] = []
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        event_type = chunk.get("type", "token_delta")

                        if event_type == "token_delta":
                            delta = chunk.get("delta", "")
                            if delta:
                                full_content.append(delta)
                                if on_event:
                                    on_event("token_delta", {"delta": delta})

                        elif event_type == "final":
                            data = chunk.get("data", {})
                            if on_event:
                                on_event("final", data)
                            return self._parse_response(data)

                        elif event_type == "error":
                            error_msg = chunk.get(
                                "message", "Unknown Hermes streaming error"
                            )
                            if on_event:
                                on_event("error", {"message": error_msg})
                            return self._fallback_on_error(
                                prompt, context, tools, skill_template,
                                Exception(error_msg),
                            )

                    # If the stream ended without a "final" event, build a result
                    # from whatever content was accumulated.
                    return AgentRuntimeResult(
                        title="Hermes 投研报告",
                        summary="已通过 Hermes 侧车模式生成投研分析。",
                        content_md="".join(full_content),
                        content_json={},
                        evidence_refs=[],
                        warnings=["External Hermes stream ended without a final event."],
                    )

        except Exception as exc:
            return self._fallback_on_error(
                prompt, context, tools, skill_template, exc
            )

    # ------------------------------------------------------------------
    # Payload and response helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
    ) -> dict[str, Any]:
        """Build the JSON payload sent to an external Hermes endpoint."""
        return {
            "prompt": prompt,
            "context": context,
            "tools": [spec.to_dict() for spec in self._tool_specs],
            "skill_template": skill_template,
            "mcp_manifest": self._manifest,
        }

    def _parse_response(self, data: dict[str, Any]) -> AgentRuntimeResult:
        """Parse an external Hermes response into an ``AgentRuntimeResult``."""
        return AgentRuntimeResult(
            title=str(data.get("title") or "Hermes 投研报告"),
            summary=str(
                data.get("summary") or "已通过 Hermes 侧车模式生成投研分析。"
            ),
            content_md=str(
                data.get("content_md") or data.get("content_markdown") or ""
            ),
            content_json=data.get("content_json") or {},
            evidence_refs=(
                data.get("evidence_refs")
                or data.get("content_json", {}).get("evidence_refs")
                or []
            ),
            warnings=data.get("warnings") or [],
        )

    def _fallback_on_error(
        self,
        prompt: str,
        context: dict[str, Any],
        tools: dict[str, Any],
        skill_template: str,
        exc: Exception,
    ) -> AgentRuntimeResult:
        """Fall back to mock adapter when external Hermes is unreachable."""
        from app.agent.runtime.mock_adapter import MockRuntimeAdapter

        result = MockRuntimeAdapter().run(prompt, context, tools, skill_template)
        result.warnings.append(
            f"Hermes external endpoint unreachable, fell back to deterministic "
            f"template. Error: {exc}"
        )
        return result
