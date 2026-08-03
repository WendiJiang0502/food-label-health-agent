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
    assert "看清每一行" in page.text
    assert health.status_code == 200
    assert health.json()["synthetic_ocr"] is True
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
