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

RAG2_BENCHMARK = (
    RAGBenchmarkCase(
        name="compound-ingredient-paraphrase",
        query="一种原料本身由好几样东西组成，包装上需要把里面的原料写出来吗",
        applicable_date="2026-08-09",
        topics=("ingredient_labeling",),
        relevant_evidence_ids=("reg.cn.gb7718-2011.55ec4a2419d5ea77",),
        allowed_standard_numbers=("GB 7718-2011",),
    ),
    RAGBenchmarkCase(
        name="ingredient-order-two-percent",
        query="用得特别少不到百分之二的配料还必须严格按多少排序吗",
        applicable_date="2026-08-09",
        topics=("ingredient_labeling",),
        relevant_evidence_ids=("reg.cn.gb7718-2011.0b7d764be42fdd13",),
        allowed_standard_numbers=("GB 7718-2011",),
    ),
    RAGBenchmarkCase(
        name="additive-name-labeling",
        query="添加剂能不能只写作用类别，还是还要把具体名称写上",
        applicable_date="2026-08-09",
        topics=("ingredient_labeling",),
        relevant_evidence_ids=("reg.cn.gb7718-2011.1ab7839e16ea7bcd",),
        allowed_standard_numbers=("GB 7718-2011",),
    ),
    RAGBenchmarkCase(
        name="allergen-cross-line-current",
        query="和含奶产品共用一条生产线，包装可以怎样提醒消费者",
        applicable_date="2026-08-09",
        topics=("allergen",),
        relevant_evidence_ids=("reg.cn.gb7718-2011.faq-62.allergen-labeling",),
        allowed_standard_numbers=("GB 7718-2011",),
    ),
    RAGBenchmarkCase(
        name="allergen-cross-line-future",
        query="生产车间可能带入花生痕量，应当怎样做预防性提示",
        applicable_date="2028-01-01",
        topics=("precautionary_labeling",),
        relevant_evidence_ids=("reg.cn.gb7718-2025.faq-39.precautionary-labeling",),
        allowed_standard_numbers=("GB 7718-2025",),
    ),
    RAGBenchmarkCase(
        name="mandatory-core-nutrients",
        query="营养表最少必须列出哪些核心项目以及参考值百分比",
        applicable_date="2026-08-09",
        topics=("nutrition_labeling",),
        relevant_evidence_ids=("reg.cn.gb28050-2011.1990b91d1c7cf88d",),
        allowed_standard_numbers=("GB 28050-2011",),
    ),
    RAGBenchmarkCase(
        name="nutrition-box-layout",
        query="营养信息是否必须放在一个方框里并使用固定表题",
        applicable_date="2026-08-09",
        topics=("nutrition_labeling",),
        relevant_evidence_ids=("reg.cn.gb28050-2011.366f67c8027b763b",),
        allowed_standard_numbers=("GB 28050-2011",),
    ),
    RAGBenchmarkCase(
        name="nutrition-serving-basis",
        query="营养数值可以按每份写吗，写每份时还需要说明什么",
        applicable_date="2026-08-09",
        topics=("nutrition_labeling",),
        relevant_evidence_ids=("reg.cn.gb28050-2011.827f4160cc4e34fc",),
        allowed_standard_numbers=("GB 28050-2011",),
    ),
    RAGBenchmarkCase(
        name="hydrogenated-oil-trans-fat",
        query="产品使用部分氢化油以后营养表还必须增加哪一项",
        applicable_date="2026-08-09",
        topics=("nutrition_labeling",),
        relevant_evidence_ids=("reg.cn.gb28050-2011.3537a71363f863fd",),
        allowed_standard_numbers=("GB 28050-2011",),
    ),
    RAGBenchmarkCase(
        name="sugar-free-threshold",
        query="声称没有糖时每一百克允许到什么水平",
        applicable_date="2026-08-09",
        topics=("nutrition_claim",),
        relevant_evidence_ids=("reg.cn.gb28050-2011.4eb4d1b095e31d9d",),
        allowed_standard_numbers=("GB 28050-2011",),
    ),
    RAGBenchmarkCase(
        name="nutrition-label-exemption",
        query="哪些小包装或生鲜预包装食品可以不强制提供营养标签",
        applicable_date="2026-08-09",
        topics=("nutrition_labeling",),
        relevant_evidence_ids=("reg.cn.gb28050-2011.68a385ee418cdc28",),
        allowed_standard_numbers=("GB 28050-2011",),
    ),
    RAGBenchmarkCase(
        name="no-applicable-official-version",
        query="乳过敏提示应写在什么位置",
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
