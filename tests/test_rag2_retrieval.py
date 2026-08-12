from __future__ import annotations

import json

from food_label_agent.regulations.models import RegulationSearchRequest
from food_label_agent.regulations.semantic import (
    OpenAIDenseEmbeddingProvider,
    OpenAIIndependentReranker,
    RAG2Settings,
    RAGProviderError,
)
from food_label_agent.regulations.service import get_default_regulation_store
from food_label_agent.regulations.store import (
    DENSE_RETRIEVAL_METHOD,
    RAG2_RETRIEVAL_METHOD,
    RegulationStore,
)

TARGET = "reg.cn.gb7718-2011.55ec4a2419d5ea77"


class ChineseSemanticFake:
    provider = "test-dense"
    model = "zh-semantic-v1"

    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def embed(self, texts):
        self.seen_texts.extend(texts)
        return tuple(
            (1.0, 0.0)
            if "一种原料由好几样组成" in text or "两种或两种以上" in text
            else (0.0, 1.0)
            for text in texts
        )


class TargetFirstReranker:
    provider = "test-reranker"
    model = "independent-reranker-v1"

    def rank(self, query, candidates):
        ids = [item["evidence_id"] for item in candidates]
        return tuple(sorted(ids, key=lambda value: value != TARGET))


def _request():
    return RegulationSearchRequest(
        query="一种原料由好几样组成时包装上怎么写",
        jurisdiction="CN",
        applicable_date="2026-08-09",
        topics=["ingredient_labeling"],
        limit=5,
    )


def test_dense_retrieval_uses_semantic_similarity_after_date_filtering() -> None:
    dense = ChineseSemanticFake()
    base = get_default_regulation_store()
    store = RegulationStore(base.clauses, dense_provider=dense)

    response = store.search(_request(), profile="hybrid_dense")

    assert response.retrieval_method == DENSE_RETRIEVAL_METHOD
    assert response.results[0]["evidence_id"] == TARGET
    assert response.results[0]["retrieval_signals"]["embedding_model"] == (
        "zh-semantic-v1"
    )
    assert not any("GB 7718-2025" in text for text in dense.seen_texts)


def test_independent_reranker_is_a_separate_observable_stage() -> None:
    store = RegulationStore(
        get_default_regulation_store().clauses,
        dense_provider=ChineseSemanticFake(),
        reranker=TargetFirstReranker(),
    )

    response = store.search(_request(), profile="hybrid_dense_rerank")

    assert response.retrieval_method == RAG2_RETRIEVAL_METHOD
    assert response.results[0]["evidence_id"] == TARGET
    signals = response.results[0]["retrieval_signals"]
    assert signals["reranker_rank"] == 1
    assert signals["reranker_model"] == "independent-reranker-v1"
    assert "pre_rerank_score" in signals


def test_openai_embedding_provider_batches_and_caches_normalized_vectors() -> None:
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append(payload)
        return {
            "data": [
                {"index": index, "embedding": [3.0, 4.0]}
                for index, _ in enumerate(payload["input"])
            ]
        }

    provider = OpenAIDenseEmbeddingProvider(
        RAG2Settings(api_key="test", embedding_dimensions=256),
        transport=transport,
    )

    first = provider.embed(("乳来源成分", "复合原料"))
    second = provider.embed(("乳来源成分",))

    assert first[0] == (0.6, 0.8)
    assert second[0] == first[0]
    assert len(calls) == 1
    assert calls[0]["dimensions"] == 256


def test_openai_reranker_can_only_return_supplied_evidence_ids() -> None:
    captured = {}

    def transport(url, headers, payload, timeout):
        captured.update(payload)
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {"scores": {"evidence-a": 20, "evidence-b": 95}}
                            ),
                        }
                    ],
                }
            ],
        }

    reranker = OpenAIIndependentReranker(
        RAG2Settings(api_key="test"), transport=transport
    )
    result = reranker.rank(
        "哪个条款更相关",
        (
            {"evidence_id": "evidence-a", "section": "A", "text": "甲"},
            {"evidence_id": "evidence-b", "section": "B", "text": "乙"},
        ),
    )

    assert result == ("evidence-b", "evidence-a")
    score_schema = captured["text"]["format"]["schema"]["properties"]["scores"]
    assert set(score_schema["properties"]) == {"evidence-a", "evidence-b"}
    assert score_schema["required"] == ["evidence-a", "evidence-b"]
    assert score_schema["additionalProperties"] is False
    assert captured["store"] is False


def test_reranker_rejects_a_response_missing_any_candidate_score() -> None:
    def transport(url, headers, payload, timeout):
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"scores": {"evidence-a": 90}}),
                        }
                    ],
                }
            ],
        }

    reranker = OpenAIIndependentReranker(
        RAG2Settings(api_key="test"), transport=transport
    )
    try:
        reranker.rank(
            "测试",
            (
                {"evidence_id": "evidence-a", "section": "A", "text": "甲"},
                {"evidence_id": "evidence-b", "section": "B", "text": "乙"},
            ),
        )
    except RAGProviderError as exc:
        assert str(exc) == "rag_reranker_response_invalid"
    else:
        raise AssertionError("Incomplete reranker scores were accepted")
