"""Conservative, inspectable parsing of product search requirements."""

from __future__ import annotations

import re

NUTRIENTS = {
    "sugars": ("糖",),
    "sodium": ("钠", "盐"),
    "protein": ("蛋白质", "蛋白"),
    "fat": ("脂肪", "脂"),
    "saturated_fat": ("饱和脂肪",),
    "dietary_fiber": ("膳食纤维", "纤维"),
    "energy": ("热量", "能量", "卡路里"),
}


def parse_product_intent(query: str | None) -> dict:
    text = (query or "").strip()
    goals, warnings = [], []
    # Deliberately do not infer allergies, numerical limits, or clinical goals.
    if re.search(
        r"过敏|不耐受|无麸质|不含.{0,8}(奶|乳|蛋|坚果|花生)|不能吃|忌口", text
    ):
        warnings.append(
            "检索文字中的过敏或禁忌需要在个人限制中确认；请确认后从检索描述中移除该限制。"
        )
    if re.search(
        r"\d\s*(?:g|克|mg|毫克|kcal|千卡|%|％)|无糖|零糖|0糖", text, re.IGNORECASE
    ):
        warnings.append(
            "暂不自动解释数值上限或无糖声称；请使用个人限制中的明确阈值，或改为相对比较。"
        )
    for clause in re.split(r"[，,。；;、\n]", text):
        if re.search(r"不要求|不用|不需要|不在意|无所谓|不必", clause):
            continue
        if re.search(r"不要|不想|不应|不高于|不低于|别", clause) and any(
            alias in clause for aliases in NUTRIENTS.values() for alias in aliases
        ):
            warnings.append(
                "这句营养要求含有否定或边界条件，请改为明确的更高／更低比较，或设置数值限制。"
            )
            continue
        for nutrient, aliases in NUTRIENTS.items():
            if nutrient == "fat" and ("饱和脂肪" in clause or "血脂" in clause):
                continue
            for alias in aliases:
                match = re.search(
                    rf"(?:{alias}.{{0,6}}?(更少|更低|更高|更多|少一点|低一点|高一点|多一点)|((?:低|少|高|多)){alias})",
                    clause,
                )
                if not match:
                    continue
                phrase = match.group(0)
                direction = (
                    "higher"
                    if re.search("高|多", match.group(1) or match.group(2))
                    else "lower"
                )
                goal = {
                    "nutrient": nutrient,
                    "direction": direction,
                    "reference": "current_product"
                    if match.group(1)
                    else "candidate_set",
                    "source_span": phrase,
                }
                if goal not in goals:
                    goals.append(goal)
                break
    for nutrient in NUTRIENTS:
        directions = {g["direction"] for g in goals if g["nutrient"] == nutrient}
        if len(directions) > 1:
            warnings.append("同一营养成分出现相反的比较方向，请明确希望更高还是更低。")
    ready = bool(re.search(r"能直接吃|可以直接吃|开袋即食|即食|无需烹饪|不用煮", text))
    if re.search(r"不要求即食|不需要即食|不要即食", text):
        ready = False
    return {
        "parser": "explicit_rules_v1",
        "status": "needs_clarification" if warnings else "parsed",
        "occasion": "breakfast" if "早餐" in text else None,
        "preparation": "ready_to_eat" if ready else None,
        "nutrition_goals": goals,
        "warnings": warnings,
        "scope": "explicit_comparison_preferences_only",
    }


def intent_focuses(intent: dict) -> list[tuple[str, str]]:
    return list(
        dict.fromkeys(
            (g["nutrient"], g["direction"]) for g in intent["nutrition_goals"]
        )
    )


def evaluate_intent(
    intent: dict, current: dict, candidate: dict, *, description: str = "", conflicts=()
) -> dict:
    checks = []
    if intent["status"] == "needs_clarification":
        return {
            "status": "needs_clarification",
            "checks": [],
            "messages": intent["warnings"],
        }
    for goal in intent["nutrition_goals"]:
        name, direction = goal["nutrient"], goal["direction"]
        value, baseline = candidate.get(name), current.get(name)
        outcome = "matched"
        if name in conflicts:
            outcome = "conflicting_evidence"
        elif value is None:
            outcome = "missing_candidate_value"
        elif goal["reference"] == "current_product":
            if baseline is None:
                outcome = "missing_current_value"
            elif value[1:] != baseline[1:]:
                outcome = "incompatible_basis"
            elif not (
                value[0] < baseline[0]
                if direction == "lower"
                else value[0] > baseline[0]
            ):
                outcome = "not_improved"
        checks.append(
            {**goal, "outcome": outcome, "candidate": value, "current": baseline}
        )
    if intent["preparation"] == "ready_to_eat":
        positive = re.search(
            r"即食|直接食用|开袋即食|ready.to.eat", description, re.IGNORECASE
        )
        negative = re.search(
            r"非即食|不可直接|不能直接|需.{0,4}(煮|烹饪|加热)|煮熟|not ready",
            description,
            re.IGNORECASE,
        )
        checks.append(
            {
                "field": "preparation",
                "outcome": "matched"
                if positive and not negative
                else "preparation_unverified",
            }
        )
    return {
        "status": "matched"
        if all(c["outcome"] == "matched" for c in checks)
        else "unresolved",
        "checks": checks,
        "messages": [],
    }
