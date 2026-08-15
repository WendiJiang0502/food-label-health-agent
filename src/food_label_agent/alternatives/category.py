"""Conservative category suggestions from confirmed label facts."""

from __future__ import annotations

from typing import Any

CATEGORY_TERMS = {
    "biscuit": ("饼干", "薄脆", "威化", "曲奇", "苏打饼"),
    "bread": ("面包", "吐司", "欧包", "餐包"),
    "breakfast_cereal": ("早餐谷物", "麦片", "燕麦片", "玉米片"),
    "instant_noodles": ("方便面", "即食面", "速食面", "杯面"),
    "drink": ("饮料", "果汁", "植物蛋白饮品", "含乳饮料", "豆奶", "燕麦奶"),
    "dairy": ("乳制品", "纯牛奶", "牛奶", "酸奶", "奶酪", "黄油", "稀奶油"),
    "snack": ("薯片", "锅巴", "虾条", "爆米花", "膨化食品", "坚果", "果仁", "瓜子"),
    "confectionery": ("糖果", "巧克力", "软糖", "硬糖", "果冻"),
    "prepared_meal": ("预制菜", "自热饭", "自热火锅", "便当"),
    "frozen_food": ("速冻", "冷冻食品", "速冻水饺", "速冻汤圆"),
    "processed_meat": ("肉制品", "香肠", "火腿", "培根", "午餐肉"),
    "seafood": ("水产制品", "鱼罐头", "即食鱼", "即食虾"),
    "sauce_condiment": ("调味品", "酱料", "豆瓣酱", "辣椒酱", "酱油", "生抽", "蚝油"),
    "canned_food": ("罐头", "黄桃罐头", "午餐肉罐头"),
}


def suggest_product_category(confirmed_fields: dict[str, str]) -> dict[str, Any]:
    """Suggest, but never silently decide, a supported same-category scope."""

    product_name = str(confirmed_fields.get("product_name") or "").strip()
    text = product_name or " ".join(
        str(confirmed_fields.get(key) or "")
        for key in ("ingredients", "label_claims")
    )
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
