from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from test_constrained_react import _ready_state

from food_label_agent.graph import react
from food_label_agent.mcp.business_tools import MCPToolCallError
from food_label_agent.persistence.sqlite import SQLiteCheckpointStore, SQLiteMemoryStore
from food_label_agent.web.app import create_app


def test_ocr_to_alternatives_uses_one_resumable_state_and_final_gate(
    tmp_path: Path,
) -> None:
    asyncio.run(_full_resume_flow(tmp_path))


async def _full_resume_flow(tmp_path: Path) -> None:
    database = tmp_path / "milestone5.sqlite3"
    app = create_app(
        checkpoint_store=SQLiteCheckpointStore(database),
        memory_store=SQLiteMemoryStore(database),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ocr = await client.post(
            "/api/v1/ocr/analyze",
            files={"image": ("label.jpg", b"\xff\xd8\xffmilestone5", "image/jpeg")},
        )
        assert ocr.status_code == 200
        request_id = ocr.json()["request_id"]
        token = ocr.json()["checkpoint"]["resume_token"]
        assert ocr.json()["checkpoint"]["sequence"] == 1
        assert ocr.json()["workflow_trace"][-1]["node_name"] == "confirm_label"
        assert ocr.json()["workflow_trace"][-1]["outcome"] == "paused"

        confirmed = await client.post(
            "/api/v1/labels/confirm",
            json={
                "request_id": request_id,
                "applicable_date": "2026-08-09",
                "fields": {"ingredients": "小麦粉、乳清蛋白"},
                "resume_token": token,
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["checkpoint"]["sequence"] == 2
        assert confirmed.json()["status"] == "needs_confirmation"
        assert confirmed.json()["next_route"] == "evaluate_safety"

        request = {
            "request_id": request_id,
            "jurisdiction": "CN",
            "applicable_date": "2026-08-09",
            "confirmed_fields": {"ingredients": "小麦粉、乳清蛋白"},
            "constraints": [
                {"kind": "allergy", "canonical_value": "milk", "severity": "severe"}
            ],
            "resume_token": token,
        }
        evaluated = await client.post("/api/v1/labels/evaluate", json=request)
        assert evaluated.status_code == 200
        assert evaluated.json()["checkpoint"]["sequence"] == 3
        assert evaluated.json()["overall_risk_level"] == "avoid"
        assert evaluated.json()["evidence"]["final_status"] == "completed"
        assert evaluated.json()["evidence"]["release_gate"]["passed"] is True
        assert evaluated.json()["evidence"]["workflow_trace"][-1]["node_name"] == (
            "final_safety_gate"
        )

        alternatives = await client.post(
            "/api/v1/alternatives/search",
            json={**request, "category": "biscuit", "region": "CN"},
        )
        assert alternatives.status_code == 200
        assert alternatives.json()["checkpoint"]["sequence"] == 4
        assert alternatives.json()["workflow_trace"][-3]["node_name"] == (
            "search_alternatives"
        )
        assert alternatives.json()["workflow_trace"][-2]["node_name"] == (
            "revalidate_alternatives"
        )
        assert alternatives.json()["workflow_trace"][-1]["node_name"] == (
            "final_safety_gate"
        )
        assert alternatives.json()["release_gate"]["passed"] is True

        resumed = await client.get(
            f"/api/v1/workflows/{request_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resumed.status_code == 200
        state = resumed.json()["state"]
        assert state["schema_version"] == 2
        assert state["risk_findings"][0]["risk_level"] == "avoid"
        assert [item["sequence"] for item in resumed.json()["history"]] == [1, 2, 3, 4]


def test_react_retries_once_and_records_recovery(monkeypatch) -> None:
    original = react.invoke_mcp_tool
    calls = 0

    def flaky(tool_name: str, arguments: dict):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise MCPToolCallError(tool_name, RuntimeError("temporary"))
        return original(tool_name, arguments)

    monkeypatch.setattr(react, "invoke_mcp_tool", flaky)
    update = react.react_orchestrator(_ready_state())

    assert update["status"].value == "in_progress"
    assert update["react_budget"]["tool_calls_used"] == 8
    assert update["tool_trace"][0].outcome == "retry_scheduled"
    assert update["tool_trace"][1].outcome == "recovered"
    assert any(
        event.event_type == "react_tool_retry_scheduled"
        for event in update["audit_events"]
    )


def test_react_blocks_after_bounded_retry_failure(monkeypatch) -> None:
    calls = 0

    def unavailable(tool_name: str, arguments: dict):
        nonlocal calls
        calls += 1
        raise MCPToolCallError(tool_name, RuntimeError("still unavailable"))

    monkeypatch.setattr(react, "invoke_mcp_tool", unavailable)
    update = react.react_orchestrator(_ready_state())

    # Three independent evidence requests are already in flight; only the
    # failed request selected for handling is retried once.
    assert calls == 4
    assert update["status"].value == "blocked"
    assert update["tool_trace"][-1].outcome == "failed"
    assert "mcp_tool_failed:search_food_regulations" in update["errors"]
    assert "search_food_regulations_unavailable" in update["unknowns"]
