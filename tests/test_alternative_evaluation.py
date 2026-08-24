from food_label_agent.alternatives.catalog import OfficialChinaCatalog
from food_label_agent.evaluation.alternatives import (
    AlternativeAvailabilityCase,
    evaluate_alternative_availability,
    evaluate_alternative_benchmark,
)
from food_label_agent.evaluation.benchmarks import ALTERNATIVE_BENCHMARK


def test_alternative_release_benchmark_passes_all_blocking_metrics() -> None:
    result = evaluate_alternative_benchmark(ALTERNATIVE_BENCHMARK)

    assert result.evaluation_passed is True
    assert result.release_blockers == ()
    assert result.hard_constraint_violation_rate == 0
    assert result.label_evidence_coverage == 1
    assert result.candidate_revalidation_rate == 1
    assert result.recommendation_traceability_rate == 1
    assert result.expected_result_accuracy == 1
    assert result.nutrition_comparison_integrity == 1


def test_official_catalog_availability_matrix_passes_repeated_health_scenarios() -> None:
    cases = (
        AlternativeAvailabilityCase(
            name="portable-sweet-exact-and-same-use",
            category="biscuit",
            substitute_categories=("biscuit", "confectionery"),
            applicable_date="2026-08-15",
            minimum_eligible=10,
        ),
        AlternativeAvailabilityCase(
            name="portable-sweet-blood-sugar",
            category="biscuit",
            substitute_categories=("biscuit", "confectionery"),
            applicable_date="2026-08-15",
            minimum_eligible=10,
            health_concerns=("blood_sugar",),
        ),
        AlternativeAvailabilityCase(
            name="portable-sweet-blood-lipids",
            category="biscuit",
            substitute_categories=("biscuit", "confectionery"),
            applicable_date="2026-08-15",
            minimum_eligible=10,
            health_concerns=("blood_lipids",),
        ),
        AlternativeAvailabilityCase(
            name="frozen-food-blood-pressure",
            category="frozen_food",
            applicable_date="2026-08-15",
            minimum_eligible=20,
            constraints=(
                {"kind": "allergy", "canonical_value": "fish", "severity": "severe"},
            ),
            health_concerns=("blood_pressure",),
        ),
        AlternativeAvailabilityCase(
            name="sauce-health-comparison",
            category="sauce_condiment",
            applicable_date="2026-08-15",
            minimum_eligible=1,
            health_concerns=("blood_pressure",),
        ),
        AlternativeAvailabilityCase(
            name="dairy-weight-comparison",
            category="dairy",
            applicable_date="2026-08-15",
            minimum_eligible=1,
            health_concerns=("weight",),
        ),
    )

    result = evaluate_alternative_availability(
        cases, catalog=OfficialChinaCatalog()
    )

    assert result.evaluation_passed is True
    assert result.availability_rate == 1
    assert result.hard_constraint_violation_rate == 0
    assert result.eligible_counts == {
        "portable-sweet-exact-and-same-use": 10,
        "portable-sweet-blood-sugar": 10,
        "portable-sweet-blood-lipids": 10,
        "frozen-food-blood-pressure": 25,
        "sauce-health-comparison": 1,
        "dairy-weight-comparison": 1,
    }
