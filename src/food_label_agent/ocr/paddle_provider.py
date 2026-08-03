"""PP-OCRv6 adapter with conservative food-label field extraction."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .config import OCRConfigurationError, OCRSettings
from .field_parser import OCRLine, parse_food_label_fields
from .models import BoundingBox, OCRFieldResult
from .ppstructure_provider import PPStructureNutritionParser
from .provider import OCRInput


class PaddleOCRProvider:
    """Local PP-OCR provider loaded once for the lifetime of the server process."""

    synthetic = False

    def __init__(
        self,
        settings: OCRSettings,
        *,
        engine_factory: Callable[..., Any] | None = None,
        structure_factory: Callable[..., Any] | None = None,
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
        self._table_parser = (
            PPStructureNutritionParser(settings, engine_factory=structure_factory)
            if settings.table_parser == "ppstructure"
            else None
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
            fields = parse_food_label_fields(lines, self.settings)
            if self._table_parser is not None and any(
                field.name == "nutrition_basis" for field in fields
            ):
                fields.extend(self._table_parser.analyze(str(temporary_path)))
            return fields
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


def _suffix_for(media_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }.get(media_type, ".img")
