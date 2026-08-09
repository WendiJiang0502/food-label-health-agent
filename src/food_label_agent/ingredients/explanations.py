"""Evidence-constrained deterministic ingredient explanations."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from food_label_agent.domain.types import RiskLevel

from .allergens import ALLERGEN_CATEGORIES


class IngredientExplanationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingredient: dict
    risk_finding: dict
    regulatory_evidence: list[dict] = Field(default_factory=list, max_length=20)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    applicable_date: date


class IngredientExplanationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    ingredient: dict
    risk_level: str
    explanation: str | None
    label_evidence_ids: list[str]
    regulatory_evidence_ids: list[str]
    citations: list[dict]
    unknowns: list[str]
    limitations: list[str]


def explain_ingredient_with_evidence(
    request: IngredientExplanationRequest,
) -> IngredientExplanationResponse:
    """Explain normalized facts without changing the deterministic risk result."""

    ingredient = request.ingredient
    finding = request.risk_finding
    risk_level = RiskLevel(finding["risk_level"])
    label_evidence_ids = list(finding.get("evidence_ids", []))
    applicable_evidence = [
        item
        for item in request.regulatory_evidence
        if _evidence_is_applicable(
            item,
            jurisdiction=request.jurisdiction,
            applicable_date=request.applicable_date,
        )
    ]
    citable_evidence = [
        item
        for item in applicable_evidence
        if _evidence_is_citable(item) and _evidence_supports_finding(item, finding)
    ][:3]
    regulatory_ids = [item["source_id"] for item in citable_evidence]
    citations = [_citation(item) for item in citable_evidence]
    unknowns: list[str] = []

    if not citable_evidence:
        unknowns.append("ingredient_explanation_missing_regulatory_evidence")
    if ingredient.get("normalization_method") == "unresolved":
        unknowns.append("ingredient_name_unresolved")
    constraint = str(finding.get("constraint", ""))
    category = ALLERGEN_CATEGORIES.get(constraint)
    ingredient_keys = set(ingredient.get("allergen_keys", []))
    relation = ingredient.get("relation", "ingredient")
    if category is None:
        unknowns.append("unsupported_constraint_for_explanation")
    elif constraint not in ingredient_keys and relation != "declared_statement":
        unknowns.append("ingredient_constraint_mapping_unverified")

    if unknowns:
        return IngredientExplanationResponse(
            status="unknown",
            ingredient=_ingredient_identity(ingredient),
            risk_level=risk_level.value,
            explanation=None,
            label_evidence_ids=label_evidence_ids,
            regulatory_evidence_ids=regulatory_ids,
            citations=citations,
            unknowns=list(dict.fromkeys(unknowns)),
            limitations=["证据不足时不对配料来源、用途或合规性作出推测。"],
        )

    raw_name = str(ingredient.get("raw_name") or ingredient.get("canonical_name"))
    if relation in {"derivative", "regulated_derivative"}:
        fact = f"“{raw_name}”在已确认标签中被识别为{category.label}来源的衍生配料。"
    elif relation == "declared_statement":
        fact = f"“{raw_name}”出现在包装的致敏物质提示中，对应{category.label}。"
    else:
        fact = f"“{raw_name}”在已确认标签中被识别为{category.label}的明确配料。"
    risk_text = {
        RiskLevel.AVOID: "它已明确命中用户的过敏回避约束，应保持避免结论。",
        RiskLevel.CAUTION: "包装信息表明可能存在该致敏物质，需要谨慎确认。",
        RiskLevel.UNKNOWN: "当前证据不足以生成肯定的安全结论。",
        RiskLevel.COMPATIBLE: "当前已确认标签中未发现相关冲突，但不代表绝对安全。",
    }[risk_level]
    return IngredientExplanationResponse(
        status="explained",
        ingredient=_ingredient_identity(ingredient),
        risk_level=risk_level.value,
        explanation=f"{fact}{risk_text}",
        label_evidence_ids=label_evidence_ids,
        regulatory_evidence_ids=regulatory_ids,
        citations=citations,
        unknowns=[],
        limitations=[
            "本解释仅基于已确认标签、当前过敏原词典和指定日期适用的官方证据。",
            "不构成医疗诊断或治疗建议。",
        ],
    )


def _ingredient_identity(ingredient: dict) -> dict:
    return {
        key: ingredient.get(key)
        for key in (
            "raw_name",
            "canonical_name",
            "category",
            "relation",
            "evidence_id",
        )
    }


def _evidence_is_applicable(
    evidence: dict, *, jurisdiction: str, applicable_date: date
) -> bool:
    if evidence.get("jurisdiction") != jurisdiction:
        return False
    start_value = evidence.get("effective_from")
    if not start_value:
        return False
    start = date.fromisoformat(start_value)
    end_value = evidence.get("effective_to")
    end = date.fromisoformat(end_value) if end_value else None
    return start <= applicable_date and (end is None or applicable_date <= end)


def _evidence_is_citable(evidence: dict) -> bool:
    required = (
        "source_id",
        "standard_number",
        "section",
        "source_url",
        "evidence_text",
        "content_hash",
    )
    if evidence.get("authority_level") != "A" or not all(
        evidence.get(key) for key in required
    ):
        return False
    return not (
        evidence.get("source_type") == "official_standard"
        and evidence.get("page_start") is None
    )


def _evidence_supports_finding(evidence: dict, finding: dict) -> bool:
    section = str(evidence.get("section", ""))
    if section.replace(" ", "") in {"前言", "引言"}:
        return False
    text = f"{section} {evidence.get('evidence_text', '')}"
    allergen_markers = ("致敏物质", "过敏原", "过敏反应")
    if not any(marker in text for marker in allergen_markers):
        return False
    reason_code = str(finding.get("reason_code", ""))
    if "PRECAUTIONARY" in reason_code:
        precautionary_markers = ("可能含有", "预防性", "生产线", "带入")
        return any(marker in text for marker in precautionary_markers)
    return True


def _citation(evidence: dict) -> dict:
    evidence_text = " ".join(str(evidence["evidence_text"]).split())
    return {
        "evidence_id": evidence["source_id"],
        "standard_number": evidence["standard_number"],
        "section": evidence["section"],
        "source_url": evidence["source_url"],
        "page_start": evidence.get("page_start"),
        "page_end": evidence.get("page_end"),
        "content_hash": evidence["content_hash"],
        "evidence_excerpt": evidence_text[:360],
    }
