from __future__ import annotations

from typing import Any

from app.agent.tools.specs import (
    ToolSpec,
    build_mcp_manifest,
    get_all_specs,
    get_spec_by_name,
    get_specs_by_category,
)


class ToolRegistry:
    """Central registry for Alpha Radar tool specifications.

    Loads all specs from :mod:`app.agent.tools.specs` and exposes them
    through lookup helpers.  No MCP SDK or external dependency is imported.
    """

    def get_all_tools(self) -> list[ToolSpec]:
        """Return every registered ToolSpec."""
        return get_all_specs()

    def get_tool(self, name: str) -> ToolSpec | None:
        """Look up a single tool spec by name."""
        return get_spec_by_name(name)

    def get_tools_by_category(self, category: str) -> list[ToolSpec]:
        """Return all tools belonging to *category*.

        Valid categories: ``market``, ``industry``, ``scoring``,
        ``evidence``, ``report``.
        """
        return get_specs_by_category(category)

    def get_mcp_manifest(self) -> dict[str, Any]:
        """Return a standard MCP-ready JSON manifest.

        The returned dict follows the MCP tool discovery protocol shape:
        ``{"protocol": "mcp", "version": "1.0", "serverInfo": ..., "tools": [...]}``
        """
        return build_mcp_manifest()


# Single shared instance (module-level singleton)
registry = ToolRegistry()
