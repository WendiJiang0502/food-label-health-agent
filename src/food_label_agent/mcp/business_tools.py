"""Transport-neutral implementations of registered MCP business tools.

FastMCP registers these exact callables for external clients.  The in-process
LangGraph uses :func:`invoke_mcp_tool` so nodes depend on the same named JSON
boundary without creating a stdio subprocess for every graph transition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any

from pydantic import Field

from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductComparisonRequest,
)
from food_label_agent.alternatives.service import (
    compare_food_products as compare_products_service,
)
from food_label_agent.alternatives.service import (
    find_alternative_products as find_alternatives_service,
)
from food_label_agent.alternatives.service import (
    revalidate_alternatives as revalidate_alternatives_service,
)
from food_label_agent.claims.models import (
    ClaimConsistencyRequest,
    ClaimInterpretationRequest,
)
from food_label_agent.claims.service import interpret_claim, verify_claim_consistency
from food_label_agent.ingredients.api_models import (
    ConstraintInput,
    SafetyEvaluationRequest,
)
from food_label_agent.ingredients.explanations import (
    IngredientExplanationRequest,
    explain_ingredient_with_evidence,
)
from food_label_agent.ingredients.service import (
    evaluate_user_constraints_result,
    normalize_food_label_result,
)
from food_label_agent.regulations.models import RegulationSearchRequest
from food_label_agent.regulations.service import search_regulations

from .contracts import get_tool_contract


class MCPToolCallError(RuntimeError):
    """A named MCP business tool could not complete its invocation."""

    def __init__(self, tool_name: str, cause: Exception) -> None:
        super().__init__(f"MCP tool {tool_name!r} failed: {cause}")
        self.tool_name = tool_name
        self.cause = cause


def normalize_food_label(
    ingredients_text: Annotated[
        str,
        Field(
            min_length=1,
            max_length=20_000,
            description="User-confirmed ingredient-list text.",
        ),
    ],
    original_ingredients_text: str | None = None,
    source_bounding_box: tuple[int, int, int, int] | None = None,
    nutrition_table_text: str | None = None,
    nutrition_basis_text: str | None = None,
    nutrition_rows: list[list[str]] | None = None,
) -> dict:
    """Normalize confirmed ingredients and nutrition facts with source evidence.

    Unbalanced brackets and unresolved names are returned explicitly and are
    never repaired or guessed by a language model.
    """

    return normalize_food_label_result(
        ingredients_text,
        original_ingredients_text=original_ingredients_text,
        source_bounding_box=source_bounding_box,
        nutrition_table_text=nutrition_table_text,
        nutrition_basis_text=nutrition_basis_text,
        nutrition_rows=nutrition_rows,
    )


def evaluate_user_constraints(
    request_id: Annotated[str, Field(min_length=1, max_length=128)],
    applicable_date: str,
    confirmed_fields: dict[str, str],
    constraints: Annotated[list[ConstraintInput], Field(min_length=1, max_length=16)],
    jurisdiction: str = "CN",
    nutrition_rows: list[list[str]] | None = None,
) -> dict:
    """Evaluate confirmed facts against deterministic allergen and nutrition rules.

    Returns avoid, caution, compatible, or unknown with matched text and
    evidence locations. Compatible never means absolute safety.
    """

    request = SafetyEvaluationRequest(
        request_id=request_id,
        jurisdiction=jurisdiction,
        applicable_date=applicable_date,
        confirmed_fields=confirmed_fields,
        nutrition_rows=nutrition_rows,
        constraints=constraints,
    )
    return evaluate_user_constraints_result(request).model_dump(mode="json")


def search_food_regulations(
    query: Annotated[str, Field(min_length=1, max_length=2_000)],
    applicable_date: str,
    jurisdiction: str = "CN",
    topics: Annotated[list[str] | None, Field(max_length=12)] = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict:
    """Hybrid-retrieve applicable clause evidence from official Chinese sources."""

    request = RegulationSearchRequest(
        query=query,
        jurisdiction=jurisdiction,
        applicable_date=applicable_date,
        topics=topics or [],
        limit=limit,
    )
    return search_regulations(request).model_dump(mode="json")


def explain_ingredient(
    ingredient: dict,
    risk_finding: dict | None,
    regulatory_evidence: Annotated[list[dict], Field(max_length=20)],
    applicable_date: str,
    jurisdiction: str = "CN",
) -> dict:
    """Explain one normalized ingredient using applicable evidence only."""

    request = IngredientExplanationRequest(
        ingredient=ingredient,
        risk_finding=risk_finding,
        regulatory_evidence=regulatory_evidence,
        jurisdiction=jurisdiction,
        applicable_date=applicable_date,
    )
    return explain_ingredient_with_evidence(request).model_dump(mode="json")


def interpret_label_claim(
    claim_text: Annotated[str, Field(min_length=1, max_length=2_000)],
    regulatory_evidence: Annotated[list[dict], Field(max_length=20)],
    applicable_date: str,
    jurisdiction: str = "CN",
) -> dict:
    """Interpret Chinese packaging claims without conflating their meanings."""

    request = ClaimInterpretationRequest(
        claim_text=claim_text,
        regulatory_evidence=regulatory_evidence,
        jurisdiction=jurisdiction,
        applicable_date=applicable_date,
    )
    return interpret_claim(request).model_dump(mode="json")


def verify_label_consistency(
    claims: Annotated[list[dict], Field(min_length=1, max_length=30)],
    applicable_date: str,
    ingredients_text: str | None = None,
    nutrition_values: dict | None = None,
    regulatory_evidence: Annotated[list[dict] | None, Field(max_length=20)] = None,
    jurisdiction: str = "CN",
) -> dict:
    """Cross-check claims against confirmed ingredient and nutrition facts."""

    request = ClaimConsistencyRequest(
        claims=claims,
        ingredients_text=ingredients_text,
        nutrition_values=nutrition_values or {},
        regulatory_evidence=regulatory_evidence or [],
        jurisdiction=jurisdiction,
        applicable_date=applicable_date,
    )
    return verify_claim_consistency(request).model_dump(mode="json")


def find_alternative_products(
    category: Annotated[str, Field(min_length=2, max_length=80)],
    applicable_date: str,
    constraints: Annotated[list[ConstraintInput], Field(min_length=1, max_length=16)],
    jurisdiction: str = "CN",
    region: str = "CN",
    exclude_product_ids: Annotated[list[str] | None, Field(max_length=50)] = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict:
    """Find products only from current, human-reviewed label evidence."""

    request = AlternativeSearchRequest(
        category=category,
        applicable_date=applicable_date,
        constraints=constraints,
        jurisdiction=jurisdiction,
        region=region,
        exclude_product_ids=exclude_product_ids or [],
        limit=limit,
    )
    return find_alternatives_service(request)


def revalidate_alternatives(
    request_id: Annotated[str, Field(min_length=1, max_length=128)],
    applicable_date: str,
    constraints: Annotated[list[ConstraintInput], Field(min_length=1, max_length=16)],
    candidates: Annotated[list[dict], Field(max_length=20)],
    jurisdiction: str = "CN",
) -> dict:
    """Re-run the complete deterministic rule engine for every candidate label."""

    request = AlternativeRevalidationRequest(
        request_id=request_id,
        applicable_date=applicable_date,
        constraints=constraints,
        candidates=candidates,
        jurisdiction=jurisdiction,
    )
    return revalidate_alternatives_service(request)


def compare_food_products(
    products: Annotated[list[dict], Field(min_length=1, max_length=20)],
    nutrient_keys: Annotated[list[str] | None, Field(max_length=20)] = None,
) -> dict:
    """Compare revalidated products only on identical nutrition bases and units."""

    arguments = {"products": products}
    if nutrient_keys is not None:
        arguments["nutrient_keys"] = nutrient_keys
    return compare_products_service(ProductComparisonRequest(**arguments))


BusinessTool = Callable[..., dict[str, Any]]

BUSINESS_TOOLS: Mapping[str, BusinessTool] = {
    "normalize_food_label": normalize_food_label,
    "evaluate_user_constraints": evaluate_user_constraints,
    "search_food_regulations": search_food_regulations,
    "explain_ingredient": explain_ingredient,
    "interpret_label_claim": interpret_label_claim,
    "verify_label_consistency": verify_label_consistency,
    "find_alternative_products": find_alternative_products,
    "compare_food_products": compare_food_products,
    "revalidate_alternatives": revalidate_alternatives,
}


def invoke_mcp_tool(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Invoke an implemented tool through the same boundary exposed by MCP."""

    contract = get_tool_contract(tool_name)
    if not contract.implemented:
        raise MCPToolCallError(tool_name, RuntimeError("tool is not implemented"))
    try:
        handler = BUSINESS_TOOLS[tool_name]
        return handler(**dict(arguments))
    except MCPToolCallError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise MCPToolCallError(tool_name, exc) from exc
