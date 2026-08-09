"""Shared application services for normalization and safety evaluation.

These functions are the single deterministic boundary used by HTTP, MCP, and
eventually the LangGraph adapters.  Keeping the serialization here prevents
different transports from producing different safety decisions.
"""

from __future__ import annotations

from collections.abc import Iterable

from food_label_agent.domain.models import UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel
from food_label_agent.nutrition.normalization import normalize_nutrition_facts
from food_label_agent.nutrition.rules import (
    RULESET_METADATA as NUTRITION_RULESET_METADATA,
)
from food_label_agent.nutrition.rules import (
    evaluate_nutrition_constraints,
)

from .allergens import RULESET_METADATA, evaluate_constraints
from .api_models import SafetyEvaluationRequest, SafetyEvaluationResponse
from .normalization import normalize_ingredients


def normalize_food_label_result(
    ingredients_text: str,
    *,
    original_ingredients_text: str | None = None,
    source_bounding_box: tuple[int, int, int, int] | None = None,
    nutrition_table_text: str | None = None,
    nutrition_basis_text: str | None = None,
    nutrition_rows: list[list[str]] | None = None,
) -> dict:
    """Return a transport-safe normalized label with source evidence intact."""

    if not ingredients_text.strip():
        raise ValueError("已确认配料表不能为空。")
    result = normalize_ingredients(
        ingredients_text,
        original_text=original_ingredients_text,
        source_bounding_box=source_bounding_box,
    ).to_dict()
    nutrition = normalize_nutrition_facts(
        nutrition_table_text,
        basis_text=nutrition_basis_text,
        rows=nutrition_rows,
    )
    result["nutrition"] = nutrition.to_dict() if nutrition else None
    if nutrition and nutrition.requires_confirmation:
        result["requires_confirmation"] = True
    return result


def evaluate_user_constraints_result(
    request: SafetyEvaluationRequest,
) -> SafetyEvaluationResponse:
    """Evaluate one validated request using only deterministic safety rules."""

    normalized = normalize_ingredients(request.confirmed_fields["ingredients"])
    nutrition = normalize_nutrition_facts(
        request.confirmed_fields.get("nutrition_table"),
        basis_text=request.confirmed_fields.get("nutrition_basis"),
        rows=request.nutrition_rows,
    )
    constraints = [
        UserConstraint(
            kind=ConstraintKind(item.kind),
            canonical_value=item.canonical_value,
            severity=item.severity,
            operator=item.operator,
            threshold=item.threshold,
            unit=item.unit,
            basis=item.basis,
        )
        for item in request.constraints
    ]
    allergy_constraints = [
        item for item in constraints if item.kind is not ConstraintKind.NUTRITION_LIMIT
    ]
    nutrition_constraints = [
        item for item in constraints if item.kind is ConstraintKind.NUTRITION_LIMIT
    ]
    findings = evaluate_constraints(
        normalized,
        allergy_constraints,
        allergen_statement=request.confirmed_fields.get("allergen_statement", ""),
        ingredients_confirmed=True,
    )
    findings.extend(evaluate_nutrition_constraints(nutrition, nutrition_constraints))
    normalized_dict = normalized.to_dict()
    normalized_dict["nutrition"] = nutrition.to_dict() if nutrition else None
    serialized_findings = [
        {
            "risk_level": finding.risk_level.value,
            "constraint": finding.constraint,
            "matched_text": finding.matched_text,
            "reason_code": finding.reason_code,
            "explanation": finding.explanation,
            "evidence_ids": list(finding.evidence_ids),
            "matched_location": matched_location(finding.evidence_ids, normalized_dict),
        }
        for finding in findings
    ]
    overall = overall_risk(finding.risk_level for finding in findings)
    return SafetyEvaluationResponse(
        request_id=request.request_id,
        status="needs_confirmation" if overall is RiskLevel.UNKNOWN else "evaluated",
        next_route=(
            "confirm_label"
            if normalized.requires_confirmation
            else "retrieve_regulations"
        ),
        overall_risk_level=overall.value,
        rule_set={
            **RULESET_METADATA,
            "allergens": RULESET_METADATA,
            "nutrition": NUTRITION_RULESET_METADATA,
        },
        normalized_label=normalized_dict,
        findings=serialized_findings,
        message=risk_message(overall),
    )


def overall_risk(levels: Iterable[RiskLevel]) -> RiskLevel:
    priority = {
        RiskLevel.COMPATIBLE: 0,
        RiskLevel.UNKNOWN: 1,
        RiskLevel.CAUTION: 2,
        RiskLevel.AVOID: 3,
    }
    return max(levels, key=priority.get, default=RiskLevel.UNKNOWN)


def risk_message(level: RiskLevel) -> str:
    return {
        RiskLevel.AVOID: "不建议食用",
        RiskLevel.CAUTION: "需要谨慎确认",
        RiskLevel.UNKNOWN: "当前信息不足",
        RiskLevel.COMPATIBLE: "在已确认标签中未发现相关成分",
    }[level]


def matched_location(evidence_ids: tuple[str, ...], normalized: dict) -> str:
    if not evidence_ids:
        return "未提供位置"
    evidence_id = evidence_ids[0]
    if evidence_id == "label.allergen_statement":
        return "过敏原提示"
    if evidence_id == "label.ingredients":
        return "已确认配料表"
    nutrition_prefix = "label.nutrition.row."
    if evidence_id.startswith(nutrition_prefix):
        return f"营养成分表第 {evidence_id.removeprefix(nutrition_prefix)} 行"
    prefix = "label.ingredients.item."
    if not evidence_id.startswith(prefix):
        return "用户约束"
    try:
        path = [int(value) for value in evidence_id.removeprefix(prefix).split(".")]
    except ValueError:
        return "已确认配料表"
    if len(path) == 1:
        return f"主配料第 {path[0]} 项"
    return f"复合配料第 {path[-1]} 项（路径 {' → '.join(map(str, path))}）"
