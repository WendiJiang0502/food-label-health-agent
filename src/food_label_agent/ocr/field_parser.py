"""Deterministic Chinese food-label field parser over OCR lines."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .config import OCRSettings
from .models import BoundingBox, OCRFieldResult, OCRLineEvidence

_SECTION_STOP = re.compile(
    r"过敏原|致敏|可能含有|本品含有|本产品含有|营养成分|贮存|储存|保质期|生产日期|"
    r"生产商|制造商|经销商|委托商|地址|电话|执行标准|产品标准|产品类型|质量等级|"
    r"质量指标|食用方法|适宜人群|不适宜人群|生产许可证|净含量|主料含量|温馨提示|"
    r"Manufactured"
)
_INGREDIENT_HEADING = re.compile(
    r"^[\s·•:：,，;；]*(?:配料(?:表)?|原材料(?:名)?|原料)\s*[:：]?\s*(.*)"
)
_DEGRADED_INGREDIENT_HEADING = re.compile(
    r"^[\s·•:：,，;；]*配(?=(?:小麦粉|大米|水[、,，]|牛肉|鸡|猪|马铃薯|白砂糖|燕麦))"
)
_ALLERGEN_CUE = re.compile(
    r"过敏原|致敏|可能含有|本品含有|本产品含有|含有(?:麸质|乳|蛋|花生|大豆|坚果|鱼|虾|蟹)"
    r"|甲壳类动物制品"
)
_NUTRITION_BASIS = re.compile(
    r"每\s*(?:100\s*(?:克|g|毫升|ml)|份(?:\s*\d+(?:\.\d+)?\s*(?:克|g|毫升|ml))?)",
    re.IGNORECASE,
)
_CLAIM_CUE = re.compile(
    r"(?:无|零|0)\s*(?:糖|蔗糖|添加|脂肪)|低\s*(?:糖|脂|钠)|高\s*(?:蛋白|纤维|钙)|无麸质|不添加",
    re.IGNORECASE,
)
_SPECIFICATION_LINE = re.compile(
    r"(?:≥|≤|mg/kg|g/100g|以干基计|指标要求|理化指标)", re.IGNORECASE
)
_NON_INGREDIENT_VALUE = re.compile(
    r"^(?:项目|营养素参考值|NRV%?|能量|蛋白质|脂肪|反式脂肪酸|"
    r"碳水化合物|钠|钙|糖|膳食纤维|\d+(?:\.\d+)?\s*(?:kJ|千焦|g|克|mg|毫克|%)?)$",
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
    nutrition_lines = _unique_lines(
        extracted for line in lines for extracted in _nutrition_basis_lines(line)
    )
    claim_lines = [line for line in lines if _CLAIM_CUE.search(line.text)]

    fields = [
        (
            _field(
                name="ingredients",
                label="配料表（请核对范围）",
                lines=ingredient_lines,
                threshold=settings.general_threshold,
                force_confirmation=True,
                confidence_ceiling=0.84,
            )
            if ingredient_section_found
            else _missing_ingredients_field()
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
        inline = _ingredient_heading_value(line.text)
        if inline is None:
            continue
        if line.bounding_box is not None:
            return _spatial_ingredient_lines(lines, index, inline)
        return _sequential_ingredient_lines(lines, index, inline)
    return []


def _sequential_ingredient_lines(
    lines: list[OCRLine], heading_index: int, inline: str
) -> list[OCRLine]:
    heading = lines[heading_index]
    selected: list[OCRLine] = []
    inline_text = _ingredient_prefix(inline)
    if inline_text:
        selected.append(OCRLine(inline_text, heading.confidence, heading.bounding_box))
    for following in lines[heading_index + 1 : heading_index + 17]:
        if (
            _ingredient_heading_value(following.text) is not None
            or _ALLERGEN_CUE.search(following.text)
            or _SPECIFICATION_LINE.search(following.text)
        ):
            break
        if selected and not _is_spatial_continuation(selected[-1], following):
            break
        stop = _SECTION_STOP.search(following.text)
        cleaned = _clean_ingredient_text(
            following.text[: stop.start()] if stop else following.text
        )
        if cleaned:
            selected.append(
                OCRLine(cleaned, following.confidence, following.bounding_box)
            )
        if stop:
            break
    return selected


def _spatial_ingredient_lines(
    lines: list[OCRLine], heading_index: int, inline: str
) -> list[OCRLine]:
    """Recover an ingredient region from OCR boxes, independent of API line order."""

    heading = lines[heading_index]
    box = heading.bounding_box
    assert box is not None
    line_height = max(box.height, 0.015)
    min_x = max(0.0, box.x - 0.22)
    min_y = max(0.0, box.y - (0.012 if _ingredient_prefix(inline) else 0.055))
    max_y = min(1.0, box.y + 0.30)

    parallel_boundaries = [
        candidate.bounding_box.x
        for candidate in lines
        if candidate.bounding_box is not None
        and candidate.bounding_box.x > box.x + 0.20
        and abs(candidate.bounding_box.y - box.y) <= 0.10
        and _is_section_boundary(candidate.text)
    ]
    blocked_right_start = min(parallel_boundaries, default=1.02)

    lower_boundaries = [
        candidate
        for candidate in lines
        if candidate.bounding_box is not None
        and candidate.bounding_box.y >= box.y - 0.01
        and candidate.bounding_box.y <= max_y
        and candidate.bounding_box.x >= min_x
        and candidate.bounding_box.x < blocked_right_start
        and _is_section_boundary(candidate.text)
    ]
    stop_line = min(
        lower_boundaries,
        key=lambda candidate: candidate.bounding_box.y,  # type: ignore[union-attr]
        default=None,
    )
    stop_y = stop_line.bounding_box.y if stop_line and stop_line.bounding_box else max_y
    stop_right = (
        stop_line.bounding_box.x + stop_line.bounding_box.width
        if stop_line and stop_line.bounding_box
        else 1.0
    )
    trailing_margin = 0.03

    candidates: list[OCRLine] = []
    for index, candidate in enumerate(lines):
        candidate_box = candidate.bounding_box
        if candidate_box is None or index == heading_index:
            continue
        if not (min_x <= candidate_box.x < blocked_right_start):
            continue
        if not (min_y <= candidate_box.y <= min(max_y, stop_y + trailing_margin)):
            continue
        if candidate_box.y > stop_y and candidate_box.x <= stop_right + 0.10:
            continue
        if _is_section_boundary(candidate.text) or _is_non_ingredient_line(
            candidate.text
        ):
            continue
        cleaned = _ingredient_prefix(candidate.text)
        if cleaned:
            candidates.append(OCRLine(cleaned, candidate.confidence, candidate_box))

    tolerance = max(0.025, line_height * 1.5)
    candidates.sort(
        key=lambda candidate: (
            round(candidate.bounding_box.y / tolerance) * tolerance,  # type: ignore[union-attr]
            candidate.bounding_box.x,  # type: ignore[union-attr]
        )
    )
    selected: list[OCRLine] = []
    inline_text = _ingredient_prefix(inline)
    if inline_text:
        selected.append(OCRLine(inline_text, heading.confidence, heading.bounding_box))
    return _unique_lines([*selected, *candidates])


def _ingredient_heading_value(text: str) -> str | None:
    match = _INGREDIENT_HEADING.search(text)
    if match:
        return match.group(1)
    degraded = _DEGRADED_INGREDIENT_HEADING.search(text)
    if degraded:
        return text[degraded.end() :]
    return None


def _is_section_boundary(text: str) -> bool:
    return bool(_SECTION_STOP.search(text) or _ALLERGEN_CUE.search(text))


def _is_non_ingredient_line(text: str) -> bool:
    normalized = re.sub(r"[\s:：]", "", text)
    return bool(
        _NON_INGREDIENT_VALUE.fullmatch(normalized)
        or _SPECIFICATION_LINE.search(text)
        or re.fullmatch(r"[\d./%\-年月日]+", normalized)
        or normalized == "第、"
        or normalized in {"(油炸方便面)", "（油炸方便面）"}
    )


def _clean_ingredient_text(value: str) -> str:
    cleaned = re.sub(r"^[\s·•:：,，;；]+", "", value).strip()
    return re.sub(r"^料[，,、]?每?\s*(?=食品添加剂)", "", cleaned)


def _ingredient_prefix(value: str) -> str:
    stop = _SECTION_STOP.search(value)
    return _clean_ingredient_text(value[: stop.start()] if stop else value)


def _missing_ingredients_field() -> OCRFieldResult:
    return OCRFieldResult(
        name="ingredients",
        label="配料表（未识别，请手动补充）",
        raw_text="",
        confidence=0.0,
        requires_confirmation=True,
    )


def _nutrition_basis_lines(line: OCRLine) -> list[OCRLine]:
    return [
        OCRLine(
            text=re.sub(r"\s+", "", match.group(0)),
            confidence=line.confidence,
            bounding_box=line.bounding_box,
        )
        for match in _NUTRITION_BASIS.finditer(line.text)
    ]


def _is_spatial_continuation(previous: OCRLine, current: OCRLine) -> bool:
    if previous.bounding_box is None or current.bounding_box is None:
        return True
    previous_box = previous.bounding_box
    current_box = current.bounding_box
    vertical_gap = current_box.y - (previous_box.y + previous_box.height)
    max_gap = max(previous_box.height, current_box.height) * 2
    horizontal_overlap = max(
        0.0,
        min(previous_box.x + previous_box.width, current_box.x + current_box.width)
        - max(previous_box.x, current_box.x),
    )
    overlap_ratio = horizontal_overlap / min(previous_box.width, current_box.width)
    same_column = overlap_ratio >= 0.2 or abs(previous_box.x - current_box.x) <= 0.15
    return -0.02 <= vertical_gap <= max_gap and same_column


def _unique_lines(lines: Iterable[OCRLine]) -> list[OCRLine]:
    selected: dict[str, OCRLine] = {}
    for line in lines:
        key = re.sub(r"\s+", "", line.text).lower()
        current = selected.get(key)
        if current is None or line.confidence > current.confidence:
            selected[key] = line
    return list(selected.values())


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
