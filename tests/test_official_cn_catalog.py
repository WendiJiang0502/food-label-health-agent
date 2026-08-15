from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from food_label_agent.alternatives.catalog import OfficialChinaCatalog
from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
)
from food_label_agent.alternatives.service import (
    find_alternative_products,
    revalidate_alternatives,
)
from food_label_agent.ingredients.api_models import ConstraintInput


def test_official_catalog_exposes_verified_mainland_sources() -> None:
    result = OfficialChinaCatalog().search(category="dairy", region="CN")

    assert result.provider == "china_official_sources"
    assert [item.display_name for item in result.records] == [
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

    assert [item.display_name for item in oats.records] == ["西麦绿色纯燕麦片"]
    assert [item.display_name for item in sauce.records] == ["李锦记薄盐生抽"]
    assert oats.records[0].label.official_store_name == "西麦官方旗舰店"
    assert sauce.records[0].label.official_store_name == "李锦记京东自营旗舰店"
    assert [item.display_name for item in nuts.records] == ["沃隆每日坚果"]
    assert nuts.records[0].label.official_store_name == "沃隆官方旗舰店"


def test_official_catalog_exposes_complete_review_queue() -> None:
    coverage = OfficialChinaCatalog().coverage()

    assert coverage["total"] == 100
    assert coverage["full_label_count"] == 50
    assert coverage["evidence_gate_count"] == 51
    assert coverage["needs_review_count"] == 50
    assert len(coverage["items"]) == 100
    assert coverage["items"][0]["label_coverage"]["review_priority"] == "high"


def test_official_catalog_turns_missing_labels_into_actionable_queue() -> None:
    queue = OfficialChinaCatalog().review_queue(applicable_date=date(2026, 8, 15))

    assert queue["total_catalog_count"] == 100
    assert queue["ready_count"] == 50
    assert queue["queue_count"] == 50
    assert queue["reverification_due_count"] == 0
    assert queue["missing_field_counts"]["完整配料表文字"] >= 45
    assert all(item["recommendation_eligible"] is False for item in queue["items"])
    assert all(item["next_action"] for item in queue["items"])
    assert all(item["source"]["record_version"] for item in queue["items"])


def test_meiji_discovery_skus_stay_out_of_safety_recommendations() -> None:
    catalog = OfficialChinaCatalog()
    result = catalog.search(category="confectionery", region="CN")
    meiji = [item for item in result.records if item.brand == "明治"]

    assert len(meiji) == 45
    assert all(item.label.evidence_quality == "partial" for item in meiji)

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
    assert sum(
        item["product_id"].startswith("cn-official:meiji:")
        for item in search["rejected"]
    ) == 45


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


def test_nestle_frozen_products_enter_independent_safety_review() -> None:
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
    result = revalidate_alternatives(
        AlternativeRevalidationRequest(
            request_id="nestle-frozen-revalidation",
            applicable_date="2026-08-15",
            constraints=[constraint],
            candidates=search["candidates"],
        )
    )

    assert len(search["candidates"]) == 20
    assert result["revalidated_count"] == 20
    assert result["eligible_count"] == 20


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
                    kind="allergy", canonical_value="peanut", severity="severe"
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
                    kind="allergy", canonical_value="peanut", severity="severe"
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
    assert search["catalog_coverage"]["conditionally_verified_count"] == 1


def test_health_concern_requires_only_its_relevant_packaging_fields() -> None:
    pressure = find_alternative_products(
        AlternativeSearchRequest(
            category="frozen_food",
            applicable_date="2026-08-15",
            constraints=[
                ConstraintInput(
                    kind="allergy", canonical_value="fish", severity="severe"
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
                    kind="allergy", canonical_value="fish", severity="severe"
                )
            ],
            health_concerns=["blood_sugar"],
            limit=20,
        ),
        catalog=OfficialChinaCatalog(),
    )

    assert len(pressure["candidates"]) == 20
    assert sugar["candidates"] == []
    assert sugar["catalog_coverage"]["context_needs_review_count"] == 27
    assert all(
        "糖" in item["label_coverage"]["context_eligibility"]["missing_required_fields"]
        for item in sugar["rejected"]
    )


def test_official_catalog_rejects_unreviewed_store_identity(tmp_path: Path) -> None:
    source = json.loads(
        Path(
            "src/food_label_agent/alternatives/data/official_cn_products.json"
        ).read_text(encoding="utf-8")
    )
    source[0]["label"]["official_store_verified_at"] = None
    path = tmp_path / "official-products.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    result = OfficialChinaCatalog(path).search(category="dairy", region="CN")

    assert [item.display_name for item in result.records] == [
        "安慕希AMX小黑钻0蔗糖酸奶"
    ]
    assert result.rejected[0]["reason_code"] == "OFFICIAL_STORE_REVIEW_INCOMPLETE"


def test_official_candidate_is_independently_revalidated() -> None:
    constraint = ConstraintInput(
        kind="allergy", canonical_value="peanut", severity="severe"
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
    }
