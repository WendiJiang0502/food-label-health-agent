from __future__ import annotations

from food_label_agent.domain.models import LabelField, UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel, WorkflowStage
from food_label_agent.graph.nodes import (
    evaluate_safety,
    final_safety_gate_node,
    interpret_claims,
    interpret_label,
    normalize_label,
    retrieve_regulations,
    verify_consistency,
)
from food_label_agent.graph.routing import route_after_normalization
from food_label_agent.graph.state import create_initial_state
from food_label_agent.mcp.business_tools import MCPToolCallError
from food_label_agent.mcp.business_tools import invoke_mcp_tool as invoke_real_mcp_tool


def test_production_nodes_normalize_then_evaluate_confirmed_label(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def invoke_spy(tool_name: str, arguments: dict) -> dict:
        calls.append(tool_name)
        return invoke_real_mcp_tool(tool_name, arguments)

    monkeypatch.setattr("food_label_agent.graph.nodes.invoke_mcp_tool", invoke_spy)
    state = create_initial_state(
        request_id="core-nodes",
        jurisdiction="CN",
        applicable_date="2026-08-08",
        user_constraints=[
            UserConstraint(
                kind=ConstraintKind.ALLERGY,
                canonical_value="milk",
                severity="severe",
            )
        ],
    )
    state["label_fields"] = {
        "ingredients": LabelField(
            name="ingredients",
            raw_text="复合调味料（白砂糖、食用盐、乳清蛋白）",
            confidence=0.62,
            confirmed_by_user=True,
        )
    }

    state.update(normalize_label(state))
    assert state["stage"] is WorkflowStage.LABEL_NORMALIZATION
    assert route_after_normalization(state) == "evaluate_safety"

    state.update(evaluate_safety(state))
    assert state["stage"] is WorkflowStage.SAFETY_EVALUATION
    assert state["risk_findings"][0].risk_level is RiskLevel.AVOID
    assert state["risk_findings"][0].evidence_ids == ("label.ingredients.item.1.3",)
    assert calls == ["normalize_food_label", "evaluate_user_constraints"]
    assert state["audit_events"][-2].actor == "mcp:normalize_food_label"
    assert state["audit_events"][-1].actor == "mcp:evaluate_user_constraints"

    state.update(retrieve_regulations(state))
    assert state["stage"] is WorkflowStage.REGULATORY_RETRIEVAL
    assert state["risk_findings"][0].risk_level is RiskLevel.AVOID
    assert state["regulatory_evidence"]
    assert {evidence.standard_number for evidence in state["regulatory_evidence"]} == {
        "GB 7718-2011"
    }
    assert all(evidence.source_url for evidence in state["regulatory_evidence"])
    assert calls == [
        "normalize_food_label",
        "evaluate_user_constraints",
        "search_food_regulations",
    ]
    assert state["audit_events"][-1].actor == "mcp:search_food_regulations"

    state.update(interpret_label(state))
    assert state["stage"] is WorkflowStage.INTERPRETATION
    assert state["risk_findings"][0].risk_level is RiskLevel.AVOID
    assert state["ingredient_explanations"][0]["status"] == "explained"
    assert state["ingredient_explanations"][0]["risk_level"] == "avoid"
    assert state["ingredient_explanations"][0]["regulatory_evidence_ids"]
    assert calls == [
        "normalize_food_label",
        "evaluate_user_constraints",
        "search_food_regulations",
        "explain_ingredient",
    ]
    assert state["audit_events"][-1].actor == "mcp:explain_ingredient"

    state.update(final_safety_gate_node(state))
    assert state["status"].value == "completed"
    assert state["stage"] is WorkflowStage.COMPLETED
    assert state["risk_findings"][0].risk_level is RiskLevel.AVOID
    assert state["errors"] == []
    assert state["audit_events"][-1].actor == "orchestrator:final_safety_gate"


def test_normalization_parse_failure_routes_to_confirmation() -> None:
    state = create_initial_state(
        request_id="parse-failure",
        jurisdiction="CN",
        applicable_date="2026-08-08",
    )
    state["label_fields"]["ingredients"] = LabelField(
        name="ingredients",
        raw_text="复合调味料（白砂糖、食用盐",
        confidence=1.0,
        confirmed_by_user=True,
    )

    state.update(normalize_label(state))

    assert route_after_normalization(state) == "confirm_label"
    assert state["normalized_label"]["requires_confirmation"] is True


def test_mcp_tool_failure_blocks_graph_without_guessing(monkeypatch) -> None:
    state = create_initial_state(
        request_id="mcp-failure",
        jurisdiction="CN",
        applicable_date="2026-08-09",
    )
    state["label_fields"]["ingredients"] = LabelField(
        name="ingredients",
        raw_text="小麦粉",
        confidence=1.0,
        confirmed_by_user=True,
    )

    def fail(tool_name: str, arguments: dict) -> dict:
        raise MCPToolCallError(tool_name, RuntimeError("unavailable"))

    monkeypatch.setattr("food_label_agent.graph.nodes.invoke_mcp_tool", fail)
    state.update(normalize_label(state))

    assert state["status"].value == "blocked"
    assert state["errors"] == ["mcp_tool_failed:normalize_food_label"]
    assert state["unknowns"] == ["normalize_food_label_unavailable"]


def test_claim_nodes_retrieve_interpret_and_verify_without_conflating_claims() -> None:
    state = create_initial_state(
        request_id="claim-nodes",
        jurisdiction="CN",
        applicable_date="2026-08-09",
    )
    state["label_fields"] = {
        "ingredients": LabelField(
            name="ingredients",
            raw_text="水、果葡糖浆",
            confidence=1.0,
            confirmed_by_user=True,
        ),
        "label_claims": LabelField(
            name="label_claims",
            raw_text="0蔗糖",
            confidence=0.7,
            confirmed_by_user=True,
        ),
    }

    state.update(interpret_claims(state))
    state.update(verify_consistency(state))

    assert state["stage"] is WorkflowStage.CONSISTENCY_VERIFICATION
    assert state["claim_interpretations"][0]["canonical_type"] == "no_sucrose"
    assert state["consistency_findings"][0]["status"] == "not_contradicted"
    assert "不能据此理解为无糖" in state["consistency_findings"][0]["explanation"]
    assert state["audit_events"][-2].actor == "mcp:interpret_label_claim"
    assert state["audit_events"][-1].actor == "mcp:verify_label_consistency"


def test_claim_threshold_without_confirmed_sugar_value_stays_unknown() -> None:
    state = create_initial_state(
        request_id="claim-unknown",
        jurisdiction="CN",
        applicable_date="2026-08-09",
    )
    state["label_fields"] = {
        "ingredients": LabelField(
            name="ingredients",
            raw_text="水、赤藓糖醇",
            confidence=1.0,
            confirmed_by_user=True,
        ),
        "label_claims": LabelField(
            name="label_claims", raw_text="无糖", confidence=1.0, confirmed_by_user=True
        ),
    }

    state.update(interpret_claims(state))
    state.update(verify_consistency(state))

    assert state["consistency_findings"][0]["status"] == "unknown"
    assert "confirmed_sugar_value_or_basis_missing" in state["unknowns"]
