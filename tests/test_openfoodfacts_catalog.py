from __future__ import annotations

from food_label_agent.alternatives.catalog import (
    CatalogSearchResult,
    CatalogUnavailable,
    HybridProductCatalog,
    JsonProductCatalog,
    OpenFoodFactsCatalog,
)
from food_label_agent.alternatives.models import AlternativeSearchRequest
from food_label_agent.alternatives.service import find_alternative_products
from food_label_agent.ingredients.api_models import ConstraintInput


def _product(*, complete: bool = True) -> dict:
    return {
        "code": "6901668938824",
        "product_name_zh": "真实示例苏打饼干",
        "brands": "示例品牌",
        "ingredients_text_zh": "小麦粉、植物油、白砂糖",
        "allergens": "en:gluten",
        "traces": "en:milk",
        "nutrition_data_per": "100g",
        "nutriments": {"proteins_100g": 8.2, "sodium_100g": 0.31},
        "last_modified_t": 1767225600,
        "states_tags": ["en:ingredients-completed"] if complete else [],
        "selected_images": {
            "ingredients": {
                "display": {"zh": "https://images.example/ingredients.jpg"}
            },
            "nutrition": {"display": {"zh": "https://images.example/nutrition.jpg"}},
        },
    }


def test_live_catalog_maps_versioned_label_and_image_evidence_and_caches() -> None:
    calls: list[str] = []

    def fetch(url: str, headers: dict[str, str], timeout: float) -> dict:
        calls.append(url)
        assert headers["User-Agent"].startswith("Milestone4Test/")
        assert timeout == 1.0
        return {"products": [_product()]}

    catalog = OpenFoodFactsCatalog(
        user_agent="Milestone4Test/1.0 (test@example.com)",
        timeout_seconds=1.0,
        fetch_json=fetch,
    )
    first = catalog.search(category="biscuit", region="CN")
    second = catalog.search(category="biscuit", region="CN")

    assert first == second
    assert len(calls) == 1
    assert first.provider == "open_food_facts"
    product = first.records[0]
    assert product.product_id == "off:6901668938824"
    assert product.label.source_record_version == "1767225600"
    assert product.label.ingredients_image_url.endswith("ingredients.jpg")
    assert product.label.source_authority == "community"
    assert product.label.nutrition_rows[-1] == ["钠", "310毫克"]


def test_live_catalog_rejects_unreviewed_ingredient_evidence() -> None:
    catalog = OpenFoodFactsCatalog(
        fetch_json=lambda *_: {"products": [_product(complete=False)]}
    )

    result = catalog.search(category="biscuit", region="CN")

    assert result.records == ()
    assert result.rejected[0]["reason_code"] == "LIVE_LABEL_EVIDENCE_INCOMPLETE"
    assert "ingredients_review_state" in result.rejected[0]["missing_fields"]


def test_live_catalog_enriches_search_record_from_product_detail() -> None:
    def fetch(url: str, _headers: dict[str, str], _timeout: float) -> dict:
        if "/search?" in url:
            return {"products": [{"code": "6901668938824"}]}
        return {"product": _product()}

    result = OpenFoodFactsCatalog(fetch_json=fetch).search(
        category="biscuit", region="CN"
    )

    assert [item.product_id for item in result.records] == ["off:6901668938824"]
    assert result.rejected == ()


def test_live_catalog_candidate_still_passes_deterministic_evidence_gate() -> None:
    catalog = OpenFoodFactsCatalog(fetch_json=lambda *_: {"products": [_product()]})
    result = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-09",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="milk", severity="severe"
                )
            ],
        ),
        catalog=catalog,
    )

    assert result["catalog_scope"] == "open_food_facts"
    assert result["catalog_status"] == "ok"
    assert len(result["candidates"]) == 1


class _UnavailableCatalog:
    def search(self, *, category: str, region: str) -> CatalogSearchResult:
        raise CatalogUnavailable("offline")


def test_hybrid_catalog_uses_explicit_reviewed_fallback_on_live_failure() -> None:
    result = HybridProductCatalog(
        live=_UnavailableCatalog(), fallback=JsonProductCatalog()
    ).search(category="biscuit", region="CN")

    assert result.status == "degraded"
    assert result.provider == "open_food_facts_with_curated_fallback"
    assert result.records
    assert result.warnings == ("live_catalog_unavailable_used_curated_fallback",)
