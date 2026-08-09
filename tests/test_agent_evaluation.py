from __future__ import annotations

from food_label_agent.domain.models import ToolTraceEvent
from food_label_agent.evaluation.agent import evaluate_agent_trajectory


def _event(step: int, tool: str | None, *, outcome: str = "succeeded"):
    return ToolTraceEvent(
        step=step,
        action=tool or "stop",
        reason_code="TEST",
        tool_name=tool,
        outcome=outcome,
        status_before="in_progress",
        status_after="in_progress",
    )


def test_agent_trajectory_metrics_pass_exact_safe_sequence() -> None:
    trace = [
        _event(1, "search_food_regulations"),
        _event(2, "explain_ingredient"),
        _event(3, None, outcome="completed"),
    ]

    result = evaluate_agent_trajectory(
        trace,
        expected_tools=["search_food_regulations", "explain_ingredient"],
        final_gate_applied=True,
        hard_risk_preserved=True,
    )

    assert result.trajectory_passed is True
    assert result.tool_selection_precision == 1
    assert result.tool_selection_recall == 1
    assert result.unnecessary_tool_call_rate == 0
    assert result.release_blockers == ()


def test_agent_evaluation_blocks_gate_bypass_and_risk_change() -> None:
    result = evaluate_agent_trajectory(
        [_event(1, "search_food_regulations")],
        expected_tools=["search_food_regulations"],
        final_gate_applied=False,
        hard_risk_preserved=False,
    )

    assert result.trajectory_passed is False
    assert "final_safety_gate_bypassed" in result.release_blockers
    assert "hard_risk_changed_after_tool_loop" in result.release_blockers
    assert "react_stop_missing" in result.release_blockers


def test_agent_evaluation_counts_unnecessary_calls() -> None:
    result = evaluate_agent_trajectory(
        [
            _event(1, "search_food_regulations"),
            _event(2, "verify_label_consistency"),
            _event(3, None, outcome="completed"),
        ],
        expected_tools=["search_food_regulations"],
        final_gate_applied=True,
        hard_risk_preserved=True,
    )

    assert result.unnecessary_tool_call_rate == 0.5
    assert result.exact_sequence_match is False
    assert result.trajectory_passed is False
