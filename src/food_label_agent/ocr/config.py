"""Server-only OCR configuration.

End users never provide these values. Deployments select an OCR provider through
process environment variables or their platform's secret/configuration manager.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ


class OCRConfigurationError(RuntimeError):
    """Raised when server-side OCR settings are invalid or unavailable."""


def _read_bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise OCRConfigurationError(f"{name} 必须是 true 或 false。")


def _read_threshold(values: Mapping[str, str], name: str, default: float) -> float:
    raw = values.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise OCRConfigurationError(f"{name} 必须是 0 到 1 之间的数字。") from exc
    if not 0 <= value <= 1:
        raise OCRConfigurationError(f"{name} 必须是 0 到 1 之间的数字。")
    return value


@dataclass(frozen=True, slots=True)
class OCRSettings:
    provider: str = "demo"
    version: str = "PP-OCRv6"
    device: str = "cpu"
    cache_dir: str | None = None
    use_orientation: bool = True
    use_unwarping: bool = True
    use_textline_orientation: bool = True
    general_threshold: float = 0.80
    allergen_threshold: float = 0.95

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> OCRSettings:
        source = environ if values is None else values
        provider = source.get("FOOD_LABEL_OCR_PROVIDER", "demo").strip().lower()
        if provider not in {"demo", "paddle"}:
            raise OCRConfigurationError(
                "FOOD_LABEL_OCR_PROVIDER 目前只支持 demo 或 paddle。"
            )
        return cls(
            provider=provider,
            version=source.get("FOOD_LABEL_OCR_VERSION", "PP-OCRv6").strip(),
            device=source.get("FOOD_LABEL_OCR_DEVICE", "cpu").strip(),
            cache_dir=source.get("FOOD_LABEL_OCR_CACHE_DIR") or None,
            use_orientation=_read_bool(
                source, "FOOD_LABEL_OCR_USE_ORIENTATION", True
            ),
            use_unwarping=_read_bool(
                source, "FOOD_LABEL_OCR_USE_UNWARPING", True
            ),
            use_textline_orientation=_read_bool(
                source, "FOOD_LABEL_OCR_USE_TEXTLINE_ORIENTATION", True
            ),
            general_threshold=_read_threshold(
                source, "FOOD_LABEL_OCR_GENERAL_THRESHOLD", 0.80
            ),
            allergen_threshold=_read_threshold(
                source, "FOOD_LABEL_OCR_ALLERGEN_THRESHOLD", 0.95
            ),
        )
