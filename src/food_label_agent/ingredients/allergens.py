"""China-focused, deterministic allergen rules for confirmed label facts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from food_label_agent.domain.models import RiskFinding, UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel

from .normalization import IngredientNode, NormalizedLabel

RULESET_METADATA = {
    "id": "cn_prepackaged_allergens_v1",
    "jurisdiction": "CN",
    "categories": 8,
    "references": [
        {
            "standard": "GB 7718-2011",
            "role": "current_labeling_reference",
            "effective_to": "2027-03-15",
        },
        {
            "standard": "GB 7718-2025",
            "role": "published_successor",
            "effective_from": "2027-03-16",
        },
    ],
    "scope_note": "用于个人约束的保守安全匹配，不代替标签合规审查。",
}


@dataclass(frozen=True, slots=True)
class AllergenCategory:
    key: str
    label: str
    aliases: tuple[str, ...]
    ambiguous_terms: tuple[str, ...] = ()


ALLERGEN_CATEGORIES: dict[str, AllergenCategory] = {
    "gluten": AllergenCategory(
        "gluten",
        "含麸质谷物及其制品",
        (
            "斯佩耳特小麦",
            "全麦粉",
            "小麦粉",
            "小麦",
            "黑麦",
            "大麦",
            "燕麦",
            "麸质",
            "谷朵粉",
            "麦芽",
        ),
        ("麦芽糊精", "麦香风味"),
    ),
    "crustacean": AllergenCategory(
        "crustacean",
        "甲壳纲类动物及其制品",
        ("龙虾", "虾粉", "南极磷虾", "虾", "蟹"),
        ("鲜味料",),
    ),
    "fish": AllergenCategory(
        "fish", "鱼类及其制品", ("鱼粉", "鱼露", "鱼油", "鱼"), ("鱼味香精",)
    ),
    "egg": AllergenCategory(
        "egg",
        "蛋类及其制品",
        ("鸡蛋", "蛋清", "蛋黄", "蛋白粉", "蛋黄酱", "蛋类"),
        ("蛋香风味",),
    ),
    "peanut": AllergenCategory(
        "peanut", "花生及其制品", ("花生酱", "花生粉", "花生"), ("花生香精",)
    ),
    "soy": AllergenCategory(
        "soy",
        "大豆及其制品",
        ("大豆分离蛋白", "大豆蛋白", "大豆卵磷脂", "大豆", "黄豆", "豆粉"),
        ("植物蛋白", "植物卵磷脂"),
    ),
    "milk": AllergenCategory(
        "milk",
        "乳及乳制品",
        (
            "酪蛋白酸钠",
            "乳清蛋白",
            "全脂乳粉",
            "脱脂乳粉",
            "乳清粉",
            "酪蛋白",
            "乳清",
            "牛奶",
            "奶粉",
            "乳粉",
            "酸奶",
            "发酵乳",
            "奶油",
            "黄油",
            "干酪",
            "酸酪",
            "乳糖",
            "乳制品",
        ),
        ("奶味香精", "乳酸", "硬脂酰乳酸钠"),
    ),
    "tree_nut": AllergenCategory(
        "tree_nut",
        "坚果及其果仁类制品",
        (
            "夏威夷果",
            "开心果",
            "扁桃仁",
            "核桃仁",
            "碧根果",
            "坚果",
            "核桃",
            "杏仁",
            "腰果",
            "榛子",
        ),
        ("坚果风味",),
    ),
}

_PRECAUTION_CUES = re.compile(
    r"可能含有|可能含|可能带入|同一生产线|本生产线|同线生产|共用生产线|本生产设备|同一设备|也加工"
)


def evaluate_constraints(
    normalized: NormalizedLabel,
    constraints: list[UserConstraint],
    *,
    allergen_statement: str = "",
    ingredients_confirmed: bool = True,
) -> list[RiskFinding]:
    """Return exactly one deterministic finding for every supported constraint."""

    return [
        _evaluate_one(
            normalized,
            constraint,
            allergen_statement=allergen_statement,
            ingredients_confirmed=ingredients_confirmed,
        )
        for constraint in constraints
    ]


def _evaluate_one(
    normalized: NormalizedLabel,
    constraint: UserConstraint,
    *,
    allergen_statement: str,
    ingredients_confirmed: bool,
) -> RiskFinding:
    key = constraint.canonical_value
    category = ALLERGEN_CATEGORIES.get(key)
    if constraint.kind is not ConstraintKind.ALLERGY or category is None:
        return RiskFinding(
            risk_level=RiskLevel.UNKNOWN,
            constraint=key,
            matched_text=key,
            reason_code="UNSUPPORTED_CONSTRAINT",
            explanation="当前确定性规则尚不支持这项约束，不能据此作出肯定结论。",
            evidence_ids=("user.constraints",),
        )
    if not ingredients_confirmed:
        return RiskFinding(
            risk_level=RiskLevel.UNKNOWN,
            constraint=key,
            matched_text="未确认的配料表",
            reason_code="LABEL_NOT_CONFIRMED",
            explanation="配料表尚未由用户确认，不能生成肯定的风险结论。",
            evidence_ids=("label.ingredients",),
        )
    if normalized.requires_confirmation:
        issue = normalized.issues[0]
        return RiskFinding(
            risk_level=RiskLevel.UNKNOWN,
            constraint=key,
            matched_text=issue.source_span or "配料表括号",
            reason_code="INGREDIENT_PARSE_UNCERTAIN",
            explanation=issue.message,
            evidence_ids=("label.ingredients",),
        )

    direct = next(
        (item for item in normalized.iter_ingredients() if key in item.allergen_keys),
        None,
    )
    if direct is not None:
        reason = (
            "DIRECT_ALLERGEN_INGREDIENT"
            if direct.relation == "direct"
            else "DIRECT_ALLERGEN_DERIVATIVE"
        )
        return RiskFinding(
            risk_level=RiskLevel.AVOID,
            constraint=key,
            matched_text=direct.raw_name,
            reason_code=reason,
            explanation=f"配料表中明确出现{category.label}来源成分{direct.raw_name}。",
            evidence_ids=(direct.evidence_id,),
        )

    statement_match = _find_statement_term(allergen_statement, category.aliases)
    if statement_match:
        matched_term, precaution = statement_match
        return RiskFinding(
            risk_level=RiskLevel.CAUTION if precaution else RiskLevel.AVOID,
            constraint=key,
            matched_text=matched_term,
            reason_code=(
                "PRECAUTIONARY_ALLERGEN_STATEMENT"
                if precaution
                else "DECLARED_ALLERGEN_STATEMENT"
            ),
            explanation=(
                f"包装提示可能存在{category.label}来源成分{matched_term}。"
                if precaution
                else f"过敏原提示中明确标示{category.label}来源成分{matched_term}。"
            ),
            evidence_ids=("label.allergen_statement",),
        )

    ambiguous = _find_ambiguous(normalized, category)
    if ambiguous:
        return RiskFinding(
            risk_level=RiskLevel.UNKNOWN,
            constraint=key,
            matched_text=ambiguous.raw_name,
            reason_code="AMBIGUOUS_INGREDIENT_NAME",
            explanation=f"配料名称“{ambiguous.raw_name}”不足以确定是否来源于{category.label}，需要厂家或官方资料确认。",
            evidence_ids=(ambiguous.evidence_id,),
        )

    return RiskFinding(
        risk_level=RiskLevel.COMPATIBLE,
        constraint=key,
        matched_text="已确认配料表",
        reason_code="NO_CONFLICT_IN_CONFIRMED_LABEL",
        explanation=f"在当前已确认标签范围内未发现{category.label}相关成分；这不等于绝对安全。",
        evidence_ids=("label.ingredients",),
    )


def _find_ambiguous(
    normalized: NormalizedLabel, category: AllergenCategory
) -> IngredientNode | None:
    for item in normalized.iter_ingredients():
        compact = re.sub(r"\s+", "", item.raw_name)
        if any(term in compact for term in category.ambiguous_terms):
            return item
    return None


def _find_statement_term(text: str, terms: tuple[str, ...]) -> tuple[str, bool] | None:
    # Precaution cues only apply to their own punctuation-delimited clause.
    # This prevents "含有小麦，可能含有花生" from weakening the wheat
    # declaration to caution.
    for clause in re.split(r"[,，;；。]", text):
        compact = re.sub(r"\s+", "", clause)
        for term in sorted(terms, key=len, reverse=True):
            if term in compact:
                return term, bool(_PRECAUTION_CUES.search(compact))
    return None
