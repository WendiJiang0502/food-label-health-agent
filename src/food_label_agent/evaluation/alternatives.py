"""Release-blocking evaluation for alternative discovery and revalidation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.alternatives.catalog import JsonProductCatalog, ProductCatalog
from food_label_agent.alternatives.category import suggest_product_category
from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductComparisonRequest,
)
from food_label_agent.alternatives.service import (
    brand_owner_key,
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
class AlternativeAvailabilityCase:
    """One repeatable catalog-availability scenario for a real substitute use."""

    name: str
    category: str
    applicable_date: str
    minimum_eligible: int
    substitute_categories: tuple[str, ...] = ()
    constraints: tuple[dict[str, Any], ...] = ()
    health_concerns: tuple[str, ...] = ()
    current_product_name: str | None = None
    minimum_target_comparable_rate: float = 0.0
    minimum_effective_display_rate: float = 0.0
    minimum_distinct_brands: int = 0
    minimum_distinct_formulas: int = 0
    minimum_verified_packaging_brands: int = 0


@dataclass(frozen=True, slots=True)
class AlternativeAvailabilityEvaluation:
    case_count: int
    passed_case_count: int
    availability_rate: float
    hard_constraint_violation_rate: float
    eligible_counts: dict[str, int]
    catalog_record_count: int
    displayable_count: int
    displayable_rate: float
    target_comparable_count: int
    target_comparable_rate: float
    effective_display_rate: float
    case_metrics: dict[str, dict[str, Any]]
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


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


@dataclass(frozen=True, slots=True)
class CategoryInferenceEvaluation:
    dataset_scope: str
    sample_count: int
    category_count: int
    top1_recall: float
    macro_recall: float
    automatic_precision: float
    per_category_recall: dict[str, float]
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_category_inference(
    records: tuple[Any, ...], *, minimum_rate: float = 0.85
) -> CategoryInferenceEvaluation:
    """Regression-check known catalog labels; this is not an external holdout."""

    if not records:
        raise ValueError("Category inference evaluation requires records")
    totals: dict[str, int] = {}
    correct: dict[str, int] = {}
    automatic_total = 0
    automatic_correct = 0
    for record in records:
        expected = str(record.category)
        result = suggest_product_category(
            {
                "product_name": record.display_name,
                "ingredients": record.label.ingredients_text,
            }
        )
        is_correct = result.get("category") == expected
        totals[expected] = totals.get(expected, 0) + 1
        correct[expected] = correct.get(expected, 0) + int(is_correct)
        if result.get("status") == "automatic":
            automatic_total += 1
            automatic_correct += int(is_correct)
    sample_count = len(records)
    per_category = {
        category: correct.get(category, 0) / total
        for category, total in sorted(totals.items())
    }
    top1 = sum(correct.values()) / sample_count
    macro = sum(per_category.values()) / len(per_category)
    automatic_precision = (
        automatic_correct / automatic_total if automatic_total else 1.0
    )
    blockers = []
    if top1 < minimum_rate:
        blockers.append("alternative_category_recall_below_threshold")
    if any(rate < minimum_rate for rate in per_category.values()):
        blockers.append("alternative_category_recall_below_threshold_for_category")
    if automatic_precision < minimum_rate:
        blockers.append("alternative_category_automatic_precision_below_threshold")
    return CategoryInferenceEvaluation(
        dataset_scope="official_catalog_self_consistency_not_external_holdout",
        sample_count=sample_count,
        category_count=len(per_category),
        top1_recall=top1,
        macro_recall=macro,
        automatic_precision=automatic_precision,
        per_category_recall=per_category,
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )


def evaluate_alternative_benchmark(
    cases: tuple[AlternativeBenchmarkCase, ...],
    *,
    catalog: ProductCatalog | None = None,
) -> AlternativeEvaluation:
    """Measure whether recommendations preserve constraints and evidence."""

    if not cases:
        raise ValueError("Alternative benchmark requires at least one case")
    benchmark_catalog = catalog or JsonProductCatalog()
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
            ),
            catalog=benchmark_catalog,
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


def evaluate_alternative_availability(
    cases: tuple[AlternativeAvailabilityCase, ...],
    *,
    catalog: ProductCatalog,
) -> AlternativeAvailabilityEvaluation:
    """Verify breadth repeatedly without rewarding unsafe or duplicate results."""

    if not cases:
        raise ValueError("Alternative availability evaluation requires at least one case")
    eligible_counts: dict[str, int] = {}
    passed = 0
    violations = 0
    eligible_total = 0
    catalog_total = 0
    target_comparable_total = 0
    effective_total = 0
    case_metrics: dict[str, dict[str, Any]] = {}
    threshold_failures: list[str] = []
    for index, case in enumerate(cases, start=1):
        constraints = [
            ConstraintInput.model_validate(item) for item in case.constraints
        ]
        search = find_alternative_products(
            AlternativeSearchRequest(
                category=case.category,
                substitute_categories=list(case.substitute_categories),
                applicable_date=case.applicable_date,
                constraints=constraints,
                health_concerns=list(case.health_concerns),
                current_product_name=case.current_product_name,
                limit=50,
            ),
            catalog=catalog,
        )
        result = revalidate_alternatives(
            AlternativeRevalidationRequest(
                request_id=f"alternative-availability-{index}",
                applicable_date=case.applicable_date,
                constraints=constraints,
                health_concerns=list(case.health_concerns),
                source_category=case.category,
                candidates=search["candidates"],
            )
        )
        eligible = [
            item for item in result["results"] if item["disposition"] == "eligible"
        ]
        eligible_counts[case.name] = len(eligible)
        passed += len(eligible) >= case.minimum_eligible
        violations += sum(item["risk_level"] != "compatible" for item in eligible)
        eligible_total += len(eligible)
        catalog_total += int(search.get("catalog_coverage", {}).get("total") or 0)
        target_comparable = [
            item
            for item in eligible
            if not item.get("catalog_eligibility", {}).get(
                "missing_comparison_fields", []
            )
        ]
        target_comparable_total += len(target_comparable)
        case_effective_count = (
            len(target_comparable) if case.health_concerns else len(eligible)
        )
        effective_total += case_effective_count
        case_catalog_total = int(search.get("catalog_coverage", {}).get("total") or 0)
        case_comparable_rate = (
            len(target_comparable) / len(eligible) if eligible else 0.0
        )
        case_effective_rate = (
            case_effective_count / case_catalog_total if case_catalog_total else 0.0
        )
        distinct_brands = sorted(
            {
                brand_owner_key(item.get("brand"))
                for item in eligible
                if str(item.get("brand") or "").strip()
            }
        )
        distinct_formula_count = len(eligible)
        verified_packaging_brands = sorted(
            {
                brand_owner_key(item.get("brand"))
                for item in eligible
                if _has_complete_verified_packaging(item)
            }
        )
        case_metrics[case.name] = {
            "catalog_record_count": case_catalog_total,
            "displayable_count": len(eligible),
            "target_comparable_count": len(target_comparable),
            "target_comparable_rate": case_comparable_rate,
            "effective_display_rate": case_effective_rate,
            "minimum_target_comparable_rate": case.minimum_target_comparable_rate,
            "minimum_effective_display_rate": case.minimum_effective_display_rate,
            "distinct_brand_count": len(distinct_brands),
            "distinct_brands": distinct_brands,
            "minimum_distinct_brands": case.minimum_distinct_brands,
            "distinct_formula_count": distinct_formula_count,
            "minimum_distinct_formulas": case.minimum_distinct_formulas,
            "verified_packaging_brand_count": len(verified_packaging_brands),
            "verified_packaging_brands": verified_packaging_brands,
            "minimum_verified_packaging_brands": (
                case.minimum_verified_packaging_brands
            ),
        }
        if case_comparable_rate < case.minimum_target_comparable_rate:
            threshold_failures.append(
                f"{case.name}:target_comparable_rate_below_minimum"
            )
        if case_effective_rate < case.minimum_effective_display_rate:
            threshold_failures.append(
                f"{case.name}:effective_display_rate_below_minimum"
            )
        if len(distinct_brands) < case.minimum_distinct_brands:
            threshold_failures.append(
                f"{case.name}:distinct_brand_count_below_minimum"
            )
        if distinct_formula_count < case.minimum_distinct_formulas:
            threshold_failures.append(
                f"{case.name}:distinct_formula_count_below_minimum"
            )
        if (
            len(verified_packaging_brands)
            < case.minimum_verified_packaging_brands
        ):
            threshold_failures.append(
                f"{case.name}:verified_packaging_brand_count_below_minimum"
            )
    violation_rate = violations / eligible_total if eligible_total else 0.0
    blockers: list[str] = []
    if passed != len(cases):
        blockers.append("alternative_catalog_availability_below_minimum")
    if violation_rate:
        blockers.append("alternative_availability_contains_constraint_violation")
    if threshold_failures:
        blockers.extend(threshold_failures)
    return AlternativeAvailabilityEvaluation(
        case_count=len(cases),
        passed_case_count=passed,
        availability_rate=passed / len(cases),
        hard_constraint_violation_rate=violation_rate,
        eligible_counts=eligible_counts,
        catalog_record_count=catalog_total,
        displayable_count=eligible_total,
        displayable_rate=(eligible_total / catalog_total if catalog_total else 0.0),
        target_comparable_count=target_comparable_total,
        target_comparable_rate=(
            target_comparable_total / eligible_total if eligible_total else 0.0
        ),
        effective_display_rate=(effective_total / catalog_total if catalog_total else 0.0),
        case_metrics=case_metrics,
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )


def _has_complete_verified_packaging(item: dict[str, Any]) -> bool:
    label = item.get("label") or {}
    sku = str(item.get("sku") or "")
    specification = str(item.get("specification") or "")
    kinds = {
        str(snapshot.get("evidence_kind") or "")
        for snapshot in label.get("packaging_snapshots") or []
        if snapshot.get("artifact_type")
        in {"packaging_photo", "official_label_artwork"}
        and snapshot.get("review_status") == "verified"
        and str(snapshot.get("sku") or "") == sku
        and str(snapshot.get("specification") or "") == specification
        and snapshot.get("primary_reviewer_id")
        and snapshot.get("secondary_reviewer_id")
        and snapshot.get("primary_reviewer_id")
        != snapshot.get("secondary_reviewer_id")
    }
    return bool(sku and specification and ("combined" in kinds or {"ingredients", "nutrition"} <= kinds))
