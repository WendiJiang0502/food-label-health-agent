"""Pure routing and safety-gate functions.

These functions are intentionally independent from LangGraph so safety behavior can
be tested without loading an LLM or third-party service.
"""

from __future__ import annotations

from dataclasses import dataclass

from food_label_agent.domain.types import AnalysisStatus, RiskLevel

from .state import AgentState

INGREDIENTS_FIELD = "ingredients"
DEFAULT_CRITICAL_OCR_CONFIDENCE = 0.85


@dataclass(frozen=True, slots=True)
class SafetyGateResult:
    status: AnalysisStatus
    can_complete: bool
    warnings: tuple[str, ...]
    unknowns: tuple[str, ...]


def critical_fields_needing_confirmation(
    state: AgentState,
    *,
    confidence_threshold: float = DEFAULT_CRITICAL_OCR_CONFIDENCE,
) -> tuple[str, ...]:
    """Return critical OCR fields that are absent, empty, or not reliable."""

    ingredients = state["label_fields"].get(INGREDIENTS_FIELD)
    if ingredients is None:
        return (INGREDIENTS_FIELD,)
    if not ingredients.raw_text.strip():
        return (INGREDIENTS_FIELD,)
    if not ingredients.is_reliable(confidence_threshold):
        return (INGREDIENTS_FIELD,)
    return ()


def route_after_ocr(state: AgentState) -> str:
    """Select the only safe next step after OCR extraction."""

    if state["ocr_evidence"].get("status") == "needs_confirmation":
        return "confirm_label"
    if critical_fields_needing_confirmation(state):
        return "confirm_label"
    return "normalize_label"


def final_safety_gate(state: AgentState) -> SafetyGateResult:
    """Derive a final status without allowing later prose generation to weaken risk."""

    warnings = list(state["warnings"])
    unknowns = list(state["unknowns"])

    missing_fields = critical_fields_needing_confirmation(state)
    if missing_fields:
        unknowns.append("critical_label_fields_unconfirmed:" + ",".join(missing_fields))

    avoid_findings = [
        finding for finding in state["risk_findings"] if finding.risk_level is RiskLevel.AVOID
    ]
    if avoid_findings:
        warnings.append("hard_constraint_conflict")

    if state["errors"]:
        return SafetyGateResult(
            status=AnalysisStatus.BLOCKED,
            can_complete=False,
            warnings=tuple(dict.fromkeys(warnings)),
            unknowns=tuple(dict.fromkeys(unknowns)),
        )

    if missing_fields:
        return SafetyGateResult(
            status=AnalysisStatus.NEEDS_CONFIRMATION,
            can_complete=False,
            warnings=tuple(dict.fromkeys(warnings)),
            unknowns=tuple(dict.fromkeys(unknowns)),
        )

    return SafetyGateResult(
        status=AnalysisStatus.COMPLETED,
        can_complete=True,
        warnings=tuple(dict.fromkeys(warnings)),
        unknowns=tuple(dict.fromkeys(unknowns)),
    )
