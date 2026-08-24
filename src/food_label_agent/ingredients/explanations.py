"""Evidence-constrained deterministic ingredient explanations."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from food_label_agent.domain.types import RiskLevel

from .additives import additive_knowledge
from .allergens import ALLERGEN_CATEGORIES


class IngredientExplanationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingredient: dict
    risk_finding: dict | None = None
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
    explanation_type: str = "allergen"
    knowledge_evidence_ids: list[str] = Field(default_factory=list)
    health_guidance: str | None = None


def explain_ingredient_with_evidence(
    request: IngredientExplanationRequest,
) -> IngredientExplanationResponse:
    """Explain normalized facts without changing the deterministic risk result."""

    ingredient = request.ingredient
    if ingredient.get("relation") in {"additive", "additive_declared"}:
        return _explain_additive(request)
    finding = request.risk_finding or {}
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


def _explain_additive(
    request: IngredientExplanationRequest,
) -> IngredientExplanationResponse:
    ingredient = request.ingredient
    raw_name = str(ingredient.get("raw_name") or ingredient.get("canonical_name") or "")
    knowledge = additive_knowledge(str(ingredient.get("canonical_name") or raw_name))
    label_ids = (
        [str(ingredient.get("evidence_id"))] if ingredient.get("evidence_id") else []
    )
    applicable = [
        item
        for item in request.regulatory_evidence
        if _evidence_is_applicable(
            item,
            jurisdiction=request.jurisdiction,
            applicable_date=request.applicable_date,
        )
        and "GB 2760"
        in f"{item.get('standard_number', '')} {item.get('evidence_text', '')}"
        and _evidence_is_citable(item)
    ][:3]
    citations = [_citation(item) for item in applicable]
    regulatory_ids = [item["source_id"] for item in applicable]
    unknowns: list[str] = []
    if knowledge is None:
        unknowns.append(
            "declared_additive_not_in_function_dictionary"
            if ingredient.get("relation") == "additive_declared"
            else "additive_name_not_in_curated_dictionary"
        )
    if not applicable:
        unknowns.append("additive_standard_evidence_missing")
    if knowledge is None:
        declared = ingredient.get("relation") == "additive_declared"
        explanation = (
            f"标签将“{raw_name}”列在食品添加剂分组中；当前解释词典尚未收录它的功能信息。"
            if declared
            else f"已从标签识别“{raw_name}”，但当前解释词典尚未建立可靠的添加剂名称映射。"
        )
        return IngredientExplanationResponse(
            status="unknown",
            ingredient=_ingredient_identity(ingredient),
            risk_level="not_applicable",
            explanation=explanation,
            label_evidence_ids=label_ids,
            regulatory_evidence_ids=regulatory_ids,
            citations=citations,
            unknowns=unknowns,
            limitations=[
                "词典未收录不等于该名称无效；在补齐可靠来源前，不推测其功能、用量、合规性或健康影响。"
            ],
            explanation_type="additive",
            health_guidance=(
                "当前名称或标准依据尚未确认，暂不能给出“可以放心食用”的结论。"
                "建议先核对包装上的完整名称。"
            ),
        )
    explanation = (
        f"“{raw_name}”属于{knowledge.function_category}。"
        f"{knowledge.plain_language_function}"
    )
    health_guidance = (
        "在该食品类别允许使用，且实际用量符合 GB 2760-2024 的限量或"
        "“按生产需要适量使用”要求时，通常可以放心食用；配料表中出现这个名称"
        "本身不等于有害。配料表不列实际添加量，因此这里不能替厂家核验是否超量。"
        if applicable
        else "已确认它的常见功能，但本次没有取得适用的 GB 2760 标准证据，"
        "暂不能给出“可以放心食用”的结论。"
    )
    return IngredientExplanationResponse(
        status="explained",
        ingredient=_ingredient_identity(ingredient),
        risk_level="not_applicable",
        explanation=explanation,
        label_evidence_ids=label_ids,
        regulatory_evidence_ids=regulatory_ids,
        citations=citations,
        unknowns=unknowns,
        limitations=[
            "功能说明来自可追溯的确定性词典，不代表该添加剂在所有食品中都允许使用。",
            "未核对食品类别、实际用量和 GB 2760 明细表前，不作合规或健康安全结论。",
        ],
        explanation_type="additive",
        knowledge_evidence_ids=[knowledge.evidence_id],
        health_guidance=health_guidance,
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
