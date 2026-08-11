"""Version-controlled benchmark cases shared by release evaluation and tests."""

from __future__ import annotations

from .alternatives import AlternativeBenchmarkCase
from .rag import RAGBenchmarkCase

RAG_BENCHMARK = (
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

ALTERNATIVE_BENCHMARK = (
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
