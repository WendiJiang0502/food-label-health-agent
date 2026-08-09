"""Recover nutrition rows from OCR text and geometry when table layout is missed."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .field_parser import OCRLine
from .models import BoundingBox, OCRFieldResult, OCRLineEvidence
from .nutrition import validate_nutrition_table

_NUTRIENTS = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠", "钙")
_CORE_NUTRIENTS = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠")
_EXPECTED_UNITS = {
    "能量": ("千焦", "kj"),
    "蛋白质": ("克", "g"),
    "脂肪": ("克", "g"),
    "碳水化合物": ("克", "g"),
    "钠": ("毫克", "mg"),
    "钙": ("毫克", "mg"),
}
_VALUE = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*(千焦|kJ|克|g|毫克|mg)\s*$", re.IGNORECASE
)
_NUMBER_ONLY = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*$")
_UNIT_ONLY = re.compile(r"^\s*(千焦|kJ|克|g|毫克|mg)\s*$", re.IGNORECASE)
_INLINE_ROW = re.compile(
    r"(能量|蛋白质|脂肪|碳水化合物|钠|钙).*?"
    r"(-?\d+(?:\.\d+)?)\s*(千焦|kJ|克|g|毫克|mg)",
    re.IGNORECASE,
)
_BASIS = re.compile(r"每\s*100\s*(?:克|g|毫升|ml)|每\s*份", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _Pair:
    label: OCRLine
    value: OCRLine
    score: float


def extract_coordinate_nutrition_table(
    lines: list[OCRLine],
) -> OCRFieldResult | None:
    labels = [
        line
        for line in lines
        if _normalize(line.text) in _NUTRIENTS and line.bounding_box is not None
    ]
    values = _expanded_values(lines)
    inline_pairs = _inline_pairs(lines)
    label_ranks = _rank_by_family(labels)
    value_ranks = _rank_by_family(values)
    values = [line for line in values if line.bounding_box is not None]
    candidates: list[tuple[float, float, str, int, _Pair]] = []
    for label in labels:
        nutrient = _normalize(label.text)
        for value_index, value in enumerate(values):
            if not _has_expected_unit(nutrient, value.text):
                continue
            pair = _pair(label, value)
            if pair is not None:
                order_penalty = abs(
                    label_ranks[(nutrient, id(label))]
                    - value_ranks[(_unit_family(value.text), id(value))]
                )
                candidates.append(
                    (
                        pair.score + order_penalty * 1.5,
                        -_pair_confidence(pair),
                        nutrient,
                        value_index,
                        pair,
                    )
                )

    pairs: dict[str, _Pair] = dict(inline_pairs)
    used_values: set[int] = set()
    for _, _, nutrient, value_index, pair in sorted(
        candidates, key=lambda candidate: (candidate[0], candidate[1])
    ):
        if nutrient in pairs or value_index in used_values:
            continue
        pairs[nutrient] = pair
        used_values.add(value_index)

    if len(pairs) < 2:
        return None
    basis = max(
        (line for line in lines if _BASIS.search(line.text)),
        key=lambda line: line.confidence,
        default=None,
    )
    rows = [["项目", basis.text if basis else "口径待确认"]]
    selected_lines: list[OCRLine] = []
    if basis:
        selected_lines.append(basis)
    for nutrient in _NUTRIENTS:
        pair = pairs.get(nutrient)
        if pair is None:
            continue
        rows.append([nutrient, pair.value.text])
        selected_lines.extend([pair.label, pair.value])

    table = validate_nutrition_table(rows)
    confidence = sum(line.confidence for line in selected_lines) / len(selected_lines)
    return OCRFieldResult(
        name="nutrition_table",
        label="营养成分表（请逐项核对）",
        raw_text="\n".join("\t".join(row) for row in rows),
        confidence=min(confidence, 0.84),
        requires_confirmation=True,
        bounding_box=_union_box(selected_lines),
        evidence_lines=[
            OCRLineEvidence(
                text=line.text,
                confidence=line.confidence,
                bounding_box=line.bounding_box,
            )
            for line in selected_lines
        ],
        nutrition_table=table,
    )


def _expanded_values(lines: list[OCRLine]) -> list[OCRLine]:
    values = [
        line
        for line in lines
        if _VALUE.fullmatch(line.text) and line.bounding_box is not None
    ]
    unit_lines = [
        line
        for line in lines
        if _UNIT_ONLY.fullmatch(line.text) and line.bounding_box is not None
    ]
    for number in lines:
        if not _NUMBER_ONLY.fullmatch(number.text) or number.bounding_box is None:
            continue
        best_unit = min(
            (
                unit
                for unit in unit_lines
                if _same_row(number, unit)
                and unit.bounding_box is not None
                and 0 <= unit.bounding_box.x - number.bounding_box.x <= 0.18
            ),
            key=lambda unit: unit.bounding_box.x,  # type: ignore[union-attr]
            default=None,
        )
        if best_unit is None:
            continue
        values.append(
            OCRLine(
                text=f"{number.text.strip()}{best_unit.text.strip()}",
                confidence=min(number.confidence, best_unit.confidence),
                bounding_box=_union_box([number, best_unit]),
            )
        )
    return values


def _inline_pairs(lines: list[OCRLine]) -> dict[str, _Pair]:
    pairs: dict[str, _Pair] = {}
    for line in lines:
        if line.bounding_box is None:
            continue
        match = _INLINE_ROW.search(_normalize(line.text))
        if not match:
            continue
        nutrient = match.group(1)
        value = OCRLine(
            text=f"{match.group(2)}{match.group(3)}",
            confidence=line.confidence,
            bounding_box=line.bounding_box,
        )
        if _has_expected_unit(nutrient, value.text):
            pairs[nutrient] = _Pair(label=line, value=value, score=-1.0)
    return pairs


def _rank_by_family(lines: list[OCRLine]) -> dict[tuple[str, int], int]:
    grouped: dict[str, list[OCRLine]] = {}
    for line in lines:
        family = (
            _unit_family(line.text)
            if _VALUE.fullmatch(line.text)
            else _nutrient_family(_normalize(line.text))
        )
        grouped.setdefault(family, []).append(line)
    ranks: dict[tuple[str, int], int] = {}
    for family, members in grouped.items():
        members.sort(key=_vertical_center)
        for rank, member in enumerate(members):
            key = _normalize(member.text) if member in lines else family
            ranks[(key if key in _NUTRIENTS else family, id(member))] = rank
    return ranks


def _nutrient_family(nutrient: str) -> str:
    if nutrient == "能量":
        return "energy"
    if nutrient in {"钠", "钙"}:
        return "mass_mg"
    return "mass_g"


def _unit_family(value: str) -> str:
    normalized = _normalize(value).lower()
    if "千焦" in normalized or "kj" in normalized:
        return "energy"
    if "毫克" in normalized or "mg" in normalized:
        return "mass_mg"
    return "mass_g"


def _same_row(left: OCRLine, right: OCRLine) -> bool:
    assert left.bounding_box is not None and right.bounding_box is not None
    tolerance = max(
        0.01, min(left.bounding_box.height, right.bounding_box.height) * 0.5
    )
    return abs(_vertical_center(left) - _vertical_center(right)) <= tolerance


def _vertical_center(line: OCRLine) -> float:
    assert line.bounding_box is not None
    return line.bounding_box.y + line.bounding_box.height / 2


def choose_best_nutrition_table(
    candidates: list[OCRFieldResult],
) -> OCRFieldResult | None:
    if not candidates:
        return None
    selected = max(candidates, key=_table_rank)
    complete = has_complete_core_nutrition_table(selected)
    return selected.model_copy(
        update={
            "name": "nutrition_table",
            "label": (
                "营养成分表（请逐项核对）"
                if complete
                else "营养成分候选（识别不完整，请手动核对）"
            ),
            "confidence": selected.confidence
            if complete
            else min(selected.confidence, 0.5),
            "requires_confirmation": True,
        }
    )


def has_complete_core_nutrition_table(field: OCRFieldResult | None) -> bool:
    if field is None:
        return False
    text = _normalize(field.raw_text).lower()
    if not _BASIS.search(text):
        return False
    return all(_has_typed_value(text, nutrient) for nutrient in _CORE_NUTRIENTS)


def _has_typed_value(text: str, nutrient: str) -> bool:
    units = "|".join(re.escape(unit) for unit in _EXPECTED_UNITS[nutrient])
    return bool(
        re.search(
            rf"{re.escape(nutrient)}-?\d+(?:\.\d+)?(?:{units})",
            text,
            re.IGNORECASE,
        )
    )


def _pair(label: OCRLine, value: OCRLine) -> _Pair | None:
    assert label.bounding_box is not None
    assert value.bounding_box is not None
    label_center = label.bounding_box.y + label.bounding_box.height / 2
    value_center = value.bounding_box.y + value.bounding_box.height / 2
    row_height = max(label.bounding_box.height, value.bounding_box.height)
    vertical_distance = abs(label_center - value_center)
    horizontal_distance = value.bounding_box.x - label.bounding_box.x
    if vertical_distance > row_height or not 0.04 <= horizontal_distance <= 0.42:
        return None
    score = vertical_distance / row_height + horizontal_distance * 0.1
    return _Pair(label=label, value=value, score=score)


def _pair_confidence(pair: _Pair) -> float:
    return (pair.label.confidence + pair.value.confidence) / 2


def _has_expected_unit(nutrient: str, value: str) -> bool:
    match = _VALUE.fullmatch(value)
    if not match:
        return False
    unit = match.group(2).lower()
    return unit in _EXPECTED_UNITS[nutrient]


def _table_rank(field: OCRFieldResult) -> tuple[int, int, float]:
    text = _normalize(field.raw_text)
    nutrient_count = sum(nutrient in text for nutrient in _NUTRIENTS)
    basis_present = int(bool(_BASIS.search(text)))
    return nutrient_count, basis_present, field.confidence


def _union_box(lines: list[OCRLine]) -> BoundingBox | None:
    boxes = [line.bounding_box for line in lines if line.bounding_box is not None]
    if not boxes:
        return None
    left = min(box.x for box in boxes)
    top = min(box.y for box in boxes)
    right = max(box.x + box.width for box in boxes)
    bottom = max(box.y + box.height for box in boxes)
    return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value)
