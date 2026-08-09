from __future__ import annotations

from food_label_agent.claims.models import (
    ClaimConsistencyRequest,
    ClaimInterpretationRequest,
)
from food_label_agent.claims.service import interpret_claim, verify_claim_consistency
from food_label_agent.mcp.business_tools import invoke_mcp_tool


def _sugar_evidence() -> dict:
    return {
        "source_id": "reg.cn.gb28050-2011.annex-c.table-c1",
        "standard_number": "GB 28050-2011",
        "section": "附录C 表C.1",
        "source_url": "https://www.nhc.gov.cn/ewebeditor/uploadfile/2013/06/20130605104041625.pdf",
        "evidence_text": "碳水化合物（糖） 无或不含糖 ≤0.5 g/100 g（固体）或100 mL（液体）；低糖 ≤5 g/100 g（固体）或100 mL（液体）。",
        "content_hash": "a" * 64,
        "authority_level": "A",
        "jurisdiction": "CN",
        "effective_from": "2013-01-01",
        "effective_to": "2027-03-15",
        "page_start": 8,
        "page_end": 8,
    }


def _interpret(text: str):
    return interpret_claim(
        ClaimInterpretationRequest(
            claim_text=text,
            applicable_date="2026-08-09",
            regulatory_evidence=[_sugar_evidence()],
        )
    )


def test_claim_aliases_remain_non_equivalent() -> None:
    result = _interpret("0糖 0蔗糖 不添加糖 不添加蔗糖")

    assert [item["canonical_type"] for item in result.claims] == [
        "sugar_free",
        "no_sucrose",
        "no_added_sugar",
        "no_added_sucrose",
    ]
    no_sucrose = result.claims[1]
    assert "不等同于无糖" in no_sucrose["meaning"]
    assert no_sucrose["regulatory_evidence_ids"] == []


def test_sugar_free_requires_confirmed_nutrition_basis() -> None:
    claim = _interpret("无糖").claims[0]
    result = verify_claim_consistency(
        ClaimConsistencyRequest(
            claims=[claim],
            ingredients_text="水、赤藓糖醇",
            applicable_date="2026-08-09",
        )
    )

    assert result.status == "unknown"
    assert result.findings[0]["reason_code"] == "SUGAR_VALUE_OR_BASIS_MISSING"


def test_sugar_free_threshold_can_be_checked_without_llm() -> None:
    claim = _interpret("0糖").claims[0]
    met = verify_claim_consistency(
        ClaimConsistencyRequest(
            claims=[claim],
            nutrition_values={"sugars_g": 0.5, "basis": "per_100ml"},
            applicable_date="2026-08-09",
        )
    )
    exceeded = verify_claim_consistency(
        ClaimConsistencyRequest(
            claims=[claim],
            nutrition_values={"sugars_g_per_100g": 0.6},
            applicable_date="2026-08-09",
        )
    )

    assert met.findings[0]["status"] == "consistent"
    assert exceeded.findings[0]["status"] == "inconsistent"


def test_invalid_sugar_value_cannot_pass_threshold() -> None:
    claim = _interpret("无糖").claims[0]
    result = verify_claim_consistency(
        ClaimConsistencyRequest(
            claims=[claim],
            nutrition_values={"sugars_g": -1, "basis": "per_100g"},
            applicable_date="2026-08-09",
        )
    )

    assert result.findings[0]["status"] == "unknown"
    assert result.findings[0]["reason_code"] == "SUGAR_VALUE_INVALID"


def test_no_sucrose_detects_direct_contradiction() -> None:
    claim = _interpret("无蔗糖").claims[0]
    result = verify_claim_consistency(
        ClaimConsistencyRequest(
            claims=[claim],
            ingredients_text="水、白砂糖、柠檬酸",
            applicable_date="2026-08-09",
        )
    )

    assert result.status == "inconsistent"
    assert result.findings[0]["matched_text"] == "白砂糖"


def test_no_sucrose_never_becomes_sugar_free_when_other_sugar_is_present() -> None:
    claim = _interpret("0蔗糖").claims[0]
    result = verify_claim_consistency(
        ClaimConsistencyRequest(
            claims=[claim],
            ingredients_text="水、果葡糖浆",
            applicable_date="2026-08-09",
        )
    )

    finding = result.findings[0]
    assert finding["status"] == "not_contradicted"
    assert "不能据此理解为无糖" in finding["explanation"]


def test_tools_are_available_through_unified_mcp_boundary() -> None:
    interpretation = invoke_mcp_tool(
        "interpret_label_claim",
        {
            "claim_text": "低糖",
            "regulatory_evidence": [_sugar_evidence()],
            "applicable_date": "2026-08-09",
        },
    )
    checked = invoke_mcp_tool(
        "verify_label_consistency",
        {
            "claims": interpretation["claims"],
            "nutrition_values": {"sugars_g_per_100g": 5},
            "regulatory_evidence": [_sugar_evidence()],
            "applicable_date": "2026-08-09",
        },
    )

    assert interpretation["claims"][0]["canonical_type"] == "low_sugar"
    assert checked["findings"][0]["status"] == "consistent"
