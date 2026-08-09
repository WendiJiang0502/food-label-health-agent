from __future__ import annotations

from food_label_agent.evaluation.rag import (
    RAGBenchmarkCase,
    evaluate_rag_benchmark,
)
from food_label_agent.regulations.service import get_default_regulation_store

BENCHMARK = (
    RAGBenchmarkCase(
        name="current-allergen-standard",
        query="乳清蛋白属于哪类致敏配料",
        applicable_date="2026-08-09",
        topics=("allergen",),
        relevant_standard_numbers=("GB 7718-2011",),
    ),
    RAGBenchmarkCase(
        name="future-allergen-standard",
        query="共用生产线可能带入过敏成分如何提示",
        applicable_date="2028-01-01",
        topics=("precautionary_labeling",),
        relevant_standard_numbers=("GB 7718-2025",),
    ),
    RAGBenchmarkCase(
        name="nutrition-claim",
        query="每百克低糖声称的含量条件",
        applicable_date="2026-08-09",
        topics=("nutrition_claim",),
        relevant_standard_numbers=("GB 28050-2011",),
    ),
    RAGBenchmarkCase(
        name="additive-standard",
        query="亚硝酸钠食品添加剂使用标准",
        applicable_date="2026-08-09",
        topics=("food_additive",),
        relevant_standard_numbers=("GB 2760-2024",),
    ),
    RAGBenchmarkCase(
        name="no-applicable-evidence",
        query="乳过敏标签要求",
        applicable_date="2010-01-01",
        topics=("allergen",),
        expect_unknown=True,
    ),
)


def test_release_rag_benchmark_passes_all_blocking_metrics() -> None:
    result = evaluate_rag_benchmark(get_default_regulation_store(), BENCHMARK, k=5)

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
        (BENCHMARK, 0, 1.0),
        (BENCHMARK, 5, 1.1),
        (missing_relevance, 5, 1.0),
    ):
        try:
            evaluate_rag_benchmark(store, cases, k=k, minimum_recall=minimum_recall)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid RAG benchmark configuration was accepted")
