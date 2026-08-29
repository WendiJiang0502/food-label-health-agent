from __future__ import annotations

from food_label_agent.alternatives.catalog import OfficialChinaCatalog
from food_label_agent.alternatives.evidence_audit import (
    audit_product_label,
    summarize_label_coverage,
)


def test_every_official_product_gets_field_level_coverage() -> None:
    catalog = OfficialChinaCatalog()
    products = [
        *catalog.search(category="dairy", region="CN").records,
        *catalog.search(category="breakfast_cereal", region="CN").records,
        *catalog.search(category="sauce_condiment", region="CN").records,
        *catalog.search(category="snack", region="CN").records,
        *catalog.search(category="frozen_food", region="CN").records,
        *catalog.search(category="confectionery", region="CN").records,
        *catalog.search(category="biscuit", region="CN").records,
    ]

    audits = {product.product_id: audit_product_label(product) for product in products}
    assert {
        "cn-official:yili:pure-milk",
        "cn-official:yili:amx-zero-sucrose-yogurt",
        "cn-official:seamild:green-pure-oats",
        "cn-official:lkk:less-salt-soy-sauce",
        "cn-official:wolong:daily-nuts",
    } < set(audits)
    assert len(audits) == 68
    assert sum(item["full_label_ready"] for item in audits.values()) == 63
    assert audits["cn-official:yili:pure-milk"]["current_evidence_gate_passed"]
    assert (
        "完整配料表文字"
        in audits["cn-official:lkk:less-salt-soy-sauce"]["verified_fields"]
    )
    assert "完整配料表文字" in audits["cn-official:wolong:daily-nuts"]["missing_fields"]

    summary = summarize_label_coverage(products)
    assert summary["total"] == 68
    assert summary["full_label_count"] == 63
    assert summary["needs_review_count"] == 5
    assert summary["evidence_gate_count"] == 64
    assert summary["packaging_snapshot_count"] == 0
    assert summary["nutrition_snapshot_count"] == 0
    assert summary["complete_packaging_snapshot_count"] == 0
    assert summary["official_page_snapshot_count"] == 0


def test_search_rejection_explains_exact_official_label_gaps() -> None:
    from food_label_agent.alternatives.models import AlternativeSearchRequest
    from food_label_agent.alternatives.service import find_alternative_products
    from food_label_agent.ingredients.api_models import ConstraintInput

    result = find_alternative_products(
        AlternativeSearchRequest(
            category="sauce_condiment",
            applicable_date="2026-08-15",
            constraints=[ConstraintInput(kind="allergy", canonical_value="peanut")],
        ),
        catalog=OfficialChinaCatalog(),
    )

    rejected = result["rejected"][0]
    assert rejected["label_coverage"]["review_priority"] == "high"
    assert "完整配料表文字" in rejected["label_coverage"]["verified_fields"]
    assert "包装过敏原提示" in rejected["label_coverage"]["missing_fields"]
    assert result["catalog_coverage"] == {
        "total": 4,
        "sku_count": 0,
        "specification_count": 0,
        "full_label_count": 3,
        "transcribed_label_count": 3,
        "evidence_gate_count": 3,
        "packaging_snapshot_count": 0,
        "nutrition_snapshot_count": 0,
        "complete_packaging_snapshot_count": 0,
        "official_page_snapshot_count": 0,
        "packaging_needs_review_count": 4,
        "packaging_coverage_rate": 0.0,
        "needs_review_count": 1,
        "coverage_rate": 0.75,
        "fully_verified_count": 0,
        "conditionally_verified_count": 3,
        "context_needs_review_count": 1,
    }
