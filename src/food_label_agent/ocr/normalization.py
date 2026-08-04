"""Semantic normalization for nutrition units while preserving OCR raw text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_BASIS = re.compile(r"每?\s*(\d+(?:\.\d+)?)\s*(克|g|毫克|mg|毫升|ml)", re.IGNORECASE)
_UNIT_ALIASES = {
    "克": "g",
    "g": "g",
    "毫克": "mg",
    "mg": "mg",
    "毫升": "ml",
    "ml": "ml",
    "千焦": "kj",
    "kj": "kj",
}


@dataclass(frozen=True, slots=True)
class NutritionBasis:
    value: float
    unit: str


def parse_nutrition_basis(value: str) -> NutritionBasis | None:
    normalized = unicodedata.normalize("NFKC", value).lower()
    match = _BASIS.search(normalized)
    if match is None:
        return None
    return NutritionBasis(
        value=float(match.group(1)),
        unit=_UNIT_ALIASES[match.group(2).lower()],
    )


def normalize_nutrition_text(value: str) -> str:
    """Canonicalize typography and measurement aliases for semantic comparison."""

    normalized = unicodedata.normalize("NFKC", value).lower()
    for source in ("毫克", "毫升", "千焦", "克"):
        normalized = normalized.replace(source, _UNIT_ALIASES[source])
    return re.sub(r"\s+", "", normalized)

