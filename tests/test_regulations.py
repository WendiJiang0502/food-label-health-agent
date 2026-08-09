from __future__ import annotations

from food_label_agent.regulations.corpus import OFFICIAL_CLAUSES
from food_label_agent.regulations.models import RegulationSearchRequest
from food_label_agent.regulations.service import search_regulations


def search(*, applicable_date: str, query: str = "乳清蛋白 过敏原"):
    return search_regulations(
        RegulationSearchRequest(
            query=query,
            jurisdiction="CN",
            applicable_date=applicable_date,
            topics=["allergen", "ingredient_labeling"],
            limit=10,
        )
    )


def test_seed_corpus_is_official_traceable_and_unique() -> None:
    evidence_ids = [clause.evidence_id for clause in OFFICIAL_CLAUSES]

    assert len(evidence_ids) == len(set(evidence_ids))
    assert OFFICIAL_CLAUSES
    for clause in OFFICIAL_CLAUSES:
        assert clause.source_url.startswith("https://www.nhc.gov.cn/")
        assert clause.authority_level == "A"
        assert len(clause.content_hash) == 64
        assert clause.section
        assert clause.evidence_text


def test_2026_search_uses_2011_version_and_excludes_future_standard() -> None:
    response = search(applicable_date="2026-08-09")

    assert response.status == "found"
    assert response.results
    assert {item["standard_number"] for item in response.results} == {"GB 7718-2011"}
    assert all(
        item["applicability_status"] == "applicable" for item in response.results
    )


def test_2028_search_uses_2025_version_and_excludes_replaced_standard() -> None:
    response = search(applicable_date="2028-01-01")

    assert response.status == "found"
    assert response.results
    assert {item["standard_number"] for item in response.results} == {"GB 7718-2025"}


def test_no_applicable_clause_is_unknown_instead_of_using_future_evidence() -> None:
    response = search(applicable_date="2010-01-01")

    assert response.status == "unknown"
    assert response.results == []
    assert response.unknowns == ["no_applicable_official_clause"]


def test_wrong_jurisdiction_does_not_leak_chinese_evidence() -> None:
    response = search_regulations(
        RegulationSearchRequest(
            query="allergen milk",
            jurisdiction="US",
            applicable_date="2026-08-09",
            topics=["allergen"],
        )
    )

    assert response.status == "unknown"
    assert response.results == []


def test_hybrid_retrieval_finds_nutrition_standard_from_packaged_index() -> None:
    response = search_regulations(
        RegulationSearchRequest(
            query="GB 28050-2011 营养成分表 能量 核心营养素",
            jurisdiction="CN",
            applicable_date="2026-08-09",
            topics=["nutrition_labeling"],
            limit=5,
        )
    )

    assert response.status == "found"
    assert response.retrieval_method == "hybrid_bm25_tfidf_rerank_v1"
    assert response.results[0]["standard_number"] == "GB 28050-2011"
    assert response.results[0]["retrieval_signals"]["bm25_score"] > 0
    assert response.results[0]["retrieval_signals"]["vector_score"] > 0
    assert response.results[0]["retrieval_signals"]["rerank_score"] > 0
    assert response.results[0]["page_start"] is not None
    assert response.results[0]["document_hash"]


def test_explicit_future_standard_query_does_not_fall_back_to_old_version() -> None:
    response = search_regulations(
        RegulationSearchRequest(
            query="GB 7718-2025 致敏物质",
            jurisdiction="CN",
            applicable_date="2026-08-09",
            topics=["allergen"],
        )
    )

    assert response.status == "unknown"
    assert response.results == []


def test_current_additive_standard_is_registered_with_official_evidence() -> None:
    response = search_regulations(
        RegulationSearchRequest(
            query="GB 2760-2024 食品添加剂使用标准",
            jurisdiction="CN",
            applicable_date="2026-08-09",
            topics=["food_additive"],
        )
    )

    assert response.status == "found"
    assert {item["standard_number"] for item in response.results} == {"GB 2760-2024"}
    assert response.results[0]["source_type"] == "official_announcement"
