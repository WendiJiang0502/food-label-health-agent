"""Product-use inference for automatic alternative discovery."""

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
    "prepared_meal": (
        "预制菜", "自热饭", "自热米饭", "即食米饭", "自热餐", "自热火锅", "便当"
    ),
    "frozen_food": (
        "速冻", "冷冻食品", "速冻水饺", "速冻汤圆", "冰淇淋", "雪糕", "冰棒", "冰棍"
    ),
    "processed_meat": ("肉制品", "香肠", "火腿", "培根", "午餐肉"),
    "seafood": ("水产制品", "鱼罐头", "即食鱼", "即食虾"),
    "sauce_condiment": ("调味品", "酱料", "豆瓣酱", "辣椒酱", "酱油", "生抽", "蚝油"),
    "canned_food": ("罐头", "黄桃罐头", "午餐肉罐头"),
}

CATEGORY_LABELS = {
    "biscuit": "饼干与便携谷物零食",
    "bread": "面包与烘焙主食",
    "breakfast_cereal": "早餐谷物与麦片",
    "instant_noodles": "方便面与速食主食",
    "drink": "直接饮用的饮品",
    "dairy": "牛奶、酸奶与乳制品",
    "snack": "便携零食与脆片",
    "confectionery": "糖果、巧克力与甜食",
    "prepared_meal": "加热即食的成品餐食",
    "frozen_food": "冷冻保存的预包装食品",
    "processed_meat": "即食或烹调肉制品",
    "seafood": "鱼虾等水产制品",
    "sauce_condiment": "烹调或佐餐调味品",
    "canned_food": "常温罐藏食品",
}

# Ordered scopes describe foods that can fill a similar eating occasion. Exact
# category matches always rank first; adjacent categories are a fallback rather
# than being presented as identical products.
SUBSTITUTION_SCOPES = {
    "biscuit": ("biscuit", "snack"),
    "bread": ("bread", "breakfast_cereal"),
    "breakfast_cereal": ("breakfast_cereal", "bread"),
    "instant_noodles": ("instant_noodles", "prepared_meal"),
    "drink": ("drink", "dairy"),
    "dairy": ("dairy", "drink"),
    "snack": ("snack", "biscuit"),
    "confectionery": ("confectionery", "snack"),
    "prepared_meal": ("prepared_meal", "instant_noodles"),
    "frozen_food": ("frozen_food",),
    "processed_meat": ("processed_meat",),
    "seafood": ("seafood", "canned_food"),
    "sauce_condiment": ("sauce_condiment",),
    "canned_food": ("canned_food",),
}

CATEGORY_INGREDIENT_SIGNALS = {
    "biscuit": ("小麦粉", "植物油", "白砂糖", "碳酸氢铵", "碳酸氢钠"),
    "bread": ("小麦粉", "酵母"),
    "breakfast_cereal": ("燕麦片", "谷物片"),
    "instant_noodles": ("小麦粉", "棕榈油", "面饼"),
    "drink": ("水", "果汁"),
    "dairy": ("生牛乳", "乳酸菌", "发酵乳"),
    "snack": ("马铃薯", "玉米", "坚果", "果仁"),
    "confectionery": ("可可脂", "可可液块", "巧克力", "明胶"),
    "processed_meat": ("鸡胸肉", "猪肉", "牛肉", "火腿"),
    "seafood": ("鱼", "虾", "蟹", "贝"),
    "sauce_condiment": ("酱油", "食醋", "豆瓣酱", "蚝油"),
}


def suggest_product_category(confirmed_fields: dict[str, str]) -> dict[str, Any]:
    """Infer the current product's use and return an automatic substitute scope."""

    product_name = str(confirmed_fields.get("product_name") or "").strip()
    supporting_text = " ".join(
        str(confirmed_fields.get(key) or "") for key in ("ingredients", "label_claims")
    )
    text = f"{product_name} {supporting_text}".strip()
    scores: dict[str, int] = {}
    matches: dict[str, list[str]] = {}
    direct_name_matches: dict[str, list[str]] = {}
    for category, terms in CATEGORY_TERMS.items():
        direct = [term for term in terms if term in product_name]
        textual = [term for term in terms if term in text]
        signals = [
            term
            for term in CATEGORY_INGREDIENT_SIGNALS.get(category, ())
            if term in supporting_text
        ]
        direct_name_matches[category] = direct
        matches[category] = list(dict.fromkeys([*textual, *signals]))
        # A longer product-name term is usually more specific than a short
        # ingredient-like term. For example, "牛奶巧克力" is a confectionery
        # product even though "牛奶" also appears in the dairy vocabulary.
        direct_score = sum(5 + min(len(term), 4) for term in direct)
        scores[category] = direct_score + len(textual) * 3 + len(signals)
    ranked = sorted(scores, key=lambda category: (-scores[category], category))
    if not ranked or scores[ranked[0]] < 3:
        return {
            "status": "unknown",
            "category": None,
            "confidence": 0.0,
            "matched_terms": [],
            "requires_confirmation": True,
            "category_label": None,
            "substitute_categories": [],
            "reason": "标签中暂未找到足够的商品用途信息",
        }
    category = ranked[0]
    tied = len(ranked) > 1 and scores[ranked[1]] == scores[category]
    terms = matches[category]
    automatic = not tied and (
        bool(direct_name_matches[category]) or scores[category] >= 4
    )
    confidence = 0.0 if tied else min(0.96, 0.5 + scores[category] * 0.07)
    substitute_categories = list(SUBSTITUTION_SCOPES[category])
    if category == "biscuit" and any(
        term in text for term in ("巧克力", "可可", "夹心", "威化", "快乐河马")
    ):
        substitute_categories.append("confectionery")
    elif category == "confectionery" and any(
        term in text for term in ("威化", "饼干", "谷物脆")
    ):
        substitute_categories.append("biscuit")
    elif category == "canned_food" and "午餐肉" in text:
        substitute_categories.append("processed_meat")
    elif category == "canned_food" and any(term in text for term in ("鱼", "虾")):
        substitute_categories.append("seafood")
    return {
        "status": "ambiguous" if tied else ("automatic" if automatic else "suggested"),
        "category": None if tied else category,
        "confidence": confidence,
        "matched_terms": terms,
        "requires_confirmation": not automatic,
        "category_label": None if tied else CATEGORY_LABELS[category],
        "substitute_categories": [] if tied else substitute_categories,
        "reason": (
            "多个用途同样匹配，需要你确认"
            if tied
            else f"根据标签中的{'、'.join(terms[:3])}识别为{CATEGORY_LABELS[category]}"
        ),
    }
