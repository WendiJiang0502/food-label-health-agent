"""Pure routing and safety-gate functions.

These functions are intentionally independent from LangGraph so safety behavior can
be tested without loading an LLM or third-party service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from food_label_agent.domain.models import Evidence
from food_label_agent.domain.types import AnalysisStatus, RiskLevel

from .state import AgentState

INGREDIENTS_FIELD = "ingredients"
LABEL_CLAIMS_FIELD = "label_claims"
DEFAULT_CRITICAL_OCR_CONFIDENCE = 0.85


@dataclass(frozen=True, slots=True)
class SafetyGateResult:
    status: AnalysisStatus
    can_complete: bool
    warnings: tuple[str, ...]
    unknowns: tuple[str, ...]
    violations: tuple[str, ...] = ()


def critical_fields_needing_confirmation(
    state: AgentState,
    *,
    confidence_threshold: float = DEFAULT_CRITICAL_OCR_CONFIDENCE,
) -> tuple[str, ...]:
    """Return critical OCR fields that are absent, empty, or not reliable."""

    missing: list[str] = []
    ingredients = state["label_fields"].get(INGREDIENTS_FIELD)
    if (
        ingredients is None
        or not ingredients.raw_text.strip()
        or not ingredients.is_reliable(confidence_threshold)
    ):
        missing.append(INGREDIENTS_FIELD)
    claims = state["label_fields"].get(LABEL_CLAIMS_FIELD)
    if (
        claims is not None
        and claims.raw_text.strip()
        and not claims.is_reliable(confidence_threshold)
    ):
        missing.append(LABEL_CLAIMS_FIELD)
    return tuple(missing)


def route_after_ocr(state: AgentState) -> str:
    """Select the only safe next step after OCR extraction."""

    if state["ocr_evidence"].get("status") == "needs_confirmation":
        return "confirm_label"
    if critical_fields_needing_confirmation(state):
        return "confirm_label"
    return "normalize_label"


def route_after_normalization(state: AgentState) -> str:
    """Route structural parse failures to human confirmation."""

    if state["normalized_label"].get("requires_confirmation"):
        return "confirm_label"
    return "evaluate_safety"


def final_safety_gate(state: AgentState) -> SafetyGateResult:
    """Derive a final status without allowing later prose generation to weaken risk."""

    warnings = list(state["warnings"])
    unknowns = list(state["unknowns"])
    violations = list(_grounding_violations(state))

    missing_fields = critical_fields_needing_confirmation(state)
    if missing_fields:
        unknowns.append("critical_label_fields_unconfirmed:" + ",".join(missing_fields))

    avoid_findings = [
        finding
        for finding in state["risk_findings"]
        if finding.risk_level is RiskLevel.AVOID
    ]
    if avoid_findings:
        warnings.append("hard_constraint_conflict")
    if any(
        finding.get("status") == "inconsistent"
        for finding in state["consistency_findings"]
    ):
        warnings.append("label_claim_inconsistency")

    explained_label_ids = {
        evidence_id
        for explanation in state["ingredient_explanations"]
        for evidence_id in explanation.get("label_evidence_ids", [])
    }
    for finding in state["risk_findings"]:
        if finding.risk_level is RiskLevel.COMPATIBLE:
            continue
        if finding.reason_code.startswith(("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")):
            continue
        if not set(finding.evidence_ids).intersection(explained_label_ids):
            unknowns.append(f"grounded_interpretation_missing:{finding.constraint}")

    if state["errors"] or violations:
        return SafetyGateResult(
            status=AnalysisStatus.BLOCKED,
            can_complete=False,
            warnings=tuple(dict.fromkeys(warnings)),
            unknowns=tuple(dict.fromkeys(unknowns)),
            violations=tuple(dict.fromkeys(violations)),
        )

    if missing_fields:
        return SafetyGateResult(
            status=AnalysisStatus.NEEDS_CONFIRMATION,
            can_complete=False,
            warnings=tuple(dict.fromkeys(warnings)),
            unknowns=tuple(dict.fromkeys(unknowns)),
            violations=tuple(dict.fromkeys(violations)),
        )

    return SafetyGateResult(
        status=AnalysisStatus.COMPLETED,
        can_complete=True,
        warnings=tuple(dict.fromkeys(warnings)),
        unknowns=tuple(dict.fromkeys(unknowns)),
        violations=tuple(dict.fromkeys(violations)),
    )


def _grounding_violations(state: AgentState) -> tuple[str, ...]:
    violations: list[str] = []
    evidence_by_id = {
        evidence.source_id: evidence for evidence in state["regulatory_evidence"]
    }
    applicable_date = date.fromisoformat(state["applicable_date"])
    for evidence_id, evidence in evidence_by_id.items():
        try:
            start = date.fromisoformat(evidence.effective_from or "")
            end = (
                date.fromisoformat(evidence.effective_to)
                if evidence.effective_to
                else None
            )
        except ValueError:
            violations.append(f"regulatory_evidence_invalid_date:{evidence_id}")
            continue
        if (
            evidence.jurisdiction != state["jurisdiction"]
            or applicable_date < start
            or (end is not None and applicable_date > end)
        ):
            violations.append(f"regulatory_evidence_not_applicable:{evidence_id}")

    findings_by_label_id = {
        evidence_id: finding
        for finding in state["risk_findings"]
        for evidence_id in finding.evidence_ids
    }
    for index, explanation in enumerate(state["ingredient_explanations"]):
        if explanation.get("status") != "explained":
            continue
        is_additive = explanation.get("explanation_type") == "additive"
        label_ids = set(explanation.get("label_evidence_ids", []))
        matching_findings = {
            findings_by_label_id[evidence_id]
            for evidence_id in label_ids
            if evidence_id in findings_by_label_id
        }
        if not label_ids or (not matching_findings and not is_additive):
            violations.append(f"interpretation_unbound_label_evidence:{index}")
        elif not is_additive:
            explanation_risk = explanation.get("risk_level")
            if any(
                explanation_risk != finding.risk_level.value
                for finding in matching_findings
            ):
                violations.append(f"interpretation_changed_risk:{index}")

        regulatory_ids = set(explanation.get("regulatory_evidence_ids", []))
        citations = explanation.get("citations", [])
        citation_ids = {
            citation.get("evidence_id")
            for citation in citations
            if citation.get("evidence_id")
        }
        if not regulatory_ids or regulatory_ids != citation_ids:
            violations.append(f"interpretation_missing_citations:{index}")
        unknown_ids = regulatory_ids - set(evidence_by_id)
        if unknown_ids:
            violations.append(f"interpretation_unknown_regulatory_evidence:{index}")
        for citation in citations:
            evidence_id = citation.get("evidence_id")
            evidence = evidence_by_id.get(evidence_id)
            if evidence is not None and not _citation_matches_evidence(
                citation, evidence
            ):
                violations.append(f"interpretation_citation_mismatch:{index}")

    claim_explanations_by_label_id = {
        evidence_id: explanation
        for explanation in state["claim_interpretations"]
        for evidence_id in explanation.get("label_evidence_ids", [])
    }
    for index, explanation in enumerate(state["claim_interpretations"]):
        regulatory_ids = set(explanation.get("regulatory_evidence_ids", []))
        citations = explanation.get("citations", [])
        citation_ids = {
            citation.get("evidence_id")
            for citation in citations
            if citation.get("evidence_id")
        }
        if regulatory_ids != citation_ids:
            violations.append(f"claim_interpretation_missing_citations:{index}")
        if regulatory_ids - set(evidence_by_id):
            violations.append(
                f"claim_interpretation_unknown_regulatory_evidence:{index}"
            )
        for citation in citations:
            evidence = evidence_by_id.get(citation.get("evidence_id"))
            if evidence is not None and not _citation_matches_evidence(
                citation, evidence
            ):
                violations.append(f"claim_interpretation_citation_mismatch:{index}")

    for index, finding in enumerate(state["consistency_findings"]):
        if finding.get("status") != "consistent":
            continue
        claim_type = finding.get("claim_type")
        if claim_type not in {"sugar_free", "low_sugar"}:
            continue
        explanation = next(
            (
                claim_explanations_by_label_id[evidence_id]
                for evidence_id in finding.get("label_evidence_ids", [])
                if evidence_id in claim_explanations_by_label_id
            ),
            None,
        )
        if explanation is None or not explanation.get("regulatory_evidence_ids"):
            violations.append(f"claim_threshold_conclusion_ungrounded:{index}")
    return tuple(dict.fromkeys(violations))


def _citation_matches_evidence(citation: dict, evidence: Evidence) -> bool:
    expected = {
        "standard_number": evidence.standard_number,
        "section": evidence.section,
        "source_url": evidence.source_url,
        "page_start": evidence.page_start,
        "page_end": evidence.page_end,
        "content_hash": evidence.content_hash,
    }
    if any(citation.get(key) != value for key, value in expected.items()):
        return False
    evidence_text = " ".join(str(evidence.evidence_text or "").split())
    return evidence_text.startswith(str(citation.get("evidence_excerpt", "")))
