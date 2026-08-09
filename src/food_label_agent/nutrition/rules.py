"""Deterministic comparisons between confirmed nutrition facts and user limits."""

from __future__ import annotations

from food_label_agent.domain.models import RiskFinding, UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel

from .normalization import NormalizedNutrition

SUPPORTED_UNITS = {
    "energy": "kJ",
    "protein": "g",
    "fat": "g",
    "saturated_fat": "g",
    "trans_fat": "g",
    "carbohydrate": "g",
    "sugars": "g",
    "dietary_fiber": "g",
    "sodium": "mg",
    "calcium": "mg",
}

RULESET_METADATA = {
    "id": "user_defined_nutrition_limits_v1",
    "scope_note": "仅比较用户自行设置的数值上限，不提供医学推荐摄入量。",
    "operators": ["max"],
}


def evaluate_nutrition_constraints(
    nutrition: NormalizedNutrition | None,
    constraints: list[UserConstraint],
) -> list[RiskFinding]:
    return [_evaluate_one(nutrition, item) for item in constraints]


def _evaluate_one(
    nutrition: NormalizedNutrition | None, constraint: UserConstraint
) -> RiskFinding:
    key = constraint.canonical_value
    if (
        constraint.kind is not ConstraintKind.NUTRITION_LIMIT
        or key not in SUPPORTED_UNITS
    ):
        return _unknown(
            constraint,
            "UNSUPPORTED_NUTRITION_CONSTRAINT",
            "当前规则不支持这项营养约束。",
        )
    if constraint.operator != "max" or constraint.threshold is None:
        return _unknown(
            constraint,
            "INVALID_NUTRITION_LIMIT",
            "营养约束必须提供用户设置的数值上限。",
        )
    if constraint.unit != SUPPORTED_UNITS[key]:
        return _unknown(
            constraint,
            "NUTRITION_UNIT_MISMATCH",
            "约束单位与该营养成分不一致，不能自动换算。",
        )
    if nutrition is None:
        return _unknown(
            constraint, "NUTRITION_LABEL_MISSING", "标签中没有已确认的营养成分事实。"
        )
    if nutrition.requires_confirmation:
        return _unknown(
            constraint, "NUTRITION_FACTS_UNCERTAIN", "营养表口径或数值仍需人工确认。"
        )
    fact = next(
        (item for item in nutrition.nutrients if item.canonical_name == key), None
    )
    if fact is None:
        return _unknown(
            constraint, "NUTRIENT_NOT_DECLARED", "已确认营养表中未找到这项营养成分。"
        )
    if not constraint.basis or fact.basis != constraint.basis:
        return _unknown(
            constraint,
            "NUTRITION_BASIS_MISMATCH",
            "标签口径与用户上限口径不同，不能直接比较。",
        )
    if fact.value > constraint.threshold:
        return RiskFinding(
            risk_level=RiskLevel.AVOID,
            constraint=key,
            matched_text=f"{fact.raw_name} {fact.value:g}{fact.unit}",
            reason_code="USER_NUTRITION_LIMIT_EXCEEDED",
            explanation=f"标签标示{fact.raw_name}{fact.value:g}{fact.unit}，超过你设置的上限{constraint.threshold:g}{constraint.unit}。",
            evidence_ids=(fact.evidence_id,),
        )
    return RiskFinding(
        risk_level=RiskLevel.COMPATIBLE,
        constraint=key,
        matched_text=f"{fact.raw_name} {fact.value:g}{fact.unit}",
        reason_code="USER_NUTRITION_LIMIT_NOT_EXCEEDED",
        explanation=f"在当前已确认标签和相同口径下，{fact.raw_name}未超过你设置的上限；这不等同于绝对适合或医学建议。",
        evidence_ids=(fact.evidence_id,),
    )


def _unknown(constraint: UserConstraint, code: str, message: str) -> RiskFinding:
    return RiskFinding(
        risk_level=RiskLevel.UNKNOWN,
        constraint=constraint.canonical_value,
        matched_text=None,
        reason_code=code,
        explanation=message,
        evidence_ids=("user.constraints",),
    )
