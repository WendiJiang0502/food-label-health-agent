"""OCR provider contracts and application service."""

from .provider import DemoOCRProvider, OCRProvider
from .service import OCRService

__all__ = ["DemoOCRProvider", "OCRProvider", "OCRService"]
