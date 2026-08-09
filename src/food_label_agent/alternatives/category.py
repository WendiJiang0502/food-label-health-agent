"""Conservative category suggestions from confirmed label facts."""

from __future__ import annotations

from typing import Any

CATEGORY_TERMS = {
    "biscuit": ("饼干", "薄脆", "威化", "曲奇", "苏打饼", "小麦粉"),
    "drink": ("饮料", "果汁", "植物蛋白饮品", "含乳饮料", "牛乳", "水"),
    "processed_meat": ("肉制品", "香肠", "火腿", "培根", "午餐肉", "鸡肉", "猪肉"),
}


def suggest_product_category(confirmed_fields: dict[str, str]) -> dict[str, Any]:
    """Suggest, but never silently decide, a supported same-category scope."""

    text = " ".join(confirmed_fields.values())
    matches = {
        category: [term for term in terms if term in text]
        for category, terms in CATEGORY_TERMS.items()
    }
    ranked = sorted(matches.items(), key=lambda item: (-len(item[1]), item[0]))
    if not ranked or not ranked[0][1]:
        return {
            "status": "unknown",
            "category": None,
            "confidence": 0.0,
            "matched_terms": [],
            "requires_confirmation": True,
        }
    category, terms = ranked[0]
    tied = len(ranked) > 1 and len(ranked[1][1]) == len(terms)
    return {
        "status": "ambiguous" if tied else "suggested",
        "category": None if tied else category,
        "confidence": 0.0 if tied else min(0.95, 0.55 + 0.15 * len(terms)),
        "matched_terms": terms,
        "requires_confirmation": True,
    }
