from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from food_label_agent.alternatives.discovery import DiscoveryRefreshResult
from food_label_agent.mcp import business_tools
from food_label_agent.persistence.sqlite import SQLiteCheckpointStore, SQLiteMemoryStore
from food_label_agent.web.app import create_app, create_production_app


async def request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_platform_index_and_health() -> None:
    page = asyncio.run(request("GET", "/"))
    health = asyncio.run(request("GET", "/api/health"))
    favicon = asyncio.run(request("GET", "/static/favicon.svg"))

    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-cache"
    assert "看懂标签" in page.text
    assert "上传食品标签" in page.text
    assert "包装声称核对" in page.text
    assert "在此设备记住这些约束" in page.text
    assert "清除全部并撤销授权" in page.text
    assert "重新查找同用途替代品" in page.text
    assert "系统会根据当前商品自动确定替代用途" in page.text
    assert "品牌官网和中国大陆官方旗舰店" in page.text
    assert "数据来源将在查找后显示" in page.text
    assert "SAFETY · BUILT IN" not in page.text
    assert "MILESTONE" not in page.text
    assert health.status_code == 200
    assert health.json()["synthetic_ocr"] is True
    assert health.json()["remote_processing"] is False
    assert health.json()["planner"] == {
        "provider": "deterministic",
        "model": None,
        "configured": True,
        "remote_processing": False,
    }
    assert health.json()["rag"] == {
        "profile": "hybrid_tfidf",
        "embedding_model": None,
        "reranker_model": None,
        "configured": True,
        "remote_processing": False,
    }
    assert health.json()["product_catalog"] == "official_cn_expanded"
    assert health.json()["public_url"] is None
    assert favicon.status_code == 200
    assert health.json()["processing_disclosure_verified"] is True
    assert health.json()["storage"]["mode"] == "ephemeral_memory"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in health.headers["content-security-policy"]


def test_readiness_reports_real_local_dependencies() -> None:
    response = asyncio.run(request("GET", "/api/ready"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["checkpoint_store"] == {
        "ok": True,
        "durable": False,
    }
    assert payload["checks"]["product_catalog"]["records"] == 93


def test_production_factory_requires_remote_access_and_admin_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOOD_LABEL_OCR_PROVIDER", "demo")
    monkeypatch.delenv("FOOD_LABEL_SITE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FOOD_LABEL_DISCOVERY_ADMIN_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="SITE_ACCESS_TOKEN"):
        create_production_app()

    monkeypatch.setenv("FOOD_LABEL_SITE_ACCESS_TOKEN", "a" * 32)
    with pytest.raises(RuntimeError, match="DISCOVERY_ADMIN_TOKEN"):
        create_production_app()


def test_production_access_gate_and_durable_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "remote.sqlite3"
    app = create_app(
        checkpoint_store=SQLiteCheckpointStore(database),
        memory_store=SQLiteMemoryStore(database),
        production_mode=True,
        site_access_token="site-access-token-that-is-long-enough",
    )

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://remote.test"
        ) as client:
            denied = await client.get("/")
            allowed = await client.get(
                "/", auth=("foodlabel", "site-access-token-that-is-long-enough")
            )
            health = await client.get("/api/health")
            ready = await client.get("/api/ready")
            return denied, allowed, health, ready

    denied, allowed, health, ready = asyncio.run(scenario())

    assert denied.status_code == 401
    assert denied.headers["www-authenticate"].startswith("Basic")
    assert allowed.status_code == 200
    assert "food_label_site_access=" in allowed.headers["set-cookie"]
    assert health.status_code == 200
    assert health.json()["storage"] == {"durable": True, "mode": "sqlite_file"}
    assert ready.status_code == 503  # synthetic OCR is forbidden in production
    assert ready.json()["checks"]["product_packaging_evidence"] == {
        "ok": False,
        "verified_records": 0,
        "records": 93,
    }
    assert database.exists()


def test_declared_oversized_request_is_rejected_before_parsing() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/confirm",
            headers={"Content-Length": str(1024 * 1024 + 1)},
            content=b"{}",
        )
    )

    assert response.status_code == 413
    assert response.json()["message"] == "请求内容过大。"


def test_ocr_rate_limit_fails_closed_before_provider_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOOD_LABEL_OCR_REQUESTS_PER_MINUTE", "2")
    app = create_app()

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            first = await client.post("/api/v1/ocr/analyze", content=b"")
            second = await client.post("/api/v1/ocr/analyze", content=b"")
            limited = await client.post("/api/v1/ocr/analyze", content=b"")
            return first, second, limited

    first, second, limited = asyncio.run(scenario())

    assert first.status_code != 429
    assert second.status_code != 429
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert limited.json()["code"] == "RATE_LIMITED"


def test_official_catalog_coverage_api_lists_every_review_item() -> None:
    response = asyncio.run(request("GET", "/api/v1/alternatives/catalog-coverage"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 93
    assert payload["full_label_count"] == 88
    assert payload["evidence_gate_count"] == 89
    assert len(payload["items"]) == 93
    assert all("missing_fields" in item["label_coverage"] for item in payload["items"])


def test_official_catalog_review_queue_api_includes_missing_package_photos() -> None:
    response = asyncio.run(request("GET", "/api/v1/alternatives/catalog-review-queue"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_catalog_count"] == 93
    assert payload["queue_count"] == 93
    assert payload["ready_count"] == 0
    assert all(item["recommendation_eligible"] is False for item in payload["items"])


class _FakeDiscovery:
    def status(self, *, category=None):
        return {
            "discovered_count": 7,
            "needs_label_count": 5,
            "ready_for_review_count": 2,
            "approved_count": 0,
            "rejected_count": 0,
            "last_refreshed_at": "2026-08-15T00:00:00+00:00",
            "items": [],
        }

    def refresh(self, *, category=None):
        return DiscoveryRefreshResult(
            status="completed", summary=self.status(category=category)
        )

    def review(self, **_kwargs):
        raise PermissionError


def test_official_discovery_refresh_and_status_api() -> None:
    app = create_app(discovery_service=_FakeDiscovery())

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            refreshed = await client.post(
                "/api/v1/alternatives/discovery/refresh", json={"category": "snack"}
            )
            status = await client.get(
                "/api/v1/alternatives/discovery", params={"category": "snack"}
            )
            forbidden = await client.post(
                "/api/v1/alternatives/discovery/review",
                headers={"Authorization": "Bearer invalid"},
                json={"candidate_id": "candidate-1", "decision": "reject"},
            )
            return refreshed, status, forbidden

    refreshed, status, forbidden = asyncio.run(scenario())

    assert refreshed.status_code == 200
    assert refreshed.json()["summary"]["discovered_count"] == 7
    assert status.json()["ready_for_review_count"] == 2
    assert forbidden.status_code == 403


def test_production_discovery_refresh_requires_separate_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOOD_LABEL_DISCOVERY_ADMIN_TOKEN", "discovery-admin-secret")
    app = create_app(
        discovery_service=_FakeDiscovery(),
        production_mode=True,
        site_access_token="site-access-token-that-is-long-enough",
    )

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://remote.test"
        ) as client:
            await client.get(
                "/", auth=("foodlabel", "site-access-token-that-is-long-enough")
            )
            denied = await client.post(
                "/api/v1/alternatives/discovery/refresh", json={"category": "snack"}
            )
            allowed = await client.post(
                "/api/v1/alternatives/discovery/refresh",
                headers={"Authorization": "Bearer discovery-admin-secret"},
                json={"category": "snack"},
            )
            return denied, allowed

    denied, allowed = asyncio.run(scenario())

    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_upload_returns_structured_demo_ocr() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/ocr/analyze",
            files={"image": ("label.jpg", b"\xff\xd8\xffsample-image", "image/jpeg")},
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["synthetic"] is True
    assert payload["next_route"] == "confirm_label"
    assert {field["name"] for field in payload["fields"]} == {
        "product_name",
        "ingredients",
        "allergen_statement",
        "nutrition_basis",
        "net_quantity",
        "nutrition_table",
        "label_claims",
    }


def test_upload_rejects_non_image() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/ocr/analyze",
            files={"image": ("label.txt", b"not-an-image", "text/plain")},
        )
    )

    assert response.status_code == 422
    assert "暂不支持" in response.json()["message"]


def test_confirmation_api_enters_normalization_route() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/confirm",
            json={
                "request_id": "request-1",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-02",
                "fields": {"ingredients": "小麦粉、白砂糖"},
            },
        )
    )

    assert response.status_code == 200
    assert response.json()["next_route"] == "normalize_label"
    assert response.json()["normalized_label"]["ingredients"][0]["raw_name"] == "小麦粉"
    assert response.json()["alternative_category_suggestion"]["category"] is None


def test_confirmation_api_returns_category_for_portion_reference() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/confirm",
            json={
                "request_id": "portion-category",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-15",
                "fields": {"ingredients": "食品名称：烧烤味薯片；配料：马铃薯、植物油"},
            },
        )
    )

    assert response.status_code == 200
    assert response.json()["alternative_category_suggestion"]["category"] == "snack"


def test_category_suggestion_does_not_treat_allergen_trace_as_product_identity() -> (
    None
):
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/confirm",
            json={
                "request_id": "category-uses-product-name",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-15",
                "fields": {
                    "product_name": "食品名称：烧烤味薯片",
                    "ingredients": "马铃薯、植物油、食用盐",
                    "allergen_statement": "可能含有花生及坚果制品",
                },
            },
        )
    )

    assert response.status_code == 200
    assert response.json()["alternative_category_suggestion"]["category"] == "snack"


def test_safety_api_returns_traceable_avoid_result() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/evaluate",
            json={
                "request_id": "request-2",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-08",
                "confirmed_fields": {
                    "ingredients": "小麦粉、复合调味料（白砂糖、食用盐、乳清蛋白）"
                },
                "constraints": [
                    {
                        "kind": "allergy",
                        "canonical_value": "milk",
                        "severity": "severe",
                    }
                ],
            },
        )
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["next_route"] == "completed"
    assert payload["overall_risk_level"] == "avoid"
    assert payload["rule_set"]["id"] == "cn_prepackaged_allergens_v1"
    assert payload["findings"][0]["matched_text"] == "乳清蛋白"
    assert payload["findings"][0]["matched_location"] == "复合配料第 3 项（路径 2 → 3）"
    assert payload["findings"][0]["evidence_ids"] == ["label.ingredients.item.2.3"]
    assert payload["evidence"]["status"] == "grounded"
    assert (
        payload["evidence"]["agent_trace"][-1]["reason_code"]
        == "NO_REQUIRED_TOOL_REMAINS"
    )
    assert payload["evidence"]["react_budget"]["tool_calls_used"] >= 2
    assert payload["evidence"]["final_status"] == "completed"
    interpretation = payload["evidence"]["interpretations"][0]
    assert interpretation["risk_level"] == "avoid"
    assert interpretation["citations"]
    assert {
        citation["standard_number"] for citation in interpretation["citations"]
    } == {"GB 7718-2011"}
    assert any(citation["page_start"] == 7 for citation in interpretation["citations"])


def test_safety_api_keeps_deterministic_result_when_rag_is_unavailable(
    monkeypatch,
) -> None:
    def unavailable_regulatory_search(**_kwargs):
        raise RuntimeError("rag_embedding_api_key_missing")

    monkeypatch.setitem(
        business_tools.BUSINESS_TOOLS,
        "search_food_regulations",
        unavailable_regulatory_search,
    )
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/evaluate",
            json={
                "request_id": "request-rag-unavailable",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-16",
                "confirmed_fields": {"ingredients": "小麦粉、乳清蛋白、食用盐"},
                "constraints": [
                    {
                        "kind": "allergy",
                        "canonical_value": "milk",
                        "severity": "severe",
                    }
                ],
            },
        )
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["overall_risk_level"] == "avoid"
    assert payload["findings"][0]["matched_text"] == "乳清蛋白"
    assert payload["evidence"]["final_status"] == "blocked"
    assert "mcp_tool_failed:search_food_regulations" in payload["evidence"]["errors"]


def test_compatible_result_does_not_claim_regulatory_safety_proof() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/evaluate",
            json={
                "request_id": "request-compatible",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-08",
                "confirmed_fields": {"ingredients": "白砂糖、食用盐"},
                "constraints": [
                    {
                        "kind": "allergy",
                        "canonical_value": "milk",
                        "severity": "severe",
                    }
                ],
            },
        )
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["overall_risk_level"] == "compatible"
    assert payload["evidence"]["status"] == "not_required"
    assert payload["evidence"]["interpretations"] == []


def test_nutrition_limit_api_uses_confirmed_row_evidence() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/evaluate",
            json={
                "request_id": "request-nutrition",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-09",
                "confirmed_fields": {
                    "ingredients": "燕麦",
                    "nutrition_table": "项目\t每100克\n糖\t3.5克\n钠\t380毫克",
                },
                "constraints": [
                    {
                        "kind": "nutrition_limit",
                        "canonical_value": "sodium",
                        "operator": "max",
                        "threshold": 300,
                        "unit": "mg",
                        "basis": "per_100g",
                    }
                ],
            },
        )
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["overall_risk_level"] == "avoid"
    assert payload["findings"][0]["matched_location"] == "营养成分表第 3 行"
    assert payload["evidence"]["final_status"] == "completed"
    assert payload["evidence"]["status"] == "not_required"


def test_additive_explanations_are_returned_without_safety_or_compliance_claim() -> (
    None
):
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/evaluate",
            json={
                "request_id": "request-additives",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-09",
                "confirmed_fields": {
                    "ingredients": "猪肉、食品添加剂（亚硝酸钠、卡拉胶）",
                },
                "constraints": [{"kind": "allergy", "canonical_value": "milk"}],
            },
        )
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["overall_risk_level"] == "compatible"
    additive = payload["evidence"]["interpretations"][0]
    assert additive["explanation_type"] == "additive"
    assert additive["risk_level"] == "not_applicable"
    assert "属于护色剂、防腐剂" in additive["explanation"]
    assert "实际用量" not in additive["explanation"]
    assert payload["evidence"]["status"] == "grounded"


def test_safety_api_includes_claim_interpretation_and_consistency_result() -> None:
    response = asyncio.run(
        request(
            "POST",
            "/api/v1/labels/evaluate",
            json={
                "request_id": "request-claim",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-09",
                "confirmed_fields": {
                    "ingredients": "水、果葡糖浆",
                    "label_claims": "0蔗糖",
                },
                "constraints": [{"kind": "allergy", "canonical_value": "milk"}],
            },
        )
    )

    payload = response.json()
    assert response.status_code == 200
    claim = payload["evidence"]["claim_interpretations"][0]
    finding = payload["evidence"]["consistency_findings"][0]
    assert claim["canonical_type"] == "no_sucrose"
    assert finding["status"] == "not_contradicted"
    assert "不能据此理解为无糖" in finding["explanation"]
