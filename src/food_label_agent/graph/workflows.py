"""Framework-neutral workflow slices used by HTTP and future graph entrypoints."""

from __future__ import annotations

from dataclasses import asdict

from food_label_agent.alternatives.models import AlternativeWorkflowRequest
from food_label_agent.domain.models import LabelField, RiskFinding, UserConstraint
from food_label_agent.domain.types import (
    AnalysisStatus,
    ConstraintKind,
    RiskLevel,
    WorkflowStage,
)
from food_label_agent.ingredients.api_models import (
    SafetyEvaluationRequest,
    SafetyEvaluationResponse,
)
from food_label_agent.ingredients.service import evaluate_user_constraints_result

from .nodes import (
    _additive_ingredients,
    final_safety_gate_node,
    revalidate_alternatives,
    search_alternatives,
)
from .react import react_orchestrator
from .state import AgentState, create_initial_state


def attach_regulatory_interpretation(
    request: SafetyEvaluationRequest,
    evaluation: SafetyEvaluationResponse,
) -> dict:
    """Continue a completed rule evaluation through evidence and the final gate."""

    evidence, _ = run_regulatory_workflow(request, evaluation)
    return evidence


def run_regulatory_workflow(
    request: SafetyEvaluationRequest,
    evaluation: SafetyEvaluationResponse,
) -> tuple[dict, AgentState]:
    """Run the evidence workflow and expose final state for durable checkpoints."""

    state = create_initial_state(
        request_id=request.request_id,
        jurisdiction=request.jurisdiction,
        applicable_date=request.applicable_date,
        user_constraints=[
            UserConstraint(
                kind=ConstraintKind(item.kind),
                canonical_value=item.canonical_value,
                severity=item.severity,
                operator=item.operator,
                threshold=item.threshold,
                unit=item.unit,
                basis=item.basis,
            )
            for item in request.constraints
        ],
    )
    state["label_fields"] = {
        name: LabelField(
            name=name,
            raw_text=value,
            confidence=1.0,
            confirmed_by_user=True,
        )
        for name, value in request.confirmed_fields.items()
    }
    state["normalized_label"] = evaluation.normalized_label
    state["risk_findings"] = [
        RiskFinding(
            risk_level=RiskLevel(item["risk_level"]),
            constraint=item["constraint"],
            matched_text=item.get("matched_text"),
            reason_code=item["reason_code"],
            explanation=item["explanation"],
            evidence_ids=tuple(item.get("evidence_ids", ())),
        )
        for item in evaluation.findings
    ]
    state["status"] = AnalysisStatus.IN_PROGRESS
    state["stage"] = WorkflowStage.SAFETY_EVALUATION

    has_additives = bool(_additive_ingredients(evaluation.normalized_label))
    needs_regulatory_explanation = has_additives or any(
        finding.risk_level is not RiskLevel.COMPATIBLE
        and not finding.reason_code.startswith(
            ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
        )
        for finding in state["risk_findings"]
    )
    state.update(react_orchestrator(state))
    state.update(final_safety_gate_node(state))

    has_claims = bool(state["claim_interpretations"])
    if not needs_regulatory_explanation and not has_claims:
        evidence_status = "not_required"
    elif state["errors"]:
        evidence_status = "blocked"
    elif (
        any(
            item.get("status") == "unknown" for item in state["ingredient_explanations"]
        )
        or (needs_regulatory_explanation and not state["ingredient_explanations"])
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

    evidence = {
        "status": evidence_status,
        "jurisdiction": request.jurisdiction,
        "applicable_date": request.applicable_date,
        "final_status": state["status"].value,
        "interpretations": state["ingredient_explanations"],
        "claim_interpretations": state["claim_interpretations"],
        "consistency_findings": state["consistency_findings"],
        "regulatory_evidence": [
            asdict(evidence) for evidence in state["regulatory_evidence"]
        ],
        "unknowns": state["unknowns"],
        "errors": state["errors"],
        "agent_trace": [asdict(item) for item in state["tool_trace"]],
        "react_budget": state["react_budget"],
    }
    return evidence, state


def run_alternative_workflow(
    request: AlternativeWorkflowRequest,
) -> tuple[dict, AgentState]:
    """Re-evaluate the current label, then discover and revalidate alternatives."""

    safety_request = SafetyEvaluationRequest(
        request_id=request.request_id,
        jurisdiction=request.jurisdiction,
        applicable_date=request.applicable_date.isoformat(),
        confirmed_fields=request.confirmed_fields,
        nutrition_rows=request.nutrition_rows,
        constraints=request.constraints,
        resume_token=request.resume_token,
    )
    evaluation = evaluate_user_constraints_result(safety_request)
    _, state = run_regulatory_workflow(safety_request, evaluation)
    state["alternative_request"] = {
        "enabled": True,
        "category": request.category,
        "region": request.region,
        "limit": 5,
    }
    state["status"] = AnalysisStatus.IN_PROGRESS
    state.update(search_alternatives(state))
    if state["status"] is not AnalysisStatus.BLOCKED:
        state.update(revalidate_alternatives(state))
    state.update(final_safety_gate_node(state))
    eligible = [
        item for item in state["alternatives"] if item.get("disposition") == "eligible"
    ]
    excluded = [
        item for item in state["alternatives"] if item.get("disposition") == "excluded"
    ]
    return {
        "status": (
            "completed"
            if state["status"] is AnalysisStatus.COMPLETED
            else state["status"].value
        ),
        "category": request.category,
        "catalog_scope": state["alternative_request"].get("catalog_scope"),
        "eligible": eligible,
        "excluded": excluded,
        "evidence_rejected": state["alternative_request"].get("search_rejected", []),
        "comparison": state["alternative_comparison"],
        "candidate_count": state["alternative_request"].get("candidate_count", 0),
        "revalidated_count": state["alternative_request"].get("revalidated_count", 0),
        "revalidation_rate": state["alternative_request"].get("revalidation_rate", 0.0),
        "unknowns": state["unknowns"],
        "errors": state["errors"],
    }, state
