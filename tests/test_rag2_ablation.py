from __future__ import annotations

from food_label_agent.evaluation.rag import RAGBenchmarkCase
from food_label_agent.evaluation.rag_ablation import evaluate_rag2_ablation
from food_label_agent.regulations.models import RegulationClause
from food_label_agent.regulations.store import RegulationStore


def _clause(evidence_id: str, text: str) -> RegulationClause:
    return RegulationClause(
        evidence_id=evidence_id,
        source_id="official-test",
        standard_number="GB 7718-2011",
        title="预包装食品标签通则",
        section=evidence_id,
        evidence_text=text,
        jurisdiction="CN",
        published_on="2011-04-20",
        effective_from="2012-04-20",
        effective_to=None,
        source_url="https://www.nhc.gov.cn/test",
        authority_level="A",
        source_type="official_standard",
        topics=("ingredient_labeling",),
        keywords=(),
    )


class SemanticProvider:
    provider = "test-dense"
    model = "semantic-v1"

    def embed(self, texts):
        return tuple(
            (1.0, 0.0) if "套着另一份配方" in text or "内部构成" in text else (0.0, 1.0)
            for text in texts
        )


class CorrectReranker:
    provider = "test-reranker"
    model = "reranker-v1"

    def rank(self, query, candidates):
        ids = [item["evidence_id"] for item in candidates]
        return tuple(sorted(ids, key=lambda value: value != "compound"))


def test_offline_ablation_records_baselines_without_remote_calls() -> None:
    result = evaluate_rag2_ablation(RegulationStore((_clause("compound", "复合配料"),)))

    assert result.case_count == 12
    assert result.dense_status == "not_run"
    assert result.reranker_status == "not_run"
    assert result.evaluation_passed is True


def test_four_way_ablation_proves_dense_and_reranker_improvement() -> None:
    store = RegulationStore(
        tuple(
            _clause(f"noise-{index}", f"包装文字应当清晰醒目 示例{index}")
            for index in range(6)
        )
        + (_clause("compound", "复合组分必须展开标注其内部构成"),)
    )
    cases = (
        RAGBenchmarkCase(
            name="semantic-paraphrase",
            query="一包里套着另一份配方怎么交代",
            applicable_date="2026-08-09",
            topics=("ingredient_labeling",),
            relevant_evidence_ids=("compound",),
            allowed_standard_numbers=("GB 7718-2011",),
        ),
    )

    result = evaluate_rag2_ablation(
        store,
        cases,
        dense_provider=SemanticProvider(),
        reranker=CorrectReranker(),
    )

    assert result.profiles["hybrid_dense"]["recall_at_k"] == 1.0
    assert result.profiles["hybrid_dense_rerank"]["top1_accuracy"] == 1.0
    assert result.final_recall_lift is not None
    assert result.final_recall_lift > 0
    assert result.evaluation_passed is True
