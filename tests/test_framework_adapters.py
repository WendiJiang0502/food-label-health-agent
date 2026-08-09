from __future__ import annotations

from typing import Any

from food_label_agent.domain.models import LabelField
from food_label_agent.domain.types import AnalysisStatus, WorkflowStage
from food_label_agent.graph.langgraph_adapter import build_graph
from food_label_agent.graph.state import AgentState, create_initial_state
from food_label_agent.mcp.server import create_server


def _node(**updates: Any):
    def run(_: AgentState) -> dict[str, Any]:
        return updates

    return run


def test_real_langgraph_compiles_and_runs_required_path() -> None:
    nodes = {
        "validate_input": _node(
            status=AnalysisStatus.IN_PROGRESS,
            stage=WorkflowStage.OCR_EXTRACTION,
        ),
        "extract_label": _node(
            label_fields={
                "ingredients": LabelField(
                    name="ingredients",
                    raw_text="小麦粉、白砂糖",
                    confidence=0.98,
                )
            }
        ),
        "confirm_label": _node(stage=WorkflowStage.HUMAN_CONFIRMATION),
        "normalize_label": _node(stage=WorkflowStage.LABEL_NORMALIZATION),
        "evaluate_safety": _node(stage=WorkflowStage.SAFETY_EVALUATION),
        "retrieve_regulations": _node(stage=WorkflowStage.REGULATORY_RETRIEVAL),
        "interpret_label": _node(stage=WorkflowStage.INTERPRETATION),
        "interpret_claims": _node(stage=WorkflowStage.CLAIM_INTERPRETATION),
        "verify_consistency": _node(stage=WorkflowStage.CONSISTENCY_VERIFICATION),
        "final_safety_gate": _node(
            status=AnalysisStatus.COMPLETED,
            stage=WorkflowStage.COMPLETED,
        ),
    }
    graph = build_graph(nodes)
    initial_state = create_initial_state(
        request_id="framework-test",
        jurisdiction="CN",
        applicable_date="2026-08-02",
    )

    result = graph.invoke(initial_state)

    assert result["status"] == AnalysisStatus.COMPLETED
    assert result["stage"] == WorkflowStage.COMPLETED
    assert result["label_fields"]["ingredients"].raw_text == "小麦粉、白砂糖"


def test_real_mcp_server_factory_exposes_named_server() -> None:
    server = create_server()

    assert server.name == "Food Label Health Agent"
