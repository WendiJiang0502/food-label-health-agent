from __future__ import annotations

import asyncio

import httpx

from food_label_agent.web.app import create_app


async def request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_platform_index_and_health() -> None:
    page = asyncio.run(request("GET", "/"))
    health = asyncio.run(request("GET", "/api/health"))
    favicon = asyncio.run(request("GET", "/static/favicon.svg"))

    assert page.status_code == 200
    assert "看懂标签" in page.text
    assert "上传食品标签" in page.text
    assert "包装声称核对" in page.text
    assert "SAFETY · BUILT IN" not in page.text
    assert "MILESTONE" not in page.text
    assert health.status_code == 200
    assert health.json()["synthetic_ocr"] is True
    assert health.json()["remote_processing"] is False
    assert favicon.status_code == 200


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
        "ingredients",
        "allergen_statement",
        "nutrition_basis",
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
    assert payload["overall_risk_level"] == "avoid"
    assert payload["rule_set"]["id"] == "cn_prepackaged_allergens_v1"
    assert payload["findings"][0]["matched_text"] == "乳清蛋白"
    assert payload["findings"][0]["matched_location"] == "复合配料第 3 项（路径 2 → 3）"
    assert payload["findings"][0]["evidence_ids"] == ["label.ingredients.item.2.3"]
    assert payload["evidence"]["status"] == "grounded"
    assert payload["evidence"]["final_status"] == "completed"
    interpretation = payload["evidence"]["interpretations"][0]
    assert interpretation["risk_level"] == "avoid"
    assert interpretation["citations"]
    assert {
        citation["standard_number"] for citation in interpretation["citations"]
    } == {"GB 7718-2011"}
    assert any(citation["page_start"] == 7 for citation in interpretation["citations"])


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


def test_additive_explanations_are_returned_without_safety_or_compliance_claim() -> None:
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
    assert "仅凭配料表无法判断实际用量" in additive["explanation"]
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
