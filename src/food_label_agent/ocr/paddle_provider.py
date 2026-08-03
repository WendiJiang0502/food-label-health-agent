"""PP-OCRv6 adapter with conservative food-label field extraction."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import OCRConfigurationError, OCRSettings
from .models import BoundingBox, OCRFieldResult
from .provider import OCRInput

_SECTION_STOP = re.compile(
    r"过敏原|致敏|可能含有|本品含有|本产品含有|营养成分|贮存|储存|保质期|生产日期|生产商|制造商|执行标准"
)
_INGREDIENT_HEADING = re.compile(r"配料(?:表)?\s*[:：]?\s*(.*)")
_ALLERGEN_CUE = re.compile(r"过敏原|致敏|可能含有|本品含有|本产品含有")
_NUTRITION_BASIS = re.compile(
    r"每\s*100\s*(?:克|g|毫升|ml)|每\s*份|营养成分表", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    confidence: float
    bounding_box: BoundingBox | None = None


class PaddleOCRProvider:
    """Local PP-OCR provider loaded once for the lifetime of the server process."""

    synthetic = False

    def __init__(
        self,
        settings: OCRSettings,
        *,
        engine_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.name = f"paddleocr-{settings.version.lower()}"
        if settings.cache_dir:
            os.environ.setdefault(
                "PADDLE_PDX_CACHE_HOME",
                str(Path(settings.cache_dir).expanduser().resolve()),
            )
        factory = engine_factory or _load_paddle_factory()
        self._engine = factory(
            ocr_version=settings.version,
            device=settings.device,
            use_doc_orientation_classify=settings.use_orientation,
            use_doc_unwarping=settings.use_unwarping,
            use_textline_orientation=settings.use_textline_orientation,
            text_rec_score_thresh=settings.general_threshold,
        )

    async def analyze(self, image: OCRInput) -> list[OCRFieldResult]:
        return await asyncio.to_thread(self._analyze_sync, image)

    def _analyze_sync(self, image: OCRInput) -> list[OCRFieldResult]:
        suffix = Path(image.file_name).suffix.lower() or _suffix_for(image.media_type)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(image.content)
                temporary_path = Path(temporary.name)
            results = self._engine.predict(str(temporary_path))
            lines = _collect_lines(
                results, image_width=image.width, image_height=image.height
            )
            if not lines:
                return [
                    OCRFieldResult(
                        name="ingredients",
                        label="配料表",
                        raw_text="",
                        confidence=0.0,
                        requires_confirmation=True,
                    )
                ]
            return _extract_food_label_fields(lines, self.settings)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def create_ocr_provider(settings: OCRSettings | None = None):
    """Build the configured provider once at application startup."""

    resolved = settings or OCRSettings.from_environment()
    if resolved.provider == "demo":
        from .provider import DemoOCRProvider

        return DemoOCRProvider()
    return PaddleOCRProvider(resolved)


def _load_paddle_factory() -> Callable[..., Any]:
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise OCRConfigurationError(
            "服务器选择了 paddle OCR，但尚未安装 PaddlePaddle 与 paddleocr。"
        ) from exc
    return PaddleOCR


def _collect_lines(
    results: Iterable[Any], *, image_width: int | None, image_height: int | None
) -> list[OCRLine]:
    lines: list[OCRLine] = []
    for result in results:
        payload = _result_payload(result)
        texts = list(payload.get("rec_texts", []))
        scores = list(payload.get("rec_scores", []))
        boxes = list(payload.get("rec_boxes", []))
        for index, text in enumerate(texts):
            normalized = str(text).strip()
            if not normalized:
                continue
            score = float(scores[index]) if index < len(scores) else 0.0
            bounding_box = None
            if index < len(boxes) and image_width and image_height:
                bounding_box = _normalize_box(boxes[index], image_width, image_height)
            lines.append(
                OCRLine(
                    text=normalized,
                    confidence=max(0.0, min(score, 1.0)),
                    bounding_box=bounding_box,
                )
            )
    return lines


def _result_payload(result: Any) -> Mapping[str, Any]:
    candidate: Any = result
    if not isinstance(candidate, Mapping):
        candidate = getattr(result, "json", None)
        if callable(candidate):
            candidate = candidate()
    if not isinstance(candidate, Mapping):
        raise OCRConfigurationError("PaddleOCR 返回了无法解析的结果格式。")
    nested = candidate.get("res")
    return nested if isinstance(nested, Mapping) else candidate


def _extract_food_label_fields(
    lines: list[OCRLine], settings: OCRSettings
) -> list[OCRFieldResult]:
    ingredient_lines = _ingredient_lines(lines)
    allergen_lines = [line for line in lines if _ALLERGEN_CUE.search(line.text)]
    nutrition_lines = [line for line in lines if _NUTRITION_BASIS.search(line.text)]

    if not ingredient_lines:
        ingredient_lines = lines

    fields = [
        _field(
            name="ingredients",
            label="配料表（请核对范围）",
            lines=ingredient_lines,
            threshold=settings.general_threshold,
            force_confirmation=True,
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
            if _SECTION_STOP.search(following.text):
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
) -> OCRFieldResult:
    confidence = sum(line.confidence for line in lines) / len(lines)
    # OCR character confidence is not semantic section confidence. Ingredients
    # always remain below the safety routing threshold until the user confirms.
    if force_confirmation:
        confidence = min(confidence, 0.84)
    return OCRFieldResult(
        name=name,
        label=label,
        raw_text="\n".join(line.text for line in lines),
        confidence=confidence,
        requires_confirmation=force_confirmation or confidence < threshold,
        bounding_box=_union_box(lines),
    )


def _normalize_box(box: Any, image_width: int, image_height: int) -> BoundingBox:
    x_min, y_min, x_max, y_max = (float(value) for value in box[:4])
    x = max(0.0, min(x_min / image_width, 1.0))
    y = max(0.0, min(y_min / image_height, 1.0))
    right = max(x, min(x_max / image_width, 1.0))
    bottom = max(y, min(y_max / image_height, 1.0))
    return BoundingBox(
        x=x,
        y=y,
        width=max((right - x), 1 / image_width),
        height=max((bottom - y), 1 / image_height),
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


def _suffix_for(media_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }.get(media_type, ".img")
