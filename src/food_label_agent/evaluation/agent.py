"""Deterministic metrics and release blockers for Agent tool trajectories."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.domain.models import ToolTraceEvent
from food_label_agent.domain.types import AnalysisStatus
from food_label_agent.graph.react import APPROVED_REACT_TOOLS
from food_label_agent.graph.state import AgentState


@dataclass(frozen=True, slots=True)
class AgentTrajectoryEvaluation:
    actual_tools: tuple[str, ...]
    expected_tools: tuple[str, ...]
    exact_sequence_match: bool
    tool_selection_precision: float
    tool_selection_recall: float
    unnecessary_tool_call_rate: float
    approved_tool_rate: float
    stopped_explicitly: bool
    trajectory_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["actual_tools"] = list(self.actual_tools)
        value["expected_tools"] = list(self.expected_tools)
        value["release_blockers"] = list(self.release_blockers)
        return value


def evaluate_agent_trajectory(
    trace: list[ToolTraceEvent] | list[dict],
    *,
    expected_tools: list[str],
    final_gate_applied: bool,
    hard_risk_preserved: bool,
) -> AgentTrajectoryEvaluation:
    """Score tool selection and flag failures that must block a release."""

    items = [_trace_dict(item) for item in trace]
    actual = tuple(
        str(item["tool_name"])
        for item in items
        if item.get("tool_name") and item.get("outcome") != "retry_scheduled"
    )
    expected = tuple(expected_tools)
    overlap = sum((Counter(actual) & Counter(expected)).values())
    extra = max(len(actual) - overlap, 0)
    blockers: list[str] = []
    unapproved = sorted(set(actual) - APPROVED_REACT_TOOLS)
    if unapproved:
        blockers.append("unapproved_tool_called:" + ",".join(unapproved))
    if any(item.get("outcome") == "budget_exhausted" for item in items):
        blockers.append("react_budget_exhausted")
    if any(item.get("outcome") == "failed" for item in items):
        blockers.append("react_tool_call_failed")
    if not final_gate_applied:
        blockers.append("final_safety_gate_bypassed")
    if not hard_risk_preserved:
        blockers.append("hard_risk_changed_after_tool_loop")
    stopped = bool(items) and items[-1].get("action") == "stop"
    if not stopped:
        blockers.append("react_stop_missing")
    exact = actual == expected
    return AgentTrajectoryEvaluation(
        actual_tools=actual,
        expected_tools=expected,
        exact_sequence_match=exact,
        tool_selection_precision=overlap / len(actual)
        if actual
        else float(not expected),
        tool_selection_recall=overlap / len(expected)
        if expected
        else float(not actual),
        unnecessary_tool_call_rate=extra / len(actual) if actual else 0.0,
        approved_tool_rate=(
            sum(tool in APPROVED_REACT_TOOLS for tool in actual) / len(actual)
            if actual
            else 1.0
        ),
        stopped_explicitly=stopped,
        trajectory_passed=exact and not blockers,
        release_blockers=tuple(blockers),
    )


def _trace_dict(value: ToolTraceEvent | dict) -> dict:
    return asdict(value) if isinstance(value, ToolTraceEvent) else value


def evaluate_workflow_release(state: AgentState) -> dict[str, Any]:
    """Apply deterministic release blockers to a completed workflow state."""

    node_names = [item.node_name for item in state["workflow_trace"]]
    required = {
        "validate_input",
        "extract_label",
        "normalize_label",
        "evaluate_safety",
        "react_orchestrator",
        "final_safety_gate",
    }
    if state.get("alternative_request", {}).get("enabled") is True:
        required.update({"search_alternatives", "revalidate_alternatives"})
    blockers = [
        f"mandatory_node_missing:{name}" for name in sorted(required - set(node_names))
    ]
    if not node_names or node_names[-1] != "final_safety_gate":
        blockers.append("final_safety_gate_bypassed")
    if state["errors"]:
        blockers.append("workflow_has_errors")
    if state["status"] is not AnalysisStatus.COMPLETED:
        blockers.append(f"workflow_not_completed:{state['status'].value}")
    return {
        "passed": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "required_nodes": sorted(required),
        "observed_nodes": node_names,
        "final_status": state["status"].value,
    }
