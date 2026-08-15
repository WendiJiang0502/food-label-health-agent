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

    assert {source["brand"] for source in stores} == {"伊利", "西麦", "李锦记", "沃隆"}
    assert all(source.get("product_seed_urls") for source in stores)
    assert all(
        url.startswith("https://item.jd.com/")
        for source in stores
        for url in source["product_seed_urls"]
    )


def test_dynamic_discovery_keeps_unreviewed_products_out_of_recommendations(
    tmp_path: Path,
) -> None:
    service = OfficialProductDiscovery(
        registry_path=_registry(tmp_path / "sources.json"),
        queue_path=tmp_path / "queue.json",
        approved_path=tmp_path / "approved.json",
        fetch_text=_fetcher,
    )

    result = service.refresh(category="snack")

    assert result.status == "completed"
    assert result.summary["discovered_count"] == 2
    assert result.summary["ready_for_review_count"] == 1
    assert result.summary["needs_label_count"] == 1
    assert all(
        item["recommendation_eligible"] is False for item in result.summary["items"]
    )
    assert all("untrusted.example" not in item["source_url"] for item in result.summary["items"])


def test_human_review_promotes_only_complete_hashed_label(
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
