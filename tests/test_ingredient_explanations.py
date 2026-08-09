from __future__ import annotations

from food_label_agent.ingredients.explanations import (
    IngredientExplanationRequest,
    explain_ingredient_with_evidence,
)


def whey() -> dict:
    return {
        "raw_name": "乳清蛋白",
        "canonical_name": "乳清蛋白",
        "category": "乳及乳制品",
        "relation": "derivative",
        "allergen_keys": ["milk"],
        "normalization_method": "dictionary_exact",
        "evidence_id": "label.ingredients.item.2",
    }


def avoid_finding() -> dict:
    return {
        "risk_level": "avoid",
        "constraint": "milk",
        "matched_text": "乳清蛋白",
        "reason_code": "DIRECT_ALLERGEN_DERIVATIVE",
        "explanation": "配料表中明确出现乳来源成分。",
        "evidence_ids": ["label.ingredients.item.2"],
    }


def regulation(*, effective_from: str = "2012-04-20") -> dict:
    return {
        "source_id": "reg.cn.gb7718-2011.4.4.3.1.allergens",
        "standard_number": "GB 7718-2011",
        "section": "4.4.3.1 致敏物质",
        "source_url": "https://www.nhc.gov.cn/example/gb7718.pdf",
        "evidence_text": "乳及乳制品作为配料时宜使用易辨识名称标示。",
        "content_hash": "a" * 64,
        "authority_level": "A",
        "page_start": 7,
        "page_end": 7,
        "jurisdiction": "CN",
        "effective_from": effective_from,
        "effective_to": "2027-03-15" if effective_from < "2027" else None,
    }


def test_explanation_preserves_avoid_and_binds_both_evidence_types() -> None:
    result = explain_ingredient_with_evidence(
        IngredientExplanationRequest(
            ingredient=whey(),
            risk_finding=avoid_finding(),
            regulatory_evidence=[regulation()],
            jurisdiction="CN",
            applicable_date="2026-08-09",
        )
    )

    assert result.status == "explained"
    assert result.risk_level == "avoid"
    assert result.label_evidence_ids == ["label.ingredients.item.2"]
    assert result.regulatory_evidence_ids == ["reg.cn.gb7718-2011.4.4.3.1.allergens"]
    assert result.citations[0]["section"] == "4.4.3.1 致敏物质"
    assert result.citations[0]["page_start"] == 7
    assert "衍生配料" in result.explanation
    assert "保持避免结论" in result.explanation


def test_future_regulation_is_not_used_for_current_explanation() -> None:
    result = explain_ingredient_with_evidence(
        IngredientExplanationRequest(
            ingredient=whey(),
            risk_finding=avoid_finding(),
            regulatory_evidence=[regulation(effective_from="2027-03-16")],
            jurisdiction="CN",
            applicable_date="2026-08-09",
        )
    )

    assert result.status == "unknown"
    assert result.explanation is None
    assert result.risk_level == "avoid"
    assert "ingredient_explanation_missing_regulatory_evidence" in result.unknowns


def test_unresolved_ingredient_remains_unknown_even_with_regulation() -> None:
    ingredient = {
        **whey(),
        "raw_name": "奶味香精",
        "canonical_name": "奶味香精",
        "normalization_method": "unresolved",
        "allergen_keys": [],
    }
    result = explain_ingredient_with_evidence(
        IngredientExplanationRequest(
            ingredient=ingredient,
            risk_finding={**avoid_finding(), "risk_level": "unknown"},
            regulatory_evidence=[regulation()],
            jurisdiction="CN",
            applicable_date="2026-08-09",
        )
    )

    assert result.status == "unknown"
    assert result.risk_level == "unknown"
    assert "ingredient_name_unresolved" in result.unknowns


def test_unrelated_regulation_cannot_ground_allergen_explanation() -> None:
    unrelated = {
        **regulation(),
        "section": "4.1 营养成分表",
        "evidence_text": "营养成分表应标示能量和核心营养素。",
    }

    result = explain_ingredient_with_evidence(
        IngredientExplanationRequest(
            ingredient=whey(),
            risk_finding=avoid_finding(),
            regulatory_evidence=[unrelated],
            jurisdiction="CN",
            applicable_date="2026-08-09",
        )
    )

    assert result.status == "unknown"
    assert result.citations == []
    assert "ingredient_explanation_missing_regulatory_evidence" in result.unknowns
