from __future__ import annotations

from food_label_agent.alternatives.catalog import (
    CatalogSearchResult,
    CatalogUnavailable,
    ExpandedChinaCatalog,
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


def test_live_catalog_uses_last_successful_cache_during_a_later_outage() -> None:
    calls = 0

    def fetch(*_args) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"products": [_product()]}
        raise OSError("temporary outage")

    catalog = OpenFoodFactsCatalog(fetch_json=fetch, cache_ttl_seconds=-1)
    first = catalog.search(category="biscuit", region="CN")
    second = catalog.search(category="biscuit", region="CN")

    assert first.records == second.records
    assert second.status == "degraded"
    assert "live_catalog_used_last_successful_cache" in second.warnings


def test_live_catalog_rejects_unreviewed_ingredient_evidence() -> None:
    catalog = OpenFoodFactsCatalog(
        fetch_json=lambda *_: {"products": [_product(complete=False)]}
    )

    result = catalog.search(category="biscuit", region="CN")

    assert result.records == ()
    assert result.rejected[0]["reason_code"] == "LIVE_LABEL_EVIDENCE_INCOMPLETE"
    assert "ingredients_review_state" in result.rejected[0]["missing_fields"]


def test_live_catalog_accepts_reviewed_ingredient_text_without_a_separate_image() -> (
    None
):
    raw = _product()
    raw["selected_images"].pop("ingredients")
    catalog = OpenFoodFactsCatalog(fetch_json=lambda *_: {"products": [raw]})

    result = catalog.search(category="biscuit", region="CN")

    assert [item.product_id for item in result.records] == ["off:6901668938824"]
    assert result.records[0].label.ingredients_image_url is None


def test_live_catalog_normalizes_drink_nutrition_per_100ml() -> None:
    raw = _product()
    raw["nutrition_data_per"] = "100ml"
    catalog = OpenFoodFactsCatalog(fetch_json=lambda *_: {"products": [raw]})

    result = catalog.search(category="drink", region="CN")

    assert result.records[0].label.nutrition_basis_text == "每100毫升"
    assert result.records[0].label.nutrition_rows[0] == ["项目", "每100毫升"]


def test_drink_search_keeps_the_same_drink_use_instead_of_any_beverage() -> None:
    products = []
    for code, name in (
        ("6900000000001", "DL橙汁"),
        ("6900000000002", "百事可乐"),
        ("6900000000003", "饮用纯净水"),
    ):
        raw = _product()
        raw["code"] = code
        raw["product_name_zh"] = name
        products.append(raw)
    catalog = OpenFoodFactsCatalog(fetch_json=lambda *_: {"products": products})

    result = find_alternative_products(
        AlternativeSearchRequest(
            category="drink",
            applicable_date="2026-08-09",
            current_product_name="鲜橙汁",
        ),
        catalog=catalog,
    )

    assert [item["display_name"] for item in result["candidates"]] == ["DL橙汁"]
    assert (
        sum(
            item["reason_code"] == "DIFFERENT_USE_WITHIN_CATEGORY"
            for item in result["rejected"]
        )
        == 2
    )


def test_chips_search_does_not_treat_candy_as_the_same_snack_use() -> None:
    products = []
    for code, name in (
        ("6900000000011", "青柠味薯片"),
        ("6900000000012", "水果软糖"),
        ("6900000000013", "每日坚果"),
    ):
        raw = _product()
        raw["code"] = code
        raw["product_name_zh"] = name
        products.append(raw)
    catalog = OpenFoodFactsCatalog(fetch_json=lambda *_: {"products": products})

    result = find_alternative_products(
        AlternativeSearchRequest(
            category="snack",
            applicable_date="2026-08-09",
            current_product_name="膨化零食与脆片",
        ),
        catalog=catalog,
    )

    assert [item["display_name"] for item in result["candidates"]] == ["青柠味薯片"]


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


class _UnexpectedCatalog:
    def search(self, *, category: str, region: str) -> CatalogSearchResult:
        raise AssertionError(f"supplement should not be called for {category}/{region}")


def test_hybrid_catalog_uses_explicit_reviewed_fallback_on_live_failure() -> None:
    result = HybridProductCatalog(
        live=_UnavailableCatalog(), fallback=JsonProductCatalog()
    ).search(category="biscuit", region="CN")

    assert result.status == "degraded"
    assert result.provider == "open_food_facts_with_curated_fallback"
    assert result.records
    assert result.warnings == ("live_catalog_unavailable_used_curated_fallback",)


def test_expanded_china_catalog_keeps_reviewed_records_and_adds_live_evidence() -> None:
    live = OpenFoodFactsCatalog(fetch_json=lambda *_: {"products": [_product()]})
    result = ExpandedChinaCatalog(
        primary=JsonProductCatalog(), supplemental=live, minimum_records=12
    ).search(category="biscuit", region="CN")

    assert result.provider == "china_official_sources_with_live_supplement"
    assert len(result.records) == 4
    assert (
        sum(item.catalog_scope == "live_open_food_facts" for item in result.records)
        == 1
    )


def test_expanded_china_catalog_degrades_without_dropping_reviewed_records() -> None:
    result = ExpandedChinaCatalog(
        primary=JsonProductCatalog(),
        supplemental=_UnavailableCatalog(),
        minimum_records=12,
    ).search(category="biscuit", region="CN")

    assert result.status == "degraded"
    assert len(result.records) == 3
    assert "live_supplement_temporarily_unavailable" in result.warnings


def test_expanded_catalog_stays_offline_when_official_minimum_is_met() -> None:
    result = ExpandedChinaCatalog(
        primary=JsonProductCatalog(), supplemental=_UnexpectedCatalog()
    ).search(category="biscuit", region="CN")

    assert result.provider == "curated_verification_catalog"
    assert result.status == "ok"
    assert len(result.records) == 3
