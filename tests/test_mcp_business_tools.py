from __future__ import annotations

import asyncio
import json

from food_label_agent.mcp.server import create_server


def _json_result(blocks) -> dict:
    assert len(blocks) == 1
    return json.loads(blocks[0].text)


def test_normalize_food_label_is_registered_and_traceable() -> None:
    asyncio.run(_test_normalize_food_label_is_registered_and_traceable())


async def _test_normalize_food_label_is_registered_and_traceable() -> None:
    server = create_server()
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert "normalize_food_label" in tools
    result = _json_result(
        await server.call_tool(
            "normalize_food_label",
            {
                "ingredients_text": "复合调味料（白砂糖、乳清蛋白）",
                "source_bounding_box": [10, 20, 300, 80],
            },
        )
    )

    whey = result["ingredients"][0]["children"][1]
    assert whey["canonical_name"] == "乳清蛋白"
    assert whey["evidence_id"] == "label.ingredients.item.1.2"
    assert whey["source_range"]["bounding_box"] == [10, 20, 300, 80]


def test_evaluate_user_constraints_is_registered_and_deterministic() -> None:
    asyncio.run(_test_evaluate_user_constraints_is_registered_and_deterministic())


async def _test_evaluate_user_constraints_is_registered_and_deterministic() -> None:
    server = create_server()
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert "evaluate_user_constraints" in tools
    result = _json_result(
        await server.call_tool(
            "evaluate_user_constraints",
            {
                "request_id": "mcp-test",
                "applicable_date": "2026-08-09",
                "confirmed_fields": {
                    "ingredients": "白砂糖、复合调味料（食用盐、乳清蛋白）"
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

    assert result["overall_risk_level"] == "avoid"
    assert result["findings"][0]["matched_text"] == "乳清蛋白"
    assert result["findings"][0]["reason_code"] == "DIRECT_ALLERGEN_DERIVATIVE"
    assert result["findings"][0]["evidence_ids"] == ["label.ingredients.item.2.2"]
    assert result["next_route"] == "retrieve_regulations"


def test_evaluate_user_constraints_preserves_unknown() -> None:
    asyncio.run(_test_evaluate_user_constraints_preserves_unknown())


async def _test_evaluate_user_constraints_preserves_unknown() -> None:
    result = _json_result(
        await create_server().call_tool(
            "evaluate_user_constraints",
            {
                "request_id": "mcp-unknown",
                "applicable_date": "2026-08-09",
                "confirmed_fields": {"ingredients": "白砂糖、奶味香精"},
                "constraints": [{"kind": "allergy", "canonical_value": "milk"}],
            },
        )
    )

    assert result["overall_risk_level"] == "unknown"
    assert result["findings"][0]["reason_code"] == "AMBIGUOUS_INGREDIENT_NAME"


def test_search_food_regulations_filters_versions_by_applicable_date() -> None:
    asyncio.run(_test_search_food_regulations_filters_versions_by_applicable_date())


async def _test_search_food_regulations_filters_versions_by_applicable_date() -> None:
    server = create_server()
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert "search_food_regulations" in tools
    result = _json_result(
        await server.call_tool(
            "search_food_regulations",
            {
                "query": "乳清蛋白 过敏原 配料表",
                "jurisdiction": "CN",
                "applicable_date": "2026-08-09",
                "topics": ["allergen", "ingredient_labeling"],
            },
        )
    )

    assert result["status"] == "found"
    assert result["results"]
    assert {item["standard_number"] for item in result["results"]} == {"GB 7718-2011"}
    assert all(
        item["source_url"].startswith("https://www.nhc.gov.cn/")
        for item in result["results"]
    )


def test_explain_ingredient_is_registered_and_cannot_lower_risk() -> None:
    asyncio.run(_test_explain_ingredient_is_registered_and_cannot_lower_risk())


async def _test_explain_ingredient_is_registered_and_cannot_lower_risk() -> None:
    server = create_server()
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert "explain_ingredient" in tools
    result = _json_result(
        await server.call_tool(
            "explain_ingredient",
            {
                "ingredient": {
                    "raw_name": "乳清蛋白",
                    "canonical_name": "乳清蛋白",
                    "category": "乳及乳制品",
                    "relation": "derivative",
                    "allergen_keys": ["milk"],
                    "normalization_method": "dictionary_exact",
                    "evidence_id": "label.ingredients.item.2",
                },
                "risk_finding": {
                    "risk_level": "avoid",
                    "constraint": "milk",
                    "matched_text": "乳清蛋白",
                    "reason_code": "DIRECT_ALLERGEN_DERIVATIVE",
                    "explanation": "已命中乳来源成分。",
                    "evidence_ids": ["label.ingredients.item.2"],
                },
                "regulatory_evidence": [
                    {
                        "source_id": "reg.cn.gb7718-2011.4.4.3.1.allergens",
                        "standard_number": "GB 7718-2011",
                        "section": "4.4.3.1 致敏物质",
                        "source_url": "https://www.nhc.gov.cn/example/gb7718.pdf",
                        "evidence_text": "乳及乳制品作为配料时宜明确标示。",
                        "content_hash": "a" * 64,
                        "authority_level": "A",
                        "page_start": 7,
                        "page_end": 7,
                        "jurisdiction": "CN",
                        "effective_from": "2012-04-20",
                        "effective_to": "2027-03-15",
                    }
                ],
                "jurisdiction": "CN",
                "applicable_date": "2026-08-09",
            },
        )
    )

    assert result["status"] == "explained"
    assert result["risk_level"] == "avoid"
    assert result["label_evidence_ids"] == ["label.ingredients.item.2"]
    assert result["regulatory_evidence_ids"]
    assert result["citations"][0]["page_start"] == 7


def test_claim_tools_are_registered_on_real_mcp_server() -> None:
    asyncio.run(_test_claim_tools_are_registered_on_real_mcp_server())


async def _test_claim_tools_are_registered_on_real_mcp_server() -> None:
    server = create_server()
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert "interpret_label_claim" in tools
    assert "verify_label_consistency" in tools
