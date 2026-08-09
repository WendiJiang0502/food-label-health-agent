from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from food_label_agent.persistence.sqlite import SQLiteCheckpointStore, SQLiteMemoryStore
from food_label_agent.web.app import create_app


def test_workflow_checkpoint_can_be_resumed_appended_and_deleted(
    tmp_path: Path,
) -> None:
    asyncio.run(_checkpoint_lifecycle(tmp_path))


async def _checkpoint_lifecycle(tmp_path: Path) -> None:
    database = tmp_path / "milestone4.sqlite3"
    app = create_app(
        checkpoint_store=SQLiteCheckpointStore(database),
        memory_store=SQLiteMemoryStore(database),
    )
    transport = httpx.ASGITransport(app=app)
    payload = {
        "request_id": "workflow-resume-api",
        "jurisdiction": "CN",
        "applicable_date": "2026-08-10",
        "confirmed_fields": {"ingredients": "白砂糖、乳清蛋白"},
        "constraints": [
            {
                "kind": "allergy",
                "canonical_value": "milk",
                "severity": "severe",
            }
        ],
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/v1/labels/evaluate", json=payload)
        assert first.status_code == 200
        checkpoint = first.json()["checkpoint"]
        token = checkpoint["resume_token"]
        assert checkpoint["sequence"] == 1
        assert token

        unauthorized = await client.get("/api/v1/workflows/workflow-resume-api")
        assert unauthorized.status_code == 403
        resumed = await client.get(
            "/api/v1/workflows/workflow-resume-api",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resumed.status_code == 200
        restored = resumed.json()["state"]
        assert restored["status"] == "completed"
        assert restored["risk_findings"][0]["risk_level"] == "avoid"
        assert restored["images"] == []
        assert restored["redactions"] == ["images"]

        duplicate_without_token = await client.post(
            "/api/v1/labels/evaluate", json=payload
        )
        assert duplicate_without_token.status_code == 403
        second = await client.post(
            "/api/v1/labels/evaluate",
            json={**payload, "resume_token": token},
        )
        assert second.status_code == 200
        assert second.json()["checkpoint"]["sequence"] == 2
        assert second.json()["checkpoint"]["resume_token"] is None

        deleted = await client.delete(
            "/api/v1/workflows/workflow-resume-api",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted_checkpoints"] == 2


def test_authorized_memory_api_supports_full_user_control(tmp_path: Path) -> None:
    asyncio.run(_memory_lifecycle(tmp_path))


async def _memory_lifecycle(tmp_path: Path) -> None:
    database = tmp_path / "milestone4.sqlite3"
    app = create_app(
        checkpoint_store=SQLiteCheckpointStore(database),
        memory_store=SQLiteMemoryStore(database),
    )
    transport = httpx.ASGITransport(app=app)
    profile_id = "profile-api-12345678"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/memory/consents",
            json={
                "profile_id": profile_id,
                "purpose": "保存长期食品约束",
                "explicit_consent": False,
            },
        )
        assert denied.status_code == 403

        granted = await client.post(
            "/api/v1/memory/consents",
            json={
                "profile_id": profile_id,
                "purpose": "跨会话保存用户明确声明的食品约束",
                "explicit_consent": True,
            },
        )
        assert granted.status_code == 201
        token = granted.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        item_payload = {
            "kind": "constraint",
            "value": {
                "kind": "allergy",
                "canonical_value": "milk",
                "severity": "severe",
            },
        }
        saved = await client.post(
            f"/api/v1/memory/items?profile_id={profile_id}",
            headers=headers,
            json=item_payload,
        )
        assert saved.status_code == 201
        memory_id = saved.json()["item"]["memory_id"]

        viewed = await client.get(
            f"/api/v1/memory/items?profile_id={profile_id}", headers=headers
        )
        assert viewed.status_code == 200
        assert viewed.json()["items"][0]["value"]["canonical_value"] == "milk"

        updated = await client.put(
            f"/api/v1/memory/items/{memory_id}?profile_id={profile_id}",
            headers=headers,
            json={
                **item_payload,
                "value": {**item_payload["value"], "severity": "moderate"},
            },
        )
        assert updated.status_code == 200
        assert updated.json()["item"]["value"]["severity"] == "moderate"

        deleted = await client.delete(
            f"/api/v1/memory/items/{memory_id}?profile_id={profile_id}",
            headers=headers,
        )
        assert deleted.status_code == 200

        await client.post(
            f"/api/v1/memory/items?profile_id={profile_id}",
            headers=headers,
            json=item_payload,
        )
        revoked = await client.delete(
            f"/api/v1/memory/consents/current?profile_id={profile_id}",
            headers=headers,
        )
        assert revoked.status_code == 200
        assert revoked.json()["deleted_memory_items"] == 1
        after_revoke = await client.get(
            f"/api/v1/memory/items?profile_id={profile_id}", headers=headers
        )
        assert after_revoke.status_code == 403
