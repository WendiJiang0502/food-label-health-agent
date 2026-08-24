"""Modular MCP server for deterministic food-label capabilities."""

from __future__ import annotations

import os

from .business_tools import (
    compare_food_products,
    evaluate_user_constraints,
    explain_ingredient,
    find_alternative_products,
    interpret_label_claim,
    normalize_food_label,
    revalidate_alternatives,
    search_food_regulations,
    verify_label_consistency,
)
from .contracts import MCP_TOOLS


def create_server():
    """Create the MCP server without claiming unimplemented analysis capabilities."""

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP SDK is not installed. Install project dependencies first."
        ) from exc

    server = FastMCP("Food Label Health Agent")

    server.tool()(normalize_food_label)
    server.tool()(evaluate_user_constraints)
    server.tool()(search_food_regulations)
    server.tool()(explain_ingredient)
    server.tool()(interpret_label_claim)
    server.tool()(verify_label_consistency)
    server.tool()(find_alternative_products)
    server.tool()(compare_food_products)
    server.tool()(revalidate_alternatives)

    @server.tool()
    def health() -> dict[str, object]:
        """Return server health and the declared capability roadmap."""

        return {
            "status": "ok",
            "service": "food-label-health-agent",
            "version": "0.2.0",
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


def run() -> None:
    """Run the modular MCP server over the standard stdio transport."""

    os.environ.setdefault("FOOD_LABEL_PRODUCT_CATALOG", "official_cn_expanded")
    create_server().run(transport="stdio")
