"""Release-blocking deterministic allergen-rule evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.domain.models import UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel
from food_label_agent.ingredients.allergens import (
    ALLERGEN_CATEGORIES,
    evaluate_constraints,
)
from food_label_agent.ingredients.normalization import normalize_ingredients


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    category_count: int
    alias_count: int
    explicit_case_count: int
    explicit_recall: float
    severe_miss_rate: float
    evidence_traceability_rate: float
    ambiguous_unknown_accuracy: float
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_allergen_rules() -> RuleEvaluation:
    aliases = [
        (key, alias)
        for key, category in ALLERGEN_CATEGORIES.items()
        for alias in category.aliases
    ]
    explicit_findings = []
    for key, alias in aliases:
        constraint = _allergy(key)
        explicit_findings.extend(
            (
                evaluate_constraints(
                    normalize_ingredients(f"白砂糖、{alias}"), [constraint]
                )[0],
                evaluate_constraints(
                    normalize_ingredients(f"复合调味料（白砂糖、{alias}）"),
                    [constraint],
                )[0],
            )
        )
    ambiguous_findings = [
        evaluate_constraints(normalize_ingredients(term), [_allergy(key)])[0]
        for key, category in ALLERGEN_CATEGORIES.items()
        for term in category.ambiguous_terms
    ]
    explicit_hits = sum(
        finding.risk_level is RiskLevel.AVOID for finding in explicit_findings
    )
    traceable = sum(
        bool(finding.matched_text and finding.evidence_ids)
        for finding in explicit_findings
    )
    ambiguous_unknowns = sum(
        finding.risk_level is RiskLevel.UNKNOWN for finding in ambiguous_findings
    )
    case_count = len(explicit_findings)
    recall = explicit_hits / case_count if case_count else 0.0
    miss_rate = 1.0 - recall
    traceability = traceable / case_count if case_count else 0.0
    ambiguous_accuracy = (
        ambiguous_unknowns / len(ambiguous_findings) if ambiguous_findings else 1.0
    )
    blockers = []
    if recall < 1.0 or miss_rate > 0:
        blockers.append("severe_allergen_miss_detected")
    if traceability < 1.0:
        blockers.append("allergen_result_not_traceable")
    if ambiguous_accuracy < 1.0:
        blockers.append("ambiguous_ingredient_was_guessed")
    return RuleEvaluation(
        category_count=len(ALLERGEN_CATEGORIES),
        alias_count=len(aliases),
        explicit_case_count=case_count,
        explicit_recall=recall,
        severe_miss_rate=miss_rate,
        evidence_traceability_rate=traceability,
        ambiguous_unknown_accuracy=ambiguous_accuracy,
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )


def _allergy(value: str) -> UserConstraint:
    return UserConstraint(
        kind=ConstraintKind.ALLERGY,
        canonical_value=value,
        severity="severe",
    )
