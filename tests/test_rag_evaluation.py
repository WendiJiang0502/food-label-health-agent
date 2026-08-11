from __future__ import annotations

from food_label_agent.evaluation.benchmarks import RAG_BENCHMARK
from food_label_agent.evaluation.rag import RAGBenchmarkCase, evaluate_rag_benchmark
from food_label_agent.regulations.service import get_default_regulation_store


def test_release_rag_benchmark_passes_all_blocking_metrics() -> None:
    result = evaluate_rag_benchmark(get_default_regulation_store(), RAG_BENCHMARK, k=5)

    assert result.evaluation_passed is True
    assert result.recall_at_k == 1.0
    assert result.hybrid_method_rate == 1.0
    assert result.official_evidence_rate == 1.0
    assert result.unknown_refusal_accuracy == 1.0
    assert result.version_violation_count == 0
    assert result.release_blockers == ()


def test_rag_evaluation_rejects_invalid_benchmark_configuration() -> None:
    store = get_default_regulation_store()

    missing_relevance = (
        RAGBenchmarkCase(
            name="missing-relevance",
            query="标签",
            applicable_date="2026-08-09",
            topics=("ingredient_labeling",),
        ),
    )
    for cases, k, minimum_recall in (
        ((), 5, 1.0),
        (RAG_BENCHMARK, 0, 1.0),
        (RAG_BENCHMARK, 5, 1.1),
        (missing_relevance, 5, 1.0),
    ):
        try:
            evaluate_rag_benchmark(store, cases, k=k, minimum_recall=minimum_recall)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid RAG benchmark configuration was accepted")
