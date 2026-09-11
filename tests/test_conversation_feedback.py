from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from food_label_agent.conversation.provider import (
    ConversationSettings,
    OpenAIConversationProvider,
)
from food_label_agent.conversation.service import ConversationAgent
from food_label_agent.conversation.store import SQLiteConversationStore
from food_label_agent.web.app import create_app


def _agent() -> ConversationAgent:
    def transport(_url, _headers, _payload, _timeout):
        return {
            "id": "response-feedback",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "usage": {"input_tokens": 20, "output_tokens": 8},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "请先确认标签再判断。"}
                    ],
                }
            ],
        }

    return ConversationAgent(
        OpenAIConversationProvider(
            ConversationSettings(api_key="feedback-test"), transport=transport
        )
    )


def _sse_payload(text: str, event_name: str) -> dict:
    blocks = [block for block in text.split("\n\n") if block]
    block = next(block for block in blocks if f"event: {event_name}" in block)
    data = next(line[6:] for line in block.splitlines() if line.startswith("data: "))
    return json.loads(data)


def test_feedback_api_records_categories_without_raw_conversation(
    tmp_path: Path, monkeypatch
) -> None:
    store = SQLiteConversationStore(tmp_path / "feedback.sqlite3")
    monkeypatch.setenv("FOOD_LABEL_DEV_TOKEN", "developer-feedback-token")
    app = create_app(conversation_store=store, conversation_agent=_agent())

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            receipt = (await client.post("/api/v1/chat/sessions")).json()["session"]
            headers = {"Authorization": f"Bearer {receipt['access_token']}"}
            answer = await client.post(
                f"/api/v1/chat/sessions/{receipt['session_id']}/messages",
                headers=headers,
                json={
                    "content": "这个能吃吗？",
                    "remote_processing_consent": True,
                },
            )
            message_id = _sse_payload(answer.text, "done")["message_id"]
            feedback = await client.post(
                f"/api/v1/chat/sessions/{receipt['session_id']}/feedback",
                headers=headers,
                json={
                    "message_id": message_id,
                    "helpful": False,
                    "reason": "evidence_gap",
                    "retry_requested": True,
                },
            )
            restored = await client.get(
                f"/api/v1/chat/sessions/{receipt['session_id']}", headers=headers
            )
            denied_metrics = await client.get("/api/v1/pilot/metrics")
            metrics = await client.get(
                "/api/v1/pilot/metrics",
                headers={"Authorization": "Bearer developer-feedback-token"},
            )
            return receipt, answer, feedback, restored, denied_metrics, metrics

    receipt, answer, feedback, restored, denied_metrics, metrics = asyncio.run(scenario())

    assert answer.status_code == 200
    assert feedback.status_code == 201
    assert feedback.json()["privacy"] == {
        "raw_conversation_stored": False,
        "retention_days": 30,
    }
    assert restored.json()["session"]["feedback"][0]["reason"] == "evidence_gap"
    assert denied_metrics.status_code == 403
    assert metrics.json()["status"] == "collecting"
    assert metrics.json()["feedback_gate_passed"] is False
    assert metrics.json()["pilot_outcome_validated"] is False
    assert metrics.json()["summary"] == {
        "feedback_count": 1,
        "helpful_count": 0,
        "helpful_rate": 0.0,
        "negative_reason_counts": {"evidence_gap": 1},
        "retry_requested_count": 1,
        "unique_session_count": 1,
        "raw_conversation_stored": False,
        "retention_days": 30,
    }
    feedback_rows = store._connection.execute(
        "SELECT * FROM conversation_feedback"
    ).fetchall()
    assert len(feedback_rows) == 1
    assert receipt["session_id"] not in str(dict(feedback_rows[0]))
    assert "这个能吃吗" not in str(dict(feedback_rows[0]))


def test_feedback_requires_assistant_message_and_negative_reason(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "feedback.sqlite3")
    receipt = store.create_session()
    user = store.append_message(
        receipt.session_id,
        receipt.access_token,
        role="user",
        content="测试问题",
    )

    try:
        store.record_feedback(
            receipt.session_id,
            receipt.access_token,
            message_id=user["message_id"],
            helpful=False,
        )
    except ValueError as exc:
        assert "requires a reason" in str(exc)
    else:
        raise AssertionError("negative feedback without a reason must fail")

    try:
        store.record_feedback(
            receipt.session_id,
            receipt.access_token,
            message_id=user["message_id"],
            helpful=True,
        )
    except ValueError as exc:
        assert "assistant message" in str(exc)
    else:
        raise AssertionError("user messages cannot receive assistant feedback")


def test_deleting_conversation_also_deletes_anonymous_feedback(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "feedback.sqlite3")
    receipt = store.create_session()
    assistant = store.append_message(
        receipt.session_id,
        receipt.access_token,
        role="assistant",
        content="测试回答",
    )
    store.record_feedback(
        receipt.session_id,
        receipt.access_token,
        message_id=assistant["message_id"],
        helpful=True,
    )

    store.delete(receipt.session_id, receipt.access_token)

    assert store.feedback_summary()["feedback_count"] == 0


def test_feedback_ui_has_accessible_recovery_and_privacy_copy() -> None:
    root = Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"
    script = (root / "app.js").read_text(encoding="utf-8")
    page = (root / "index.html").read_text(encoding="utf-8")

    assert "appendChatFeedback" in script
    assert "aria-pressed" in script
    assert "重新回答" in script
    assert "对照包装纠正标签" in script
    assert "不保存对话或标签原文" in page


def test_feedback_metrics_cannot_claim_human_pilot_validation(
    tmp_path: Path, monkeypatch
) -> None:
    store = SQLiteConversationStore(tmp_path / "feedback.sqlite3")
    monkeypatch.setenv("FOOD_LABEL_DEV_TOKEN", "developer-feedback-token")
    monkeypatch.setattr(store, "feedback_summary", lambda: {
        "feedback_count": 100,
        "helpful_count": 90,
        "helpful_rate": 0.9,
        "negative_reason_counts": {},
        "retry_requested_count": 0,
        "unique_session_count": 20,
        "raw_conversation_stored": False,
        "retention_days": 30,
    })
    app = create_app(conversation_store=store, conversation_agent=_agent())

    async def request_metrics():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get(
                "/api/v1/pilot/metrics",
                headers={"Authorization": "Bearer developer-feedback-token"},
            )

    payload = asyncio.run(request_metrics()).json()

    assert payload["status"] == "feedback_thresholds_met"
    assert payload["feedback_gate_passed"] is True
    assert payload["pilot_outcome_validated"] is False
