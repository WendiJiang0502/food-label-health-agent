from __future__ import annotations

import json
from pathlib import Path

import pytest

from food_label_agent.alternatives.discovery import (
    SOURCE_REGISTRY_PATH,
    OfficialProductDiscovery,
)
from food_label_agent.alternatives.evidence_audit import label_content_hash
from food_label_agent.alternatives.models import ProductRecord

NEWLY_COVERED_CATEGORIES = {
    "bread",
    "instant_noodles",
    "drink",
    "prepared_meal",
    "processed_meat",
    "seafood",
    "canned_food",
}
ALL_ALTERNATIVE_CATEGORIES = {
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
}


class _TrustedTestPackagingStore:
    def verify_artifact(self, _snapshot) -> bool:
        return True


def _registry(path: Path) -> Path:
    path.write_text(
        json.dumps(
            [
                {
                    "source_id": "brand-official",
                    "brand": "测试品牌",
                    "category": "snack",
                    "discovery_urls": ["https://brand.example/products"],
                    "allowed_hosts": ["brand.example"],
                    "product_path_markers": ["/product/"],
                    "official_store_url": "https://brand.jd.com/",
                    "official_store_name": "测试品牌官方旗舰店",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _fetcher(url: str, _timeout: float) -> str:
    pages = {
        "https://brand.example/products": """
            <html><head><title>产品中心</title><script>window.site = {};</script></head><body>
              <a href="/product/complete">完整商品</a>
              <a href="/product/partial">信息不全商品</a>
              <a href="https://untrusted.example/product/no">站外链接</a>
            </body></html>
        """,
        "https://brand.example/product/complete": """
            <html><head><script type="application/ld+json">
            {"@type":"Product","name":"完整商品","ingredients":"燕麦、花生",
             "size":"30克","nutrition":{"servingSize":"每100克","energy":"1800千焦",
             "proteinContent":"12克","fatContent":"18克","carbohydrateContent":"55克",
             "sodiumContent":"120毫克"}}
            </script></head><body>过敏原提示：含花生</body></html>
        """,
        "https://brand.example/product/partial": """
            <html><head><meta property="og:title" content="信息不全商品"></head>
            <body><h1>信息不全商品</h1>适合早餐与加餐</body></html>
        """,
    }
    return pages[url]


def _review_product(source_url: str) -> dict:
    payload = {
        "product_id": "cn-official:test:complete",
        "display_name": "完整商品",
        "brand": "测试品牌",
        "sku": "TEST-30G",
        "specification": "30克",
        "category": "snack",
        "region": "CN",
        "use_case": "日常加餐",
        "catalog_scope": "official_cn_catalog",
        "label": {
            "evidence_id": "official.test.complete.2026-08-15",
            "ingredients_text": "燕麦、花生",
            "allergen_statement": "含花生",
            "nutrition_table_text": "每100克：能量1800千焦，蛋白质12克，脂肪18克，碳水化合物55克，钠120毫克",
            "nutrition_basis_text": "每100克",
            "nutrition_rows": [
                ["项目", "每100克"],
                ["能量", "1800千焦"],
                ["蛋白质", "12克"],
                ["脂肪", "18克"],
                ["碳水化合物", "55克"],
                ["钠", "120毫克"],
            ],
            "confirmed_by": "human_review",
            "confirmed_at": "2026-08-15",
            "source_url": source_url,
            "content_hash": f"sha256:{'0' * 64}",
            "evidence_quality": "complete",
            "source_provider": "test_official_website",
            "source_type": "official_product_page",
            "source_verified_at": "2026-08-15",
            "source_language": "zh-CN",
            "source_access_region": "CN",
            "source_record_version": "review-1",
            "official_store_url": "https://brand.jd.com/",
            "official_store_name": "测试品牌官方旗舰店",
            "official_store_verified_at": "2026-08-15",
            "source_authority": "manufacturer",
            "packaging_snapshots": [
                {
                    "snapshot_id": "packaging:test-combined",
                    "evidence_kind": "combined",
                    "artifact_type": "packaging_photo",
                    "source_url": "capture://test/TEST-30G",
                    "captured_at": "2026-08-15",
                    "content_hash": f"sha256:{'1' * 64}",
                    "media_type": "image/png",
                    "byte_size": 128,
                    "pixel_width": 640,
                    "pixel_height": 800,
                    "sharpness_score": 100.0,
                    "contrast_score": 40.0,
                    "artifact_path": f"sha256/11/{'1' * 64}.png",
                    "sku": "TEST-30G",
                    "specification": "30克",
                    "review_status": "verified",
                    "primary_reviewer_id": "reviewer-a",
                    "secondary_reviewer_id": "reviewer-b",
                    "reviewed_at": "2026-08-16",
                }
            ],
        },
    }
    provisional = ProductRecord.model_validate(payload)
    payload["label"]["content_hash"] = label_content_hash(provisional)
    return payload


def test_registry_includes_mainland_official_store_product_seeds() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    stores = [
        source
        for source in sources
        if source.get("source_type") == "official_flagship_store"
    ]

    assert {source["brand"] for source in stores} == {
        "伊利",
        "西麦",
        "李锦记",
        "沃隆",
        "雀巢",
    }
    stores_with_seeds = [source for source in stores if source["brand"] != "雀巢"]
    assert all(source.get("product_seed_urls") for source in stores_with_seeds)
    assert all(
        url.startswith("https://item.jd.com/")
        for source in stores_with_seeds
        for url in source["product_seed_urls"]
    )


def test_registry_includes_processed_meat_manufacturer_discovery() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    processed_meat = [
        source for source in sources if source.get("category") == "processed_meat"
    ]

    assert any(source["brand"] == "荷美尔" for source in processed_meat)
    assert all(source.get("product_seed_urls") for source in processed_meat)


def test_missing_sugar_sources_feed_the_review_target_into_discovery() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    target_source_ids = {
        "yili-official",
        "lkk-official",
        "nestle-china-ice-cream-official",
        "kinder-china-confectionery-official",
    }

    assert target_source_ids <= {source["source_id"] for source in sources}
    assert all(
        source.get("review_target_fields") == ["糖"]
        for source in sources
        if source["source_id"] in target_source_ids
    )


def test_registry_feeds_every_new_category_to_the_automatic_discovery_queue(
    tmp_path: Path,
) -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    registered = {source["category"] for source in sources}

    assert registered == ALL_ALTERNATIVE_CATEGORIES
    assert NEWLY_COVERED_CATEGORIES <= registered
    for category in NEWLY_COVERED_CATEGORIES:
        category_sources = [
            source for source in sources if source["category"] == category
        ]
        assert category_sources
        assert all(source.get("discovery_urls") for source in category_sources)
        assert all(source.get("product_seed_urls") for source in category_sources)
        assert all(source.get("allowed_hosts") for source in category_sources)

    service = OfficialProductDiscovery(
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
    )
    assert all(service._sources(category) for category in NEWLY_COVERED_CATEGORIES)


def test_discovery_status_exposes_brand_and_packaging_review_priorities(
    tmp_path: Path,
) -> None:
    service = OfficialProductDiscovery(
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
    )

    status = service.status(category="bread")

    assert status["source_coverage"]["distinct_brand_count"] == 1
    assert "add_second_brand_official_source" in status["source_coverage"][
        "priority_reasons"
    ]
    assert "capture_packaging_label_snapshot" in status["source_coverage"][
        "priority_reasons"
    ]


def test_dynamic_discovery_keeps_unreviewed_products_out_of_recommendations(
    tmp_path: Path,
) -> None:
    service = OfficialProductDiscovery(
        registry_path=_registry(tmp_path / "sources.json"),
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        fetch_text=_fetcher,
        packaging_store=_TrustedTestPackagingStore(),
    )

    result = service.refresh(category="snack")

    assert result.status == "completed"
    assert result.summary["discovered_count"] == 2
    assert result.summary["ready_for_review_count"] == 0
    assert result.summary["needs_label_count"] == 2
    assert all(
        item["recommendation_eligible"] is False for item in result.summary["items"]
    )
    assert all(
        item["capture_requirements"]["official_page_capture_is_sufficient"]
        is False
        for item in result.summary["items"]
    )
    assert all(
        "untrusted.example" not in item["source_url"]
        for item in result.summary["items"]
    )


def test_human_review_promotes_only_complete_hashed_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = OfficialProductDiscovery(
        registry_path=_registry(tmp_path / "sources.json"),
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        fetch_text=_fetcher,
        packaging_store=_TrustedTestPackagingStore(),
    )
    service.refresh(category="snack")
    candidate = next(
        item
        for item in service.status(category="snack")["items"]
        if item["display_name"] == "完整商品"
    )
    monkeypatch.setenv("FOOD_LABEL_CATALOG_REVIEW_TOKEN", "review-secret")

    reviewed = service.review(
        candidate_id=candidate["candidate_id"],
        decision="approve",
        review_token="review-secret",
        product=_review_product(candidate["source_url"]),
    )

    assert reviewed["review_status"] == "approved"
    approved = json.loads((tmp_path / "approved.json").read_text(encoding="utf-8"))
    assert [item["display_name"] for item in approved] == ["完整商品"]

    def changed_fetcher(url: str, timeout: float) -> str:
        return _fetcher(url, timeout).replace("燕麦、花生", "燕麦、花生、芝麻")

    service.fetch_text = changed_fetcher
    service.refresh(category="snack")
    changed = next(
        item
        for item in service.status(category="snack")["items"]
        if item["display_name"] == "完整商品"
    )
    assert changed["review_status"] == "change_detected"
    assert changed["recommendation_eligible"] is False
    assert json.loads((tmp_path / "approved.json").read_text(encoding="utf-8")) == []


def test_review_rejects_incomplete_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = OfficialProductDiscovery(
        registry_path=_registry(tmp_path / "sources.json"),
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        fetch_text=_fetcher,
    )
    service.refresh(category="snack")
    candidate = service.status(category="snack")["items"][0]
    payload = _review_product(candidate["source_url"])
    payload["label"]["allergen_statement"] = None
    monkeypatch.setenv("FOOD_LABEL_CATALOG_REVIEW_TOKEN", "review-secret")

    with pytest.raises(ValueError, match="核心包装字段"):
        service.review(
            candidate_id=candidate["candidate_id"],
            decision="approve",
            review_token="review-secret",
            product=payload,
        )


def test_review_rejects_snapshot_metadata_when_artifact_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = OfficialProductDiscovery(
        registry_path=_registry(tmp_path / "sources.json"),
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        fetch_text=_fetcher,
    )
    service.refresh(category="snack")
    candidate = next(
        item
        for item in service.status(category="snack")["items"]
        if item["display_name"] == "完整商品"
    )
    monkeypatch.setenv("FOOD_LABEL_CATALOG_REVIEW_TOKEN", "review-secret")

    with pytest.raises(ValueError, match="双人复核实物背标"):
        service.review(
            candidate_id=candidate["candidate_id"],
            decision="approve",
            review_token="review-secret",
            product=_review_product(candidate["source_url"]),
        )
