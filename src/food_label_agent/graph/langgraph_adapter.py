"""Lazy LangGraph integration.

Real OCR and retrieval nodes will be registered in later milestones. Keeping the
import lazy allows the domain and safety tests to run before dependencies are installed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .routing import (
    route_after_confirmation,
    route_after_normalization,
    route_after_ocr,
    route_after_react,
    route_after_safety,
)
from .state import AgentState
from .topology import validate_topology

NodeFunction = Callable[[AgentState], Mapping[str, Any]]


def build_graph(
    nodes: Mapping[str, NodeFunction], *, checkpointer: Any | None = None
) -> Any:
    """Compile the required workflow using caller-provided production node functions."""

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is not installed. Install the project dependencies before compiling."
        ) from exc

    validate_topology()
    required = {
        "validate_input",
        "extract_label",
        "confirm_label",
        "normalize_label",
        "evaluate_safety",
        "react_orchestrator",
        "retrieve_regulations",
        "interpret_label",
        "interpret_claims",
        "verify_consistency",
        "final_safety_gate",
    }
    missing = required - set(nodes)
    if missing:
        raise ValueError(f"Missing required node implementations: {sorted(missing)}")
    supplied_alternative_nodes = {
        "search_alternatives",
        "revalidate_alternatives",
    }.intersection(nodes)
    if supplied_alternative_nodes and len(supplied_alternative_nodes) != 2:
        raise ValueError("Alternative discovery requires both graph nodes")
    has_alternatives = len(supplied_alternative_nodes) == 2

    graph = StateGraph(AgentState)
    for name, function in nodes.items():
        graph.add_node(name, function)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "extract_label")
    graph.add_conditional_edges(
        "extract_label",
        route_after_ocr,
        {
            "confirm_label": "confirm_label",
            "normalize_label": "normalize_label",
        },
    )
    graph.add_conditional_edges(
        "confirm_label",
        route_after_confirmation,
        {"pause": END, "normalize_label": "normalize_label"},
    )
    graph.add_conditional_edges(
        "normalize_label",
        route_after_normalization,
        {
            "confirm_label": END,
            "evaluate_safety": "evaluate_safety",
        },
    )
    graph.add_conditional_edges(
        "evaluate_safety",
        route_after_safety,
        {"pause": END, "react_orchestrator": "react_orchestrator"},
    )
    if has_alternatives:
        graph.add_conditional_edges(
            "react_orchestrator",
            route_after_react,
            {
                "search_alternatives": "search_alternatives",
                "final_safety_gate": "final_safety_gate",
            },
        )
        graph.add_edge("search_alternatives", "revalidate_alternatives")
        graph.add_edge("revalidate_alternatives", "final_safety_gate")
    else:
        graph.add_edge("react_orchestrator", "final_safety_gate")
    graph.add_edge("final_safety_gate", END)
    return graph.compile(checkpointer=checkpointer)
