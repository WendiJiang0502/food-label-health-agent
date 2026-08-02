"""Application service coordinating file validation, OCR, and confirmation."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from food_label_agent.domain.models import LabelField
from food_label_agent.graph.routing import route_after_ocr
from food_label_agent.graph.state import create_initial_state

from .models import ConfirmLabelRequest, ConfirmLabelResponse, OCRAnalysisResponse
from .provider import OCRInput, OCRProvider

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


class OCRService:
    def __init__(self, provider: OCRProvider) -> None:
        self.provider = provider

    async def analyze(
        self,
        *,
        content: bytes,
        file_name: str,
        media_type: str,
    ) -> OCRAnalysisResponse:
        self._validate_image(content=content, media_type=media_type)
        fields = await self.provider.analyze(
            OCRInput(content=content, file_name=file_name, media_type=media_type)
        )
        request_id = str(uuid4())
        state = create_initial_state(
            request_id=request_id,
            jurisdiction="CN",
            applicable_date=date.today().isoformat(),
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
        warnings = []
        if self.provider.synthetic:
            warnings.append("演示识别结果，不代表图片的真实 OCR 内容。")
        return OCRAnalysisResponse(
            request_id=request_id,
            provider=self.provider.name,
            synthetic=self.provider.synthetic,
            file_name=file_name,
            fields=fields,
            warnings=warnings,
            next_route=route_after_ocr(state),
        )

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
        return ConfirmLabelResponse(
            request_id=request.request_id,
            status="confirmed",
            next_route=next_route,
            confirmed_fields=sorted(request.fields),
            message="标签事实已由用户确认，可以进入配料规范化。",
        )

    @staticmethod
    def _validate_image(*, content: bytes, media_type: str) -> None:
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise InvalidImageError("暂不支持该文件类型，请上传 JPG、PNG、WebP 或 HEIC 图片。")
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
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if media_type in {"image/heic", "image/heif"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    return False
