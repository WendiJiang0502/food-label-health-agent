"""MCP server factory with explicit placeholder capabilities."""

from __future__ import annotations

from .contracts import MCP_TOOLS


def create_server():
    """Create the MCP server without claiming unimplemented analysis capabilities."""

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("MCP SDK is not installed. Install project dependencies first.") from exc

    server = FastMCP("Food Label Health Agent")

    @server.tool()
    def health() -> dict[str, object]:
        """Return server health and the declared capability roadmap."""

        return {
            "status": "ok",
            "service": "food-label-health-agent",
            "version": "0.1.0",
            "tools": [
                {
                    "name": contract.name,
                    "implemented": contract.implemented,
                    "safety_critical": contract.safety_critical,
                }
                for contract in MCP_TOOLS
            ],
        }

    return server
