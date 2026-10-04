"""Query-specific screening of manufacturer facts, separate from label approval."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime

from food_label_agent.nutrition.normalization import normalize_nutrition_facts

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


def _facts(fields):
    parsed = normalize_nutrition_facts(
        None,
        basis_text=fields.get("nutrition_basis_text"),
        rows=fields.get("nutrition_rows"),
    )
    if not parsed or parsed.requires_confirmation:
        return {}
    counts = Counter(f.canonical_name for f in parsed.nutrients)
    return {
        f.canonical_name: f
        for f in parsed.nutrients
        if counts[f.canonical_name] == 1 and "菊粉" not in f.raw_name
    }


def screen_official_sources(items, request):
    """Never promotes candidates or treats missing facts as passing constraints."""
    today = datetime.now(UTC).date()
    intent = parse_product_intent(request.retrieval_query)
    baseline = _facts({"nutrition_rows": getattr(request, "nutrition_rows", None)})
    output = []
    for item in items:
        if (
            item.get("category") != request.category
            or item.get("region") != request.region
        ):
            continue
        if item.get("source_id") not in {
            "simplelove-public-products",
            "quaker-instant-oats",
            "quaker-snack-cereal",
        }:
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
        flags = list(item.get("source_quality_flags", []))
        try:
            seen = date.fromisoformat(item.get("last_seen_at", "")[:10])
            if not 0 <= (today - seen).days <= 35:
                flags.append("官网资料超过复查周期或日期异常")
        except ValueError:
            flags.append("官网资料日期缺失")
        if item.get("review_status") == "change_detected":
            flags.append("来源变化待核实")
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

        def usable(key, facts=facts, flags=flags, check=check):
            fact = facts.get(key)
            if flags:
                check(key, "unknown", "；".join(flags), gap="source_review")
            elif not fact:
                check(
                    key,
                    "unknown",
                    "缺少可比数值或计量口径待核实",
                    gap="nutrition_field",
                )
            else:
                return fact
            return None

        for c in request.constraints:
            key = c.canonical_value
            if c.kind != "nutrition_limit":
                check(
                    key,
                    "unknown",
                    "配料及过敏原等限制仍需对应包装证据复核",
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
                "source_fingerprint": item.get("source_fingerprint", "unknown"),
                "display_name": item["display_name"],
                "source_url": item.get("source_url"),
                "specification": item.get("specification"),
                "status": status,
                "checks": checks,
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
