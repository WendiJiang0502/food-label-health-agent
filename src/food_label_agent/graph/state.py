"""Canonical state passed between LangGraph nodes.

The state contract intentionally uses TypedDict and standard-library value objects.
LangGraph is an orchestration adapter, not the owner of the domain model.
"""

from __future__ import annotations

from typing import Any, TypedDict

from food_label_agent.domain.models import (
    AuditEvent,
    Evidence,
    ImageInput,
    LabelField,
    RiskFinding,
    ToolTraceEvent,
    UserConstraint,
)
from food_label_agent.domain.types import AnalysisStatus, WorkflowStage


class AgentState(TypedDict):
    request_id: str
    jurisdiction: str
    applicable_date: str
    status: AnalysisStatus
    stage: WorkflowStage
    images: list[ImageInput]
    label_fields: dict[str, LabelField]
    ocr_evidence: dict[str, Any]
    normalized_label: dict[str, Any]
    user_constraints: list[UserConstraint]
    risk_findings: list[RiskFinding]
    regulatory_evidence: list[Evidence]
    ingredient_explanations: list[dict[str, Any]]
    claim_interpretations: list[dict[str, Any]]
    consistency_findings: list[dict[str, Any]]
    alternative_request: dict[str, Any]
    alternatives: list[dict[str, Any]]
    alternative_comparison: dict[str, Any]
    warnings: list[str]
    unknowns: list[str]
    errors: list[str]
    audit_events: list[AuditEvent]
    tool_trace: list[ToolTraceEvent]
    react_budget: dict[str, int]


def create_initial_state(
    *,
    request_id: str,
    jurisdiction: str,
    applicable_date: str,
    images: list[ImageInput] | None = None,
    user_constraints: list[UserConstraint] | None = None,
) -> AgentState:
    """Create a complete state so nodes never depend on missing collection keys."""

    return AgentState(
        request_id=request_id,
        jurisdiction=jurisdiction,
        applicable_date=applicable_date,
        status=AnalysisStatus.RECEIVED,
        stage=WorkflowStage.INPUT_VALIDATION,
        images=list(images or []),
        label_fields={},
        ocr_evidence={"status": "not_assessed", "issues": []},
        normalized_label={},
        user_constraints=list(user_constraints or []),
        risk_findings=[],
        regulatory_evidence=[],
        ingredient_explanations=[],
        claim_interpretations=[],
        consistency_findings=[],
        alternative_request={},
        alternatives=[],
        alternative_comparison={},
        warnings=[],
        unknowns=[],
        errors=[],
        audit_events=[
            AuditEvent(
                event_type="state_created",
                actor="orchestrator",
                detail={
                    "jurisdiction": jurisdiction,
                    "applicable_date": applicable_date,
                },
            )
        ],
        tool_trace=[],
        react_budget={"max_steps": 32, "max_tool_calls": 32, "tool_calls_used": 0},
    )
