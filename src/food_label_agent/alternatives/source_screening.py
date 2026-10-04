"""Query-specific screening of manufacturer facts, separate from label approval."""

from __future__ import annotations

from collections import Counter

from .evidence import (
    OFFICIAL_SOURCE_IDS,
    nutrition_facts,
    official_evidence,
    source_flags,
)
from .ingredient_profile import ingredient_profile
from .ingredient_screening import GAP_LABELS, field_gap_state, ingredient_conflict
from .intent import parse_product_intent

NAMES = {
    "protein": "蛋白质",
    "fat": "脂肪",
    "sugars": "糖",
    "sodium": "钠",
    "energy": "能量",
    "carbohydrate": "碳水化合物",
    "dietary_fiber": "膳食纤维",
    "saturated_fat": "饱和脂肪",
    "calcium": "钙",
}
FOCUS = {
    "blood_sugar": ["sugars", "carbohydrate"],
    "sugar_control": ["sugars"],
    "blood_lipids": ["saturated_fat", "fat"],
    "blood_pressure": ["sodium"],
    "weight": ["energy"],
    "gut": ["dietary_fiber"],
    "child": ["sugars", "sodium"],
}


_facts = nutrition_facts


def screen_official_sources(items, request):
    """Never promotes candidates or treats missing facts as passing constraints."""
    intent = parse_product_intent(request.retrieval_query)
    baseline = _facts({"nutrition_rows": getattr(request, "nutrition_rows", None)})
    output = []
    for item in items:
        if (
            item.get("category") != request.category
            or item.get("region") != request.region
        ):
            continue
        if item.get("source_id") not in OFFICIAL_SOURCE_IDS:
            continue
        if item.get("review_status") in {"rejected", "approved"}:
            continue
        if item.get("candidate_id") in getattr(request, "exclude_product_ids", []):
            continue
        current_name = (
            getattr(request, "confirmed_fields", {}).get("product_name", "").strip()
        )
        if item.get("candidate_id") == getattr(request, "current_product_id", None):
            continue
        if current_name and item.get("display_name", "").strip() == current_name:
            continue
        fields = item.get("extracted_fields", {})
        facts = _facts(fields)
        flags = source_flags(item)
        checks = []

        def check(key, state, reason, value=None, gap=None, checks=checks):
            checks.append(
                {
                    "field": key,
                    "label": NAMES.get(key, key),
                    "status": state,
                    "reason": reason,
                    "value": value,
                    "gap": gap,
                }
            )

        def usable(key, facts=facts, flags=flags, check=check, item=item):
            fact = facts.get(key)
            if flags:
                check(key, "unknown", "；".join(flags), gap="source_review")
            elif not fact:
                check(
                    key,
                    "unknown",
                    GAP_LABELS[field_gap_state(item, key)],
                    gap="nutrition_field",
                )
            else:
                return fact
            return None

        for c in request.constraints:
            key = c.canonical_value
            if c.kind != "nutrition_limit":
                conflict = ingredient_conflict(fields, c) if not flags else None
                if conflict:
                    check(key, "not_matched", conflict["reason"])
                    checks[-1].update(
                        reason_code=conflict["reason_code"],
                        matched_text=conflict["matched_text"],
                    )
                    continue
                check(
                    key,
                    "unknown",
                    "；".join(flags)
                    if flags
                    else "未确认明确冲突；"
                    + GAP_LABELS[field_gap_state(item, key)]
                    + "，不能认定符合",
                    gap="packaging_review",
                )
                continue
            f = usable(key)
            if f:
                if f.unit != c.unit or f.basis != c.basis:
                    check(key, "unknown", "单位或计量口径不一致")
                else:
                    check(
                        key,
                        "matched" if f.value <= c.threshold else "not_matched",
                        f"官网数值 {f.value:g}{f.unit}，上限 {c.threshold:g}{c.unit}（{f.basis}）",
                        {"amount": f.value, "unit": f.unit, "basis": f.basis},
                    )
        if intent["warnings"]:
            check("检索要求", "unknown", "；".join(intent["warnings"]))
        for goal in intent["nutrition_goals"]:
            key = goal["nutrient"]
            f = usable(key)
            if not f:
                continue
            b = baseline.get(key)
            if goal["reference"] != "current_product" or not b:
                check(
                    key, "unknown", "已有官网数值，但需要原商品数值才能确认更高或更低"
                )
            elif (f.unit, f.basis) != (b.unit, b.basis):
                check(key, "unknown", "原商品与候选的单位或口径不同")
            else:
                passed = (
                    f.value < b.value
                    if goal["direction"] == "lower"
                    else f.value > b.value
                )
                check(
                    key,
                    "matched" if passed else "not_matched",
                    f"官网 {f.value:g}{f.unit}，原商品 {b.value:g}{b.unit}（{f.basis}）",
                )
        for concern in request.health_concerns:
            for key in FOCUS.get(concern, [concern]):
                f = usable(key)
                if f:
                    check(
                        key, "unknown", "相关数值已有；健康关注尚未转换为明确比较条件"
                    )
        if intent["preparation"] or intent["occasion"]:
            check("用途", "unknown", "即食或早餐用途仍需核实")
        for result in checks:
            if result.get("gap"):
                result["gap_state"] = field_gap_state(
                    item, result["field"], flagged=bool(flags)
                )
            result["reason"] = (
                result["reason"]
                .replace("per_100g", "每100克")
                .replace("per_100ml", "每100毫升")
                .replace("per_serving", "每份")
            )
        states = {c["status"] for c in checks}
        status = (
            "not_matched"
            if "not_matched" in states
            else "unknown"
            if "unknown" in states
            else "matched"
            if checks
            else "not_evaluated"
        )
        output.append(
            {
                "candidate_id": item["candidate_id"],
                "evidence": official_evidence(item),
                "source_fingerprint": item.get("source_fingerprint", "unknown"),
                "display_name": item["display_name"],
                "source_url": item.get("source_url"),
                "specification": item.get("specification"),
                "status": status,
                "checks": checks,
                "ingredient_profile": ingredient_profile(item),
                "source_quality_flags": flags,
                "available_nutrients": [NAMES.get(k, k) for k in facts],
                "identity_status": "specification_available"
                if item.get("specification")
                else "specification_missing",
                "recommendation_eligible": False,
                "evidence_level": "manufacturer_page_unverified_package",
            }
        )
    order = {"matched": 0, "unknown": 1, "not_evaluated": 2, "not_matched": 3}
    output.sort(key=lambda x: order[x["status"]])
    return {
        "scope": "official_source_preliminary_screening",
        "total": len(output),
        "counts": dict(Counter(x["status"] for x in output)),
        "items": output,
        "notice": "按官网资料初步筛选；符合仅指本次列出的条件，包装版本与商品身份仍需核实，不等于已审核推荐。",
    }
