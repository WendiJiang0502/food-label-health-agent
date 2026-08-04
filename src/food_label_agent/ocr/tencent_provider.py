"""Tencent Cloud OCR adapter for Chinese food labels.

The provider sends the image to GeneralAccurateOCR for line evidence and, when
nutrition content is detected, to RecognizeTableAccurateOCR for cell structure.
It never logs or serializes credentials or source images.
"""

from __future__ import annotations

import asyncio
from base64 import b64encode
from collections.abc import Callable, Iterable
from statistics import fmean
from typing import Any

from .config import OCRConfigurationError, OCRSettings
from .field_parser import OCRLine, parse_food_label_fields
from .models import BoundingBox, OCRFieldResult, OCRLineEvidence
from .nutrition import validate_nutrition_table
from .provider import OCRInput, OCRProviderError

_NUTRITION_CUES = ("营养成分", "能量", "蛋白质", "脂肪", "碳水化合物", "钠")


class TencentCloudOCRProvider:
    """Managed OCR provider using Tencent Cloud's official Python SDK."""

    name = "tencentcloud-general-accurate+table-v3"
    synthetic = False
    remote_processing = True

    def __init__(
        self,
        settings: OCRSettings,
        *,
        client: Any | None = None,
        general_request_factory: Callable[[], Any] | None = None,
        table_request_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.settings = settings
        if client is None:
            client, sdk_general_factory, sdk_table_factory = _load_sdk(settings)
            general_request_factory = general_request_factory or sdk_general_factory
            table_request_factory = table_request_factory or sdk_table_factory
        if general_request_factory is None or table_request_factory is None:
            raise OCRConfigurationError("腾讯云 OCR 请求工厂未正确初始化。")
        self._client = client
        self._general_request_factory = general_request_factory
        self._table_request_factory = table_request_factory
        self._inference_lock = asyncio.Lock()

    async def analyze(self, image: OCRInput) -> list[OCRFieldResult]:
        async with self._inference_lock:
            return await asyncio.to_thread(self._analyze_sync, image)

    def _analyze_sync(self, image: OCRInput) -> list[OCRFieldResult]:
        try:
            return self._call_ocr(image)
        except Exception as exc:
            translated = _translate_tencent_error(exc)
            if translated is not None:
                raise translated from exc
            raise

    def _call_ocr(self, image: OCRInput) -> list[OCRFieldResult]:
        encoded = b64encode(image.content).decode("ascii")
        request = self._general_request_factory()
        request.ImageBase64 = encoded
        response = self._client.GeneralAccurateOCR(request)
        lines = _general_lines(
            getattr(response, "TextDetections", None) or [],
            image_width=image.width,
            image_height=image.height,
        )
        fields = parse_food_label_fields(lines, self.settings)

        if self.settings.tencent_table_enabled and _has_nutrition_content(lines):
            table_request = self._table_request_factory()
            table_request.ImageBase64 = encoded
            table_request.UseNewModel = self.settings.tencent_table_new_model
            table_response = self._client.RecognizeTableAccurateOCR(table_request)
            table_field = _best_nutrition_table(
                getattr(table_response, "TableDetections", None) or [],
                image_width=image.width,
                image_height=image.height,
            )
            if table_field is not None:
                fields.append(table_field)
        return fields


def _translate_tencent_error(exc: Exception) -> OCRProviderError | None:
    get_code = getattr(exc, "get_code", None)
    if not callable(get_code):
        return None
    code = str(get_code() or "TencentCloud.Unknown")
    if code == "FailedOperation.UnOpenError":
        return OCRProviderError(
            code,
            "腾讯云 OCR 服务尚未开通，请在文字识别控制台同意服务条款并点击立即开通。",
        )
    if code.startswith("AuthFailure"):
        return OCRProviderError(
            code,
            "腾讯云 OCR 凭证验证失败，请检查服务端 SecretId、SecretKey 和系统时间。",
        )
    if code in {"UnauthorizedOperation", "AuthFailure.UnauthorizedOperation"}:
        return OCRProviderError(
            code,
            "腾讯云 OCR 子账号权限不足，请检查 CAM 最小权限策略。",
        )
    if code == "ResourceUnavailable.ResourcePackageRunOut":
        return OCRProviderError(
            code,
            "腾讯云 OCR 资源包已用尽，请检查用量或计费设置。",
        )
    retryable = code.startswith(("RequestLimitExceeded", "InternalError"))
    return OCRProviderError(
        code,
        "腾讯云 OCR 暂时无法完成识别，请稍后重试。",
        retryable=retryable,
    )


def _load_sdk(
    settings: OCRSettings,
) -> tuple[Any, Callable[[], Any], Callable[[], Any]]:
    try:
        from tencentcloud.common.credential import DefaultCredentialProvider
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.ocr.v20181119 import models
        from tencentcloud.ocr.v20181119.ocr_client import OcrClient
    except ImportError as exc:
        raise OCRConfigurationError(
            "服务器选择了腾讯云 OCR，但尚未安装 cloud-ocr 可选依赖。"
        ) from exc

    credential = DefaultCredentialProvider().get_credential()
    http_profile = HttpProfile()
    http_profile.endpoint = "ocr.tencentcloudapi.com"
    client_profile = ClientProfile(httpProfile=http_profile)
    client = OcrClient(credential, settings.tencent_region, client_profile)
    return (
        client,
        models.GeneralAccurateOCRRequest,
        models.RecognizeTableAccurateOCRRequest,
    )


def _general_lines(
    detections: Iterable[Any], *, image_width: int | None, image_height: int | None
) -> list[OCRLine]:
    lines: list[OCRLine] = []
    for detection in detections:
        text = str(getattr(detection, "DetectedText", "") or "").strip()
        if not text:
            continue
        lines.append(
            OCRLine(
                text=text,
                confidence=_confidence(getattr(detection, "Confidence", 0)),
                bounding_box=_polygon_box(
                    getattr(detection, "Polygon", None),
                    image_width=image_width,
                    image_height=image_height,
                ),
            )
        )
    return lines


def _has_nutrition_content(lines: list[OCRLine]) -> bool:
    joined = " ".join(line.text for line in lines)
    return (
        "营养成分" in joined or sum(cue in joined for cue in _NUTRITION_CUES[1:]) >= 2
    )


def _best_nutrition_table(
    tables: Iterable[Any], *, image_width: int | None, image_height: int | None
) -> OCRFieldResult | None:
    candidates = []
    for table in tables:
        cells = list(getattr(table, "Cells", None) or [])
        joined = " ".join(str(getattr(cell, "Text", "") or "") for cell in cells)
        nutrient_count = sum(cue in joined for cue in _NUTRITION_CUES)
        if nutrient_count < 2:
            continue
        candidates.append((nutrient_count, cells, table))
    if not candidates:
        return None

    _, cells, table = max(candidates, key=lambda candidate: candidate[0])
    rows = _table_rows(cells)
    evidence = [
        OCRLineEvidence(
            text=str(getattr(cell, "Text", "") or "").strip(),
            confidence=_confidence(getattr(cell, "Confidence", 0)),
            bounding_box=_polygon_box(
                getattr(cell, "Polygon", None),
                image_width=image_width,
                image_height=image_height,
            ),
        )
        for cell in cells
        if str(getattr(cell, "Text", "") or "").strip()
    ]
    confidences = [item.confidence for item in evidence]
    confidence = min(fmean(confidences), 0.84) if confidences else 0.0
    table_box = _polygon_box(
        getattr(table, "TableCoordPoint", None),
        image_width=image_width,
        image_height=image_height,
    )
    return OCRFieldResult(
        name="nutrition_table",
        label="营养成分表（请逐项核对）",
        raw_text="\n".join("\t".join(row) for row in rows),
        confidence=confidence,
        requires_confirmation=True,
        bounding_box=table_box or _union_boxes(evidence),
        evidence_lines=evidence,
        nutrition_table=validate_nutrition_table(rows),
    )


def _table_rows(cells: list[Any]) -> list[list[str]]:
    indexed: dict[int, dict[int, str]] = {}
    for cell in cells:
        row = int(getattr(cell, "RowTl", 0) or 0)
        column = int(getattr(cell, "ColTl", 0) or 0)
        text = str(getattr(cell, "Text", "") or "").strip()
        if text:
            indexed.setdefault(row, {})[column] = text
    return [
        [columns[column] for column in sorted(columns)]
        for _, columns in sorted(indexed.items())
    ]


def _confidence(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric > 1:
        numeric /= 100
    return max(0.0, min(numeric, 1.0))


def _polygon_box(
    polygon: Any, *, image_width: int | None, image_height: int | None
) -> BoundingBox | None:
    if not polygon or not image_width or not image_height:
        return None
    points = [
        (float(getattr(point, "X", 0) or 0), float(getattr(point, "Y", 0) or 0))
        for point in polygon
    ]
    if not points:
        return None
    left = max(0.0, min(point[0] for point in points) / image_width)
    top = max(0.0, min(point[1] for point in points) / image_height)
    right = min(1.0, max(point[0] for point in points) / image_width)
    bottom = min(1.0, max(point[1] for point in points) / image_height)
    if right <= left or bottom <= top:
        return None
    return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)


def _union_boxes(lines: list[OCRLineEvidence]) -> BoundingBox | None:
    boxes = [line.bounding_box for line in lines if line.bounding_box is not None]
    if not boxes:
        return None
    left = min(box.x for box in boxes)
    top = min(box.y for box in boxes)
    right = max(box.x + box.width for box in boxes)
    bottom = max(box.y + box.height for box in boxes)
    return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)
