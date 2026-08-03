"""Optional PP-StructureV3 adapter for nutrition-table row/column evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from html.parser import HTMLParser
from typing import Any

from .config import OCRConfigurationError, OCRSettings
from .models import OCRFieldResult
from .nutrition import validate_nutrition_table

_NUTRIENT_TERMS = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠")


class PPStructureNutritionParser:
    """Load PP-StructureV3 only when explicitly enabled by server configuration."""

    def __init__(
        self,
        settings: OCRSettings,
        *,
        engine_factory: Callable[..., Any] | None = None,
    ) -> None:
        factory = engine_factory or _load_structure_factory()
        self._threshold = settings.general_threshold
        self._engine = factory(
            device=settings.device,
            # PP-StructureV3 currently supports OCR v3/v4/v5 independently
            # from the main PP-OCRv6 text pipeline.
            ocr_version=settings.table_ocr_version,
            use_doc_orientation_classify=settings.use_orientation,
            use_doc_unwarping=settings.use_unwarping,
            use_textline_orientation=settings.use_textline_orientation,
            use_table_recognition=True,
            use_formula_recognition=False,
            use_chart_recognition=False,
            use_seal_recognition=False,
            use_region_detection=False,
            text_rec_score_thresh=settings.general_threshold,
        )

    def analyze(self, image_path: str) -> list[OCRFieldResult]:
        fields: list[OCRFieldResult] = []
        for result in self._engine.predict(image_path):
            payload = _result_payload(result)
            for table_index, table in enumerate(payload.get("table_res_list", [])):
                if not isinstance(table, Mapping):
                    continue
                rows = parse_table_html(str(table.get("pred_html", "")))
                if not _looks_like_nutrition_table(rows):
                    continue
                table_data = validate_nutrition_table(rows)
                scores = _table_scores(table)
                confidence = round(sum(scores) / len(scores), 6) if scores else 0.0
                requires_confirmation = confidence < self._threshold or any(
                    issue.severity == "blocking" for issue in table_data.issues
                )
                fields.append(
                    OCRFieldResult(
                        name=f"nutrition_table_{table_index + 1}",
                        label="营养成分表（结构化）",
                        raw_text="\n".join("\t".join(row) for row in rows),
                        confidence=confidence,
                        requires_confirmation=requires_confirmation,
                        nutrition_table=table_data,
                    )
                )
        return fields


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None


def parse_table_html(value: str) -> list[list[str]]:
    parser = _TableHTMLParser()
    parser.feed(value)
    return parser.rows


def _looks_like_nutrition_table(rows: list[list[str]]) -> bool:
    text = " ".join(cell for row in rows for cell in row)
    return "营养成分" in text or sum(term in text for term in _NUTRIENT_TERMS) >= 2


def _table_scores(table: Mapping[str, Any]) -> list[float]:
    ocr = table.get("table_ocr_pred", {})
    if not isinstance(ocr, Mapping):
        return []
    return [max(0.0, min(float(value), 1.0)) for value in ocr.get("rec_scores", [])]


def _result_payload(result: Any) -> Mapping[str, Any]:
    candidate: Any = result
    if not isinstance(candidate, Mapping):
        candidate = getattr(result, "json", None)
        if callable(candidate):
            candidate = candidate()
    if not isinstance(candidate, Mapping):
        raise OCRConfigurationError("PP-StructureV3 返回了无法解析的结果格式。")
    nested = candidate.get("res")
    return nested if isinstance(nested, Mapping) else candidate


def _load_structure_factory() -> Callable[..., Any]:
    try:
        from paddleocr import PPStructureV3
    except ImportError as exc:
        raise OCRConfigurationError(
            "服务器启用了 PP-StructureV3，但尚未安装 PaddleOCR。"
        ) from exc
    return PPStructureV3
