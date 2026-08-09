from __future__ import annotations

import pytest

from food_label_agent.domain.models import LabelField, RiskFinding, UserConstraint
from food_label_agent.domain.types import (
    AnalysisStatus,
    ConstraintKind,
    RiskLevel,
    WorkflowStage,
)
from food_label_agent.graph.react import (
    APPROVED_REACT_TOOLS,
    ReactDecision,
    react_orchestrator,
    validate_react_decision,
)
from food_label_agent.graph.state import create_initial_state
from food_label_agent.ingredients.service import normalize_food_label_result


def _ready_state():
    state = create_initial_state(
        request_id="react-test",
        jurisdiction="CN",
        applicable_date="2026-08-09",
        user_constraints=[
            UserConstraint(kind=ConstraintKind.ALLERGY, canonical_value="milk")
        ],
    )
    ingredients = "乳清蛋白、食品添加剂（亚硝酸钠）"
    state["label_fields"] = {
        "ingredients": LabelField("ingredients", ingredients, 1.0, True),
        "label_claims": LabelField("label_claims", "低糖", 1.0, True),
        "nutrition_table": LabelField(
            "nutrition_table", "项目 每100克\n糖 3.5克", 1.0, True
        ),
    }
    state["normalized_label"] = normalize_food_label_result(
        ingredients,
        nutrition_table_text="项目 每100克\n糖 3.5克",
    )
    state["risk_findings"] = [
        RiskFinding(
            risk_level=RiskLevel.AVOID,
            constraint="milk",
            matched_text="乳清蛋白",
            reason_code="DIRECT_ALLERGEN_DERIVATIVE",
            explanation="配料表中明确出现乳来源成分乳清蛋白。",
            evidence_ids=("label.ingredients.item.1",),
        )
    ]
    state["status"] = AnalysisStatus.IN_PROGRESS
    state["stage"] = WorkflowStage.SAFETY_EVALUATION
    return state


def test_react_selects_only_approved_tools_and_records_auditable_trace() -> None:
    state = _ready_state()

    update = react_orchestrator(state)

    tools = [item.tool_name for item in update["tool_trace"] if item.tool_name]
    assert tools == [
        "search_food_regulations",
        "search_food_regulations",
        "search_food_regulations",
        "explain_ingredient",
        "explain_ingredient",
        "interpret_label_claim",
        "verify_label_consistency",
    ]
    assert set(tools) <= APPROVED_REACT_TOOLS
    assert update["react_budget"]["tool_calls_used"] == 7
    assert update["tool_trace"][-1].reason_code == "NO_REQUIRED_TOOL_REMAINS"
    assert "risk_findings" not in update
    assert state["risk_findings"][0].risk_level is RiskLevel.AVOID
    assert all("arguments" not in item.observation for item in update["tool_trace"])


def test_react_stops_without_unnecessary_tool_call_for_compatible_plain_label() -> None:
    state = _ready_state()
    state["label_fields"].pop("label_claims")
    state["label_fields"].pop("nutrition_table")
    state["normalized_label"] = normalize_food_label_result("白砂糖、食用盐")
    state["risk_findings"] = [
        RiskFinding(
            risk_level=RiskLevel.COMPATIBLE,
            constraint="milk",
            matched_text=None,
            reason_code="NO_ALLERGEN_MATCH_IN_CONFIRMED_LABEL",
            explanation="未发现冲突。",
        )
    ]

    update = react_orchestrator(state)

    assert update["react_budget"]["tool_calls_used"] == 0
    assert update["tool_trace"][-1].action == "stop"


def test_react_cannot_run_before_normalization_and_safety_evaluation() -> None:
    state = create_initial_state(
        request_id="react-prerequisite",
        jurisdiction="CN",
        applicable_date="2026-08-09",
        user_constraints=[
            UserConstraint(kind=ConstraintKind.ALLERGY, canonical_value="milk")
        ],
    )
    state["label_fields"]["ingredients"] = LabelField(
        "ingredients", "乳清蛋白", 1.0, True
    )

    update = react_orchestrator(state)

    assert update["status"] is AnalysisStatus.BLOCKED
    assert update["unknowns"] == ["react_requires_normalized_label"]
    assert update["react_budget"]["tool_calls_used"] == 0


def test_react_budget_exhaustion_blocks_instead_of_skipping_evidence() -> None:
    update = react_orchestrator(_ready_state(), max_steps=8, max_tool_calls=1)

    assert update["status"] is AnalysisStatus.BLOCKED
    assert "react_tool_budget_exhausted" in update["errors"]
    assert update["tool_trace"][-1].outcome == "budget_exhausted"
    assert update["react_budget"]["tool_calls_used"] == 1


@pytest.mark.parametrize("budget_name", ["max_steps", "max_tool_calls"])
def test_react_rejects_non_positive_explicit_budget(budget_name: str) -> None:
    state = _ready_state()

    with pytest.raises(ValueError, match="budgets must be positive"):
        react_orchestrator(state, **{budget_name: 0})


def test_unapproved_or_mismatched_action_is_rejected() -> None:
    for decision in (
        ReactDecision(
            action="find_alternative_products",
            reason_code="TRY_UNIMPLEMENTED_TOOL",
            tool_name="find_alternative_products",
        ),
        ReactDecision(
            action="explain_ingredient",
            reason_code="MISMATCHED_ACTION",
            tool_name="search_food_regulations",
        ),
    ):
        try:
            validate_react_decision(decision)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe ReAct decision was accepted")
