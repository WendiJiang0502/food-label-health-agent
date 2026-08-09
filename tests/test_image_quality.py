from __future__ import annotations

import asyncio

import pytest

from food_label_agent.ocr.models import OCRFieldResult
from food_label_agent.ocr.provider import OCRInput
from food_label_agent.ocr.quality import (
    ImageQualityError,
    ImageQualityIssue,
    ImageQualityMetrics,
    ImageQualityReport,
    QualitySeverity,
    evaluate_quality_metrics,
)
from food_label_agent.ocr.service import OCRService


class RecordingRealProvider:
    name = "recording-real-provider"
    synthetic = False

    def __init__(self) -> None:
        self.received: OCRInput | None = None

    async def analyze(self, image: OCRInput) -> list[OCRFieldResult]:
        self.received = image
        return [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="小麦粉、白砂糖",
                confidence=0.84,
                requires_confirmation=True,
            )
        ]


def test_quality_metrics_block_blurry_small_text_image() -> None:
    metrics = ImageQualityMetrics(
        width=320,
        height=900,
        blur_score=22,
        brightness=130,
        contrast=42,
        foreground_ratio=0.001,
    )

    issues = evaluate_quality_metrics(metrics)
    blocking_codes = {
        issue.code for issue in issues if issue.severity is QualitySeverity.BLOCKING
    }

    assert blocking_codes == {
        "IMAGE_TOO_SMALL",
        "IMAGE_BLURRY",
        "TEXT_AREA_TOO_SMALL",
    }


def test_compact_but_sharp_crop_is_warned_not_blocked_by_size() -> None:
    metrics = ImageQualityMetrics(
        width=500,
        height=900,
        blur_score=240,
        brightness=130,
        contrast=42,
        foreground_ratio=0.08,
    )

    issues = evaluate_quality_metrics(metrics)

    assert [(issue.code, issue.severity) for issue in issues] == [
        ("IMAGE_SIZE_CAUTION", QualitySeverity.WARNING)
    ]


def test_geometry_and_local_focus_signals_are_review_warnings() -> None:
    metrics = ImageQualityMetrics(
        width=1200,
        height=1600,
        blur_score=240,
        brightness=130,
        contrast=42,
        foreground_ratio=0.08,
        text_skew_degrees=14,
        text_angle_spread=18,
        local_sharpness_ratio=22,
    )

    issues = evaluate_quality_metrics(metrics)

    assert {issue.code for issue in issues} == {
        "IMAGE_PERSPECTIVE_CAUTION",
        "IMAGE_LOCAL_WARP_CAUTION",
        "IMAGE_LOCAL_FOCUS_CAUTION",
    }
    assert all(issue.severity is QualitySeverity.WARNING for issue in issues)


def test_quality_gate_stops_provider_before_ocr() -> None:
    provider = RecordingRealProvider()
    report = ImageQualityReport(
        metrics=ImageQualityMetrics(500, 900, 22, 130, 42, 0.001),
        issues=(
            ImageQualityIssue("IMAGE_BLURRY", QualitySeverity.BLOCKING, "图片明显模糊"),
        ),
    )
    service = OCRService(provider, quality_assessor=lambda _: report)

    with pytest.raises(ImageQualityError, match="图片明显模糊"):
        asyncio.run(
            service.analyze(
                content=b"\xff\xd8\xffimage",
                file_name="label.jpg",
                media_type="image/jpeg",
            )
        )

    assert provider.received is None


def test_quality_warning_reaches_response_and_dimensions_reach_provider() -> None:
    provider = RecordingRealProvider()
    report = ImageQualityReport(
        metrics=ImageQualityMetrics(1200, 1600, 88, 130, 42, 0.04),
        issues=(
            ImageQualityIssue(
                "IMAGE_BLUR_CAUTION",
                QualitySeverity.WARNING,
                "图片清晰度一般，请核对低置信度文字",
            ),
        ),
    )
    service = OCRService(provider, quality_assessor=lambda _: report)

    result = asyncio.run(
        service.analyze(
            content=b"\xff\xd8\xffimage",
            file_name="label.jpg",
            media_type="image/jpeg",
        )
    )

    assert provider.received is not None
    assert provider.received.width == 1200
    assert provider.received.height == 1600
    assert result.warnings == ["图片清晰度一般，请核对低置信度文字"]
    assert result.image_quality is not None
    assert result.image_quality.blur_score == 88
