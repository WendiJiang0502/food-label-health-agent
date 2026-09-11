"""Tencent Cloud OCR adapter for Chinese food labels.

The provider sends the image to GeneralAccurateOCR for line evidence and, when
nutrition content is detected, to RecognizeTableAccurateOCR for cell structure.
It never logs or serializes credentials or source images.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from base64 import b64encode
from collections.abc import Callable, Iterable
from statistics import fmean
from typing import Any

from .config import OCRConfigurationError, OCRSettings
from .field_parser import OCRLine, parse_food_label_fields
from .models import BoundingBox, OCRFieldResult, OCRLineEvidence
from .nutrition import validate_nutrition_table
from .nutrition_coordinates import (
    choose_best_nutrition_table,
    extract_coordinate_nutrition_table,
    has_complete_core_nutrition_table,
)
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
        self._table_api_available = settings.tencent_table_enabled
        self._inference_slots = asyncio.Semaphore(settings.tencent_max_concurrency)
        self._circuit_lock = threading.Lock()
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    async def analyze(self, image: OCRInput) -> list[OCRFieldResult]:
        self._require_closed_circuit()
        try:
            await asyncio.wait_for(
                self._inference_slots.acquire(),
                timeout=self.settings.tencent_queue_timeout_seconds,
            )
        except TimeoutError as exc:
            raise OCRProviderError(
                "TencentCloud.LocalBackpressure",
                "OCR 请求正在排队，请稍后重试。",
                retryable=True,
            ) from exc
        try:
            result = await asyncio.to_thread(self._analyze_sync, image)
        except Exception as exc:
            self._record_failure(exc)
            raise
        else:
            with self._circuit_lock:
                self._consecutive_failures = 0
            return result
        finally:
            self._inference_slots.release()

    def _require_closed_circuit(self) -> None:
        with self._circuit_lock:
            if time.monotonic() < self._circuit_open_until:
                raise OCRProviderError(
                    "TencentCloud.CircuitOpen",
                    "OCR 服务暂时不可用，请稍后重试。",
                    retryable=True,
                )

    def _record_failure(self, error: Exception) -> None:
        if isinstance(error, OCRProviderError) and not error.retryable:
            return
        with self._circuit_lock:
            self._consecutive_failures += 1
            if (
                self._consecutive_failures
                >= self.settings.tencent_circuit_failure_threshold
            ):
                self._circuit_open_until = (
                    time.monotonic()
                    + self.settings.tencent_circuit_recovery_seconds
                )

    def _analyze_sync(self, image: OCRInput) -> list[OCRFieldResult]:
        for attempt in range(3):
            try:
                return self._call_ocr(image)
            except Exception as exc:
                translated = _translate_tencent_error(exc)
                if translated is not None:
                    if translated.retryable and attempt < 2:
                        continue
                    raise translated from exc
                raise
        raise AssertionError("unreachable")

    def _call_ocr(self, image: OCRInput) -> list[OCRFieldResult]:
        prepared_content, prepared_width, prepared_height = _prepare_cloud_image(
            image.content,
            width=image.width,
            height=image.height,
        )
        encoded = b64encode(prepared_content).decode("ascii")
        original_encoded = b64encode(image.content).decode("ascii")
        lines = self._call_general(
            encoded,
            image_width=prepared_width,
            image_height=prepared_height,
        )
        field_sets = [parse_food_label_fields(lines, self.settings)]
        line_sets = [lines]
        if prepared_content != image.content and (
            not image.fast_path_allowed
            or not _has_ingredient_text(field_sets[0])
            or not _has_nutrition_content(lines)
        ):
            try:
                original_lines = self._call_general(
                    original_encoded,
                    image_width=image.width,
                    image_height=image.height,
                )
            except Exception as exc:
                translated = _translate_tencent_error(exc)
                if translated is None or not translated.retryable:
                    raise
            else:
                line_sets.append(original_lines)
                field_sets.append(
                    parse_food_label_fields(original_lines, self.settings)
                )
        fields = _choose_general_fields(field_sets)

        table_candidates = []
        for candidate_lines in line_sets:
            coordinate_table = extract_coordinate_nutrition_table(candidate_lines)
            if coordinate_table is not None:
                table_candidates.append(coordinate_table)
        if self._table_api_available and any(
            _has_nutrition_content(candidate_lines) for candidate_lines in line_sets
        ):
            cloud_table = self._try_table_api(
                encoded,
                image_width=prepared_width,
                image_height=prepared_height,
            )
            if cloud_table is not None:
                table_candidates.append(cloud_table)
            if prepared_content != image.content and not any(
                has_complete_core_nutrition_table(candidate)
                for candidate in table_candidates
            ):
                original_table = self._try_table_api(
                    original_encoded,
                    image_width=image.width,
                    image_height=image.height,
                )
                if original_table is not None:
                    table_candidates.append(original_table)
        best_table = choose_best_nutrition_table(table_candidates)
        if self._table_api_available and not has_complete_core_nutrition_table(
            best_table
        ):
            crop = _nutrition_table_crop(
                image.content,
                lines=[line for candidate_lines in line_sets for line in candidate_lines],
            )
            if crop is not None:
                crop_content, crop_width, crop_height, crop_region = crop
                crop_table = self._try_table_api(
                    b64encode(crop_content).decode("ascii"),
                    image_width=crop_width,
                    image_height=crop_height,
                )
                if crop_table is not None:
                    table_candidates.append(
                        _remap_crop_field(crop_table, crop_region=crop_region)
                    )
                    best_table = choose_best_nutrition_table(table_candidates)
        if best_table is not None:
            best_table = _corroborate_energy_value(
                best_table,
                lines=[line for candidate_lines in line_sets for line in candidate_lines],
            )
            fields = [field for field in fields if field.name != "nutrition_table"]
            fields.append(best_table)
        return fields

    def _call_general(
        self, encoded: str, *, image_width: int | None, image_height: int | None
    ) -> list[OCRLine]:
        request = self._general_request_factory()
        request.ImageBase64 = encoded
        request.EnableDetectSplit = self.settings.tencent_detect_split_enabled
        request.ConfigID = "OCR"
        if self.settings.tencent_printed_text_only:
            request.WordsType = "2"
        response = self._client.GeneralAccurateOCR(request)
        return _general_lines(
            getattr(response, "TextDetections", None) or [],
            image_width=image_width,
            image_height=image_height,
        )

    def _try_table_api(
        self, encoded: str, *, image_width: int | None, image_height: int | None
    ) -> OCRFieldResult | None:
        table_request = self._table_request_factory()
        table_request.ImageBase64 = encoded
        table_request.UseNewModel = self.settings.tencent_table_new_model
        for attempt in range(2):
            try:
                table_response = self._client.RecognizeTableAccurateOCR(table_request)
                break
            except Exception as exc:
                translated = _translate_tencent_error(exc)
                if translated is None:
                    raise
                if translated.retryable and attempt == 0:
                    continue
                if not translated.retryable:
                    self._table_api_available = False
                    self.name = "tencentcloud-general-accurate+coordinate-table"
                return None
        else:
            return None
        return _best_nutrition_table(
            getattr(table_response, "TableDetections", None) or [],
            image_width=image_width,
            image_height=image_height,
        )


def _prepare_cloud_image(
    content: bytes, *, width: int | None, height: int | None
) -> tuple[bytes, int | None, int | None]:
    """Enlarge legible packaging text before upload without inventing detail."""

    if not width or not height or min(width, height) >= 1000:
        return content, width, height
    try:
        import cv2
        import numpy as np

        decoded = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            return content, width, height
        scale = 1100 / min(width, height)
        resized = cv2.resize(
            decoded,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
        ok, encoded = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            return content, width, height
        prepared_height, prepared_width = resized.shape[:2]
        return encoded.tobytes(), prepared_width, prepared_height
    except (ImportError, ValueError):
        return content, width, height


def _nutrition_table_crop(
    content: bytes, *, lines: list[OCRLine]
) -> tuple[bytes, int, int, tuple[float, float, float, float]] | None:
    headings = [
        line
        for line in lines
        if "营养成分" in line.text and line.bounding_box is not None
    ]
    if not headings:
        return None
    heading = max(headings, key=lambda line: line.confidence)
    box = heading.bounding_box
    assert box is not None
    try:
        import cv2
        import numpy as np

        decoded = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            return None
        height, width = decoded.shape[:2]
        left = max(0.0, box.x - 0.22)
        top = max(0.0, box.y - 0.04)
        right = min(1.0, max(box.x + box.width + 0.20, box.x + 0.56))
        bottom = min(1.0, box.y + 0.28)
        crop = decoded[
            int(top * height) : max(int(bottom * height), int(top * height) + 1),
            int(left * width) : max(int(right * width), int(left * width) + 1),
        ]
        if not crop.size:
            return None
        crop_height, crop_width = crop.shape[:2]
        scale = min(4.0, max(2.0, 1000 / min(crop_width, crop_height)))
        enlarged = cv2.resize(
            crop,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
        ok, encoded = cv2.imencode(
            ".jpg", enlarged, [cv2.IMWRITE_JPEG_QUALITY, 95]
        )
        if not ok:
            return None
        output_height, output_width = enlarged.shape[:2]
        return encoded.tobytes(), output_width, output_height, (left, top, right, bottom)
    except (ImportError, ValueError):
        return None


def _remap_crop_field(
    field: OCRFieldResult, *, crop_region: tuple[float, float, float, float]
) -> OCRFieldResult:
    left, top, right, bottom = crop_region
    width = right - left
    height = bottom - top

    def remap(box: BoundingBox | None) -> BoundingBox | None:
        if box is None:
            return None
        return BoundingBox(
            x=left + box.x * width,
            y=top + box.y * height,
            width=box.width * width,
            height=box.height * height,
        )

    evidence = [
        item.model_copy(update={"bounding_box": remap(item.bounding_box)})
        for item in field.evidence_lines
    ]
    return field.model_copy(
        update={"bounding_box": remap(field.bounding_box), "evidence_lines": evidence}
    )


def _corroborate_energy_value(
    field: OCRFieldResult, *, lines: list[OCRLine]
) -> OCRFieldResult:
    if field.nutrition_table is None:
        return field
    rows = [list(row) for row in field.nutrition_table.rows]
    energy_index = next(
        (index for index, row in enumerate(rows) if row and row[0] == "能量"), None
    )
    if energy_index is None or len(rows[energy_index]) < 2:
        return field
    value = rows[energy_index][1]
    amount = re.search(r"\d+(?:\.\d+)?", value)
    if amount is None:
        return field
    compact = amount.group(0).replace(".", "")
    candidates = [
        line
        for line in lines
        if re.fullmatch(rf"\s*{re.escape(compact)}\s*[Nn]\s*", line.text)
    ]
    if len(candidates) != 1 or amount.group(0) == compact:
        return field
    rows[energy_index][1] = value.replace(amount.group(0), compact, 1)
    raw_text = "\n".join("\t".join(row) for row in rows)
    corroborating = candidates[0]
    evidence = [
        *field.evidence_lines,
        OCRLineEvidence(
            text=corroborating.text,
            confidence=corroborating.confidence,
            bounding_box=corroborating.bounding_box,
        ),
    ]
    return field.model_copy(
        update={
            "raw_text": raw_text,
            "nutrition_table": validate_nutrition_table(rows),
            "evidence_lines": evidence,
            "requires_confirmation": True,
            "confidence": min(field.confidence, corroborating.confidence, 0.5),
        }
    )


_FIELD_CONTAMINATION_CUES = (
    "营养成分",
    "生产日期",
    "贮存",
    "消费者",
    "扫一扫",
    "活动规则",
    "食用方法",
    "分钟",
)


def _has_ingredient_text(fields: list[OCRFieldResult]) -> bool:
    return any(field.name == "ingredients" and field.raw_text.strip() for field in fields)


def _choose_general_fields(
    field_sets: list[list[OCRFieldResult]],
) -> list[OCRFieldResult]:
    candidates: dict[str, list[OCRFieldResult]] = {}
    for fields in field_sets:
        for field in fields:
            candidates.setdefault(field.name, []).append(field)
    return [
        max(options, key=_general_field_rank)
        for _, options in sorted(candidates.items())
    ]


def _general_field_rank(field: OCRFieldResult) -> tuple[int, int, int, int, float]:
    text = field.raw_text.strip()
    contamination = sum(cue in text for cue in _FIELD_CONTAMINATION_CUES)
    balanced = int(text.count("(") + text.count("（") == text.count(")") + text.count("）"))
    useful_length = min(len(text), 500)
    if field.name != "ingredients":
        contamination = 0
    return bool(text), -contamination, balanced, useful_length, field.confidence

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
    retryable = code.startswith(
        ("RequestLimitExceeded", "InternalError", "ClientNetworkError")
    ) or code == "FailedOperation.UnKnowError"
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
    rows = [
        [columns[column] for column in sorted(columns)]
        for _, columns in sorted(indexed.items())
    ]
    return [_normalize_table_row(row) for row in rows]


def _normalize_table_row(row: list[str]) -> list[str]:
    if not row:
        return row
    normalized = [*row]
    label = re.sub(r"^[\s—–一-]+", "", normalized[0]).strip()
    if label in {"脂", "量", "熊量"} and len(normalized) > 1 and re.search(
        r"(?:千焦|kJ)", normalized[1], re.IGNORECASE
    ):
        label = "能量"
    if label != "碳水化合物" and "化合物" in label:
        label = "碳水化合物"
    aliases = {
        "饱和脂肪酸": "饱和脂肪",
        "反式脂肪酸": "反式脂肪",
    }
    normalized[0] = aliases.get(label, label)
    return normalized


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
