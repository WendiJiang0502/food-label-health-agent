"""Deterministic Chinese label-claim semantics and cross-field checks."""

from __future__ import annotations

import re
from datetime import date
from math import isfinite

from .models import (
    ClaimConsistencyRequest,
    ClaimConsistencyResponse,
    ClaimInterpretationRequest,
    ClaimInterpretationResponse,
    ClaimType,
)

_CLAIM_ALIASES: tuple[tuple[ClaimType, tuple[str, ...]], ...] = (
    (ClaimType.NO_ADDED_SUCROSE, ("不添加蔗糖", "未添加蔗糖", "无添加蔗糖")),
    (ClaimType.NO_ADDED_SUGAR, ("不添加糖", "未添加糖", "无添加糖")),
    (ClaimType.NO_SUCROSE, ("0蔗糖", "零蔗糖", "无蔗糖")),
    (ClaimType.SUGAR_FREE, ("100%不含糖", "0g糖", "0糖", "零糖", "无糖", "不含糖")),
    (ClaimType.LOW_SUGAR, ("低糖",)),
)

_DISPLAY_NAMES = {
    ClaimType.SUGAR_FREE: "无糖",
    ClaimType.LOW_SUGAR: "低糖",
    ClaimType.NO_SUCROSE: "无蔗糖",
    ClaimType.NO_ADDED_SUGAR: "不添加糖",
    ClaimType.NO_ADDED_SUCROSE: "不添加蔗糖",
    ClaimType.UNKNOWN: "未识别声称",
}

_MEANINGS = {
    ClaimType.SUGAR_FREE: "这是糖含量声称；现行标准要求糖含量不超过 0.5 g/100 g（固体）或 100 mL（液体）。",
    ClaimType.LOW_SUGAR: "这是糖含量声称；现行标准要求糖含量不超过 5 g/100 g（固体）或 100 mL（液体）。",
    ClaimType.NO_SUCROSE: "它只指向蔗糖，不等同于无糖；产品仍可能含葡萄糖、果糖、乳糖等其他糖。",
    ClaimType.NO_ADDED_SUGAR: "它描述生产时未主动添加糖，不等同于成品无糖；原料仍可能天然含糖。",
    ClaimType.NO_ADDED_SUCROSE: "它只描述未主动添加蔗糖，不等同于无糖，也不排除添加其他糖。",
    ClaimType.UNKNOWN: "当前词典无法确定该包装声称的规范含义。",
}

_SUCROSE_INGREDIENTS = ("白砂糖", "蔗糖", "赤砂糖", "红糖", "冰糖", "绵白糖")
_ADDED_SUGAR_INGREDIENTS = (
    *_SUCROSE_INGREDIENTS,
    "葡萄糖",
    "果糖",
    "麦芽糖",
    "蜂蜜",
    "糖浆",
    "果葡糖浆",
    "玉米糖浆",
    "葡萄糖浆",
    "麦芽糖浆",
)


def interpret_claim(
    request: ClaimInterpretationRequest,
) -> ClaimInterpretationResponse:
    """Normalize claims and explain only what each claim actually establishes."""

    normalized = _extract_claims(request.claim_text)
    applicable = [
        item
        for item in request.regulatory_evidence
        if _evidence_is_applicable(item, request.jurisdiction, request.applicable_date)
    ]
    claims: list[dict] = []
    unknowns: list[str] = []
    for index, (raw_text, claim_type) in enumerate(normalized, start=1):
        evidence = _supporting_evidence(applicable, claim_type)
        needs_threshold_evidence = claim_type in {
            ClaimType.SUGAR_FREE,
            ClaimType.LOW_SUGAR,
        }
        item_unknowns: list[str] = []
        status = "interpreted"
        if claim_type is ClaimType.UNKNOWN:
            status = "unknown"
            item_unknowns.append("unrecognized_label_claim")
        elif needs_threshold_evidence and not evidence:
            status = "unknown"
            item_unknowns.append("claim_interpretation_missing_regulatory_evidence")
        elif claim_type in {
            ClaimType.NO_SUCROSE,
            ClaimType.NO_ADDED_SUGAR,
            ClaimType.NO_ADDED_SUCROSE,
        }:
            item_unknowns.append(
                "regulatory_compliance_not_established_by_semantic_interpretation"
            )
        citations = [_citation(item) for item in evidence[:3]]
        claims.append(
            {
                "status": status,
                "raw_text": raw_text,
                "canonical_type": claim_type.value,
                "canonical_name": _DISPLAY_NAMES[claim_type],
                "meaning": _MEANINGS[claim_type] if status != "unknown" else None,
                "label_evidence_ids": [f"label.claims.item.{index}"],
                "regulatory_evidence_ids": [item["source_id"] for item in evidence[:3]],
                "citations": citations,
                "unknowns": item_unknowns,
                "limitations": _limitations(claim_type),
            }
        )
        unknowns.extend(item_unknowns)
    return ClaimInterpretationResponse(
        status=(
            "interpreted"
            if claims and all(c["status"] == "interpreted" for c in claims)
            else "unknown"
        ),
        claims=claims,
        unknowns=list(dict.fromkeys(unknowns)),
    )


def verify_claim_consistency(
    request: ClaimConsistencyRequest,
) -> ClaimConsistencyResponse:
    """Cross-check normalized claims against confirmed ingredients and nutrition."""

    findings = [_verify_one(claim, request) for claim in request.claims]
    unknowns = [
        unknown for finding in findings for unknown in finding.get("unknowns", [])
    ]
    statuses = {finding["status"] for finding in findings}
    if "inconsistent" in statuses:
        status = "inconsistent"
    elif "unknown" in statuses:
        status = "unknown"
    else:
        status = "checked"
    return ClaimConsistencyResponse(
        status=status,
        findings=findings,
        unknowns=list(dict.fromkeys(unknowns)),
    )


def _extract_claims(text: str) -> list[tuple[str, ClaimType]]:
    compact = re.sub(r"\s+", "", text)
    matches: list[tuple[int, int, str, ClaimType]] = []
    for claim_type, aliases in _CLAIM_ALIASES:
        for alias in aliases:
            for match in re.finditer(re.escape(alias), compact, flags=re.IGNORECASE):
                matches.append((match.start(), match.end(), match.group(), claim_type))
    selected: list[tuple[int, int, str, ClaimType]] = []
    for candidate in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if any(
            candidate[0] < end and candidate[1] > start for start, end, _, _ in selected
        ):
            continue
        selected.append(candidate)
    selected.sort(key=lambda item: item[0])
    if not selected:
        return [(text.strip(), ClaimType.UNKNOWN)]
    return [(raw, claim_type) for _, _, raw, claim_type in selected]


def _verify_one(claim: dict, request: ClaimConsistencyRequest) -> dict:
    try:
        claim_type = ClaimType(claim.get("canonical_type", ClaimType.UNKNOWN))
    except ValueError:
        claim_type = ClaimType.UNKNOWN
    label_ids = list(claim.get("label_evidence_ids", []))
    base = {
        "claim_type": claim_type.value,
        "claim_text": claim.get("raw_text"),
        "label_evidence_ids": label_ids,
        "regulatory_evidence_ids": list(claim.get("regulatory_evidence_ids", [])),
        "matched_text": None,
        "unknowns": [],
        "limitations": _limitations(claim_type),
    }
    if claim_type in {ClaimType.SUGAR_FREE, ClaimType.LOW_SUGAR}:
        return {**base, **_verify_sugar_threshold(claim_type, request.nutrition_values)}
    if claim_type in {
        ClaimType.NO_SUCROSE,
        ClaimType.NO_ADDED_SUCROSE,
        ClaimType.NO_ADDED_SUGAR,
    }:
        if not request.ingredients_text:
            return {
                **base,
                "status": "unknown",
                "reason_code": "INGREDIENTS_NOT_CONFIRMED",
                "explanation": "缺少已确认配料表，无法检查包装声称与配料是否冲突。",
                "unknowns": ["ingredients_not_confirmed_for_claim_check"],
            }
        candidates = (
            _ADDED_SUGAR_INGREDIENTS
            if claim_type is ClaimType.NO_ADDED_SUGAR
            else _SUCROSE_INGREDIENTS
        )
        matched = _first_ingredient_match(request.ingredients_text, candidates)
        if matched:
            return {
                **base,
                "status": "inconsistent",
                "reason_code": "CLAIM_CONTRADICTED_BY_INGREDIENT",
                "matched_text": matched,
                "explanation": f"已确认配料表出现“{matched}”，与“{claim.get('raw_text')}”声称存在直接冲突。",
            }
        explanation = "已确认配料表中未发现与该声称直接冲突的配料名称；这不是实验室含量或合规证明。"
        if claim_type in {ClaimType.NO_SUCROSE, ClaimType.NO_ADDED_SUCROSE}:
            other = _first_ingredient_match(
                request.ingredients_text,
                tuple(
                    item
                    for item in _ADDED_SUGAR_INGREDIENTS
                    if item not in _SUCROSE_INGREDIENTS
                ),
            )
            if other:
                explanation += f"但配料表含“{other}”，因此不能据此理解为无糖。"
        return {
            **base,
            "status": "not_contradicted",
            "reason_code": "NO_DIRECT_INGREDIENT_CONTRADICTION_FOUND",
            "matched_text": None,
            "explanation": explanation,
        }
    return {
        **base,
        "status": "unknown",
        "reason_code": "UNSUPPORTED_CLAIM",
        "explanation": "当前规则尚不支持这一包装声称。",
        "unknowns": ["unsupported_label_claim"],
    }


def _verify_sugar_threshold(claim_type: ClaimType, values: dict) -> dict:
    basis = str(values.get("basis", "")).lower()
    value = values.get("sugars_g")
    if value is None:
        if "sugars_g_per_100g" in values:
            value, basis = values["sugars_g_per_100g"], "per_100g"
        elif "sugars_g_per_100ml" in values:
            value, basis = values["sugars_g_per_100ml"], "per_100ml"
    if value is None or basis not in {"per_100g", "per_100ml", "100g", "100ml"}:
        return {
            "status": "unknown",
            "reason_code": "SUGAR_VALUE_OR_BASIS_MISSING",
            "explanation": "缺少已确认的糖含量或每 100 g/100 mL 计量口径，不能验证该声称。",
            "unknowns": ["confirmed_sugar_value_or_basis_missing"],
        }
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return {
            "status": "unknown",
            "reason_code": "SUGAR_VALUE_INVALID",
            "explanation": "糖含量无法解析为有效数值，不能验证该声称。",
            "unknowns": ["confirmed_sugar_value_invalid"],
        }
    if not isfinite(numeric) or numeric < 0:
        return {
            "status": "unknown",
            "reason_code": "SUGAR_VALUE_INVALID",
            "explanation": "糖含量不是有效的非负有限数值，不能验证该声称。",
            "unknowns": ["confirmed_sugar_value_invalid"],
        }
    threshold = 0.5 if claim_type is ClaimType.SUGAR_FREE else 5.0
    unit = "g/100 g" if "g" in basis and "ml" not in basis else "g/100 mL"
    if numeric <= threshold:
        return {
            "status": "consistent",
            "reason_code": "SUGAR_THRESHOLD_MET",
            "explanation": f"已确认糖含量为 {numeric:g} {unit}，不超过 {threshold:g} {unit} 的声称阈值。",
            "measured_value": numeric,
            "threshold": threshold,
            "basis": basis,
        }
    return {
        "status": "inconsistent",
        "reason_code": "SUGAR_THRESHOLD_EXCEEDED",
        "explanation": f"已确认糖含量为 {numeric:g} {unit}，超过 {threshold:g} {unit} 的声称阈值。",
        "measured_value": numeric,
        "threshold": threshold,
        "basis": basis,
    }


def _first_ingredient_match(text: str, candidates: tuple[str, ...]) -> str | None:
    compact = re.sub(r"\s+", "", text)
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate in compact:
            return candidate
    return None


def _supporting_evidence(evidence: list[dict], claim_type: ClaimType) -> list[dict]:
    if claim_type not in {ClaimType.SUGAR_FREE, ClaimType.LOW_SUGAR}:
        return []
    markers = (
        ("无或不含糖", "0.5") if claim_type is ClaimType.SUGAR_FREE else ("低糖", "5 g")
    )
    return [
        item
        for item in evidence
        if item.get("authority_level") == "A"
        and all(
            item.get(key)
            for key in (
                "source_id",
                "standard_number",
                "section",
                "source_url",
                "evidence_text",
                "content_hash",
            )
        )
        and all(
            marker in f"{item.get('section', '')} {item.get('evidence_text', '')}"
            for marker in markers
        )
    ]


def _evidence_is_applicable(
    evidence: dict, jurisdiction: str, applicable_date: date
) -> bool:
    if evidence.get("jurisdiction") != jurisdiction or not evidence.get(
        "effective_from"
    ):
        return False
    try:
        start = date.fromisoformat(evidence["effective_from"])
        end = (
            date.fromisoformat(evidence["effective_to"])
            if evidence.get("effective_to")
            else None
        )
    except ValueError:
        return False
    return start <= applicable_date and (end is None or applicable_date <= end)


def _citation(evidence: dict) -> dict:
    text = " ".join(str(evidence["evidence_text"]).split())
    return {
        "evidence_id": evidence["source_id"],
        "standard_number": evidence["standard_number"],
        "section": evidence["section"],
        "source_url": evidence["source_url"],
        "page_start": evidence.get("page_start"),
        "page_end": evidence.get("page_end"),
        "content_hash": evidence["content_hash"],
        "evidence_excerpt": text[:360],
    }


def _limitations(claim_type: ClaimType) -> list[str]:
    common = ["一致性检查仅基于用户确认的标签文字，不替代实验室检测或监管认定。"]
    if claim_type in {ClaimType.NO_SUCROSE, ClaimType.NO_ADDED_SUCROSE}:
        return ["无蔗糖或不添加蔗糖不等于无糖。", *common]
    if claim_type is ClaimType.NO_ADDED_SUGAR:
        return ["不添加糖不等于成品不含天然糖。", *common]
    if claim_type is ClaimType.SUGAR_FREE:
        return ["无糖不等于适合所有糖尿病患者。", *common]
    return common
