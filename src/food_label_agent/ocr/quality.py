"""Deterministic image-quality gate for label OCR."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .config import OCRConfigurationError


class QualitySeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class ImageQualityIssue:
    code: str
    severity: QualitySeverity
    message: str


@dataclass(frozen=True, slots=True)
class ImageQualityMetrics:
    width: int
    height: int
    blur_score: float
    brightness: float
    contrast: float
    foreground_ratio: float


@dataclass(frozen=True, slots=True)
class ImageQualityReport:
    metrics: ImageQualityMetrics
    issues: tuple[ImageQualityIssue, ...]

    @property
    def blocking_issues(self) -> tuple[ImageQualityIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity is QualitySeverity.BLOCKING
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            issue.message
            for issue in self.issues
            if issue.severity is QualitySeverity.WARNING
        )


class ImageQualityError(ValueError):
    def __init__(self, report: ImageQualityReport) -> None:
        self.report = report
        message = "；".join(issue.message for issue in report.blocking_issues)
        super().__init__(message or "图片质量不足，请重新拍摄。")


def assess_image_quality(content: bytes) -> ImageQualityReport:
    """Decode an image once and derive capture-quality signals without an LLM."""

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise OCRConfigurationError(
            "真实 OCR 已启用，但图片质量检查依赖尚未安装。"
        ) from exc

    encoded = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法解码图片，请重新选择原始照片。")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    _, foreground = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    foreground_ratio = float((foreground > 0).mean())

    metrics = ImageQualityMetrics(
        width=width,
        height=height,
        blur_score=blur_score,
        brightness=brightness,
        contrast=contrast,
        foreground_ratio=foreground_ratio,
    )
    return ImageQualityReport(metrics=metrics, issues=evaluate_quality_metrics(metrics))


def evaluate_quality_metrics(
    metrics: ImageQualityMetrics,
) -> tuple[ImageQualityIssue, ...]:
    issues: list[ImageQualityIssue] = []
    short_side = min(metrics.width, metrics.height)

    if short_side < 640:
        issues.append(
            ImageQualityIssue(
                "IMAGE_TOO_SMALL",
                QualitySeverity.BLOCKING,
                "图片分辨率过低，请靠近标签重新拍摄",
            )
        )
    elif short_side < 1000:
        issues.append(
            ImageQualityIssue(
                "IMAGE_SIZE_CAUTION",
                QualitySeverity.WARNING,
                "图片分辨率偏低，请重点核对小字",
            )
        )

    if metrics.blur_score < 60:
        issues.append(
            ImageQualityIssue(
                "IMAGE_BLURRY",
                QualitySeverity.BLOCKING,
                "图片明显模糊，请对焦配料文字后重新拍摄",
            )
        )
    elif metrics.blur_score < 100:
        issues.append(
            ImageQualityIssue(
                "IMAGE_BLUR_CAUTION",
                QualitySeverity.WARNING,
                "图片清晰度一般，请核对低置信度文字",
            )
        )

    if metrics.brightness < 35:
        issues.append(
            ImageQualityIssue(
                "IMAGE_TOO_DARK",
                QualitySeverity.BLOCKING,
                "图片过暗，请增加均匀光线后重新拍摄",
            )
        )
    elif metrics.brightness > 240:
        issues.append(
            ImageQualityIssue(
                "IMAGE_OVEREXPOSED",
                QualitySeverity.BLOCKING,
                "图片过曝，请避开强光和反光后重新拍摄",
            )
        )
    elif metrics.brightness < 55 or metrics.brightness > 225:
        issues.append(
            ImageQualityIssue(
                "IMAGE_EXPOSURE_CAUTION",
                QualitySeverity.WARNING,
                "图片曝光不均，请重点核对浅色或反光区域",
            )
        )

    if metrics.contrast < 18:
        issues.append(
            ImageQualityIssue(
                "IMAGE_LOW_CONTRAST",
                QualitySeverity.BLOCKING,
                "标签文字与背景对比不足，请调整角度重新拍摄",
            )
        )
    elif metrics.contrast < 28:
        issues.append(
            ImageQualityIssue(
                "IMAGE_CONTRAST_CAUTION",
                QualitySeverity.WARNING,
                "标签对比较低，请仔细核对识别文字",
            )
        )

    if metrics.foreground_ratio < 0.003:
        issues.append(
            ImageQualityIssue(
                "TEXT_AREA_TOO_SMALL",
                QualitySeverity.BLOCKING,
                "标签文字在画面中占比过小，请靠近后重新拍摄",
            )
        )
    elif metrics.foreground_ratio < 0.008:
        issues.append(
            ImageQualityIssue(
                "TEXT_AREA_CAUTION",
                QualitySeverity.WARNING,
                "标签文字占比较小，请确认没有遗漏配料行",
            )
        )

    return tuple(issues)
