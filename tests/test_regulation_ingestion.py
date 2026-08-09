from __future__ import annotations

from datetime import date

from food_label_agent.regulations.bm25 import BM25Index
from food_label_agent.regulations.ingestion import PageText, ingest_pages
from food_label_agent.regulations.registry import (
    documents_applicable_on,
    get_document,
    validate_registry,
)
from food_label_agent.regulations.serialization import (
    load_clause_index,
    save_ingestion_result,
)
from food_label_agent.regulations.service import DATA_DIR
from food_label_agent.regulations.vector import TfidfVectorIndex


def test_registry_has_contiguous_version_windows_and_official_sources() -> None:
    validate_registry()

    current = {
        document.document_id for document in documents_applicable_on(date(2026, 8, 9))
    }
    future = {
        document.document_id for document in documents_applicable_on(date(2028, 1, 1))
    }
    assert "GB7718-2011" in current
    assert "GB7718-2025" not in current
    assert "GB7718-2025" in future
    assert "GB7718-2011" not in future
    assert "GB2760-2024" in current


def test_structure_aware_ingestion_splits_sections_and_preserves_pages() -> None:
    document = get_document("GB7718-2011")
    pages = (
        PageText(
            page_number=1,
            text=(
                "GB 7718-2011\n"
                "1 范围\n本标准适用于预包装食品标签。\n"
                "2 术语和定义\n配料是加工时使用的物质。"
            ),
        ),
        PageText(
            page_number=2,
            text=(
                "2.1 预包装食品\n预先定量包装的食品。\n"
                "附录 D\nD.1 致敏物质\n可在配料表中标示。\n"
                "D.2 可能含有致敏物质时宜提示"
            ),
        ),
    )

    result = ingest_pages(document, pages, document_hash="a" * 64)

    sections = [clause.section for clause in result.clauses]
    assert "1 范围" in sections
    assert "2 术语和定义" in sections
    assert "2.1 预包装食品" in sections
    assert "D.1 致敏物质" in sections
    assert "D.2 可能含有致敏物质时宜提示" in sections
    assert all(clause.document_hash == "a" * 64 for clause in result.clauses)
    assert result.clauses[-1].page_start == 2
    assert result.warnings == ()


def test_ingestion_index_round_trip(tmp_path) -> None:
    document = get_document("GB28050-2011")
    result = ingest_pages(
        document,
        (
            PageText(
                page_number=1,
                text="1 范围\n本标准规定了营养标签和营养成分表。",
            ),
        ),
        document_hash="b" * 64,
    )
    output = tmp_path / "gb28050.json"

    save_ingestion_result(result, output)
    loaded = load_clause_index(output)

    assert loaded == result.clauses


def test_bm25_ranks_exact_regulatory_terms() -> None:
    index = BM25Index(
        (
            "致敏物质 可能含有 同一生产线 交叉污染",
            "营养成分表 能量 蛋白质 脂肪 钠",
            "食品添加剂 使用量 食品分类",
        )
    )

    hits = index.search("同线生产可能带入过敏原")

    assert hits
    assert hits[0].index == 0


def test_vector_retrieval_connects_reviewed_domain_paraphrases() -> None:
    index = TfidfVectorIndex(
        (
            "生产加工过程可能带入致敏物质时宜标示提示信息",
            "营养成分表应标示能量和核心营养素",
        )
    )

    hits = index.search("交叉污染风险如何提示")

    assert hits
    assert hits[0].index == 0
    assert hits[0].score > 0


def test_packaged_official_indexes_are_structured_and_hashed() -> None:
    gb7718 = load_clause_index(DATA_DIR / "GB7718-2011.json")
    gb28050 = load_clause_index(DATA_DIR / "GB28050-2011.json")

    assert len(gb7718) >= 70
    assert len(gb28050) >= 60
    assert all(clause.document_hash for clause in (*gb7718, *gb28050))
    assert any(clause.section == "2.3 配料" for clause in gb7718)
    assert any(clause.section.startswith("4.1 ") for clause in gb28050)
