"""Deterministic Chinese food-label field parser over OCR lines."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import OCRSettings
from .models import BoundingBox, OCRFieldResult, OCRLineEvidence

_SECTION_STOP = re.compile(
    r"过敏原|致敏|可能含有|本品含有|本产品含有|营养成分|贮存|储存|保质期|生产日期|生产商|制造商|执行标准|产品标准"
)
_INGREDIENT_HEADING = re.compile(r"(?:配料(?:表)?|原料)\s*[:：]?\s*(.*)")
_ALLERGEN_CUE = re.compile(
    r"过敏原|致敏|可能含有|本品含有|本产品含有|含有(?:麸质|乳|蛋|花生|大豆|坚果|鱼|虾|蟹)"
)
_NUTRITION_BASIS = re.compile(
    r"每\s*100\s*(?:克|g|毫升|ml)|每\s*份|营养成分表|营养标示",
    re.IGNORECASE,
)
_CLAIM_CUE = re.compile(
    r"(?:无|零|0)\s*(?:糖|蔗糖|添加|脂肪)|低\s*(?:糖|脂|钠)|高\s*(?:蛋白|纤维|钙)|无麸质|不添加",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    confidence: float
    bounding_box: BoundingBox | None = None


def parse_food_label_fields(
    lines: list[OCRLine], settings: OCRSettings
) -> list[OCRFieldResult]:
    ingredient_lines = _ingredient_lines(lines)
    ingredient_section_found = bool(ingredient_lines)
    allergen_lines = [line for line in lines if _ALLERGEN_CUE.search(line.text)]
    nutrition_lines = [line for line in lines if _NUTRITION_BASIS.search(line.text)]
    claim_lines = [line for line in lines if _CLAIM_CUE.search(line.text)]

    fields = [
        _field(
            name="ingredients" if ingredient_section_found else "unclassified_text",
            label=(
                "配料表（请核对范围）"
                if ingredient_section_found
                else "未定位到配料表"
            ),
            lines=ingredient_lines if ingredient_section_found else lines,
            threshold=settings.general_threshold,
            force_confirmation=True,
            confidence_ceiling=0.84 if ingredient_section_found else 0.50,
        )
    ]
    if allergen_lines:
        fields.append(
            _field(
                name="allergen_statement",
                label="过敏原提示",
                lines=allergen_lines,
                threshold=settings.allergen_threshold,
                force_confirmation=False,
            )
        )
    if nutrition_lines:
        fields.append(
            _field(
                name="nutrition_basis",
                label="营养标示口径",
                lines=nutrition_lines,
                threshold=settings.general_threshold,
                force_confirmation=False,
            )
        )
    if claim_lines:
        fields.append(
            _field(
                name="label_claims",
                label="包装声称",
                lines=claim_lines,
                threshold=settings.general_threshold,
                force_confirmation=True,
                confidence_ceiling=0.84,
            )
        )
    return fields


def _ingredient_lines(lines: list[OCRLine]) -> list[OCRLine]:
    for index, line in enumerate(lines):
        match = _INGREDIENT_HEADING.search(line.text)
        if not match:
            continue
        selected: list[OCRLine] = []
        inline_text = match.group(1).strip()
        if inline_text:
            selected.append(OCRLine(inline_text, line.confidence, line.bounding_box))
        for following in lines[index + 1 : index + 9]:
            if _SECTION_STOP.search(following.text) or _ALLERGEN_CUE.search(
                following.text
            ):
                break
            selected.append(following)
        return selected
    return []


def _field(
    *,
    name: str,
    label: str,
    lines: list[OCRLine],
    threshold: float,
    force_confirmation: bool,
    confidence_ceiling: float | None = None,
) -> OCRFieldResult:
    confidence = sum(line.confidence for line in lines) / len(lines)
    if confidence_ceiling is not None:
        confidence = min(confidence, confidence_ceiling)
    return OCRFieldResult(
        name=name,
        label=label,
        raw_text="\n".join(line.text for line in lines),
        confidence=confidence,
        requires_confirmation=force_confirmation or confidence < threshold,
        bounding_box=_union_box(lines),
        evidence_lines=[
            OCRLineEvidence(
                text=line.text,
                confidence=line.confidence,
                bounding_box=line.bounding_box,
            )
            for line in lines
        ],
    )


def _union_box(lines: list[OCRLine]) -> BoundingBox | None:
    boxes = [line.bounding_box for line in lines if line.bounding_box is not None]
    if not boxes:
        return None
    left = min(box.x for box in boxes)
    top = min(box.y for box in boxes)
    right = max(box.x + box.width for box in boxes)
    bottom = max(box.y + box.height for box in boxes)
    return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)
