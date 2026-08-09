"""Post-OCR completeness checks that never ask an LLM to repair evidence."""

from __future__ import annotations

import re
from itertools import pairwise

from .models import OCREvidenceIssue, OCREvidenceReport, OCRFieldResult
from .nutrition_coordinates import has_complete_core_nutrition_table

_NON_INGREDIENT_SECTION = re.compile(
    r"生产日期|保质期|贮存条件|储存条件|产品标准|执行标准|生产商|制造商|经销商|"
    r"厂址|地址|净含量|主料含量|产品类型|质量等级|质量指标|食用方法|适宜人群|"
    r"生产许可证|营养成分|温馨提示"
)
_INGREDIENT_DELIMITER = re.compile(r"[、,，;；]")


def assess_ocr_evidence(fields: list[OCRFieldResult]) -> OCREvidenceReport:
    indexed = {field.name: field for field in fields}
    issues: list[OCREvidenceIssue] = []
    ingredients = indexed.get("ingredients")

    if ingredients is None:
        issues.append(
            _issue(
                "INGREDIENT_HEADING_NOT_FOUND",
                "blocking",
                "未可靠定位配料表标题，不能把包装全文作为配料事实",
                "ingredients",
            )
        )
    else:
        text = ingredients.raw_text.strip()
        if not text:
            issues.append(
                _issue(
                    "INGREDIENT_TEXT_MISSING",
                    "blocking",
                    "未可靠识别配料表内容，请重新拍摄或手动补充",
                    "ingredients",
                )
            )
        elif len(text) < 2:
            issues.append(
                _issue(
                    "INGREDIENT_SECTION_TOO_SHORT",
                    "blocking",
                    "配料内容异常短，可能存在漏行",
                    "ingredients",
                )
            )
        if text and _NON_INGREDIENT_SECTION.search(text):
            issues.append(
                _issue(
                    "INGREDIENT_BOUNDARY_CONTAMINATED",
                    "blocking",
                    "配料字段混入了生产或包装信息",
                    "ingredients",
                )
            )
        if text and _has_unbalanced_brackets(text):
            issues.append(
                _issue(
                    "INGREDIENT_BRACKET_MISMATCH",
                    "blocking",
                    "配料括号不完整，可能存在缺失文字",
                    "ingredients",
                )
            )
        if text and _looks_truncated(text):
            issues.append(
                _issue(
                    "INGREDIENT_TEXT_SUSPECTED_TRUNCATION",
                    "blocking",
                    "配料文字疑似在分隔符或残缺词处中断，必须对照原图补全",
                    "ingredients",
                )
            )
        if _has_fragmented_geometry(ingredients):
            issues.append(
                _issue(
                    "INGREDIENT_LINES_FRAGMENTED",
                    "warning",
                    "配料文字行间距异常，请核对是否漏行",
                    "ingredients",
                )
            )

    if "nutrition_basis" in indexed and "nutrition_table" not in indexed:
        issues.append(
            _issue(
                "NUTRITION_TABLE_NOT_STRUCTURED",
                "blocking",
                "检测到营养标示口径，但未可靠恢复营养素与数值对应关系",
                "nutrition_table",
            )
        )
    elif (
        "nutrition_basis" in indexed or "nutrition_table" in indexed
    ) and not has_complete_core_nutrition_table(indexed.get("nutrition_table")):
        issues.append(
            _issue(
                "NUTRITION_CORE_FIELDS_INCOMPLETE",
                "blocking",
                "营养成分表未完整恢复能量、蛋白质、脂肪、碳水化合物和钠的数值与单位",
                "nutrition_table",
            )
        )

    status = "passed"
    if any(issue.severity == "blocking" for issue in issues):
        status = "needs_confirmation"
    elif issues:
        status = "review_recommended"
    return OCREvidenceReport(status=status, issues=issues)


def _has_unbalanced_brackets(value: str) -> bool:
    return value.count("（") + value.count("(") != value.count("）") + value.count(")")


def _looks_truncated(value: str) -> bool:
    normalized = value.rstrip()
    if normalized.endswith(("、", ",", "，", ";", "；")):
        return True
    segments = [segment.strip() for segment in _INGREDIENT_DELIMITER.split(normalized)]
    return len(segments) > 1 and len(segments[-1]) == 1


def _has_fragmented_geometry(field: OCRFieldResult) -> bool:
    lines = [line for line in field.evidence_lines if line.bounding_box is not None]
    for previous, current in pairwise(lines):
        assert previous.bounding_box is not None
        assert current.bounding_box is not None
        previous_bottom = previous.bounding_box.y + previous.bounding_box.height
        gap = current.bounding_box.y - previous_bottom
        expected_height = max(previous.bounding_box.height, current.bounding_box.height)
        if gap > expected_height * 1.75:
            return True
    return False


def _issue(code: str, severity: str, message: str, field_name: str) -> OCREvidenceIssue:
    return OCREvidenceIssue(
        code=code,
        severity=severity,
        message=message,
        field_name=field_name,
    )
