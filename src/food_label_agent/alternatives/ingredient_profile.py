"""Positive-only ingredient evidence derived from the exact source text."""

from food_label_agent.ingredients.normalization import normalize_ingredients

GROUPS = {
    "sugar_ingredients": {
        "白砂糖",
        "白糖",
        "蔗糖",
        "食用葡萄糖",
        "葡萄糖",
        "果糖",
        "果葡糖浆",
        "葡萄糖浆",
        "蜂蜜",
        "赤砂糖",
        "冰糖",
        "焦糖糖浆",
    },
    "polyols": {"赤藓糖醇", "麦芽糖醇", "木糖醇", "山梨糖醇", "异麦芽酮糖醇"},
    "sweeteners": {"甜菊糖苷", "三氯蔗糖", "阿斯巴甜", "安赛蜜", "罗汉果甜苷"},
    "fiber_ingredients": {"菊粉", "抗性糊精", "低聚半乳糖", "低聚果糖", "聚葡萄糖"},
    "milk_sources": {
        "生牛乳",
        "生牛奶",
        "牛乳",
        "牛奶",
        "乳清蛋白粉",
        "乳清蛋白",
        "浓缩牛奶蛋白",
        "乳粉",
        "全脂乳粉",
        "脱脂乳粉",
        "稀奶油",
        "奶油",
        "加糖炼乳",
        "干酪",
    },
    "egg_sources": {"蛋黄粉", "蛋黄液", "冰蛋制品", "蛋清", "鸡蛋", "蛋白粉"},
}


def ingredient_profile(item):
    text = item.get("extracted_fields", {}).get("ingredients_text") or ""
    parsed = normalize_ingredients(text)
    uncertain = bool(item.get("source_quality_flags")) or parsed.requires_confirmation
    observations = []
    for node in parsed.iter_ingredients():
        for group, terms in GROUPS.items():
            if node.raw_name in terms or node.canonical_name in terms:
                observations.append(
                    {
                        "group": group,
                        "ingredient": node.raw_name,
                        "evidence_id": node.evidence_id,
                        "source_span": node.source_span,
                        "source_url": item.get("source_url"),
                        "source_fingerprint": item.get("source_fingerprint"),
                        "status": "needs_review" if uncertain else "source_declared",
                    }
                )
    return {
        "schema": "positive_ingredient_evidence_v1",
        "status": "missing"
        if not text
        else "needs_review"
        if uncertain
        else "source_text_available",
        "observations": observations,
        "negative_claims_supported": False,
        "total_sugars_inferred": False,
        "note": "仅表示来源配料中出现的成分；不代表总糖含量、添加量或未出现成分绝对不存在。",
    }
