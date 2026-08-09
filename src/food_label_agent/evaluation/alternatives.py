"""Release-blocking evaluation for alternative discovery and revalidation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductComparisonRequest,
)
from food_label_agent.alternatives.service import (
    compare_food_products,
    find_alternative_products,
    revalidate_alternatives,
)
from food_label_agent.ingredients.api_models import ConstraintInput


@dataclass(frozen=True, slots=True)
class AlternativeBenchmarkCase:
    name: str
    category: str
    applicable_date: str
    constraints: tuple[dict[str, Any], ...]
    expected_eligible_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlternativeEvaluation:
    case_count: int
    hard_constraint_violation_rate: float
    label_evidence_coverage: float
    candidate_revalidation_rate: float
    recommendation_traceability_rate: float
    expected_result_accuracy: float
    nutrition_comparison_integrity: float
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_alternative_benchmark(
    cases: tuple[AlternativeBenchmarkCase, ...],
) -> AlternativeEvaluation:
    """Measure whether recommendations preserve constraints and evidence."""

    if not cases:
        raise ValueError("Alternative benchmark requires at least one case")
    eligible_count = 0
    violations = 0
    evidence_complete = 0
    traceable = 0
    discovered = 0
    revalidated = 0
    expected_matches = 0
    comparison_checks: list[bool] = []

    for index, case in enumerate(cases, start=1):
        constraints = [
            ConstraintInput.model_validate(item) for item in case.constraints
        ]
        search = find_alternative_products(
            AlternativeSearchRequest(
                category=case.category,
                applicable_date=case.applicable_date,
                constraints=constraints,
            )
        )
        result = revalidate_alternatives(
            AlternativeRevalidationRequest(
                request_id=f"alternative-benchmark-{index}",
                applicable_date=case.applicable_date,
                constraints=constraints,
                candidates=search["candidates"],
            )
        )
        discovered += result["candidate_count"]
        revalidated += result["revalidated_count"]
        eligible = [
            item for item in result["results"] if item["disposition"] == "eligible"
        ]
        eligible_count += len(eligible)
        violations += sum(item["risk_level"] != "compatible" for item in eligible)
        evidence_complete += sum(
            bool(item.get("evidence_ids") and item.get("label_source_url"))
            for item in eligible
        )
        traceable += sum(
            item.get("revalidated") is True
            and item.get("reason_code") == "INDEPENDENT_REVALIDATION_PASSED"
            for item in eligible
        )
        actual_ids = {item["product_id"] for item in eligible}
        expected_matches += actual_ids == set(case.expected_eligible_ids)
        if eligible:
            comparison = compare_food_products(
                ProductComparisonRequest(products=eligible)
            )
            comparison_checks.extend(
                len(item["values"]) == len(eligible)
                and bool(item.get("basis"))
                and bool(item.get("unit"))
                for item in comparison["comparisons"]
            )

    hard_violation_rate = violations / eligible_count if eligible_count else 0.0
    evidence_rate = evidence_complete / eligible_count if eligible_count else 1.0
    revalidation_rate = revalidated / discovered if discovered else 1.0
    traceability_rate = traceable / eligible_count if eligible_count else 1.0
    expected_accuracy = expected_matches / len(cases)
    comparison_integrity = (
        sum(comparison_checks) / len(comparison_checks) if comparison_checks else 1.0
    )
    blockers: list[str] = []
    if hard_violation_rate > 0:
        blockers.append("alternative_hard_constraint_violation")
    if evidence_rate < 1.0:
        blockers.append("alternative_label_evidence_incomplete")
    if revalidation_rate < 1.0:
        blockers.append("alternative_not_independently_revalidated")
    if traceability_rate < 1.0:
        blockers.append("alternative_reason_not_traceable")
    if expected_accuracy < 1.0:
        blockers.append("alternative_expected_result_regression")
    if comparison_integrity < 1.0:
        blockers.append("alternative_nutrition_basis_mismatch")
    return AlternativeEvaluation(
        case_count=len(cases),
        hard_constraint_violation_rate=hard_violation_rate,
        label_evidence_coverage=evidence_rate,
        candidate_revalidation_rate=revalidation_rate,
        recommendation_traceability_rate=traceability_rate,
        expected_result_accuracy=expected_accuracy,
        nutrition_comparison_integrity=comparison_integrity,
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )
