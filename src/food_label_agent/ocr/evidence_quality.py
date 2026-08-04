"""Post-OCR completeness checks that never ask an LLM to repair evidence."""

from __future__ import annotations

import re
from itertools import pairwise

from .models import OCREvidenceIssue, OCREvidenceReport, OCRFieldResult

_NON_INGREDIENT_SECTION = re.compile(
    r"生产日期|保质期|贮存条件|储存条件|产品标准|执行标准|生产商|制造商|厂址|净含量"
)


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
        if len(text) < 8:
            issues.append(
                _issue(
                    "INGREDIENT_SECTION_TOO_SHORT",
                    "blocking",
                    "配料内容异常短，可能存在漏行",
                    "ingredients",
                )
            )
        if _NON_INGREDIENT_SECTION.search(text):
            issues.append(
                _issue(
                    "INGREDIENT_BOUNDARY_CONTAMINATED",
                    "blocking",
                    "配料字段混入了生产或包装信息",
                    "ingredients",
                )
            )
        if _has_unbalanced_brackets(text):
            issues.append(
                _issue(
                    "INGREDIENT_BRACKET_MISMATCH",
                    "blocking",
                    "配料括号不完整，可能存在缺失文字",
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

    status = "passed"
    if any(issue.severity == "blocking" for issue in issues):
        status = "needs_confirmation"
    elif issues:
        status = "review_recommended"
    return OCREvidenceReport(status=status, issues=issues)


def _has_unbalanced_brackets(value: str) -> bool:
    return value.count("（") + value.count("(") != value.count("）") + value.count(")")


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


def _issue(
    code: str, severity: str, message: str, field_name: str
) -> OCREvidenceIssue:
    return OCREvidenceIssue(
        code=code,
        severity=severity,
        message=message,
        field_name=field_name,
    )
