"""Stable tool boundary exposed by the future modular MCP server."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolContract:
    name: str
    purpose: str
    safety_critical: bool = False
    implemented: bool = False


MCP_TOOLS: tuple[ToolContract, ...] = (
    ToolContract("analyze_label_image", "Extract label fields with field-level confidence"),
    ToolContract("normalize_food_label", "Normalize ingredients, nutrition, and claims"),
    ToolContract("explain_ingredient", "Explain an ingredient with applicable evidence"),
    ToolContract(
        "evaluate_user_constraints",
        "Evaluate allergen and dietary hard constraints",
        safety_critical=True,
    ),
    ToolContract(
        "search_food_regulations",
        "Retrieve versioned and applicable official clauses",
        safety_critical=True,
    ),
    ToolContract("interpret_label_claim", "Interpret a claim under applicable rules"),
    ToolContract(
        "verify_label_consistency",
        "Cross-check claims, ingredients, and nutrition facts",
        safety_critical=True,
    ),
    ToolContract("find_alternative_products", "Find candidates after hard filtering"),
    ToolContract(
        "compare_food_products",
        "Compare products on normalized and compatible measurement bases",
    ),
)


def get_tool_contract(name: str) -> ToolContract:
    for contract in MCP_TOOLS:
        if contract.name == name:
            return contract
    raise KeyError(f"Unknown MCP tool contract: {name}")
