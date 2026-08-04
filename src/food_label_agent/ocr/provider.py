"""Replaceable OCR provider boundary.

The demo provider returns synthetic content so the upload and confirmation workflow
can be exercised without pretending that real OCR is already integrated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import BoundingBox, OCRFieldResult


class OCRProviderError(RuntimeError):
    """Safe, provider-neutral error that may be shown to operators or users."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class OCRInput:
    content: bytes
    file_name: str
    media_type: str
    width: int | None = None
    height: int | None = None
    fast_path_allowed: bool = True


class OCRProvider(Protocol):
    name: str
    synthetic: bool

    async def analyze(self, image: OCRInput) -> list[OCRFieldResult]: ...


class DemoOCRProvider:
    """Deterministic sample output for UI and orchestration development."""

    name = "demo-ocr-provider"
    synthetic = True
    remote_processing = False

    async def analyze(self, image: OCRInput) -> list[OCRFieldResult]:
        del image
        return [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="小麦粉、白砂糖、植物油、麦芽糊精、食用盐、食品添加剂",
                confidence=0.62,
                requires_confirmation=True,
                bounding_box=BoundingBox(x=0.08, y=0.18, width=0.84, height=0.30),
            ),
            OCRFieldResult(
                name="allergen_statement",
                label="过敏原提示",
                raw_text="本产品含有小麦，可能含有花生及坚果制品",
                confidence=0.91,
                requires_confirmation=False,
                bounding_box=BoundingBox(x=0.08, y=0.53, width=0.84, height=0.13),
            ),
            OCRFieldResult(
                name="nutrition_basis",
                label="营养标示口径",
                raw_text="每100克",
                confidence=0.96,
                requires_confirmation=False,
                bounding_box=BoundingBox(x=0.08, y=0.70, width=0.32, height=0.09),
            ),
        ]
