"""Application service coordinating file validation, OCR, and confirmation."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from time import monotonic, perf_counter
from uuid import uuid4

from food_label_agent.domain.models import LabelField
from food_label_agent.graph.routing import route_after_ocr
from food_label_agent.graph.state import create_initial_state
from food_label_agent.ingredients.service import normalize_food_label_result

from .evidence_quality import assess_ocr_evidence
from .models import (
    ConfirmLabelRequest,
    ConfirmLabelResponse,
    ImageQualityData,
    OCRAnalysisResponse,
    OCRFieldResult,
    OCRProcessingData,
)
from .provider import OCRInput, OCRProvider
from .quality import ImageQualityError, ImageQualityReport, assess_image_quality

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _CachedOCR:
    stored_at: float
    fields: list[OCRFieldResult]
    quality: ImageQualityReport | None


class OCRService:
    def __init__(
        self,
        provider: OCRProvider,
        *,
        quality_assessor=assess_image_quality,
        cache_size: int = 64,
        cache_ttl_seconds: float = 900,
    ) -> None:
        self.provider = provider
        self.quality_assessor = quality_assessor
        self.cache_size = max(cache_size, 0)
        self.cache_ttl_seconds = max(cache_ttl_seconds, 0)
        self._cache: OrderedDict[str, _CachedOCR] = OrderedDict()

    async def analyze(
        self,
        *,
        content: bytes,
        file_name: str,
        media_type: str,
    ) -> OCRAnalysisResponse:
        started_at = perf_counter()
        self._validate_image(content=content, media_type=media_type)
        cache_key = sha256(content).hexdigest()
        cached = self._cache_get(cache_key)
        cache_hit = cached is not None
        quality_ms = 0.0
        ocr_ms = 0.0
        if cached is not None:
            quality = cached.quality
            fields = cached.fields
        else:
            quality: ImageQualityReport | None = None
            quality_started = perf_counter()
            if not self.provider.synthetic:
                quality = self.quality_assessor(content)
                if quality.blocking_issues:
                    raise ImageQualityError(quality)
            quality_ms = _elapsed_ms(quality_started)
            ocr_started = perf_counter()
            fields = await self.provider.analyze(
                OCRInput(
                    content=content,
                    file_name=file_name,
                    media_type=media_type,
                    width=quality.metrics.width if quality else None,
                    height=quality.metrics.height if quality else None,
                    fast_path_allowed=_fast_path_allowed(quality),
                )
            )
            ocr_ms = _elapsed_ms(ocr_started)
            self._cache_put(cache_key, fields=fields, quality=quality)
        evidence_quality = assess_ocr_evidence(fields)
        request_id = str(uuid4())
        state = create_initial_state(
            request_id=request_id,
            jurisdiction="CN",
            applicable_date=datetime.now(UTC).date().isoformat(),
        )
        state["label_fields"] = {
            field.name: LabelField(
                name=field.name,
                raw_text=field.raw_text,
                confidence=field.confidence,
                confirmed_by_user=False,
            )
            for field in fields
        }
        state["ocr_evidence"] = evidence_quality.model_dump(mode="json")
        warnings = []
        if self.provider.synthetic:
            warnings.append("演示识别结果，不代表图片的真实 OCR 内容。")
        if quality:
            warnings.extend(quality.warnings)
        warnings.extend(
            issue.message
            for issue in evidence_quality.issues
            if issue.severity == "warning"
        )
        return OCRAnalysisResponse(
            request_id=request_id,
            provider=self.provider.name,
            synthetic=self.provider.synthetic,
            file_name=file_name,
            fields=fields,
            image_quality=(
                ImageQualityData(
                    width=quality.metrics.width,
                    height=quality.metrics.height,
                    blur_score=quality.metrics.blur_score,
                    brightness=quality.metrics.brightness,
                    contrast=quality.metrics.contrast,
                    foreground_ratio=quality.metrics.foreground_ratio,
                    text_skew_degrees=quality.metrics.text_skew_degrees,
                    text_angle_spread=quality.metrics.text_angle_spread,
                    local_sharpness_ratio=quality.metrics.local_sharpness_ratio,
                )
                if quality
                else None
            ),
            processing=OCRProcessingData(
                total_ms=_elapsed_ms(started_at),
                quality_ms=quality_ms,
                ocr_ms=ocr_ms,
                cache_hit=cache_hit,
            ),
            evidence_quality=evidence_quality,
            warnings=warnings,
            next_route=route_after_ocr(state),
        )

    def _cache_get(self, key: str) -> _CachedOCR | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if monotonic() - entry.stored_at > self.cache_ttl_seconds:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return entry

    def _cache_put(
        self,
        key: str,
        *,
        fields: list[OCRFieldResult],
        quality: ImageQualityReport | None,
    ) -> None:
        if self.cache_size == 0:
            return
        self._cache[key] = _CachedOCR(
            stored_at=monotonic(), fields=fields, quality=quality
        )
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def confirm(self, request: ConfirmLabelRequest) -> ConfirmLabelResponse:
        state = create_initial_state(
            request_id=request.request_id,
            jurisdiction=request.jurisdiction,
            applicable_date=request.applicable_date,
        )
        state["label_fields"] = {
            name: LabelField(
                name=name,
                raw_text=value,
                confidence=1.0,
                confirmed_by_user=True,
            )
            for name, value in request.fields.items()
        }
        next_route = route_after_ocr(state)
        normalized = normalize_food_label_result(
            request.fields["ingredients"],
            original_ingredients_text=request.original_fields.get("ingredients"),
            nutrition_table_text=request.fields.get("nutrition_table"),
            nutrition_basis_text=request.fields.get("nutrition_basis"),
            nutrition_rows=request.nutrition_rows,
        )
        return ConfirmLabelResponse(
            request_id=request.request_id,
            status="confirmed",
            next_route=next_route,
            confirmed_fields=sorted(request.fields),
            message="标签事实已由用户确认，可以进入配料规范化。",
            normalized_label=normalized,
            normalization_issues=[
                {
                    "code": issue["code"],
                    "message": issue["message"],
                    "source_span": issue["source_span"],
                }
                for issue in [
                    *normalized["issues"],
                    *((normalized.get("nutrition") or {}).get("issues", [])),
                ]
            ],
        )

    @staticmethod
    def _validate_image(*, content: bytes, media_type: str) -> None:
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise InvalidImageError(
                "暂不支持该文件类型，请上传 JPG、PNG、WebP 或 HEIC 图片。"
            )
        if not content:
            raise InvalidImageError("图片内容为空，请重新选择文件。")
        if len(content) > MAX_IMAGE_BYTES:
            raise InvalidImageError("单张图片不能超过 10 MB，请压缩后重试。")
        if not _matches_image_signature(content=content, media_type=media_type):
            raise InvalidImageError("文件内容与图片类型不一致，请重新选择原始图片。")


def _matches_image_signature(*, content: bytes, media_type: str) -> bool:
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/webp":
        return (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )
    if media_type in {"image/heic", "image/heif"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    return False


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def _fast_path_allowed(quality: ImageQualityReport | None) -> bool:
    if quality is None:
        return True
    high_complexity_codes = {
        "IMAGE_PERSPECTIVE_CAUTION",
        "IMAGE_LOCAL_WARP_CAUTION",
        "IMAGE_LOCAL_FOCUS_CAUTION",
    }
    return not any(issue.code in high_complexity_codes for issue in quality.issues)
