from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from food_label_agent.persistence.sqlite import SQLiteCheckpointStore, SQLiteMemoryStore
from food_label_agent.web.app import create_app


def test_alternative_api_revalidates_every_candidate_and_appends_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FOOD_LABEL_PRODUCT_CATALOG", "curated")
    asyncio.run(_alternative_api_lifecycle(tmp_path))


async def _alternative_api_lifecycle(tmp_path: Path) -> None:
    database = tmp_path / "alternatives.sqlite3"
    app = create_app(
        checkpoint_store=SQLiteCheckpointStore(database),
        memory_store=SQLiteMemoryStore(database),
    )
    transport = httpx.ASGITransport(app=app)
    evaluation = {
        "request_id": "alternative-api-test",
        "jurisdiction": "CN",
        "applicable_date": "2026-08-09",
        "confirmed_fields": {"ingredients": "小麦粉、乳清蛋白"},
        "constraints": [
            {"kind": "allergy", "canonical_value": "milk", "severity": "severe"}
        ],
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        evaluated = await client.post("/api/v1/labels/evaluate", json=evaluation)
        assert evaluated.status_code == 200
        assert evaluated.json()["alternative_category_suggestion"]["category"] is None
        assert (
            evaluated.json()["alternative_category_suggestion"]["requires_confirmation"]
            is True
        )
        token = evaluated.json()["checkpoint"]["resume_token"]

        response = await client.post(
            "/api/v1/alternatives/search",
            json={
                **evaluation,
                "category": "biscuit",
                "region": "CN",
                "health_concerns": ["weight"],
                "resume_token": token,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["catalog_scope"] == "curated_verification_catalog"
        assert payload["selection_basis"]["category_match"] == "exact"
        assert payload["selection_basis"]["constraint_evaluation"] == (
            "independent_revalidation_required"
        )
        assert payload["selection_basis"]["health_concerns"] == ["weight"]
        assert payload["catalog_coverage"]["total"] == 3
        assert payload["catalog_coverage"]["needs_review_count"] >= 1
        assert payload["candidate_count"] == payload["revalidated_count"] == 2
        assert payload["revalidation_rate"] == 1.0
        assert [item["product_id"] for item in payload["eligible"]] == [
            "fixture-biscuit-oat-plain"
        ]
        assert payload["excluded"][0]["risk_level"] == "avoid"
        assert payload["evidence_rejected"][0]["reason_code"] == (
            "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
        )
        assert payload["checkpoint"]["sequence"] == 2
        assert payload["checkpoint"]["resume_token"] is None


def test_health_focus_can_find_alternatives_without_a_hard_constraint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FOOD_LABEL_PRODUCT_CATALOG", "curated")
    asyncio.run(_health_focus_alternative_lifecycle(tmp_path))


async def _health_focus_alternative_lifecycle(tmp_path: Path) -> None:
    database = tmp_path / "health-focus-alternatives.sqlite3"
    app = create_app(
        checkpoint_store=SQLiteCheckpointStore(database),
        memory_store=SQLiteMemoryStore(database),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ocr = await client.post(
            "/api/v1/ocr/analyze",
            files={"image": ("label.jpg", b"\xff\xd8\xffhealth-focus", "image/jpeg")},
        )
        request_id = ocr.json()["request_id"]
        token = ocr.json()["checkpoint"]["resume_token"]
        confirmed_fields = {
            "product_name": "原味燕麦饼干",
            "ingredients": "燕麦粉、植物油、白砂糖",
        }
        confirmed = await client.post(
            "/api/v1/labels/confirm",
            json={
                "request_id": request_id,
                "applicable_date": "2026-08-23",
                "fields": confirmed_fields,
                "resume_token": token,
            },
        )
        assert confirmed.status_code == 200

        response = await client.post(
            "/api/v1/alternatives/search",
            json={
                "request_id": request_id,
                "applicable_date": "2026-08-23",
                "confirmed_fields": confirmed_fields,
                "constraints": [],
                "health_concerns": ["blood_sugar"],
                "category": "biscuit",
                "substitute_categories": ["biscuit"],
                "region": "CN",
                "resume_token": token,
            },
        )

        payload = response.json()
        assert response.status_code == 200
        assert payload["status"] == "completed"
        assert payload["candidate_count"] == payload["revalidated_count"] == 3
        assert len(payload["eligible"]) == 3
        assert payload["release_gate"]["passed"] is True
