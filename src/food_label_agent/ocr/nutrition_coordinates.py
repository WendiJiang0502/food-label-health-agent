"""Recover nutrition rows from OCR text and geometry when table layout is missed."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .field_parser import OCRLine
from .models import BoundingBox, OCRFieldResult, OCRLineEvidence
from .nutrition import validate_nutrition_table

_NUTRIENTS = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠", "钙")
_CORE_NUTRIENTS = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠")
_VALUE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(千焦|kJ|克|g|毫克|mg)\s*$", re.IGNORECASE)
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
    values = [
        line
        for line in lines
        if _VALUE.fullmatch(line.text) and line.bounding_box is not None
    ]
    pairs: dict[str, _Pair] = {}
    for label in labels:
        nutrient = _normalize(label.text)
        candidates = [_pair(label, value) for value in values]
        valid = [candidate for candidate in candidates if candidate is not None]
        if not valid:
            continue
        best = min(valid, key=lambda candidate: candidate.score)
        current = pairs.get(nutrient)
        if current is None or _pair_confidence(best) > _pair_confidence(current):
            pairs[nutrient] = best

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


def choose_best_nutrition_table(
    candidates: list[OCRFieldResult],
) -> OCRFieldResult | None:
    if not candidates:
        return None
    selected = max(candidates, key=_table_rank)
    return selected.model_copy(
        update={
            "name": "nutrition_table",
            "label": "营养成分表（请逐项核对）",
            "requires_confirmation": True,
        }
    )


def has_complete_core_nutrition_table(field: OCRFieldResult | None) -> bool:
    if field is None:
        return False
    text = _normalize(field.raw_text)
    return bool(_BASIS.search(text)) and all(
        nutrient in text for nutrient in _CORE_NUTRIENTS
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
