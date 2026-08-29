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
                "required_fields_for_hard_constraints",
                "current_for_applicable_date",
                "content_hash_verified",
                "health_comparison_fields_rank_but_do_not_block",
            ],
            "constraint_evaluation": "independent_revalidation_required",
            "health_concerns": [],
            "health_data_policy": "ranking_only_unless_explicit_limit",
            "source_category": "biscuit",
            "searched_categories": ["biscuit"],
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


def test_search_collapses_equivalent_pack_sizes_before_candidate_limit() -> None:
    result = find_alternative_products(
        AlternativeSearchRequest(
            category="confectionery",
            applicable_date="2026-08-23",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="fish", severity="moderate"
                )
            ],
            limit=50,
        )
    )

    hashes = [item["label"]["content_hash"] for item in result["candidates"]]
    assert len(hashes) == len(set(hashes))
    assert result["catalog_coverage"]["equivalent_package_variants_collapsed"] > 0


def test_expired_label_is_excluded_and_exposes_evidence_state() -> None:
    result = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2028-08-09",
            constraints=[_allergy("fish")],
        ),
        catalog=JsonProductCatalog(),
    )

    assert result["status"] == "unknown"
    expired = next(
        item
        for item in result["rejected"]
        if item["reason_code"] == "LABEL_EVIDENCE_EXPIRED"
    )
    assert expired["label_coverage"]["evidence_status"]["status"] == "expired"
    assert expired["label_coverage"]["evidence_status"]["label"] == "已过有效期"


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


def test_health_concern_ranking_runs_after_safety_and_explains_improvement() -> None:
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=[_allergy("fish")],
        ),
        catalog=JsonProductCatalog(),
    )
    for candidate in search["candidates"]:
        candidate["label"]["nutrition_rows"].append(["碳水化合物", "60克"])
    result = revalidate_alternatives(
        AlternativeRevalidationRequest(
            request_id="alternative-health-ranking",
            applicable_date="2026-08-09",
            constraints=[_allergy("fish")],
            health_concerns=["blood_sugar"],
            current_nutrition_rows=[
                ["项目", "每100克"],
                ["糖", "10克"],
                ["碳水化合物", "60克"],
            ],
            candidates=search["candidates"],
        )
    )

    eligible = [item for item in result["results"] if item["disposition"] == "eligible"]
    assert [item["product_id"] for item in eligible] == [
        "fixture-biscuit-milk-cracker",
        "fixture-biscuit-oat-plain",
    ]
    assert eligible[0]["ranking_layers"] == {
        "same_category_use": True,
        "same_use_fallback": False,
        "constraint_safety": True,
        "health_focus_points": 3,
        "health_metrics_compared": 2,
        "official_store_available": False,
        "portion_basis_available": False,
    }
    assert (
        "与当前商品同口径比较，糖5g，更低于当前的10g"
        in eligible[0]["ranking_reasons"]
    )
    assert eligible[0]["health_comparisons"][0] == {
        "nutrient": "sugars",
        "label": "糖",
        "candidate_value": 5.0,
        "current_value": 10.0,
        "unit": "g",
        "basis": "per_100g",
        "direction": "lower",
        "outcome": "improved",
    }
    assert result["ranking_method"]["layers"] == [
        "same_category_use",
        "allergen_and_constraint_safety",
        "health_concern_nutrition",
        "purchase_and_portion_usability",
    ]


def test_health_comparison_fields_rank_candidates_without_blocking_safety() -> None:
    baseline = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=[_allergy("fish")],
        ),
        catalog=JsonProductCatalog(),
    )
    with_health_focus = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=[_allergy("fish")],
            health_concerns=["blood_lipids"],
        ),
        catalog=JsonProductCatalog(),
    )

    assert len(with_health_focus["candidates"]) == len(baseline["candidates"])
    assert all(
        "饱和脂肪" in item["catalog_eligibility"]["missing_comparison_fields"]
        for item in with_health_focus["candidates"]
    )
    assert all(
        item["catalog_eligibility"]["eligible_for_current_context"]
        for item in with_health_focus["candidates"]
    )


def test_search_rejects_a_requested_category_that_is_not_a_same_use_scope() -> None:
    result = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            substitute_categories=["biscuit", "drink"],
            applicable_date="2026-08-09",
            constraints=[_allergy("milk")],
            limit=20,
        ),
        catalog=JsonProductCatalog(),
    )

    assert {
        item["product_id"] for item in result["candidates"]
    } == {"fixture-biscuit-oat-plain", "fixture-biscuit-milk-cracker"}
    assert any(
        item["reason_code"] == "NOT_A_GENUINE_SAME_USE_SUBSTITUTE"
        for item in result["rejected"]
    )
    assert result["selection_basis"]["category_match"] == "same_use_scope"


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


def test_comparison_normalizes_packaging_serving_to_per_100g() -> None:
    products = [
        {
            "product_id": "serving",
            "display_name": "每份标示商品",
            "revalidated": True,
            "disposition": "eligible",
            "risk_level": "compatible",
            "normalized_label": {
                "nutrition": {
                    "basis": {"type": "per_serving", "amount": 25, "unit": "g"},
                    "nutrients": [
                        {
                            "canonical_name": "sugars",
                            "value": 2,
                            "unit": "g",
                            "basis": "per_serving",
                            "evidence_id": "serving.sugar",
                        }
                    ],
                }
            },
        },
        {
            "product_id": "hundred",
            "display_name": "每百克标示商品",
            "revalidated": True,
            "disposition": "eligible",
            "risk_level": "compatible",
            "normalized_label": {
                "nutrition": {
                    "basis": {"type": "per_100g", "amount": 100, "unit": "g"},
                    "nutrients": [
                        {
                            "canonical_name": "sugars",
                            "value": 10,
                            "unit": "g",
                            "basis": "per_100g",
                            "evidence_id": "hundred.sugar",
                        }
                    ],
                }
            },
        },
    ]

    result = compare_food_products(
        ProductComparisonRequest(products=products, nutrient_keys=["sugars"])
    )

    assert result["status"] == "compared"
    assert result["comparisons"][0]["basis"] == "per_100g"
    assert [item["value"] for item in result["comparisons"][0]["values"]] == [
        8.0,
        10.0,
    ]


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
