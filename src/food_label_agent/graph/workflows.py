"""Resumable workflow operations shared by HTTP and other entrypoints."""

from __future__ import annotations

from dataclasses import asdict

from food_label_agent.alternatives.models import AlternativeWorkflowRequest
from food_label_agent.domain.models import LabelField, UserConstraint
from food_label_agent.domain.types import AnalysisStatus, ConstraintKind, RiskLevel
from food_label_agent.evaluation.agent import evaluate_workflow_release
from food_label_agent.ingredients.api_models import (
    SafetyEvaluationRequest,
    SafetyEvaluationResponse,
)

from .nodes import _additive_ingredients
from .runtime import run_agent_graph
from .state import AgentState, create_initial_state


def attach_regulatory_interpretation(
    request: SafetyEvaluationRequest,
    evaluation: SafetyEvaluationResponse,
) -> dict:
    evidence, _ = run_regulatory_workflow(request, evaluation)
    return evidence


def prepare_evaluation_state(
    request: SafetyEvaluationRequest, *, state: AgentState | None = None
) -> AgentState:
    """Apply confirmed facts and constraints to a new or resumed canonical state."""

    working = state or create_initial_state(
        request_id=request.request_id,
        jurisdiction=request.jurisdiction,
        applicable_date=request.applicable_date,
    )
    if working["request_id"] != request.request_id:
        raise ValueError("恢复会话与当前 request_id 不一致")
    working["jurisdiction"] = request.jurisdiction
    working["applicable_date"] = request.applicable_date
    working["label_fields"] = {
        name: LabelField(
            name=name,
            raw_text=value,
            confidence=1.0,
            confirmed_by_user=True,
            bounding_box=(
                working["label_fields"][name].bounding_box
                if name in working["label_fields"]
                else None
            ),
        )
        for name, value in request.confirmed_fields.items()
    }
    working["ocr_evidence"] = {
        **working["ocr_evidence"],
        "status": "confirmed",
    }
    working["user_constraints"] = [_constraint(item) for item in request.constraints]
    working["status"] = AnalysisStatus.IN_PROGRESS
    _clear_retriable_failures(working)
    return working


def run_regulatory_workflow(
    request: SafetyEvaluationRequest,
    evaluation: SafetyEvaluationResponse | None = None,
    *,
    state: AgentState | None = None,
) -> tuple[dict, AgentState]:
    """Run normalization, deterministic safety, ReAct evidence and final gate."""

    final_state = run_agent_graph(prepare_evaluation_state(request, state=state))
    return evidence_payload(final_state), final_state


def run_alternative_workflow(
    request: AlternativeWorkflowRequest,
    *,
    state: AgentState | None = None,
) -> tuple[dict, AgentState]:
    """Resume the same state and independently revalidate product candidates."""

    safety_request = SafetyEvaluationRequest(
        request_id=request.request_id,
        jurisdiction=request.jurisdiction,
        applicable_date=request.applicable_date.isoformat(),
        confirmed_fields=request.confirmed_fields,
        nutrition_rows=request.nutrition_rows,
        constraints=request.constraints,
        resume_token=request.resume_token,
    )
    working = prepare_evaluation_state(safety_request, state=state)
    working["alternative_request"] = {
        "enabled": True,
        "category": request.category,
        "region": request.region,
        "exclude_product_ids": (
            [request.current_product_id] if request.current_product_id else []
        ),
        "health_concerns": request.health_concerns,
        "limit": 5,
    }
    final_state = run_agent_graph(working)
    return alternative_payload(final_state, request.category), final_state


def evidence_payload(state: AgentState) -> dict:
    has_additives = bool(_additive_ingredients(state["normalized_label"]))
    needs_explanation = has_additives or any(
        finding.risk_level is not RiskLevel.COMPATIBLE
        and not finding.reason_code.startswith(
            ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
        )
        for finding in state["risk_findings"]
    )
    if not needs_explanation and not state["claim_interpretations"]:
        evidence_status = "not_required"
    elif state["errors"]:
        evidence_status = "blocked"
    elif (
        any(
            item.get("status") == "unknown" for item in state["ingredient_explanations"]
        )
        or (needs_explanation and not state["ingredient_explanations"])
        or any(
            item.get("status") == "unknown" or item.get("unknowns")
            for item in state["claim_interpretations"]
        )
        or any(
            item.get("status") == "unknown" for item in state["consistency_findings"]
        )
    ):
        evidence_status = "unknown"
    else:
        evidence_status = "grounded"
    return {
        "status": evidence_status,
        "jurisdiction": state["jurisdiction"],
        "applicable_date": state["applicable_date"],
        "final_status": state["status"].value,
        "interpretations": state["ingredient_explanations"],
        "claim_interpretations": state["claim_interpretations"],
        "consistency_findings": state["consistency_findings"],
        "regulatory_evidence": [asdict(item) for item in state["regulatory_evidence"]],
        "unknowns": state["unknowns"],
        "errors": state["errors"],
        "agent_trace": [asdict(item) for item in state["tool_trace"]],
        "workflow_trace": [asdict(item) for item in state["workflow_trace"]],
        "react_budget": state["react_budget"],
        "release_gate": evaluate_workflow_release(state),
    }


def alternative_payload(state: AgentState, category: str) -> dict:
    return {
        "status": state["status"].value,
        "category": category,
        "catalog_scope": state["alternative_request"].get("catalog_scope"),
        "catalog_status": state["alternative_request"].get("catalog_status"),
        "catalog_warnings": state["alternative_request"].get("catalog_warnings", []),
        "catalog_coverage": state["alternative_request"].get("catalog_coverage", {}),
        "selection_basis": state["alternative_request"].get("selection_basis"),
        "eligible": [
            item
            for item in state["alternatives"]
            if item.get("disposition") == "eligible"
        ],
        "excluded": [
            item
            for item in state["alternatives"]
            if item.get("disposition") == "excluded"
        ],
        "evidence_rejected": state["alternative_request"].get("search_rejected", []),
        "comparison": state["alternative_comparison"],
        "candidate_count": state["alternative_request"].get("candidate_count", 0),
        "revalidated_count": state["alternative_request"].get("revalidated_count", 0),
        "revalidation_rate": state["alternative_request"].get("revalidation_rate", 0.0),
        "unknowns": state["unknowns"],
        "errors": state["errors"],
        "workflow_trace": [asdict(item) for item in state["workflow_trace"]],
        "release_gate": evaluate_workflow_release(state),
    }


def _constraint(item) -> UserConstraint:
    return UserConstraint(
        kind=ConstraintKind(item.kind),
        canonical_value=item.canonical_value,
        severity=item.severity,
        operator=item.operator,
        threshold=item.threshold,
        unit=item.unit,
        basis=item.basis,
    )


def _clear_retriable_failures(state: AgentState) -> None:
    state["errors"] = [
        item for item in state["errors"] if not item.startswith("mcp_tool_failed:")
    ]
    state["unknowns"] = [
        item for item in state["unknowns"] if not item.endswith("_unavailable")
    ]
