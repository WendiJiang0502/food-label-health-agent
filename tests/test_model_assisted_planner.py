from __future__ import annotations

import json

from test_constrained_react import _ready_state

from food_label_agent.domain.types import RiskLevel
from food_label_agent.graph.planner import (
    OpenAIActionProposer,
    PlannerProposal,
    PlannerSettings,
)
from food_label_agent.graph.react import choose_next_action, react_orchestrator


class ScriptedProposer:
    provider = "test-model"
    model = "planner-test-v1"

    def __init__(self, *, choose_last: bool = False, invalid: bool = False) -> None:
        self.choose_last = choose_last
        self.invalid = invalid

    def propose(self, *, context: dict, candidates: list[dict]) -> PlannerProposal:
        assert "confirmed_facts" in context
        action_id = (
            "DELETE_ALL_EVIDENCE"
            if self.invalid
            else candidates[-1 if self.choose_last else 0]["action_id"]
        )
        return PlannerProposal(
            action_id=action_id,
            provider=self.provider,
            model=self.model,
            response_id="resp_test",
            input_tokens=40,
            output_tokens=5,
        )


def test_openai_proposer_uses_structured_action_ids_without_tool_arguments() -> None:
    captured = {}

    def transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
        captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {
            "id": "resp_planner_1",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "usage": {"input_tokens": 31, "output_tokens": 4},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"action_id": "ACTION_B"}),
                        }
                    ],
                }
            ],
        }

    proposer = OpenAIActionProposer(
        PlannerSettings(provider="openai", api_key="test-key"),
        transport=transport,
    )
    proposal = proposer.propose(
        context={"task": {"request_id": "request-1"}},
        candidates=[
            {"action_id": "ACTION_A", "tool_name": "one", "purpose": "first"},
            {"action_id": "ACTION_B", "tool_name": "two", "purpose": "second"},
        ],
    )

    assert proposal.action_id == "ACTION_B"
    assert proposal.response_id == "resp_planner_1"
    assert proposal.input_tokens == 31
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    schema = captured["payload"]["text"]["format"]["schema"]
    assert schema["properties"]["action_id"]["enum"] == ["ACTION_A", "ACTION_B"]
    assert captured["payload"]["store"] is False
    assert "arguments" not in captured["payload"]["input"]


def test_model_may_reorder_legal_actions_but_never_own_arguments() -> None:
    state = _ready_state()
    selection = choose_next_action(
        state, action_proposer=ScriptedProposer(choose_last=True)
    )

    assert selection.mode == "model_guarded"
    assert selection.outcome == "accepted"
    assert selection.decision.reason_code == "RETRIEVE_CLAIM_RULES"
    assert selection.decision.tool_name == "search_food_regulations"
    assert selection.decision.arguments["topics"] == ["nutrition_claim"]
    assert selection.decision.arguments["jurisdiction"] == "CN"


def test_non_candidate_model_action_is_rejected_and_falls_back() -> None:
    selection = choose_next_action(
        _ready_state(), action_proposer=ScriptedProposer(invalid=True)
    )

    assert selection.outcome == "deterministic_fallback"
    assert selection.error_code == "planner_proposed_non_candidate_action"
    assert selection.decision.reason_code == "RETRIEVE_ALLERGEN_RULES"


def test_model_assisted_runtime_is_auditable_and_preserves_hard_risk() -> None:
    state = _ready_state()
    update = react_orchestrator(
        state,
        action_proposer=ScriptedProposer(choose_last=True),
    )

    tool_events = [item for item in update["tool_trace"] if item.tool_name]
    assert tool_events
    assert all(
        item.observation["planner_mode"] == "model_guarded" for item in tool_events
    )
    assert all(
        item.observation["planner_response_id"] == "resp_test" for item in tool_events
    )
    assert any(
        item.event_type == "planner_action_selected" for item in update["audit_events"]
    )
    assert "risk_findings" not in update
    assert state["risk_findings"][0].risk_level is RiskLevel.AVOID


def test_missing_model_credentials_fall_back_without_blocking_workflow() -> None:
    proposer = OpenAIActionProposer(
        PlannerSettings(provider="openai", api_key=None),
    )
    update = react_orchestrator(_ready_state(), action_proposer=proposer)

    assert update["status"].value == "in_progress"
    assert update["tool_trace"][0].observation["planner_outcome"] == (
        "deterministic_fallback"
    )
    assert update["tool_trace"][0].observation["planner_error_code"] == (
        "planner_api_key_missing"
    )
