from __future__ import annotations

from food_label_agent.alternatives.catalog import JsonProductCatalog
from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductComparisonRequest,
)
from food_label_agent.alternatives.service import (
    compare_food_products,
    find_alternative_products,
    revalidate_alternatives,
)
from food_label_agent.domain.models import LabelField
from food_label_agent.graph.routing import final_safety_gate
from food_label_agent.graph.state import create_initial_state
from food_label_agent.ingredients.api_models import ConstraintInput


def _allergy(value: str) -> ConstraintInput:
    return ConstraintInput(kind="allergy", canonical_value=value, severity="severe")


def test_search_rejects_incomplete_label_before_recommendation() -> None:
    result = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=[_allergy("milk")],
        ),
        catalog=JsonProductCatalog(),
    )

    assert result["status"] == "candidates_found"
    assert len(result["candidates"]) == 2
    assert result["selection_basis"] == {
        "source": "curated_verification_catalog",
        "category_match": "exact",
        "region_match": "exact",
        "evidence_requirements": [
            "required_fields_for_active_context",
            "current_for_applicable_date",
            "content_hash_verified",
        ],
        "constraint_evaluation": "independent_revalidation_required",
        "health_concerns": [],
    }
    assert len(result["rejected"]) == 1
    rejected = result["rejected"][0]
    assert rejected["product_id"] == "fixture-biscuit-partial-label"
    assert rejected["display_name"] == "示例·配方待核对薄脆"
    assert rejected["reason_code"] == "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
    assert rejected["evidence_ids"] == [
        "product.fixture-biscuit-partial-label.label.2026-08"
    ]
    assert rejected["label_coverage"]["status"] == "needs_review"


def test_search_excludes_current_product_before_revalidation() -> None:
    result = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=[_allergy("milk")],
            exclude_product_ids=["fixture-biscuit-oat-plain"],
        ),
        catalog=JsonProductCatalog(),
    )

    assert all(
        item["product_id"] != "fixture-biscuit-oat-plain"
        for item in result["candidates"]
    )


def test_every_candidate_is_revalidated_and_milk_match_is_never_eligible() -> None:
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=[_allergy("milk")],
        ),
        catalog=JsonProductCatalog(),
    )
    result = revalidate_alternatives(
        AlternativeRevalidationRequest(
            request_id="alternative-rule-test",
            applicable_date="2026-08-09",
            constraints=[_allergy("milk")],
            candidates=search["candidates"],
        )
    )

    assert result["revalidation_rate"] == 1.0
    assert result["candidate_count"] == result["revalidated_count"] == 2
    eligible = [item for item in result["results"] if item["disposition"] == "eligible"]
    excluded = [item for item in result["results"] if item["disposition"] == "excluded"]
    assert [item["product_id"] for item in eligible] == ["fixture-biscuit-oat-plain"]
    assert excluded[0]["risk_level"] == "avoid"
    assert excluded[0]["findings"][0]["matched_text"] == "全脂乳粉"
    assert all(item["revalidated"] is True for item in result["results"])
    assert all(item["evidence_ids"] for item in result["results"])
    assert eligible[0]["rank"] == 1
    assert eligible[0]["ranking_reasons"]
    assert eligible[0]["packaging_label"]["ingredients_text"]
    assert eligible[0]["packaging_label"]["evidence_quality"] == "complete"
    assert eligible[0]["packaging_label"]["evidence_id"] in eligible[0]["evidence_ids"]


def test_nutrition_hard_limit_filters_high_sodium_candidate() -> None:
    constraint = ConstraintInput(
        kind="nutrition_limit",
        canonical_value="sodium",
        operator="max",
        threshold=300,
        unit="mg",
        basis="per_100g",
    )
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="processed_meat",
            applicable_date="2026-08-09",
            constraints=[constraint],
        ),
        catalog=JsonProductCatalog(),
    )
    result = revalidate_alternatives(
        AlternativeRevalidationRequest(
            request_id="alternative-nutrition-test",
            applicable_date="2026-08-09",
            constraints=[constraint],
            candidates=search["candidates"],
        )
    )

    risks = {item["product_id"]: item["risk_level"] for item in result["results"]}
    assert risks["fixture-meat-chicken-low-sodium"] == "compatible"
    assert risks["fixture-meat-chicken-high-sodium"] == "avoid"


def test_comparison_refuses_mismatched_nutrition_basis() -> None:
    products = [
        {
            "product_id": "one",
            "display_name": "一号",
            "revalidated": True,
            "disposition": "eligible",
            "risk_level": "compatible",
            "normalized_label": {
                "nutrition": {
                    "nutrients": [
                        {
                            "canonical_name": "sodium",
                            "value": 100,
                            "unit": "mg",
                            "basis": "per_100g",
                            "evidence_id": "one.sodium",
                        }
                    ]
                }
            },
        },
        {
            "product_id": "two",
            "display_name": "二号",
            "revalidated": True,
            "disposition": "eligible",
            "risk_level": "compatible",
            "normalized_label": {
                "nutrition": {
                    "nutrients": [
                        {
                            "canonical_name": "sodium",
                            "value": 80,
                            "unit": "mg",
                            "basis": "per_100ml",
                            "evidence_id": "two.sodium",
                        }
                    ]
                }
            },
        },
    ]

    result = compare_food_products(ProductComparisonRequest(products=products))

    assert result["status"] == "unknown"
    assert result["comparisons"] == []
    assert "nutrition_basis_or_unit_not_comparable:sodium" in result["unknowns"]


def test_final_gate_blocks_forged_eligible_alternative() -> None:
    state = create_initial_state(
        request_id="alternative-gate-test",
        jurisdiction="CN",
        applicable_date="2026-08-09",
    )
    state["label_fields"] = {
        "ingredients": LabelField(
            name="ingredients",
            raw_text="白砂糖",
            confidence=1.0,
            confirmed_by_user=True,
        )
    }
    state["alternatives"] = [
        {
            "product_id": "forged",
            "disposition": "eligible",
            "risk_level": "avoid",
            "revalidated": False,
            "evidence_ids": [],
        }
    ]

    result = final_safety_gate(state)

    assert result.can_complete is False
    assert "eligible_alternative_not_revalidated:0" in result.violations
    assert "eligible_alternative_has_constraint_risk:0" in result.violations
    assert "eligible_alternative_missing_label_evidence:0" in result.violations


def test_final_gate_requires_image_evidence_for_live_alternative() -> None:
    state = create_initial_state(
        request_id="live-alternative-gate-test",
        jurisdiction="CN",
        applicable_date="2026-08-09",
    )
    state["label_fields"] = {
        "ingredients": LabelField(
            name="ingredients",
            raw_text="白砂糖",
            confidence=1.0,
            confirmed_by_user=True,
        )
    }
    state["alternatives"] = [
        {
            "product_id": "off:123",
            "catalog_scope": "live_open_food_facts",
            "disposition": "eligible",
            "risk_level": "compatible",
            "revalidated": True,
            "evidence_ids": ["off.product.123.label"],
            "label_source_url": "https://world.openfoodfacts.org/product/123",
            "ingredients_image_url": None,
        }
    ]

    result = final_safety_gate(state)

    assert result.can_complete is False
    assert "eligible_live_alternative_missing_label_image:0" in result.violations
