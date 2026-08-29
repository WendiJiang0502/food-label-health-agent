"""Production LangGraph runtime for the resumable food-label workflow."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any

from food_label_agent.domain.models import WorkflowTraceEvent
from food_label_agent.domain.types import AnalysisStatus

from .langgraph_adapter import build_graph
from .nodes import (
    confirm_label,
    evaluate_safety,
    extract_label,
    final_safety_gate_node,
    interpret_claims,
    interpret_label,
    normalize_label,
    retrieve_regulations,
    revalidate_alternatives,
    search_alternatives,
    validate_input,
    verify_consistency,
)
from .react import react_orchestrator
from .state import AgentState


def run_agent_graph(state: AgentState) -> AgentState:
    """Run the real graph from the persisted state to its next safe stop."""

    result = _production_graph().invoke(state)
    return AgentState(**result)


@lru_cache(maxsize=1)
def _production_graph():
    nodes = {
        "validate_input": validate_input,
        "extract_label": extract_label,
        "confirm_label": confirm_label,
        "normalize_label": normalize_label,
        "evaluate_safety": evaluate_safety,
        "react_orchestrator": react_orchestrator,
        "retrieve_regulations": retrieve_regulations,
        "interpret_label": interpret_label,
        "interpret_claims": interpret_claims,
        "verify_consistency": verify_consistency,
        "search_alternatives": search_alternatives,
        "revalidate_alternatives": revalidate_alternatives,
        "final_safety_gate": final_safety_gate_node,
    }
    return build_graph({name: _traced(name, node) for name, node in nodes.items()})


def _traced(
    node_name: str, node: Callable[[AgentState], Mapping[str, Any]]
) -> Callable[[AgentState], dict[str, Any]]:
    def run(state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        update = dict(node(state))
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        status_before = state["status"]
        stage_before = state["stage"]
        status_after = update.get("status", status_before)
        stage_after = update.get("stage", stage_before)
        if status_after is AnalysisStatus.BLOCKED:
            outcome = "blocked"
        elif status_after is AnalysisStatus.NEEDS_CONFIRMATION:
            outcome = "paused"
        else:
            outcome = "succeeded"
        update["workflow_trace"] = [
            *state.get("workflow_trace", []),
            WorkflowTraceEvent(
                sequence=len(state.get("workflow_trace", [])) + 1,
                node_name=node_name,
                outcome=outcome,
                status_before=status_before.value,
                status_after=status_after.value,
                stage_before=stage_before.value,
                stage_after=stage_after.value,
                detail={
                    "error_count": len(update.get("errors", state["errors"])),
                    "unknown_count": len(update.get("unknowns", state["unknowns"])),
                    "duration_ms": duration_ms,
                },
            ),
        ]
        return update

    return run
