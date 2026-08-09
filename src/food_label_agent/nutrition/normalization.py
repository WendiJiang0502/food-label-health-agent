"""Normalize confirmed Chinese nutrition tables into traceable facts."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NutritionBasis:
    type: str
    amount: float
    unit: str
    raw_text: str


@dataclass(frozen=True, slots=True)
class NutritionFact:
    raw_name: str
    canonical_name: str
    value: float
    unit: str
    basis: str
    nrv_percent: float | None
    source_span: str
    row_index: int
    evidence_id: str
    confidence: float = 1.0
    normalization_method: str = "dictionary_exact"


@dataclass(frozen=True, slots=True)
class NutritionIssue:
    code: str
    message: str
    source_span: str
    row_index: int | None = None
    requires_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class NormalizedNutrition:
    raw_text: str
    basis: NutritionBasis | None
    nutrients: tuple[NutritionFact, ...]
    issues: tuple[NutritionIssue, ...]
    source_field: str = "nutrition_table"

    @property
    def requires_confirmation(self) -> bool:
        return any(issue.requires_confirmation for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "source_field": self.source_field,
            "basis": asdict(self.basis) if self.basis else None,
            "nutrients": [asdict(item) for item in self.nutrients],
            "issues": [asdict(issue) for issue in self.issues],
            "requires_confirmation": self.requires_confirmation,
        }


_NUTRIENT_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("饱和脂肪酸", "saturated_fat", "g"),
    ("反式脂肪酸", "trans_fat", "g"),
    ("碳水化合物", "carbohydrate", "g"),
    ("膳食纤维", "dietary_fiber", "g"),
    ("蛋白质", "protein", "g"),
    ("能量", "energy", "kJ"),
    ("脂肪", "fat", "g"),
    ("糖", "sugars", "g"),
    ("钠", "sodium", "mg"),
    ("钙", "calcium", "mg"),
)
_NUMBER = re.compile(r"(?<![\d.])-?\d+(?:\.\d+)?")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_UNIT = re.compile(r"(?i)(千焦|kj|毫克|mg|克|g)(?![a-z])")


def normalize_nutrition_facts(
    raw_text: str | None,
    *,
    basis_text: str | None = None,
    rows: list[list[str]] | None = None,
) -> NormalizedNutrition | None:
    """Parse only confirmed facts; malformed rows remain explicit unknowns."""

    if not raw_text and not rows:
        return None
    source = raw_text or "\n".join("\t".join(row) for row in rows or [])
    parsed_rows = rows or _text_rows(source)
    basis = _parse_basis(" ".join(filter(None, [basis_text, source])))
    issues: list[NutritionIssue] = []
    if basis is None:
        issues.append(
            NutritionIssue(
                code="NUTRITION_BASIS_MISSING",
                message="未确认营养数值是每100克、每100毫升还是每份。",
                source_span=basis_text or source[:80],
                requires_confirmation=True,
            )
        )

    facts: list[NutritionFact] = []
    seen: set[str] = set()
    for row_index, row in enumerate(parsed_rows, start=1):
        row_text = " ".join(cell.strip() for cell in row if cell.strip())
        matched = _nutrient(row_text)
        if matched is None:
            continue
        raw_name, canonical_name, expected_unit = matched
        value_text = row_text.replace(raw_name, "", 1)
        numbers = _NUMBER.findall(value_text)
        unit_match = _UNIT.search(value_text)
        if not numbers or unit_match is None:
            issues.append(
                NutritionIssue(
                    code="NUTRIENT_VALUE_OR_UNIT_MISSING",
                    message=f"{raw_name}行缺少可确认的数值或单位。",
                    source_span=row_text,
                    row_index=row_index,
                )
            )
            continue
        value = float(numbers[0])
        unit = _canonical_unit(unit_match.group(1))
        if not math.isfinite(value) or value < 0:
            issues.append(
                NutritionIssue(
                    code="INVALID_NUTRIENT_VALUE",
                    message=f"{raw_name}数值无效，必须人工核对。",
                    source_span=row_text,
                    row_index=row_index,
                )
            )
            continue
        if unit != expected_unit:
            issues.append(
                NutritionIssue(
                    code="NUTRIENT_UNIT_MISMATCH",
                    message=f"{raw_name}的单位与预期不一致，不能自动换算。",
                    source_span=row_text,
                    row_index=row_index,
                )
            )
            continue
        if canonical_name in seen:
            issues.append(
                NutritionIssue(
                    code="DUPLICATE_NUTRIENT_ROW",
                    message=f"{raw_name}出现多行，必须确认表格边界。",
                    source_span=row_text,
                    row_index=row_index,
                )
            )
            continue
        seen.add(canonical_name)
        percentages = _PERCENT.findall(value_text)
        facts.append(
            NutritionFact(
                raw_name=raw_name,
                canonical_name=canonical_name,
                value=value,
                unit=unit,
                basis=basis.type if basis else "unknown",
                nrv_percent=float(percentages[-1]) if percentages else None,
                source_span=row_text,
                row_index=row_index,
                evidence_id=f"label.nutrition.row.{row_index}",
            )
        )
    return NormalizedNutrition(
        raw_text=source,
        basis=basis,
        nutrients=tuple(facts),
        issues=tuple(issues),
    )


def _text_rows(value: str) -> list[list[str]]:
    return [
        [cell for cell in re.split(r"\t+|\s{2,}|[;；]", line) if cell.strip()]
        for line in value.splitlines()
        if line.strip()
    ]


def _parse_basis(value: str) -> NutritionBasis | None:
    match = re.search(r"每\s*100\s*(克|g|毫升|ml)", value, re.IGNORECASE)
    if match:
        unit = "g" if match.group(1).lower() in {"克", "g"} else "ml"
        return NutritionBasis(f"per_100{unit}", 100, unit, match.group(0))
    match = re.search(
        r"每\s*份(?:\s*\(?\s*(\d+(?:\.\d+)?)\s*(克|g|毫升|ml)\s*\)?)?",
        value,
        re.IGNORECASE,
    )
    if match:
        amount = float(match.group(1)) if match.group(1) else 1
        unit = _canonical_unit(match.group(2)) if match.group(2) else "serving"
        return NutritionBasis("per_serving", amount, unit, match.group(0))
    return None


def _nutrient(value: str) -> tuple[str, str, str] | None:
    compact = re.sub(r"\s+", "", value)
    for alias, canonical, unit in _NUTRIENT_ALIASES:
        if alias in compact:
            return alias, canonical, unit
    return None


def _canonical_unit(value: str) -> str:
    compact = value.lower()
    return {
        "千焦": "kJ",
        "kj": "kJ",
        "毫克": "mg",
        "mg": "mg",
        "克": "g",
        "g": "g",
        "毫升": "ml",
        "ml": "ml",
    }.get(compact, compact)
