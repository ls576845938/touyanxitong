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

from typing import Any

from fastapi import APIRouter

from app.agent.mcp_server import MCPServer
from app.db.session import SessionLocal

# Module-level server singleton (one DB session factory, reused for all calls)
_server = MCPServer(session_factory=SessionLocal)

mcp_router = APIRouter(prefix="/mcp", tags=["mcp"])


@mcp_router.post("/")
def mcp_http_endpoint(request: dict[str, Any]) -> dict[str, Any]:
    """HTTP transport for MCP JSON-RPC 2.0 requests.

    Accepts a JSON-RPC request body and returns the corresponding
    JSON-RPC response.  Supports ``tools/list``, ``tools/call``,
    and ``initialize``.
    """
    return _server.handle_request(request)


@mcp_router.get("/")
def mcp_info() -> dict[str, Any]:
    """Return basic MCP server metadata (convenience for discovery)."""
    return {
        "server": "alpha-radar-agent",
        "version": "2.2",
        "protocol": "mcp",
        "transport": "http",
    }
