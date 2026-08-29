from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from food_label_agent.alternatives.catalog import OfficialChinaCatalog
from food_label_agent.alternatives.evidence_audit import (
    audit_product_label,
    label_content_hash,
)
from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductRecord,
)
from food_label_agent.alternatives.service import (
    find_alternative_products,
    revalidate_alternatives,
)
from food_label_agent.ingredients.api_models import ConstraintInput

NEWLY_COVERED_CATEGORIES = (
    "bread",
    "instant_noodles",
    "drink",
    "prepared_meal",
    "processed_meat",
    "seafood",
    "canned_food",
)

ALL_PRODUCT_CATEGORIES = (
    "biscuit",
    "bread",
    "breakfast_cereal",
    "instant_noodles",
    "drink",
    "dairy",
    "snack",
    "confectionery",
    "prepared_meal",
    "frozen_food",
    "processed_meat",
    "seafood",
    "sauce_condiment",
    "canned_food",
)


def test_official_catalog_exposes_verified_mainland_sources() -> None:
    result = OfficialChinaCatalog().search(category="dairy", region="CN")

    assert result.provider == "china_official_sources"
    assert [item.display_name for item in result.records[:2]] == [
        "伊利纯牛奶",
        "安慕希AMX小黑钻0蔗糖酸奶",
    ]
    label = result.records[0].label
    assert label.source_type == "official_product_page"
    assert label.source_authority == "manufacturer"
    assert label.source_access_region == "CN"
    assert label.official_store_name == "伊利牛奶官方旗舰店"
    assert label.official_store_url and "jd.com" in label.official_store_url


def test_official_catalog_covers_priority_mainland_categories() -> None:
    catalog = OfficialChinaCatalog()

    oats = catalog.search(category="breakfast_cereal", region="CN")
    sauce = catalog.search(category="sauce_condiment", region="CN")
    nuts = catalog.search(category="snack", region="CN")

    assert oats.records[0].display_name == "西麦绿色纯燕麦片"
    assert sauce.records[0].display_name == "李锦记薄盐生抽"
    assert oats.records[0].label.official_store_name == "西麦官方旗舰店"
    assert sauce.records[0].label.official_store_name == "李锦记京东自营旗舰店"
    assert nuts.records[0].display_name == "沃隆每日坚果"
    assert nuts.records[0].label.official_store_name == "沃隆官方旗舰店"


def test_official_catalog_exposes_complete_review_queue() -> None:
    coverage = OfficialChinaCatalog().coverage()

    assert coverage["total"] == 93
    assert coverage["full_label_count"] == 88
    assert coverage["evidence_gate_count"] == 89
    assert coverage["needs_review_count"] == 5
    assert len(coverage["items"]) == 93
    assert coverage["items"][0]["label_coverage"]["review_priority"] == "high"


def test_official_catalog_turns_missing_labels_into_actionable_queue() -> None:
    queue = OfficialChinaCatalog().review_queue(applicable_date=date(2026, 8, 15))

    assert queue["total_catalog_count"] == 93
    assert queue["ready_count"] == 0
    assert queue["queue_count"] == 93
    assert queue["reverification_due_count"] == 0
    assert queue["missing_field_counts"]["完整配料表文字"] >= 1
    assert queue["missing_field_counts"]["双人复核实物包装配料图"] == 93
    assert queue["missing_field_counts"]["双人复核实物包装营养图"] == 93
    assert all(item["recommendation_eligible"] is False for item in queue["items"])
    assert all(item["next_action"] for item in queue["items"])
    assert all(
        item["capture_requirements"]["official_page_capture_is_sufficient"]
        is False
        for item in queue["items"]
    )
    assert all(
        item["capture_requirements"]["minimum_distinct_reviewers"] == 2
        for item in queue["items"]
    )
    assert all(item["source"]["record_version"] for item in queue["items"])


@pytest.mark.parametrize("category", ALL_PRODUCT_CATEGORIES)
def test_every_category_has_three_complete_distinct_formulas(category: str) -> None:
    records = OfficialChinaCatalog().search(category=category, region="CN").records
    complete = [
        item for item in records if audit_product_label(item)["full_label_ready"]
    ]

    assert len(complete) >= 3, category
    assert len({item.label.content_hash for item in complete}) >= 3, category


@pytest.mark.parametrize("category", ALL_PRODUCT_CATEGORIES)
def test_every_category_has_three_packaging_sugar_formulas(category: str) -> None:
    records = OfficialChinaCatalog().search(category=category, region="CN").records
    with_sugar = [
        item
        for item in records
        if audit_product_label(item)["full_label_ready"]
        and "糖" in {row[0] for row in (item.label.nutrition_rows or [])[1:]}
        and "packaging-sugar-reviewed" in (item.label.source_record_version or "")
    ]

    assert len({item.label.content_hash for item in with_sugar}) >= 3, category


@pytest.mark.parametrize("category", NEWLY_COVERED_CATEGORIES)
def test_each_new_mainland_category_has_a_reproducible_full_label(
    category: str,
) -> None:
    records = OfficialChinaCatalog().search(category=category, region="CN").records

    assert records, category
    product = records[0]
    audit = audit_product_label(product)
    assert audit["full_label_ready"] is True
    assert product.label.evidence_quality == "complete"
    assert product.label.source_authority == "manufacturer"
    assert product.label.source_access_region == "CN"
    assert product.label.source_verified_at is not None
    assert product.label.content_hash == label_content_hash(product)
    assert {row[0] for row in (product.label.nutrition_rows or [])[1:]} >= {
        "能量",
        "蛋白质",
        "脂肪",
        "碳水化合物",
        "钠",
    }


@pytest.mark.parametrize("category", NEWLY_COVERED_CATEGORIES)
def test_new_category_records_still_fail_closed_when_evidence_is_downgraded(
    category: str, tmp_path: Path
) -> None:
    payload = json.loads(
        Path(
            "src/food_label_agent/alternatives/data/official_cn_expansion.json"
        ).read_text(encoding="utf-8")
    )
    product = next(item for item in payload if item["category"] == category)
    product["label"]["evidence_quality"] = "partial"
    product["label"]["ingredients_text"] = "完整包装配料表待核验"
    product["label"]["allergen_statement"] = None
    provisional = ProductRecord.model_validate(product)
    product["label"]["content_hash"] = label_content_hash(provisional)
    path = tmp_path / f"{category}.json"
    path.write_text(json.dumps([product], ensure_ascii=False), encoding="utf-8")
    catalog = OfficialChinaCatalog(path=path, expansion_path=None)

    search = find_alternative_products(
        AlternativeSearchRequest(
            category=category,
            applicable_date="2026-08-27",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="peanut", severity="moderate"
                )
            ],
        ),
        catalog=catalog,
    )

    assert search["candidates"] == []
    assert search["rejected"][0]["reason_code"] == (
        "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
    )


def test_meiji_name_only_skus_stay_in_discovery_not_active_catalog() -> None:
    catalog = OfficialChinaCatalog()
    result = catalog.search(category="confectionery", region="CN")
    meiji = [item for item in result.records if item.brand == "明治"]

    assert meiji == []

    sources = json.loads(
        Path(
            "src/food_label_agent/alternatives/data/official_cn_sources.json"
        ).read_text(encoding="utf-8")
    )
    meiji_sources = [item for item in sources if item["brand"] == "明治"]
    assert len(meiji_sources) == 1
    assert meiji_sources[0]["discovery_urls"] == [
        "https://www.meiji.com.cn/product/cookie-product.html"
    ]

    search = find_alternative_products(
        AlternativeSearchRequest(
            category="confectionery",
            applicable_date="2026-08-15",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="peanut", severity="severe"
                )
            ],
            limit=20,
        ),
        catalog=catalog,
    )

    assert all(item["brand"] != "明治" for item in search["candidates"])
    assert all(
        not item["product_id"].startswith("cn-official:meiji:")
        for item in search["rejected"]
    )


def test_nestle_official_pages_expose_complete_frozen_products() -> None:
    catalog = OfficialChinaCatalog()
    result = catalog.search(category="frozen_food", region="CN")

    assert len(result.records) == 27
    assert all(item.label.evidence_quality == "complete" for item in result.records)
    assert all("nestle.com.cn" in item.label.source_url for item in result.records)
    assert all(
        item.label.official_store_name == "雀巢冰淇淋京东自营旗舰店"
        for item in result.records
    )
    assert all(
        item.label.nutrition_rows
        and {row[0] for row in item.label.nutrition_rows[1:]}
        >= {"能量", "蛋白质", "脂肪", "碳水化合物", "钠"}
        for item in result.records
    )


def test_severe_allergy_blocks_products_without_packaging_snapshot() -> None:
    constraint = ConstraintInput(
        kind="allergy", canonical_value="fish", severity="severe"
    )
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="frozen_food",
            applicable_date="2026-08-15",
            constraints=[constraint],
            limit=20,
        ),
        catalog=OfficialChinaCatalog(),
    )
    assert search["candidates"] == []
    evidence_rejections = [
        item
        for item in search["rejected"]
        if item.get("reason_code") == "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
    ]
    assert len(evidence_rejections) == 27
    assert all(
        "可复核的包装配料/过敏原图片"
        in item["label_coverage"]["context_eligibility"]["missing_required_fields"]
        for item in evidence_rejections
    )


def test_current_product_family_pack_sizes_are_not_returned_as_substitutes() -> None:
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            substitute_categories=["confectionery"],
            applicable_date="2026-08-15",
            constraints=[],
            current_product_name="健达快乐河马1条装（20.7克）",
            limit=50,
        ),
        catalog=OfficialChinaCatalog(),
    )

    names = [item["display_name"] for item in search["candidates"]]
    assert all("快乐河马" not in name for name in names)
    assert any("轻脆怡" in name for name in names)


def test_official_catalog_merges_dynamically_approved_records(tmp_path: Path) -> None:
    source = json.loads(
        Path(
            "src/food_label_agent/alternatives/data/official_cn_products.json"
        ).read_text(encoding="utf-8")
    )
    approved = tmp_path / "approved.json"
    extra = source[0]
    extra["product_id"] = "cn-official:yili:pure-milk-reviewed-copy"
    extra["display_name"] = "伊利纯牛奶审核新增规格"
    approved.write_text(json.dumps([extra], ensure_ascii=False), encoding="utf-8")

    result = OfficialChinaCatalog(approved_path=approved).search(
        category="dairy", region="CN"
    )

    assert "伊利纯牛奶审核新增规格" in [item.display_name for item in result.records]


def test_partial_official_label_is_visible_but_not_safety_recommended() -> None:
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="sauce_condiment",
            applicable_date="2026-08-15",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="peanut", severity="moderate"
                )
            ],
        ),
        catalog=OfficialChinaCatalog(),
    )

    assert search["candidates"] == []
    assert search["rejected"][0]["display_name"] == "李锦记薄盐生抽"
    assert search["rejected"][0]["reason_code"] == (
        "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
    )


def test_field_level_gate_marks_partial_catalog_record_conditionally_usable() -> None:
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="dairy",
            applicable_date="2026-08-15",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="peanut", severity="moderate"
                )
            ],
            health_concerns=[],
        ),
        catalog=OfficialChinaCatalog(),
    )

    pure_milk = next(
        item
        for item in search["candidates"]
        if item["product_id"] == "cn-official:yili:pure-milk"
    )
    assert pure_milk["catalog_eligibility"]["status"] == "conditionally_verified"
    assert pure_milk["catalog_eligibility"]["eligible_for_current_context"] is True
    assert search["catalog_coverage"]["conditionally_verified_count"] == 4


def test_health_concern_comparison_fields_rank_without_blocking_safety_candidates() -> (
    None
):
    pressure = find_alternative_products(
        AlternativeSearchRequest(
            category="frozen_food",
            applicable_date="2026-08-15",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="fish", severity="moderate"
                )
            ],
            health_concerns=["blood_pressure"],
            limit=20,
        ),
        catalog=OfficialChinaCatalog(),
    )
    sugar = find_alternative_products(
        AlternativeSearchRequest(
            category="frozen_food",
            applicable_date="2026-08-15",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="fish", severity="moderate"
                )
            ],
            health_concerns=["blood_sugar"],
            limit=20,
        ),
        catalog=OfficialChinaCatalog(),
    )

    assert len(pressure["candidates"]) == 20
    assert len(sugar["candidates"]) == 20
    assert sugar["catalog_coverage"]["fully_verified_count"] == 0
    assert sugar["catalog_coverage"]["conditionally_verified_count"] == 27
    assert sugar["catalog_coverage"]["context_needs_review_count"] == 0
    comparable = [
        item
        for item in sugar["candidates"]
        if "糖" not in item["catalog_eligibility"]["missing_comparison_fields"]
    ]
    assert len({item["label"]["content_hash"] for item in comparable}) >= 3
    assert all(
        "糖" not in item["catalog_eligibility"]["missing_required_fields"]
        for item in sugar["candidates"]
    )


def test_numeric_sugar_limit_never_admits_a_record_without_packaging_sugar() -> None:
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="frozen_food",
            applicable_date="2026-08-28",
            constraints=[
                ConstraintInput(
                    kind="nutrition_limit",
                    canonical_value="sugars",
                    operator="max",
                    threshold=10,
                    unit="g",
                    basis="per_serving",
                )
            ],
            limit=50,
        ),
        catalog=OfficialChinaCatalog(),
    )

    assert search["candidates"]
    assert all(
        "糖" in {row[0] for row in item["label"]["nutrition_rows"][1:]}
        for item in search["candidates"]
    )
    assert any(
        item["reason_code"] == "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
        for item in search["rejected"]
    )


def test_every_displayable_missing_sugar_candidate_has_an_audited_reason() -> None:
    catalog = OfficialChinaCatalog()
    missing_sugar: list[dict] = []
    for category in ALL_PRODUCT_CATEGORIES:
        search = find_alternative_products(
            AlternativeSearchRequest(
                category=category,
                applicable_date="2026-08-28",
                health_concerns=["blood_sugar"],
                limit=50,
            ),
            catalog=catalog,
        )
        revalidated = revalidate_alternatives(
            AlternativeRevalidationRequest(
                request_id=f"sugar-evidence-audit-{category}",
                applicable_date="2026-08-28",
                health_concerns=["blood_sugar"],
                source_category=category,
                candidates=search["candidates"],
            )
        )
        missing_sugar.extend(
            item
            for item in revalidated["results"]
            if item["disposition"] == "eligible"
            and "糖"
            in item["catalog_eligibility"]["missing_comparison_fields"]
        )

    assert len(missing_sugar) == 31
    assert Counter(
        item["catalog_eligibility"]["sugars_review_status"]
        for item in missing_sugar
    ) == Counter({"not_declared": 29, "source_insufficient": 2})
    assert all(
        item["catalog_eligibility"]["sugars_reviewed_at"]
        and item["catalog_eligibility"]["sugars_review_note"]
        for item in missing_sugar
    )
    assert not any(
        item["catalog_eligibility"]["sugars_review_status"] == "not_reviewed"
        for item in missing_sugar
    )


def test_same_use_juice_and_sausage_searches_offer_three_formulas() -> None:
    catalog = OfficialChinaCatalog()
    juice = find_alternative_products(
        AlternativeSearchRequest(
            category="drink",
            applicable_date="2026-08-28",
            constraints=[],
            current_product_name="橙汁饮料",
            limit=50,
        ),
        catalog=catalog,
    )
    sausage = find_alternative_products(
        AlternativeSearchRequest(
            category="processed_meat",
            applicable_date="2026-08-28",
            constraints=[],
            current_product_name="德式香肠",
            limit=50,
        ),
        catalog=catalog,
    )

    assert len({item["label"]["content_hash"] for item in juice["candidates"]}) >= 3
    assert len({item["label"]["content_hash"] for item in sausage["candidates"]}) >= 3


def test_official_catalog_rejects_unreviewed_store_identity(tmp_path: Path) -> None:
    source = json.loads(
        Path(
            "src/food_label_agent/alternatives/data/official_cn_products.json"
        ).read_text(encoding="utf-8")
    )
    source[0]["label"]["official_store_verified_at"] = None
    path = tmp_path / "official-products.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    result = OfficialChinaCatalog(path, expansion_path=None).search(
        category="dairy", region="CN"
    )

    assert [item.display_name for item in result.records] == [
        "安慕希AMX小黑钻0蔗糖酸奶"
    ]
    assert result.rejected[0]["reason_code"] == "OFFICIAL_STORE_REVIEW_INCOMPLETE"


def test_official_candidate_is_independently_revalidated() -> None:
    constraint = ConstraintInput(
        kind="allergy", canonical_value="peanut", severity="moderate"
    )
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="dairy",
            applicable_date="2026-08-15",
            constraints=[constraint],
        ),
        catalog=OfficialChinaCatalog(),
    )
    result = revalidate_alternatives(
        AlternativeRevalidationRequest(
            request_id="official-cn-revalidation",
            applicable_date="2026-08-15",
            constraints=[constraint],
            candidates=search["candidates"],
        )
    )

    assert search["catalog_scope"] == "china_official_sources"
    assert result["eligible_count"] == 1
    eligible = result["results"][0]
    assert eligible["catalog_tier"] == "conditionally_verified"
    assert eligible["catalog_eligibility"]["verified_required_fields"] == [
        "完整配料表文字",
        "包装过敏原及交叉接触提示",
    ]
    assert eligible["label_source_type"] == "official_product_page"
    assert eligible["official_store_name"] == "伊利牛奶官方旗舰店"
    assert eligible["packaging_label"] == {
        "ingredients_text": "生牛乳",
        "allergen_statement": "本产品含有乳及乳制品",
        "nutrition_basis_text": "每100毫升",
        "nutrition_rows": [
            ["项目", "每100毫升"],
            ["蛋白质", "3.2克"],
            ["钙", "100毫克"],
        ],
        "evidence_quality": "complete",
        "evidence_id": "official.yili.pure-milk.label.2026-08-15",
        "record_version": "manual-review-2026-08-15",
        "confirmed_at": "2026-08-15",
        "source_verified_at": "2026-08-15",
        "valid_through": "2027-08-15",
    }
    assert eligible["evidence_status"] == {
        "status": "partially_verified",
        "label": "部分证据，本次所需字段已核对",
        "confirmed_at": "2026-08-15",
        "source_verified_at": "2026-08-15",
        "valid_through": "2027-08-15",
        "record_version": "manual-review-2026-08-15",
        "source_type": "official_product_page",
        "source_authority": "manufacturer",
        "source_language": "zh-CN",
        "source_access_region": "CN",
    }
