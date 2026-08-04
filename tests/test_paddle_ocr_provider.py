from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from food_label_agent.ocr.config import OCRConfigurationError, OCRSettings
from food_label_agent.ocr.paddle_provider import PaddleOCRProvider, create_ocr_provider
from food_label_agent.ocr.provider import DemoOCRProvider, OCRInput


class FakePaddleEngine:
    def __init__(self) -> None:
        self.received_path: Path | None = None

    def predict(self, path: str):
        self.received_path = Path(path)
        assert self.received_path.exists()
        return [
            {
                "res": {
                    "rec_texts": [
                        "配料表：小麦粉、白砂糖",
                        "植物油、食用盐",
                        "本产品含有小麦，可能含有花生",
                        "营养成分表 每100克",
                    ],
                    "rec_scores": [0.98, 0.96, 0.99, 0.97],
                    "rec_boxes": [
                        [100, 100, 900, 180],
                        [100, 200, 800, 280],
                        [100, 400, 1000, 480],
                        [100, 600, 700, 680],
                    ],
                }
            }
        ]


def test_default_server_configuration_uses_demo_provider() -> None:
    settings = OCRSettings.from_environment({})
    provider = create_ocr_provider(settings)

    assert isinstance(provider, DemoOCRProvider)
    assert provider.synthetic is True
    assert settings.table_parser == "disabled"
    assert settings.table_ocr_version == "PP-OCRv5"
    assert settings.use_orientation is False
    assert settings.use_unwarping is False
    assert settings.fast_path_enabled is True
    assert settings.fast_detection_model == "PP-OCRv6_medium_det"
    assert settings.fast_recognition_model == "PP-OCRv6_small_rec"


def test_invalid_boolean_configuration_fails_fast() -> None:
    with pytest.raises(OCRConfigurationError, match="true 或 false"):
        OCRSettings.from_environment({"FOOD_LABEL_OCR_USE_UNWARPING": "maybe"})


def test_invalid_table_parser_configuration_fails_fast() -> None:
    with pytest.raises(OCRConfigurationError, match="TABLE_PARSER"):
        OCRSettings.from_environment({"FOOD_LABEL_OCR_TABLE_PARSER": "magic"})


def test_provider_name_discloses_structured_table_pipeline() -> None:
    provider = PaddleOCRProvider(
        OCRSettings(provider="paddle", table_parser="ppstructure"),
        engine_factory=lambda **_: FakePaddleEngine(),
        structure_factory=lambda **_: object(),
    )

    assert provider.name == "paddleocr-pp-ocrv6-cascade+ppstructurev3-pp-ocrv5"


def test_fast_path_uses_small_recognizer_then_medium_fallback() -> None:
    calls = []

    def factory(**options):
        calls.append(options)
        return FakePaddleEngine()

    provider = PaddleOCRProvider(
        OCRSettings(provider="paddle"), engine_factory=factory
    )
    asyncio.run(
        provider.analyze(
            OCRInput(
                content=b"\x89PNG\r\n\x1a\nimage",
                file_name="label.png",
                media_type="image/png",
                width=1200,
                height=800,
            )
        )
    )

    assert len(calls) == 2
    assert calls[0]["text_detection_model_name"] == "PP-OCRv6_medium_det"
    assert calls[0]["text_recognition_model_name"] == "PP-OCRv6_small_rec"
    assert calls[0]["use_textline_orientation"] is False
    assert calls[1]["ocr_version"] == "PP-OCRv6"


def test_complete_fast_path_skips_medium_engine() -> None:
    class CompleteFastEngine:
        def predict(self, path: str):
            del path
            texts = [
                "配料：生牛乳",
                "每100克",
                "能量",
                "271千焦",
                "蛋白质",
                "3.2克",
                "脂肪",
                "3.6克",
                "碳水化合物",
                "4.9克",
                "钠",
                "55毫克",
            ]
            boxes = [[100, 100, 300, 130], [500, 180, 620, 210]]
            for index in range(5):
                y = 240 + index * 50
                boxes.extend([[150, y, 300, y + 30], [500, y, 650, y + 30]])
            return [
                {
                    "res": {
                        "rec_texts": texts,
                        "rec_scores": [0.99] * len(texts),
                        "rec_boxes": boxes,
                    }
                }
            ]

    calls = []

    def factory(**options):
        calls.append(options)
        return CompleteFastEngine()

    provider = PaddleOCRProvider(
        OCRSettings(provider="paddle"), engine_factory=factory
    )
    fields = asyncio.run(
        provider.analyze(
            OCRInput(
                content=b"\x89PNG\r\n\x1a\nimage",
                file_name="label.png",
                media_type="image/png",
                width=1000,
                height=1000,
            )
        )
    )

    assert len(calls) == 1
    assert {field.name for field in fields} >= {
        "ingredients",
        "nutrition_basis",
        "nutrition_table",
    }


def test_paddle_provider_maps_lines_and_deletes_temporary_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = FakePaddleEngine()
    captured_options = {}
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)

    def factory(**options):
        captured_options.update(options)
        return engine

    settings = OCRSettings(
        provider="paddle", use_unwarping=False, cache_dir=str(tmp_path / "models")
    )
    provider = PaddleOCRProvider(settings, engine_factory=factory)
    fields = asyncio.run(
        provider.analyze(
            OCRInput(
                content=b"\x89PNG\r\n\x1a\nimage",
                file_name="label.png",
                media_type="image/png",
                width=1200,
                height=800,
            )
        )
    )

    indexed = {field.name: field for field in fields}
    assert captured_options["ocr_version"] == "PP-OCRv6"
    assert captured_options["use_doc_unwarping"] is False
    assert Path(os.environ["PADDLE_PDX_CACHE_HOME"]) == tmp_path / "models"
    assert indexed["ingredients"].raw_text == "小麦粉、白砂糖\n植物油、食用盐"
    assert indexed["ingredients"].requires_confirmation is True
    assert indexed["ingredients"].confidence < 0.85
    assert indexed["ingredients"].bounding_box is not None
    assert indexed["ingredients"].bounding_box.x == pytest.approx(100 / 1200)
    assert indexed["ingredients"].bounding_box.y == pytest.approx(100 / 800)
    assert indexed["ingredients"].bounding_box.width == pytest.approx(800 / 1200)
    assert indexed["ingredients"].bounding_box.height == pytest.approx(180 / 800)
    assert "可能含有花生" in indexed["allergen_statement"].raw_text
    assert "每100克" in indexed["nutrition_basis"].raw_text
    assert engine.received_path is not None
    assert not engine.received_path.exists()


def test_paddle_provider_falls_back_to_full_text_for_manual_review() -> None:
    class NoHeadingEngine:
        def predict(self, path: str):
            return [{"res": {"rec_texts": ["小麦粉、糖、盐"], "rec_scores": [0.94]}}]

    provider = PaddleOCRProvider(
        OCRSettings(provider="paddle"), engine_factory=lambda **_: NoHeadingEngine()
    )
    fields = asyncio.run(
        provider.analyze(
            OCRInput(
                content=b"\xff\xd8\xffimage",
                file_name="label.jpg",
                media_type="image/jpeg",
            )
        )
    )

    assert len(fields) == 1
    assert fields[0].name == "unclassified_text"
    assert fields[0].raw_text == "小麦粉、糖、盐"
    assert fields[0].requires_confirmation is True
