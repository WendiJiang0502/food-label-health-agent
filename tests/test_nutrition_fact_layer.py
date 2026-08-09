from __future__ import annotations

from food_label_agent.domain.models import LabelField, UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel
from food_label_agent.graph.nodes import (
    evaluate_safety,
    normalize_label,
    verify_consistency,
)
from food_label_agent.graph.state import create_initial_state
from food_label_agent.ingredients.api_models import SafetyEvaluationRequest
from food_label_agent.ingredients.service import evaluate_user_constraints_result
from food_label_agent.nutrition.normalization import normalize_nutrition_facts

TABLE = """项目\t每100克\tNRV%
能量\t890千焦\t11%
蛋白质\t5.2克\t9%
脂肪\t8.0克\t13%
碳水化合物\t31.0克\t10%
糖\t3.5克
钠\t380毫克\t19%"""


def test_confirmed_nutrition_table_becomes_traceable_fact_layer() -> None:
    nutrition = normalize_nutrition_facts(TABLE)

    assert nutrition is not None
    assert nutrition.requires_confirmation is False
    assert nutrition.basis is not None
    assert nutrition.basis.type == "per_100g"
    sugar = next(
        item for item in nutrition.nutrients if item.canonical_name == "sugars"
    )
    carbs = next(
        item for item in nutrition.nutrients if item.canonical_name == "carbohydrate"
    )
    assert sugar.value == 3.5
    assert carbs.value == 31.0
    assert sugar.evidence_id == "label.nutrition.row.6"
    assert sugar.source_span == "糖 3.5克"


def test_carbohydrate_is_never_substituted_for_missing_sugars() -> None:
    nutrition = normalize_nutrition_facts("项目 每100克\n碳水化合物 31克")

    assert nutrition is not None
    assert {item.canonical_name for item in nutrition.nutrients} == {"carbohydrate"}


def test_user_nutrition_limit_exceeded_is_avoid_with_row_evidence() -> None:
    response = evaluate_user_constraints_result(
        SafetyEvaluationRequest(
            request_id="nutrition-avoid",
            applicable_date="2026-08-09",
            confirmed_fields={"ingredients": "燕麦", "nutrition_table": TABLE},
            constraints=[
                {
                    "kind": "nutrition_limit",
                    "canonical_value": "sodium",
                    "operator": "max",
                    "threshold": 300,
                    "unit": "mg",
                    "basis": "per_100g",
                }
            ],
        )
    )

    assert response.overall_risk_level == "avoid"
    assert response.findings[0]["reason_code"] == "USER_NUTRITION_LIMIT_EXCEEDED"
    assert response.findings[0]["evidence_ids"] == ["label.nutrition.row.7"]
    assert response.findings[0]["matched_location"] == "营养成分表第 7 行"


def test_user_nutrition_limit_met_is_qualified_compatible() -> None:
    response = evaluate_user_constraints_result(
        SafetyEvaluationRequest(
            request_id="nutrition-compatible",
            applicable_date="2026-08-09",
            confirmed_fields={"ingredients": "燕麦", "nutrition_table": TABLE},
            constraints=[
                {
                    "kind": "nutrition_limit",
                    "canonical_value": "sugars",
                    "operator": "max",
                    "threshold": 5,
                    "unit": "g",
                    "basis": "per_100g",
                }
            ],
        )
    )

    assert response.overall_risk_level == "compatible"
    assert "不等同于绝对适合或医学建议" in response.findings[0]["explanation"]


def test_basis_mismatch_is_unknown_instead_of_converted_or_guessed() -> None:
    response = evaluate_user_constraints_result(
        SafetyEvaluationRequest(
            request_id="nutrition-unknown",
            applicable_date="2026-08-09",
            confirmed_fields={"ingredients": "燕麦", "nutrition_table": TABLE},
            constraints=[
                {
                    "kind": "nutrition_limit",
                    "canonical_value": "sodium",
                    "operator": "max",
                    "threshold": 300,
                    "unit": "mg",
                    "basis": "per_serving",
                }
            ],
        )
    )

    assert response.overall_risk_level == "unknown"
    assert response.findings[0]["reason_code"] == "NUTRITION_BASIS_MISMATCH"


def test_langgraph_nodes_use_normalized_sugar_fact_for_claim_check() -> None:
    state = create_initial_state(
        request_id="nutrition-graph",
        jurisdiction="CN",
        applicable_date="2026-08-09",
        user_constraints=[
            UserConstraint(
                kind=ConstraintKind.NUTRITION_LIMIT,
                canonical_value="sugars",
                operator="max",
                threshold=5,
                unit="g",
                basis="per_100g",
            )
        ],
    )
    state["label_fields"] = {
        "ingredients": LabelField("ingredients", "燕麦", 1.0, True),
        "nutrition_table": LabelField("nutrition_table", TABLE, 1.0, True),
        "label_claims": LabelField("label_claims", "低糖", 1.0, True),
    }

    state.update(normalize_label(state))
    state.update(evaluate_safety(state))
    state["claim_interpretations"] = [
        {
            "canonical_type": "low_sugar",
            "raw_text": "低糖",
            "label_evidence_ids": ["label.claims.item.1"],
        }
    ]
    state.update(verify_consistency(state))

    assert state["risk_findings"][0].risk_level is RiskLevel.COMPATIBLE
    assert state["consistency_findings"][0]["status"] == "consistent"
