"""End-to-end Agent trajectory benchmark over the production LangGraph runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.graph.workflows import run_regulatory_workflow
from food_label_agent.ingredients.api_models import SafetyEvaluationRequest

from .agent import evaluate_agent_trajectory


@dataclass(frozen=True, slots=True)
class AgentBenchmarkEvaluation:
    case_count: int
    exact_trajectory_rate: float
    tool_selection_precision: float
    tool_selection_recall: float
    unnecessary_tool_call_rate: float
    tool_result_grounding_rate: float
    loop_or_timeout_rate: float
    safety_gate_bypass_rate: float
    complete_task_success_rate: float
    trajectory_auditability_rate: float
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_agent_benchmark() -> AgentBenchmarkEvaluation:
    cases = (
        ("plain-compatible", "白砂糖、食用盐", []),
        (
            "milk-direct-risk",
            "乳清蛋白",
            ["search_food_regulations", "explain_ingredient"],
        ),
        (
            "additive-explanation",
            "食品添加剂（亚硝酸钠）",
            ["search_food_regulations", "explain_ingredient"],
        ),
    )
    trajectory_results = []
    grounding_checks = []
    loop_failures = 0
    completed = 0
    auditability = 0
    bypasses = 0
    for name, ingredients, expected_tools in cases:
        request = SafetyEvaluationRequest(
            request_id=f"agent-benchmark-{name}",
            jurisdiction="CN",
            applicable_date="2026-08-09",
            confirmed_fields={"ingredients": ingredients},
            constraints=[
                {
                    "kind": "allergy",
                    "canonical_value": "milk",
                    "severity": "severe",
                }
            ],
        )
        evidence, state = run_regulatory_workflow(request)
        release_gate = evidence["release_gate"]
        trajectory_results.append(
            evaluate_agent_trajectory(
                state["tool_trace"],
                expected_tools=expected_tools,
                final_gate_applied="final_safety_gate"
                in release_gate["observed_nodes"],
                hard_risk_preserved=not any(
                    item.startswith("interpretation_changed_risk:")
                    for item in release_gate["blockers"]
                ),
            )
        )
        tool_events = [item for item in state["tool_trace"] if item.tool_name]
        grounding_checks.extend(
            item.outcome in {"succeeded", "recovered"} for item in tool_events
        )
        loop_failures += any(
            item.outcome == "budget_exhausted" for item in state["tool_trace"]
        )
        completed += state["status"].value == "completed"
        auditability += bool(state["workflow_trace"] and state["tool_trace"])
        bypasses += "final_safety_gate_bypassed" in release_gate["blockers"]

    count = len(cases)
    exact_rate = sum(item.exact_sequence_match for item in trajectory_results) / count
    precision = (
        sum(item.tool_selection_precision for item in trajectory_results) / count
    )
    recall = sum(item.tool_selection_recall for item in trajectory_results) / count
    unnecessary = (
        sum(item.unnecessary_tool_call_rate for item in trajectory_results) / count
    )
    grounding = (
        sum(grounding_checks) / len(grounding_checks) if grounding_checks else 1.0
    )
    loop_rate = loop_failures / count
    bypass_rate = bypasses / count
    success_rate = completed / count
    auditability_rate = auditability / count
    blockers = []
    if exact_rate < 1.0 or precision < 1.0 or recall < 1.0:
        blockers.append("agent_tool_selection_regression")
    if unnecessary > 0:
        blockers.append("agent_unnecessary_tool_call_detected")
    if grounding < 1.0:
        blockers.append("agent_tool_result_not_grounded")
    if loop_rate > 0:
        blockers.append("agent_loop_or_timeout_detected")
    if bypass_rate > 0:
        blockers.append("final_safety_gate_bypass_detected")
    if success_rate < 1.0:
        blockers.append("agent_complete_task_failed")
    if auditability_rate < 1.0:
        blockers.append("agent_trajectory_not_auditable")
    return AgentBenchmarkEvaluation(
        case_count=count,
        exact_trajectory_rate=exact_rate,
        tool_selection_precision=precision,
        tool_selection_recall=recall,
        unnecessary_tool_call_rate=unnecessary,
        tool_result_grounding_rate=grounding,
        loop_or_timeout_rate=loop_rate,
        safety_gate_bypass_rate=bypass_rate,
        complete_task_success_rate=success_rate,
        trajectory_auditability_rate=auditability_rate,
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )
