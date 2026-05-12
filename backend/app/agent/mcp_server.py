"""Lightweight MCP-compatible JSON-RPC 2.0 server for Alpha Radar tools.

No external MCP SDK required.  Supports ``tools/list``, ``tools/call``,
and ``initialize`` — the three methods needed for read-only MCP tool
execution over HTTP or stdio transport.
"""

from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable

from app.agent.tools import (
    evidence_tools,
    industry_tools,
    market_tools,
    report_tools,
    scoring_tools,
)
from app.agent.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Tool function map — maps every spec name to its Python implementation
# ---------------------------------------------------------------------------

_TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    # Market (4)
    "get_stock_basic": market_tools.get_stock_basic,
    "get_price_trend": market_tools.get_price_trend,
    "get_momentum_rank": market_tools.get_momentum_rank,
    "get_market_coverage_status": market_tools.get_market_coverage_status,
    # Industry (4)
    "get_industry_mapping": industry_tools.get_industry_mapping,
    "get_industry_chain": industry_tools.get_industry_chain,
    "get_related_stocks_by_industry": industry_tools.get_related_stocks_by_industry,
    "get_industry_heatmap": industry_tools.get_industry_heatmap,
    # Scoring (4)
    "get_stock_score": scoring_tools.get_stock_score,
    "get_score_breakdown": scoring_tools.get_score_breakdown,
    "get_top_scored_stocks": scoring_tools.get_top_scored_stocks,
    "get_risk_flags": scoring_tools.get_risk_flags,
    # Evidence (4)
    "get_stock_evidence": evidence_tools.get_stock_evidence,
    "get_industry_evidence": evidence_tools.get_industry_evidence,
    "get_recent_catalysts": evidence_tools.get_recent_catalysts,
    "get_evidence_summary": evidence_tools.get_evidence_summary,
    # Report (3)
    "get_latest_daily_report": report_tools.get_latest_daily_report,
    "generate_report_outline": report_tools.generate_report_outline,
    "format_research_report": report_tools.format_research_report,
}


def _first_param_is_session(func: Callable[..., Any]) -> bool:
    """Return ``True`` if the callable's first parameter is named *session*."""
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    return bool(params) and params[0] == "session"


# Pre-compute the set of tools that expect a ``session`` argument
_TOOLS_REQUIRING_SESSION: set[str] = {
    name
    for name, func in _TOOL_FUNCTIONS.items()
    if _first_param_is_session(func)
}


class MCPServer:
    """Lightweight MCP-compatible JSON-RPC 2.0 server.

    Handles ``tools/list``, ``tools/call``, and ``initialize`` methods.
    No external MCP SDK is imported.

    Parameters
    ----------
    session_factory :
        A zero-argument callable that returns a new SQLAlchemy ``Session``
        (e.g. ``SessionLocal``).  Only required when tools that need a
        database connection are invoked.
    """

    def __init__(self, session_factory: Callable[[], Any] | None = None) -> None:
        self.registry = ToolRegistry()
        self.session_factory = session_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a single JSON-RPC 2.0 request and return the response."""
        method: str | None = request.get("method")
        params: Any = request.get("params", {})
        req_id: Any = request.get("id")

        if method == "tools/list":
            return self._list_tools(req_id)
        if method == "tools/call":
            return self._call_tool(req_id, params)
        if method == "initialize":
            return self._initialize(req_id, params)

        return self._error(
            req_id, -32601, f"Method not found: {method}",
        )

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 response helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _success(req_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _error(
        req_id: Any,
        code: int,
        message: str,
        data: Any = None,
    ) -> dict[str, Any]:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": err}

    # ------------------------------------------------------------------
    # MCP method implementations
    # ------------------------------------------------------------------

    def _list_tools(self, req_id: Any) -> dict[str, Any]:
        """Return every registered tool in MCP tool-discovery format."""
        tools: list[dict[str, Any]] = []
        for spec in self.registry.get_all_tools():
            tools.append({
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.input_schema,
            })
        return self._success(req_id, {"tools": tools})

    def _initialize(self, req_id: Any, params: Any) -> dict[str, Any]:
        """Return server capabilities and protocol version."""
        return self._success(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "alpha-radar-agent",
                "version": "2.2",
            },
            "capabilities": {
                "tools": {
                    "readOnly": True,
                },
            },
        })

    def _call_tool(self, req_id: Any, params: Any) -> dict[str, Any]:
        """Execute a tool by name and return its result."""
        if not isinstance(params, dict):
            return self._error(
                req_id, -32600, "Invalid params: must be a dict",
            )

        tool_name: str | None = params.get("name")
        arguments: dict[str, Any] = params.get("arguments", {})

        if not tool_name:
            return self._error(
                req_id, -32602, "Missing required parameter: name",
            )

        # 1. Look up the spec
        spec = self.registry.get_tool(tool_name)
        if spec is None:
            return self._error(
                req_id, -32602, f"Unknown tool: {tool_name}",
            )

        # 2. Enforce read-only policy
        if not spec.read_only:
            return self._error(
                req_id, -32603,
                f"Tool {tool_name} is not read-only — execution rejected",
            )

        # 3. Look up the implementation function
        func = _TOOL_FUNCTIONS.get(tool_name)
        if func is None:
            return self._error(
                req_id, -32603,
                f"No implementation registered for tool: {tool_name}",
            )

        # 4. Execute
        try:
            result = self._execute_tool(func, tool_name, arguments)
        except Exception as exc:
            tb = traceback.format_exc()
            return self._error(
                req_id, -32603,
                f"Tool execution failed: {exc}",
                data={"traceback": tb} if tb else None,
            )

        return self._success(req_id, result)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def _execute_tool(
        self,
        func: Callable[..., Any],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call *func* with *arguments*, creating a DB session when needed.

        Tools whose first parameter is named ``session`` receive a fresh
        database session; tools without it (e.g. ``generate_report_outline``)
        are called directly.
        """
        if tool_name in _TOOLS_REQUIRING_SESSION:
            if self.session_factory is None:
                raise RuntimeError(
                    "session_factory is required for tools that need a "
                    "database session"
                )
            session = self.session_factory()
            try:
                return func(session, **arguments)
            finally:
                session.close()

        # Tools that don't require a session (generate_report_outline,
        # format_research_report) are called with arguments directly.
        return func(**arguments)
