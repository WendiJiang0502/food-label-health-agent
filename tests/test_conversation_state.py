from __future__ import annotations

from pathlib import Path

from food_label_agent.conversation.provider import (
    ConversationSettings,
    OpenAIConversationProvider,
)
from food_label_agent.conversation.service import ConversationAgent
from food_label_agent.conversation.state import (
    StructuredConversationState,
    classify_conversation_intent,
    compare_confirmed_products,
    correction_guidance,
    reasoning_effort_for_intent,
    update_structured_state,
)
from food_label_agent.conversation.store import SQLiteConversationStore
from food_label_agent.domain.models import LabelField
from food_label_agent.graph.state import create_initial_state


def _workflow(request_id: str, name: str, sugar: float, *, issue: str | None = None):
    state = create_initial_state(
        request_id=request_id, jurisdiction="CN", applicable_date="2026-09-11"
    )
    state["label_fields"] = {
        "product_name": LabelField("product_name", name, 1.0, True),
        "ingredients": LabelField("ingredients", "燕麦、水", 1.0, True),
        "unconfirmed": LabelField("unconfirmed", "不得进入状态", 0.2, False),
    }
    state["normalized_label"] = {
        "ingredients": [
            {
                "raw_name": "乳清蛋白",
                "canonical_name": "whey protein",
                "children": [],
            }
        ],
        "nutrition": {
            "basis": {"type": "per_100g", "amount": 100, "unit": "g"},
            "nutrients": [
                {
                    "canonical_name": "sugars",
                    "value": sugar,
                    "unit": "g",
                    "evidence_id": f"{request_id}.sugar",
                }
            ],
        }
    }
    if issue:
        state["unknowns"].append(issue)
    return state


def test_structured_state_keeps_two_confirmed_products_and_no_ocr_guess() -> None:
    current = update_structured_state(
        StructuredConversationState(), message="先看这个", workflow_state=_workflow("a", "甲", 3)
    )
    current = update_structured_state(
        current, message="比较哪一个", workflow_state=_workflow("b", "乙", 8)
    )

    assert current.active_product_id == "b"
    assert [item.display_name for item in current.products] == ["甲", "乙"]
    assert all("unconfirmed" not in item.confirmed_fields for item in current.products)
    assert current.current_intent == "compare_products"
    comparison = compare_confirmed_products(current)
    assert comparison["status"] == "compared"
    assert comparison["comparisons"][0]["values"] == [
        {"product": "甲", "value": 3.0},
        {"product": "乙", "value": 8.0},
    ]
    assert comparison["boundary"] == "evidence_comparison_only_no_medical_decision"


def test_correction_guidance_never_writes_back_label_fact() -> None:
    current = update_structured_state(
        StructuredConversationState(),
        message="括号识别错了怎么改",
        workflow_state=_workflow("c", "丙", 5, issue="配料括号结构待确认"),
    )

    guidance = correction_guidance(current)
    assert guidance["status"] == "review_required"
    assert guidance["auto_correction_applied"] is False
    assert "配料括号结构待确认" in guidance["issues"]


def test_structured_state_is_capability_protected_and_deleted(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "chat.sqlite3")
    receipt = store.create_session()
    state = update_structured_state(
        StructuredConversationState(), message="当前商品", workflow_state=_workflow("d", "丁", 1)
    )
    store.save_structured_state(receipt.session_id, receipt.access_token, state.to_dict())

    restored = StructuredConversationState.from_dict(
        store.structured_state(receipt.session_id, receipt.access_token)
    )
    assert restored.active_product_id == "d"
    store.delete(receipt.session_id, receipt.access_token)
    assert store._connection.execute("SELECT COUNT(*) FROM conversation_states").fetchone()[0] == 0


def test_comparison_intent_routes_to_medium_reasoning_and_records_cost() -> None:
    payloads = []

    def transport(_url, _headers, payload, _timeout):
        payloads.append(payload)
        return {
            "id": "resp-routing",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "_first_token_ms": 12.0,
            "usage": {"input_tokens": 1_000, "output_tokens": 100},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "只比较同口径证据。"}]}],
        }

    structured = update_structured_state(
        StructuredConversationState(), message="比较哪个", workflow_state=_workflow("e", "戊", 2)
    )
    structured = update_structured_state(
        structured, message="比较哪个", workflow_state=_workflow("f", "己", 4)
    )
    provider = OpenAIConversationProvider(
        ConversationSettings(api_key="test", input_usd_per_million=2, output_usd_per_million=12),
        transport=transport,
    )
    reply = ConversationAgent(provider).reply(
        session_id="routing", messages=[{"role": "user", "content": "哪个更适合？"}], conversation_state=structured
    )

    assert payloads[0]["reasoning"]["effort"] == "medium"
    assert payloads[0]["stream"] is True
    assert reply.reasoning_effort == "medium"
    assert reply.first_token_ms is not None
    assert reply.cost_usd == 0.0032
    assert reasoning_effort_for_intent("general_question") == "low"
    assert reasoning_effort_for_intent(
        classify_conversation_intent("两份证据说法不一致怎么办？")
    ) == "medium"


def test_approved_tool_failure_is_structured_and_does_not_escape(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("secret provider detail")

    monkeypatch.setattr("food_label_agent.conversation.service.invoke_mcp_tool", fail)
    agent = ConversationAgent(
        OpenAIConversationProvider(ConversationSettings(api_key="test"), transport=lambda *_: {})
    )
    result = agent._invoke_tool(
        "explain_current_ingredient",
        {"ingredient_name": "乳清蛋白"},
        _workflow("tool", "工具测试", 2),
        StructuredConversationState(),
    )

    assert result == {
        "status": "unavailable",
        "reason": "approved_tool_failed",
        "error_type": "RuntimeError",
    }
    assert "secret provider detail" not in str(result)


def test_agent_executes_two_product_comparison_through_whitelist() -> None:
    calls = []

    def transport(_url, _headers, payload, _timeout):
        calls.append(payload)
        if len(calls) == 1:
            return {
                "id": "resp-tool",
                "status": "completed",
                "model": "gpt-5.6-terra",
                "output": [
                    {
                        "type": "function_call",
                        "name": "compare_confirmed_products",
                        "call_id": "compare-1",
                        "arguments": "{}",
                    }
                ],
            }
        return {
            "id": "resp-final",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "只按每100克确认数据比较，不替你作医疗决定。",
                        }
                    ],
                }
            ],
        }

    structured = update_structured_state(
        StructuredConversationState(),
        message="先记录甲",
        workflow_state=_workflow("compare-a", "甲", 2),
    )
    structured = update_structured_state(
        structured,
        message="比较哪一个",
        workflow_state=_workflow("compare-b", "乙", 7),
    )
    agent = ConversationAgent(
        OpenAIConversationProvider(
            ConversationSettings(api_key="test"), transport=transport
        )
    )
    reply = agent.reply(
        session_id="compare-session",
        messages=[{"role": "user", "content": "两个产品有什么差别？"}],
        conversation_state=structured,
    )

    assert reply.tool_events == (
        {"name": "compare_confirmed_products", "status": "compared"},
    )
    tool_output = next(
        item for item in calls[1]["input"] if item.get("type") == "function_call_output"
    )["output"]
    assert '"boundary":"evidence_comparison_only_no_medical_decision"' in tool_output
    assert calls[0]["reasoning"]["effort"] == "medium"
