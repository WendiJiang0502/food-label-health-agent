from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from food_label_agent.ocr.models import ConfirmLabelRequest
from food_label_agent.ocr.provider import DemoOCRProvider
from food_label_agent.ocr.service import InvalidImageError, OCRService


def test_demo_ocr_is_explicitly_synthetic_and_requires_confirmation() -> None:
    service = OCRService(DemoOCRProvider())

    result = asyncio.run(
        service.analyze(
            content=b"\xff\xd8\xffdemo-jpeg",
            file_name="label.jpg",
            media_type="image/jpeg",
        )
    )

    assert result.synthetic is True
    assert result.provider == "demo-ocr-provider"
    assert result.next_route == "confirm_label"
    assert result.fields[0].name == "ingredients"
    assert result.fields[0].requires_confirmation is True
    assert "演示识别结果" in result.warnings[0]


def test_ocr_rejects_unsupported_media_type() -> None:
    service = OCRService(DemoOCRProvider())

    with pytest.raises(InvalidImageError, match="暂不支持"):
        asyncio.run(
            service.analyze(
                content=b"document",
                file_name="label.pdf",
                media_type="application/pdf",
            )
        )


def test_ocr_rejects_mime_type_with_wrong_file_signature() -> None:
    service = OCRService(DemoOCRProvider())

    with pytest.raises(InvalidImageError, match="文件内容"):
        asyncio.run(
            service.analyze(
                content=b"this-is-not-a-jpeg",
                file_name="renamed.jpg",
                media_type="image/jpeg",
            )
        )


def test_confirmation_requires_non_empty_ingredients() -> None:
    with pytest.raises(ValidationError):
        ConfirmLabelRequest(
            request_id="request-1",
            applicable_date="2026-08-02",
            fields={"ingredients": "  "},
        )


def test_confirmed_fields_route_to_normalization() -> None:
    service = OCRService(DemoOCRProvider())
    request = ConfirmLabelRequest(
        request_id="request-1",
        applicable_date="2026-08-02",
        fields={
            "ingredients": "小麦粉、白砂糖",
            "allergen_statement": "含有小麦",
        },
    )

    result = service.confirm(request)

    assert result.status == "confirmed"
    assert result.next_route == "normalize_label"
    assert result.confirmed_fields == ["allergen_statement", "ingredients"]
