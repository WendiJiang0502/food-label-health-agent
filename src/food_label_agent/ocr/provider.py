"""Replaceable OCR provider boundary.

The demo provider returns synthetic content so the upload and confirmation workflow
can be exercised without pretending that real OCR is already integrated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import BoundingBox, OCRFieldResult, NutritionTableData


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
            OCRFieldResult(
                name="nutrition_table",
                label="营养成分表（演示数据，请逐项核对）",
                raw_text=(
                    "项目\t每100克\tNRV%\n"
                    "能量\t890千焦\t11%\n"
                    "蛋白质\t5.2克\t9%\n"
                    "脂肪\t8.0克\t13%\n"
                    "碳水化合物\t31.0克\t10%\n"
                    "糖\t3.5克\n"
                    "钠\t380毫克\t19%"
                ),
                confidence=0.70,
                requires_confirmation=True,
                bounding_box=BoundingBox(x=0.08, y=0.68, width=0.84, height=0.22),
                nutrition_table=NutritionTableData(
                    rows=[
                        ["项目", "每100克", "NRV%"],
                        ["能量", "890千焦", "11%"],
                        ["蛋白质", "5.2克", "9%"],
                        ["脂肪", "8.0克", "13%"],
                        ["碳水化合物", "31.0克", "10%"],
                        ["糖", "3.5克"],
                        ["钠", "380毫克", "19%"],
                    ]
                ),
            ),
            OCRFieldResult(
                name="label_claims",
                label="包装声称",
                raw_text="0蔗糖",
                confidence=0.72,
                requires_confirmation=True,
                bounding_box=BoundingBox(x=0.55, y=0.70, width=0.25, height=0.09),
            ),
        ]
