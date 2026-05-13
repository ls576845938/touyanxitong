"""HTTP transport for the Alpha Radar MCP server (FastAPI router).

Usage
-----
This router is registered in ``app.main``::

    from app.agent.mcp_router import mcp_router
    app.include_router(mcp_router)

Clients send JSON-RPC 2.0 POST requests to ``/mcp/`` and receive JSON-RPC
2.0 responses.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from app.agent.mcp_server import MCPServer
from app.db.session import SessionLocal

# Module-level server singleton (one DB session factory, reused for all calls)
_server = MCPServer(session_factory=SessionLocal)

mcp_router = APIRouter(prefix="/mcp", tags=["mcp"])


@mcp_router.post("/")
async def mcp_http_endpoint(request: Request) -> dict[str, Any]:
    """HTTP transport for MCP JSON-RPC 2.0 requests.

    Accepts a JSON-RPC request body and returns the corresponding
    JSON-RPC response.  Supports ``tools/list``, ``tools/call``,
    and ``initialize``.

    Malformed JSON bodies are reported as JSON-RPC 2.0 parse errors
    (code -32700).  Non-dict bodies are rejected with -32600.
    """
    try:
        body: Any = await request.json()
    except json.JSONDecodeError:
        return MCPServer._error(
            None, -32700, "Parse error",
            data="Request body is not valid JSON",
        )

    if not isinstance(body, dict):
        return MCPServer._error(
            None, -32600, "Invalid Request",
            data="Request body must be a JSON object",
        )

    return _server.handle_request(body)


@mcp_router.get("/")
def mcp_info() -> dict[str, Any]:
    """Return basic MCP server metadata (convenience for discovery)."""
    return {
        "server": "alpha-radar-agent",
        "version": "2.2",
        "protocol": "mcp",
        "transport": "http",
    }
