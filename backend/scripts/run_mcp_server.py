#!/usr/bin/env python3
"""Run Alpha Radar MCP server via stdio transport.

Reads line-delimited JSON-RPC 2.0 requests from **stdin** and writes the
corresponding responses to **stdout**.  This is the transport format expected
by MCP clients (including Claude Desktop) when connecting to a subprocess.

Usage
-----
    python scripts/run_mcp_server.py

Then send one JSON-RPC request per line::

    {"jsonrpc":"2.0","id":1,"method":"tools/list"}
    {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_latest_daily_report","arguments":{}}}

Or pipe from a file::

    python scripts/run_mcp_server.py < requests.jsonl
"""

from __future__ import annotations

import json
import sys
import traceback

from app.agent.mcp_server import MCPServer
from app.db.session import SessionLocal


def main() -> None:
    """Read JSON-RPC 2.0 requests line-by-line from stdin and respond.

    A single ``MCPServer`` instance is reused across all requests; a fresh
    database session is created on demand for each ``tools/call`` invocation.
    """
    server = MCPServer(session_factory=SessionLocal)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        # -- Parse the JSON-RPC request --------------------------------
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {exc}",
                },
            }
            _write_response(response)
            continue

        # -- Validate top-level shape -----------------------------------
        if not isinstance(request, dict):
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: body must be a JSON object",
                },
            }
            _write_response(response)
            continue

        # -- Process ----------------------------------------------------
        try:
            response = server.handle_request(request)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {exc}",
                    "data": {"traceback": traceback.format_exc()},
                },
            }

        _write_response(response)


def _write_response(response: dict[str, object]) -> None:
    """Serialize *response* as a single JSON line to stdout."""
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
