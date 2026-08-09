from __future__ import annotations

from food_label_agent.graph.workflows import attach_regulatory_interpretation
from food_label_agent.ingredients.api_models import SafetyEvaluationRequest
from food_label_agent.ingredients.explanations import (
    IngredientExplanationRequest,
    explain_ingredient_with_evidence,
)
from food_label_agent.ingredients.normalization import normalize_ingredients
from food_label_agent.ingredients.service import evaluate_user_constraints_result


def test_additives_inside_declared_group_are_normalized_and_traceable() -> None:
    label = normalize_ingredients(
        "猪肉、食品添加剂（三聚磷酸钠、D-异抗坏血酸钠、亚硝酸钠）"
    )

    group = label.ingredients[1]
    assert group.relation == "group"
    assert [item.relation for item in group.children] == [
        "additive",
        "additive",
        "additive",
    ]
    assert group.children[2].category == "食品添加剂·护色剂、防腐剂"
    assert group.children[2].evidence_id == "label.ingredients.item.2.3"


def test_additive_explanation_separates_function_from_compliance() -> None:
    response = explain_ingredient_with_evidence(
        IngredientExplanationRequest(
            ingredient={
                "raw_name": "亚硝酸钠",
                "canonical_name": "亚硝酸钠",
                "category": "食品添加剂·护色剂、防腐剂",
                "relation": "additive",
                "evidence_id": "label.ingredients.item.2.1",
            },
            regulatory_evidence=[_gb2760_announcement()],
            jurisdiction="CN",
            applicable_date="2026-08-09",
        )
    )

    assert response.status == "explained"
    assert response.explanation_type == "additive"
    assert response.risk_level == "not_applicable"
    assert response.knowledge_evidence_ids == ["knowledge.additives.cn.v1.亚硝酸钠"]
    assert response.regulatory_evidence_ids == ["reg.cn.gb2760-2024.announcement"]
    assert "仅凭配料表无法判断实际用量" in response.explanation
    assert "安全" not in response.explanation
    assert "有害" not in response.explanation


def test_unknown_name_inside_additive_group_stays_unknown_without_guessing() -> None:
    request = SafetyEvaluationRequest(
        request_id="additive-unknown",
        applicable_date="2026-08-09",
        confirmed_fields={"ingredients": "食品添加剂（神秘粉）"},
        constraints=[{"kind": "allergy", "canonical_value": "milk"}],
    )
    evaluation = evaluate_user_constraints_result(request)
    evidence = attach_regulatory_interpretation(request, evaluation)

    explanation = evidence["interpretations"][0]
    assert explanation["status"] == "unknown"
    assert explanation["explanation_type"] == "additive"
    assert explanation["unknowns"] == ["additive_name_not_in_curated_dictionary"]
    assert evidence["final_status"] == "completed"


def test_workflow_retrieves_current_additive_standard_and_explains_known_name() -> None:
    request = SafetyEvaluationRequest(
        request_id="additive-known",
        applicable_date="2026-08-09",
        confirmed_fields={"ingredients": "猪肉、食品添加剂（亚硝酸钠、卡拉胶）"},
        constraints=[{"kind": "allergy", "canonical_value": "milk"}],
    )
    evaluation = evaluate_user_constraints_result(request)
    evidence = attach_regulatory_interpretation(request, evaluation)

    assert evaluation.overall_risk_level == "compatible"
    assert {
        item["ingredient"]["canonical_name"] for item in evidence["interpretations"]
    } == {
        "亚硝酸钠",
        "卡拉胶",
    }
    assert {item["standard_number"] for item in evidence["regulatory_evidence"]} == {
        "GB 2760-2024"
    }
    assert evidence["final_status"] == "completed"
    assert evidence["status"] == "grounded"


def test_allergen_and_additive_retrieval_keep_both_evidence_tracks() -> None:
    request = SafetyEvaluationRequest(
        request_id="additive-and-allergen",
        applicable_date="2026-08-09",
        confirmed_fields={"ingredients": "乳清蛋白、食品添加剂（亚硝酸钠）"},
        constraints=[{"kind": "allergy", "canonical_value": "milk"}],
    )
    evaluation = evaluate_user_constraints_result(request)
    evidence = attach_regulatory_interpretation(request, evaluation)

    assert evaluation.overall_risk_level == "avoid"
    assert {item["standard_number"] for item in evidence["regulatory_evidence"]} == {
        "GB 7718-2011",
        "GB 2760-2024",
    }
    assert {
        (item["explanation_type"], item["status"])
        for item in evidence["interpretations"]
    } == {
        ("allergen", "explained"),
        ("additive", "explained"),
    }
    assert evidence["status"] == "grounded"


def _gb2760_announcement() -> dict:
    return {
        "source_id": "reg.cn.gb2760-2024.announcement",
        "standard_number": "GB 2760-2024",
        "section": "2024年第1号公告",
        "source_url": "https://www.nhc.gov.cn/sps/c100088/202403/bda120e678df4a49a8beb90852559d7c.shtml",
        "evidence_text": "国家卫生健康委员会发布GB 2760-2024《食品安全国家标准 食品添加剂使用标准》。",
        "content_hash": "a" * 64,
        "authority_level": "A",
        "source_type": "official_announcement",
        "jurisdiction": "CN",
        "effective_from": "2025-02-08",
        "effective_to": None,
    }
