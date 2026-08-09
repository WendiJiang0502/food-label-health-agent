from __future__ import annotations

from food_label_agent.context.builder import build_node_context
from food_label_agent.domain.models import (
    Evidence,
    LabelField,
    RiskFinding,
    UserConstraint,
)
from food_label_agent.domain.types import ConstraintKind, RiskLevel
from food_label_agent.graph.state import create_initial_state


def _context_state():
    state = create_initial_state(
        request_id="context-test",
        jurisdiction="CN",
        applicable_date="2026-08-10",
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
            raw_text="白砂糖、乳清蛋白",
            confidence=1.0,
            confirmed_by_user=True,
        ),
        "unconfirmed_note": LabelField(
            name="unconfirmed_note",
            raw_text="模型猜测文字",
            confidence=0.2,
            confirmed_by_user=False,
        ),
    }
    state["normalized_label"] = {
        "ingredients": [
            {"canonical_name": "白砂糖", "evidence_id": "label.ingredients.item.1"},
            {"canonical_name": "乳清蛋白", "evidence_id": "label.ingredients.item.2"},
        ]
    }
    state["risk_findings"] = [
        RiskFinding(
            risk_level=RiskLevel.AVOID,
            constraint="milk",
            matched_text="乳清蛋白",
            reason_code="DIRECT_ALLERGEN_DERIVATIVE",
            explanation="明确命中乳来源成分。",
            evidence_ids=("label.ingredients.item.2",),
        )
    ]
    state["regulatory_evidence"] = [
        Evidence(
            source_id=f"evidence-{index}",
            title="预包装食品标签通则",
            jurisdiction="CN",
            standard_number="GB 7718-2011",
            section="4.4.3.1",
            evidence_text="乳及乳制品作为配料时宜明确标示。" * 20,
            source_url="https://www.nhc.gov.cn/example.pdf",
            retrieval_score=0.9,
        )
        for index in range(8)
    ]
    return state


def test_each_node_receives_only_its_required_context_layers() -> None:
    state = _context_state()

    normalize = build_node_context(state, "normalize_label")
    safety = build_node_context(state, "evaluate_safety")
    react = build_node_context(state, "react_orchestrator")

    assert set(normalize.payload) == {"task", "confirmed_facts"}
    assert "user_constraints" not in normalize.payload
    assert "risk_findings" not in safety.payload
    assert "retrieval_evidence" in react.payload
    assert (
        "unconfirmed_note" not in normalize.payload["confirmed_facts"]["label_fields"]
    )
    assert "audit_events" not in str(react.payload)
    assert "tool_trace" not in str(react.payload)


def test_budget_truncates_evidence_before_safety_constraints_or_findings() -> None:
    context = build_node_context(
        _context_state(), "react_orchestrator", token_budget=220
    )

    assert context.truncated is True
    assert context.payload["user_constraints"][0]["canonical_value"] == "milk"
    assert context.payload["risk_findings"][0]["risk_level"] == "avoid"
    assert len(context.payload["retrieval_evidence"]) < 8
    assert context.budget_exceeded is True
    assert len(context.digest) == 64


def test_unknown_profile_or_invalid_budget_is_rejected() -> None:
    state = _context_state()

    for node_name, budget in (("free_form_agent", 2_000), ("react_orchestrator", 63)):
        try:
            build_node_context(state, node_name, token_budget=budget)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid context configuration was accepted")
