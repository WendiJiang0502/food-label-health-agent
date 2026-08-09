from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from food_label_agent.persistence.sqlite import SQLiteCheckpointStore, SQLiteMemoryStore
from food_label_agent.web.app import create_app


def test_alternative_api_revalidates_every_candidate_and_appends_checkpoint(
    tmp_path: Path,
) -> None:
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
        token = evaluated.json()["checkpoint"]["resume_token"]

        response = await client.post(
            "/api/v1/alternatives/search",
            json={
                **evaluation,
                "category": "biscuit",
                "region": "CN",
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
        assert payload["candidate_count"] == payload["revalidated_count"] == 2
        assert payload["revalidation_rate"] == 1.0
        assert [item["product_id"] for item in payload["eligible"]] == [
            "fixture-biscuit-oat-plain"
        ]
        assert payload["excluded"][0]["risk_level"] == "avoid"
        assert payload["evidence_rejected"][0]["reason_code"] == (
            "LABEL_EVIDENCE_INCOMPLETE"
        )
        assert payload["checkpoint"]["sequence"] == 2
        assert payload["checkpoint"]["resume_token"] is None
