"""Framework-neutral workflow slices used by HTTP and future graph entrypoints."""

from __future__ import annotations

from dataclasses import asdict

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

from .nodes import (
    final_safety_gate_node,
    interpret_claims,
    interpret_label,
    retrieve_regulations,
    verify_consistency,
)
from .state import create_initial_state


def attach_regulatory_interpretation(
    request: SafetyEvaluationRequest,
    evaluation: SafetyEvaluationResponse,
) -> dict:
    """Continue a completed rule evaluation through evidence and the final gate."""

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

    needs_regulatory_explanation = any(
        finding.risk_level is not RiskLevel.COMPATIBLE
        and not finding.reason_code.startswith(
            ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
        )
        for finding in state["risk_findings"]
    )
    if needs_regulatory_explanation:
        state.update(retrieve_regulations(state))
        if state["status"] is not AnalysisStatus.BLOCKED:
            state.update(interpret_label(state))
    if state["status"] is not AnalysisStatus.BLOCKED:
        state.update(interpret_claims(state))
    if state["status"] is not AnalysisStatus.BLOCKED:
        state.update(verify_consistency(state))
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

    return {
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
    }
