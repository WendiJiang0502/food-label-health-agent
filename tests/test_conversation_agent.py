from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from food_label_agent.conversation.provider import (
    ConversationSettings,
    OpenAIConversationProvider,
)
from food_label_agent.conversation.service import ConversationAgent
from food_label_agent.conversation.store import SQLiteConversationStore
from food_label_agent.web.app import create_app


def _settings() -> ConversationSettings:
    return ConversationSettings(
        api_key="test-key",
        model="gpt-5.6-terra",
        max_tool_calls=6,
    )


def test_short_term_conversation_store_is_token_protected(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "conversation.sqlite3")
    receipt = store.create_session()
    store.append_message(
        receipt.session_id,
        receipt.access_token,
        role="user",
        content="这个配料是什么意思？",
    )

    session = store.session(receipt.session_id, receipt.access_token)

    assert session["messages"][0]["content"] == "这个配料是什么意思？"
    assert store.durable is True
    with pytest.raises(PermissionError):
        store.session(receipt.session_id, "wrong-token")

    store.delete(receipt.session_id, receipt.access_token)
    remaining_messages = store._connection.execute(
        "SELECT COUNT(*) FROM conversation_messages"
    ).fetchone()[0]
    assert remaining_messages == 0


def test_provider_replays_only_approved_tool_results_and_disables_storage() -> None:
    payloads: list[dict] = []

    def transport(_url, _headers, payload, _timeout):
        payloads.append(payload)
        if len(payloads) == 1:
            return {
                "id": "resp-tool",
                "status": "completed",
                "model": "gpt-5.6-terra",
                "usage": {"input_tokens": 20, "output_tokens": 5},
                "output": [
                    {
                        "type": "function_call",
                        "name": "search_current_regulations",
                        "call_id": "call-1",
                        "arguments": '{"query":"乳过敏原","topics":["allergen"]}',
                    }
                ],
            }
        return {
            "id": "resp-final",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "usage": {"input_tokens": 30, "output_tokens": 12},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "根据已确认标签，需要避免。"}
                    ],
                }
            ],
        }

    provider = OpenAIConversationProvider(_settings(), transport=transport)
    reply = provider.complete(
        instructions="test",
        messages=[{"role": "user", "content": "能吃吗"}],
        tools=[
            {
                "type": "function",
                "name": "search_current_regulations",
                "parameters": {"type": "object"},
            }
        ],
        tool_handler=lambda name, arguments: {
            "status": "found",
            "name": name,
            "query": arguments["query"],
        },
        safety_key="session-1",
    )

    assert reply.text == "根据已确认标签，需要避免。"
    assert reply.input_tokens == 50
    assert reply.output_tokens == 17
    assert reply.tool_events == (
        {"name": "search_current_regulations", "status": "found"},
    )
    assert all(payload["store"] is False for payload in payloads)
    assert payloads[0]["parallel_tool_calls"] is False
    assert payloads[0]["max_tool_calls"] == 6
    assert reply.request_count == 2
    assert reply.latency_ms >= 0
    assert any(
        item.get("type") == "function_call_output" for item in payloads[1]["input"]
    )


def test_provider_omits_tool_controls_when_no_tools_are_available() -> None:
    payloads: list[dict] = []

    def transport(_url, _headers, payload, _timeout):
        payloads.append(payload)
        return {
            "id": "resp-chat",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "你好。"}],
                }
            ],
        }

    provider = OpenAIConversationProvider(_settings(), transport=transport)
    reply = provider.complete(
        instructions="test",
        messages=[{"role": "user", "content": "你好"}],
        tools=[],
        tool_handler=lambda *_args: pytest.fail("tool handler must not be called"),
        safety_key="session-no-tools",
    )

    assert reply.text == "你好。"
    assert "tools" not in payloads[0]
    assert "tool_choice" not in payloads[0]
    assert "parallel_tool_calls" not in payloads[0]


def test_emergency_reply_does_not_call_remote_model() -> None:
    def transport(*_args):
        raise AssertionError("remote model must not be called")

    agent = ConversationAgent(
        OpenAIConversationProvider(_settings(), transport=transport)
    )
    reply = agent.reply(
        session_id="session-emergency",
        messages=[{"role": "user", "content": "我现在喉咙肿而且呼吸困难"}],
    )

    assert reply.boundary == "emergency"
    assert "立即" in reply.text
    assert "急救" in reply.text
    assert reply.model is None


def test_chat_api_creates_streams_and_deletes_a_session() -> None:
    def transport(_url, _headers, _payload, _timeout):
        return {
            "id": "resp-chat",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "usage": {"input_tokens": 25, "output_tokens": 18},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "可以先拍摄并确认配料表，我再结合标签回答。",
                        }
                    ],
                }
            ],
        }

    store = SQLiteConversationStore()
    agent = ConversationAgent(
        OpenAIConversationProvider(_settings(), transport=transport)
    )
    app = create_app(conversation_store=store, conversation_agent=agent)

    async def scenario():
        transport_client = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport_client, base_url="http://test"
        ) as client:
            created = await client.post("/api/v1/chat/sessions")
            receipt = created.json()["session"]
            headers = {"Authorization": f"Bearer {receipt['access_token']}"}
            streamed = await client.post(
                f"/api/v1/chat/sessions/{receipt['session_id']}/messages",
                headers=headers,
                json={
                    "content": "这个食品适合我吗？",
                    "remote_processing_consent": True,
                },
            )
            fetched = await client.get(
                f"/api/v1/chat/sessions/{receipt['session_id']}",
                headers=headers,
            )
            deleted = await client.delete(
                f"/api/v1/chat/sessions/{receipt['session_id']}",
                headers=headers,
            )
            return created, streamed, fetched, deleted

    created, streamed, fetched, deleted = asyncio.run(scenario())

    assert created.status_code == 201
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in streamed.text
    assert "event: delta" in streamed.text
    assert "event: done" in streamed.text
    assert len(fetched.json()["session"]["messages"]) == 2
    assert deleted.json()["status"] == "deleted"


def test_chat_api_requires_explicit_remote_processing_consent() -> None:
    agent = ConversationAgent(
        OpenAIConversationProvider(
            _settings(),
            transport=lambda *_args: pytest.fail("model must not be called"),
        )
    )
    app = create_app(
        conversation_store=SQLiteConversationStore(), conversation_agent=agent
    )

    async def scenario():
        transport_client = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport_client, base_url="http://test"
        ) as client:
            created = await client.post("/api/v1/chat/sessions")
            receipt = created.json()["session"]
            return await client.post(
                f"/api/v1/chat/sessions/{receipt['session_id']}/messages",
                headers={"Authorization": f"Bearer {receipt['access_token']}"},
                json={"content": "请解释这个配料"},
            )

    response = asyncio.run(scenario())

    assert response.status_code == 412
    assert response.json()["code"] == "REMOTE_PROCESSING_CONSENT_REQUIRED"
