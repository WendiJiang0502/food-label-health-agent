from food_label_agent.evaluation.alternatives import (
    AlternativeBenchmarkCase,
    evaluate_alternative_benchmark,
)


def test_alternative_release_benchmark_passes_all_blocking_metrics() -> None:
    cases = (
        AlternativeBenchmarkCase(
            name="milk-free-biscuit",
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=(
                {"kind": "allergy", "canonical_value": "milk", "severity": "severe"},
            ),
            expected_eligible_ids=("fixture-biscuit-oat-plain",),
        ),
        AlternativeBenchmarkCase(
            name="soy-free-drink",
            category="drink",
            applicable_date="2026-08-09",
            constraints=(
                {"kind": "allergy", "canonical_value": "soy", "severity": "severe"},
            ),
            expected_eligible_ids=("fixture-drink-oat", "fixture-drink-milk"),
        ),
        AlternativeBenchmarkCase(
            name="sodium-limited-meat",
            category="processed_meat",
            applicable_date="2026-08-09",
            constraints=(
                {
                    "kind": "nutrition_limit",
                    "canonical_value": "sodium",
                    "operator": "max",
                    "threshold": 300,
                    "unit": "mg",
                    "basis": "per_100g",
                },
            ),
            expected_eligible_ids=("fixture-meat-chicken-low-sodium",),
        ),
    )

    result = evaluate_alternative_benchmark(cases)

    assert result.evaluation_passed is True
    assert result.release_blockers == ()
    assert result.hard_constraint_violation_rate == 0
    assert result.label_evidence_coverage == 1
    assert result.candidate_revalidation_rate == 1
    assert result.recommendation_traceability_rate == 1
    assert result.expected_result_accuracy == 1
    assert result.nutrition_comparison_integrity == 1
