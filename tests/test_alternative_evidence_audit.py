from __future__ import annotations

from food_label_agent.alternatives.catalog import OfficialChinaCatalog
from food_label_agent.alternatives.evidence_audit import (
    assess_product_eligibility,
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
        "sku_specification_identity_count": 0,
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
        "nutrition_field_counts": {
            "energy": 3,
            "protein": 3,
            "fat": 3,
            "carbohydrate": 3,
            "sodium": 3,
            "sugars": 3,
            "saturated_fat": 0,
            "dietary_fiber": 0,
        },
        "nutrition_field_coverage_rates": {
            "energy": 0.75,
            "protein": 0.75,
            "fat": 0.75,
            "carbohydrate": 0.75,
            "sodium": 0.75,
            "sugars": 0.75,
            "saturated_fat": 0.0,
            "dietary_fiber": 0.0,
        },
        "packaging_verified_nutrition_field_counts": {
            "energy": 0,
            "protein": 0,
            "fat": 0,
            "carbohydrate": 0,
            "sodium": 0,
            "sugars": 0,
            "saturated_fat": 0,
            "dietary_fiber": 0,
        },
        "core_nutrition_complete_count": 3,
        "health_comparison_nutrition_complete_count": 0,
        "expired_evidence_count": 0,
        "expired_evidence_rate": 0.0,
        "stale_evidence_count": 0,
        "stale_evidence_rate": 0.0,
        "current_purchase_evidence_count": 0,
        "purchase_availability_rate": 0.0,
        "metrics_as_of": "2026-08-15",
        "fully_verified_count": 0,
        "conditionally_verified_count": 3,
        "context_needs_review_count": 1,
    }


def test_declared_zero_total_fat_provides_only_a_conservative_saturated_bound() -> None:
    product = next(
        item
        for item in OfficialChinaCatalog().search(category="drink", region="CN").records
        if item.product_id == "cn-official:cocacola:zero-sugar:500ml"
    )

    assessment = assess_product_eligibility(
        product, health_concerns=("blood_lipids",)
    )

    assert assessment["missing_comparison_fields"] == []
    assert assessment["bounded_comparison_fields"] == [
        {
            "nutrient": "saturated_fat",
            "qualifier": "upper_bound",
            "value": 0.5,
            "unit": "g",
            "basis": "per_100ml",
            "derivation": "saturated_fat_not_greater_than_declared_total_fat",
            "regulation_reference": "GB 28050-2011:C.1",
            "source_evidence_id": product.label.evidence_id,
            "label": "饱和脂肪",
        }
    ]


def test_saturated_bound_never_satisfies_an_exact_nutrition_limit() -> None:
    from food_label_agent.ingredients.api_models import ConstraintInput

    product = next(
        item
        for item in OfficialChinaCatalog().search(category="drink", region="CN").records
        if item.product_id == "cn-official:cocacola:zero-sugar:500ml"
    )

    assessment = assess_product_eligibility(
        product,
        constraints=(
            ConstraintInput(
                kind="nutrition_limit",
                canonical_value="saturated_fat",
                operator="max",
                threshold=0.5,
                unit="g",
                basis="per_100ml",
            ),
        ),
    )

    assert assessment["eligible_for_current_context"] is False
    assert "饱和脂肪" in assessment["missing_required_fields"]
