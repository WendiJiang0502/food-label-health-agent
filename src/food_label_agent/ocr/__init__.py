"""OCR provider contracts and application service."""

from .config import OCRConfigurationError, OCRSettings
from .paddle_provider import PaddleOCRProvider, create_ocr_provider
from .provider import DemoOCRProvider, OCRProvider
from .service import OCRService

__all__ = [
    "DemoOCRProvider",
    "OCRConfigurationError",
    "OCRProvider",
    "OCRService",
    "OCRSettings",
    "PaddleOCRProvider",
    "create_ocr_provider",
]
