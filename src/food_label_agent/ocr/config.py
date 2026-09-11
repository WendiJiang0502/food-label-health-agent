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


def _read_int_range(
    values: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int
) -> int:
    raw = values.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise OCRConfigurationError(
            f"{name} 必须是 {minimum} 到 {maximum} 之间的整数。"
        ) from exc
    if not minimum <= value <= maximum:
        raise OCRConfigurationError(
            f"{name} 必须是 {minimum} 到 {maximum} 之间的整数。"
        )
    return value


def _read_positive_float(
    values: Mapping[str, str], name: str, default: float, *, maximum: float
) -> float:
    raw = values.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise OCRConfigurationError(f"{name} 必须是正数。") from exc
    if not 0 < value <= maximum:
        raise OCRConfigurationError(f"{name} 必须是大于 0 且不超过 {maximum} 的数字。")
    return value


@dataclass(frozen=True, slots=True)
class OCRSettings:
    provider: str = "demo"
    version: str = "PP-OCRv6"
    device: str = "cpu"
    cache_dir: str | None = None
    use_orientation: bool = False
    use_unwarping: bool = False
    use_textline_orientation: bool = True
    fast_path_enabled: bool = True
    fast_detection_model: str = "PP-OCRv6_medium_det"
    fast_recognition_model: str = "PP-OCRv6_small_rec"
    general_threshold: float = 0.80
    allergen_threshold: float = 0.95
    table_parser: str = "disabled"
    table_ocr_version: str = "PP-OCRv5"
    tencent_region: str = "ap-guangzhou"
    tencent_detect_split_enabled: bool = True
    tencent_printed_text_only: bool = True
    tencent_table_enabled: bool = True
    tencent_table_new_model: bool = True
    tencent_max_concurrency: int = 2
    tencent_queue_timeout_seconds: float = 10.0
    tencent_circuit_failure_threshold: int = 5
    tencent_circuit_recovery_seconds: float = 30.0

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> OCRSettings:
        source = environ if values is None else values
        provider = source.get("FOOD_LABEL_OCR_PROVIDER", "demo").strip().lower()
        if provider not in {"demo", "paddle", "tencent"}:
            raise OCRConfigurationError(
                "FOOD_LABEL_OCR_PROVIDER 目前只支持 demo、paddle 或 tencent。"
            )
        table_parser = (
            source.get("FOOD_LABEL_OCR_TABLE_PARSER", "disabled").strip().lower()
        )
        if table_parser not in {"disabled", "ppstructure"}:
            raise OCRConfigurationError(
                "FOOD_LABEL_OCR_TABLE_PARSER 目前只支持 disabled 或 ppstructure。"
            )
        return cls(
            provider=provider,
            version=source.get("FOOD_LABEL_OCR_VERSION", "PP-OCRv6").strip(),
            device=source.get("FOOD_LABEL_OCR_DEVICE", "cpu").strip(),
            cache_dir=source.get("FOOD_LABEL_OCR_CACHE_DIR") or None,
            use_orientation=_read_bool(source, "FOOD_LABEL_OCR_USE_ORIENTATION", False),
            use_unwarping=_read_bool(source, "FOOD_LABEL_OCR_USE_UNWARPING", False),
            use_textline_orientation=_read_bool(
                source, "FOOD_LABEL_OCR_USE_TEXTLINE_ORIENTATION", True
            ),
            fast_path_enabled=_read_bool(source, "FOOD_LABEL_OCR_FAST_PATH", True),
            fast_detection_model=source.get(
                "FOOD_LABEL_OCR_FAST_DETECTION_MODEL", "PP-OCRv6_medium_det"
            ).strip(),
            fast_recognition_model=source.get(
                "FOOD_LABEL_OCR_FAST_RECOGNITION_MODEL", "PP-OCRv6_small_rec"
            ).strip(),
            general_threshold=_read_threshold(
                source, "FOOD_LABEL_OCR_GENERAL_THRESHOLD", 0.80
            ),
            allergen_threshold=_read_threshold(
                source, "FOOD_LABEL_OCR_ALLERGEN_THRESHOLD", 0.95
            ),
            table_parser=table_parser,
            table_ocr_version=source.get(
                "FOOD_LABEL_OCR_TABLE_OCR_VERSION", "PP-OCRv5"
            ).strip(),
            tencent_region=source.get(
                "FOOD_LABEL_TENCENT_REGION", "ap-guangzhou"
            ).strip(),
            tencent_detect_split_enabled=_read_bool(
                source, "FOOD_LABEL_TENCENT_DETECT_SPLIT_ENABLED", True
            ),
            tencent_printed_text_only=_read_bool(
                source, "FOOD_LABEL_TENCENT_PRINTED_TEXT_ONLY", True
            ),
            tencent_table_enabled=_read_bool(
                source, "FOOD_LABEL_TENCENT_TABLE_ENABLED", True
            ),
            tencent_table_new_model=_read_bool(
                source, "FOOD_LABEL_TENCENT_TABLE_NEW_MODEL", True
            ),
            tencent_max_concurrency=_read_int_range(
                source,
                "FOOD_LABEL_TENCENT_MAX_CONCURRENCY",
                2,
                minimum=1,
                maximum=16,
            ),
            tencent_queue_timeout_seconds=_read_positive_float(
                source,
                "FOOD_LABEL_TENCENT_QUEUE_TIMEOUT_SECONDS",
                10.0,
                maximum=120.0,
            ),
            tencent_circuit_failure_threshold=_read_int_range(
                source,
                "FOOD_LABEL_TENCENT_CIRCUIT_FAILURE_THRESHOLD",
                5,
                minimum=1,
                maximum=100,
            ),
            tencent_circuit_recovery_seconds=_read_positive_float(
                source,
                "FOOD_LABEL_TENCENT_CIRCUIT_RECOVERY_SECONDS",
                30.0,
                maximum=600.0,
            ),
        )
