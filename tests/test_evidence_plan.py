from __future__ import annotations

from food_label_agent.domain.models import LabelField, RiskFinding, UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel
from food_label_agent.graph.evidence_plan import (
    build_evidence_plan,
    evidence_supports_need,
)
from food_label_agent.graph.state import create_initial_state
from food_label_agent.ingredients.service import normalize_food_label_result


def _state():
    state = create_initial_state(
        request_id="evidence-plan",
        jurisdiction="CN",
        applicable_date="2026-08-09",
        user_constraints=[
            UserConstraint(kind=ConstraintKind.ALLERGY, canonical_value="milk")
        ],
    )
    state["label_fields"] = {
        "ingredients": LabelField("ingredients", "乳清蛋白、山梨酸钾", 1.0, True),
        "label_claims": LabelField("label_claims", "低糖", 1.0, True),
    }
    state["normalized_label"] = normalize_food_label_result("乳清蛋白、山梨酸钾")
    state["risk_findings"] = [
        RiskFinding(
            risk_level=RiskLevel.AVOID,
            constraint="milk",
            matched_text="乳清蛋白",
            reason_code="DIRECT_ALLERGEN_DERIVATIVE",
            explanation="confirmed",
        )
    ]
    return state


def test_evidence_plan_decomposes_independent_topics() -> None:
    needs = build_evidence_plan(_state())
    assert [item.need_id for item in needs] == [
        "allergen_labeling",
        "food_additive",
        "nutrition_claim",
    ]
    assert {item.expected_standard_prefixes[0] for item in needs} == {
        "GB 7718",
        "GB 2760",
        "GB 28050",
    }


def test_support_check_rejects_related_but_wrong_standard() -> None:
    need = build_evidence_plan(_state())[0]
    assert evidence_supports_need(
        {"topics": ["allergen"], "standard_number": "GB 7718-2011"}, need
    )
    assert not evidence_supports_need(
        {"topics": ["allergen"], "standard_number": "GB 28050-2011"}, need
    )
    assert not evidence_supports_need(
        {"topics": ["food_additive"], "standard_number": "GB 7718-2011"}, need
    )
