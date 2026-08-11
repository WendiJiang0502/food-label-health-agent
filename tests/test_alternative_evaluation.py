from food_label_agent.evaluation.alternatives import (
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
