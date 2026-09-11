from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
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


def test_discovery_encodes_spaces_in_official_product_links(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")

    def fetcher(url: str, _timeout: float) -> str:
        if url == "https://brand.example/products":
            return '<a href="/product/Aromatic Red Cooking soy sauce">商品</a>'
        if url == "https://brand.example/product/Aromatic%20Red%20Cooking%20soy%20sauce":
            return """
                <script type="application/ld+json">
                {"@type":"Product","name":"红烧酱油","ingredients":"水、大豆、小麦、食用盐",
                 "size":"500毫升"}
                </script><p>过敏原提示：含大豆和小麦</p>
            """
        raise AssertionError(f"unexpected URL: {url}")

    discovery = OfficialProductDiscovery(
        registry_path=registry,
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        packaging_store=_TrustedTestPackagingStore(),
        fetch_text=fetcher,
    )

    result = discovery.refresh()

    assert result.status == "completed"
    assert result.summary["discovered_count"] == 1
    assert result.summary["items"][0]["source_url"].endswith(
        "Aromatic%20Red%20Cooking%20soy%20sauce"
    )


def test_discovery_rejects_generic_navigation_pages_as_skus(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")

    def fetcher(url: str, _timeout: float) -> str:
        if url == "https://brand.example/products":
            return """
                <a href="/product/about">关于我们</a>
                <a href="/product/business">主营产品</a>
                <a href="/product/search">Search</a>
                <a href="/product/real">真实坚果 120克</a>
            """
        if url == "https://brand.example/product/real":
            return '<h1>真实坚果</h1><p>净含量：120克</p>'
        raise AssertionError(f"generic page should not be fetched: {url}")

    discovery = OfficialProductDiscovery(
        registry_path=registry,
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        fetch_text=fetcher,
    )

    result = discovery.refresh(category="snack")

    assert result.status == "completed"
    assert result.summary["discovered_count"] == 1
    assert result.summary["items"][0]["display_name"] == "真实坚果"


def test_listing_seed_products_capture_identity_without_mixing_label_text(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "registry.json")
    sources = json.loads(registry.read_text(encoding="utf-8"))
    sources[0]["discovery_urls"] = ["https://brand.example/product/display"]
    sources[0]["product_seed_urls"] = ["https://brand.example/product/display"]
    sources[0]["seed_products"] = [
        {
            "display_name": "可核验坚果",
            "sku": "6956511998326",
            "specification": "120克",
            "source_url": "https://brand.example/product/display",
            "packaging_photo_url": "https://brand.example/evidence/nut.jpg",
        },
        {
            "display_name": "可核验果干",
            "sku": "6956511998999",
            "specification": "100克",
            "source_url": "https://brand.example/product/display",
        },
    ]
    registry.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")

    def fetcher(_url: str, _timeout: float) -> str:
        return """
            <h1>产品中心</h1>
            <p>可核验坚果 120克 69码：6956511998326</p>
            <p>另一商品配料表：不应串到种子商品；营养成分：脂肪0克</p>
        """

    discovery = OfficialProductDiscovery(
        registry_path=registry,
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        fetch_text=fetcher,
    )

    result = discovery.refresh(category="snack")

    assert result.status == "completed"
    assert result.summary["discovered_count"] == 2
    assert {item["sku"] for item in result.summary["items"]} == {
        "6956511998326",
        "6956511998999",
    }
    assert all(
        item["extracted_fields"]["ingredients_text"] is None
        for item in result.summary["items"]
    )
    assert all(
        item["identity_evidence"]["label_fields_extracted_from_listing"] is False
        for item in result.summary["items"]
    )
    nut = next(
        item for item in result.summary["items"] if item["display_name"] == "可核验坚果"
    )
    assert nut["evidence_assets"] == [
        {
            "url": "https://brand.example/evidence/nut.jpg",
            "artifact_type": "packaging_photo",
        }
    ]
    assert all(
        item["recommendation_eligible"] is False for item in result.summary["items"]
    )


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
        "古龙",
        "自嗨锅",
    }
    stores_with_seeds = [source for source in stores if source["brand"] != "雀巢"]
    assert all(source.get("product_seed_urls") for source in stores_with_seeds)
    jd_item_seed_stores = [
        source
        for source in stores_with_seeds
        if source["brand"] in {"伊利", "西麦", "李锦记", "沃隆"}
    ]
    assert all(
        url.startswith("https://item.jd.com/")
        for source in jd_item_seed_stores
        for url in source["product_seed_urls"]
    )
    assert next(source for source in stores if source["brand"] == "古龙")[
        "product_seed_urls"
    ][0].startswith("https://gulong.jd.com/")
    assert next(source for source in stores if source["brand"] == "自嗨锅")[
        "product_seed_urls"
    ][0].startswith("https://detail.youzan.com/")


def test_registry_includes_processed_meat_manufacturer_discovery() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    processed_meat = [
        source for source in sources if source.get("category") == "processed_meat"
    ]

    assert any(source["brand"] == "荷美尔" for source in processed_meat)
    assert all(source.get("product_seed_urls") for source in processed_meat)


def test_three_squirrels_official_identity_seeds_are_sku_bound() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    source = next(
        item
        for item in sources
        if item["source_id"] == "three-squirrels-china-snack-official"
    )

    assert len(source["seed_products"]) == 8
    assert len({item["sku"] for item in source["seed_products"]}) == 8
    assert all(len(item["sku"]) == 13 for item in source["seed_products"])
    assert all(item["specification"] for item in source["seed_products"])


def test_nanfang_official_label_artwork_seed_is_bound_to_barcode_and_spec() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    source = next(
        item
        for item in sources
        if item["source_id"] == "nanfang-stone-ground-sesame-official-label"
    )
    seed = source["seed_products"][0]

    assert seed["sku"] == "6901333388886"
    assert seed["specification"] == "315克（35克×9袋）"
    assert seed["official_label_artwork_url"].startswith(
        "https://32034701.s21i.faiusr.com/"
    )


def test_chubang_and_maling_second_brand_seeds_are_exact_sku_bound() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    by_id = {source["source_id"]: source for source in sources}

    chubang = by_id["chubang-yipinxian-official"]["seed_products"][0]
    assert chubang["sku"] == "6902902009324"
    assert chubang["specification"] == "500毫升"
    assert chubang["source_url"].startswith("https://m.chubang.cn/")
    assert chubang["packaging_photo_url"].startswith(
        "https://imgservice.suning.cn/"
    )

    maling = by_id["maling-delicious-luncheon-official"]["seed_products"][0]
    assert maling["sku"] == "6902131112949"
    assert maling["specification"] == "340克"
    assert maling["official_label_artwork_url"].startswith(
        "https://img.alicdn.com/"
    )


def test_shuanghui_second_brand_seed_is_exact_sku_bound() -> None:
    sources = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    source = next(
        item
        for item in sources
        if item["source_id"] == "shuanghui-china-meat-official"
    )
    seed = source["seed_products"][0]

    assert seed["display_name"] == "双汇王中王火腿肠"
    assert seed["sku"] == "6902890228325"
    assert seed["specification"] == "240克"
    assert seed["source_url"] == "https://www.shuanghui.net/page-32.html"
    assert seed["packaging_photo_url"].startswith("https://www.lingshi.us/")


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
    assert all(
        len(
            {
                source["brand"]
                for source in sources
                if source["category"] == category
            }
        )
        >= 2
        for category in ALL_ALTERNATIVE_CATEGORIES
    )
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

    assert status["source_coverage"]["distinct_brand_count"] == 2
    assert "add_second_brand_official_source" not in status["source_coverage"][
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


def test_concurrent_source_merges_do_not_overwrite_each_other(tmp_path: Path) -> None:
    service = OfficialProductDiscovery(
        registry_path=_registry(tmp_path / "sources.json"),
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
    )

    def merge(source_id: str) -> None:
        service._merge_queue(
            [
                {
                    "candidate_id": f"candidate:{source_id}",
                    "source_id": source_id,
                    "category": "snack",
                    "display_name": source_id,
                    "source_fingerprint": f"sha256:{source_id}",
                    "first_discovered_at": "2026-08-30T00:00:00+00:00",
                    "last_seen_at": "2026-08-30T00:00:00+00:00",
                    "review_status": "evidence_incomplete",
                }
            ],
            {source_id},
            {"snack"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(merge, ("source-a", "source-b")))

    assert {
        item["candidate_id"] for item in service._read_json_list(service.queue_path)
    } == {"candidate:source-a", "candidate:source-b"}


def test_corrupt_queue_recovers_from_last_atomic_backup(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    OfficialProductDiscovery._write_json_list(queue, [{"candidate_id": "first"}])
    OfficialProductDiscovery._write_json_list(queue, [{"candidate_id": "second"}])
    queue.write_text("{truncated", encoding="utf-8")

    assert OfficialProductDiscovery._read_json_list(queue) == [
        {"candidate_id": "first"}
    ]
