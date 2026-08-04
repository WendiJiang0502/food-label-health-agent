from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from food_label_agent.ocr.config import OCRSettings
from food_label_agent.ocr.provider import OCRInput
from food_label_agent.ocr.tencent_provider import TencentCloudOCRProvider


def point(x: int, y: int) -> SimpleNamespace:
    return SimpleNamespace(X=x, Y=y)


def detection(text: str, confidence: float, box: tuple[int, int, int, int]):
    left, top, right, bottom = box
    return SimpleNamespace(
        DetectedText=text,
        Confidence=confidence,
        Polygon=[
            point(left, top),
            point(right, top),
            point(right, bottom),
            point(left, bottom),
        ],
    )


def cell(row: int, column: int, text: str, confidence: float = 98):
    top = 300 + row * 40
    left = 100 + column * 220
    return SimpleNamespace(
        RowTl=row,
        ColTl=column,
        Text=text,
        Confidence=confidence,
        Polygon=[
            point(left, top),
            point(left + 200, top),
            point(left + 200, top + 35),
            point(left, top + 35),
        ],
    )


class FakeRequest:
    ImageBase64: str | None = None
    UseNewModel: bool | None = None


class FakeClient:
    def __init__(self) -> None:
        self.general_request = None
        self.table_request = None

    def GeneralAccurateOCR(self, request):
        self.general_request = request
        return SimpleNamespace(
            TextDetections=[
                detection("配料：生牛乳", 99, (100, 100, 500, 150)),
                detection("营养成分表", 98, (100, 260, 400, 295)),
                detection("每100克", 98, (320, 300, 480, 335)),
                detection("能量", 98, (100, 340, 260, 375)),
                detection("蛋白质", 98, (100, 380, 260, 415)),
            ]
        )

    def RecognizeTableAccurateOCR(self, request):
        self.table_request = request
        cells = [
            cell(0, 0, "项目"),
            cell(0, 1, "每100克"),
            cell(1, 0, "能量"),
            cell(1, 1, "271千焦"),
            cell(2, 0, "蛋白质"),
            cell(2, 1, "3.2克"),
            cell(3, 0, "脂肪"),
            cell(3, 1, "3.6克"),
            cell(4, 0, "碳水化合物"),
            cell(4, 1, "4.9克"),
            cell(5, 0, "钠"),
            cell(5, 1, "55毫克"),
        ]
        return SimpleNamespace(
            TableDetections=[
                SimpleNamespace(
                    Cells=cells,
                    TableCoordPoint=[
                        point(100, 300),
                        point(520, 300),
                        point(520, 575),
                        point(100, 575),
                    ],
                )
            ]
        )


def provider(client: FakeClient, **settings) -> TencentCloudOCRProvider:
    return TencentCloudOCRProvider(
        OCRSettings(provider="tencent", **settings),
        client=client,
        general_request_factory=FakeRequest,
        table_request_factory=FakeRequest,
    )


def test_tencent_provider_maps_general_text_and_table_cells() -> None:
    client = FakeClient()
    fields = asyncio.run(
        provider(client).analyze(
            OCRInput(
                content=b"image-bytes",
                file_name="label.jpg",
                media_type="image/jpeg",
                width=1000,
                height=800,
            )
        )
    )

    indexed = {field.name: field for field in fields}
    assert indexed["ingredients"].raw_text == "生牛乳"
    assert indexed["ingredients"].bounding_box is not None
    assert indexed["ingredients"].bounding_box.x == pytest.approx(0.1)
    assert indexed["nutrition_basis"].raw_text == "每100克"
    assert indexed["nutrition_table"].nutrition_table is not None
    assert indexed["nutrition_table"].nutrition_table.rows[1] == ["能量", "271千焦"]
    assert "钠\t55毫克" in indexed["nutrition_table"].raw_text
    assert indexed["nutrition_table"].requires_confirmation is True
    assert client.general_request.ImageBase64
    assert client.table_request.UseNewModel is False


def test_tencent_provider_skips_table_api_without_nutrition_cues() -> None:
    client = FakeClient()
    client.GeneralAccurateOCR = lambda request: SimpleNamespace(
        TextDetections=[detection("配料：燕麦、可可粉", 98, (10, 20, 500, 80))]
    )

    fields = asyncio.run(
        provider(client).analyze(
            OCRInput(
                content=b"image-bytes",
                file_name="label.jpg",
                media_type="image/jpeg",
                width=1000,
                height=800,
            )
        )
    )

    assert {field.name for field in fields} == {"ingredients"}
    assert client.table_request is None


def test_tencent_configuration_can_disable_table_api() -> None:
    client = FakeClient()
    fields = asyncio.run(
        provider(client, tencent_table_enabled=False).analyze(
            OCRInput(
                content=b"image-bytes",
                file_name="label.jpg",
                media_type="image/jpeg",
                width=1000,
                height=800,
            )
        )
    )

    assert "nutrition_table" not in {field.name for field in fields}
    assert client.table_request is None


def test_tencent_environment_settings_are_server_only() -> None:
    settings = OCRSettings.from_environment(
        {
            "FOOD_LABEL_OCR_PROVIDER": "tencent",
            "FOOD_LABEL_TENCENT_REGION": "ap-shanghai",
            "FOOD_LABEL_TENCENT_TABLE_ENABLED": "false",
            "FOOD_LABEL_TENCENT_TABLE_NEW_MODEL": "true",
        }
    )

    assert settings.provider == "tencent"
    assert settings.tencent_region == "ap-shanghai"
    assert settings.tencent_table_enabled is False
    assert settings.tencent_table_new_model is True
