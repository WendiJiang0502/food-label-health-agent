"""Deterministic structure and validation rules for nutrition-facts tables."""

from __future__ import annotations

import re
from collections import Counter

from .models import NutritionTableData, NutritionValidationIssue

_BASIS = re.compile(r"每?\s*100\s*(?:克|g|毫升|ml)|每\s*份", re.IGNORECASE)
_NUTRIENTS = {
    "能量": ("kj", "千焦"),
    "蛋白质": ("g", "克"),
    "脂肪": ("g", "克"),
    "碳水化合物": ("g", "克"),
    "钠": ("mg", "毫克"),
}
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_AMBIGUOUS_DIGIT = re.compile(r"(?<![A-Za-z])[oOilI](?=\d)|(?<=\d)[oOilI]")


def validate_nutrition_table(rows: list[list[str]]) -> NutritionTableData:
    issues: list[NutritionValidationIssue] = []
    joined = " ".join(cell for row in rows for cell in row)
    if not _BASIS.search(joined):
        issues.append(
            _issue(
                "NUTRITION_BASIS_MISSING",
                "warning",
                "未可靠识别每100克、每100毫升或每份口径",
            )
        )

    seen: Counter[str] = Counter()
    for index, row in enumerate(rows):
        row_text = " ".join(row)
        nutrient = next((name for name in _NUTRIENTS if name in row_text), None)
        if nutrient is None:
            continue
        seen[nutrient] += 1
        values = _NUMBER.findall(row_text)
        if not values:
            issues.append(
                _issue(
                    "NUTRIENT_VALUE_MISSING",
                    "blocking",
                    f"{nutrient} 行未可靠识别数值",
                    index,
                )
            )
        if _AMBIGUOUS_DIGIT.search(row_text):
            issues.append(
                _issue(
                    "AMBIGUOUS_NUMERIC_GLYPH",
                    "blocking",
                    f"{nutrient} 行包含易混淆数字字符，必须人工核对",
                    index,
                )
            )
        if values and float(values[0]) < 0:
            issues.append(
                _issue(
                    "NEGATIVE_NUTRIENT_VALUE",
                    "blocking",
                    f"{nutrient} 数值不能为负数",
                    index,
                )
            )
        expected_units = _NUTRIENTS[nutrient]
        normalized = row_text.lower()
        if values and not any(unit in normalized for unit in expected_units):
            issues.append(
                _issue(
                    "NUTRIENT_UNIT_MISSING",
                    "blocking",
                    f"{nutrient} 行未识别到匹配的单位",
                    index,
                )
            )
        percentages = [
            float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*%", row_text)
        ]
        if any(value > 500 for value in percentages):
            issues.append(
                _issue(
                    "NRV_PERCENT_OUTLIER",
                    "warning",
                    f"{nutrient} 的 NRV% 异常偏高，请核对",
                    index,
                )
            )

    for nutrient, count in seen.items():
        if count > 1:
            issues.append(
                _issue(
                    "DUPLICATE_NUTRIENT_ROW",
                    "warning",
                    f"{nutrient} 出现多行，请确认表格边界",
                )
            )
    return NutritionTableData(rows=rows, issues=issues)


def _issue(
    code: str, severity: str, message: str, row_index: int | None = None
) -> NutritionValidationIssue:
    return NutritionValidationIssue(
        code=code, severity=severity, message=message, row_index=row_index
    )
