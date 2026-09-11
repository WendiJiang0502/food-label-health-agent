from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from food_label_agent.ocr.config import OCRSettings
from food_label_agent.ocr.provider import OCRInput, OCRProviderError
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
    EnableDetectSplit: bool | None = None
    ConfigID: str | None = None
    WordsType: str | None = None


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
    assert client.general_request.EnableDetectSplit is True
    assert client.general_request.ConfigID == "OCR"
    assert client.general_request.WordsType == "2"
    assert client.table_request.UseNewModel is True


def test_tencent_provider_enlarges_720p_packaging_before_upload() -> None:
    client = FakeClient()
    source = np.full((720, 1280, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", source)
    assert ok

    asyncio.run(
        provider(client).analyze(
            OCRInput(
                content=encoded.tobytes(),
                file_name="label.jpg",
                media_type="image/jpeg",
                width=1280,
                height=720,
            )
        )
    )

    uploaded = cv2.imdecode(
        np.frombuffer(base64.b64decode(client.general_request.ImageBase64), np.uint8),
        cv2.IMREAD_COLOR,
    )
    assert min(uploaded.shape[:2]) == 1100


def test_table_row_repairs_energy_label_from_unambiguous_kilojoule_unit() -> None:
    client = FakeClient()
    original = client.RecognizeTableAccurateOCR

    def mislabeled_energy(request):
        response = original(request)
        response.TableDetections[0].Cells[2].Text = "脂"
        return response

    client.RecognizeTableAccurateOCR = mislabeled_energy
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

    table = {field.name: field for field in fields}["nutrition_table"]
    assert "能量\t271千焦" in table.raw_text


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
            "FOOD_LABEL_TENCENT_DETECT_SPLIT_ENABLED": "false",
            "FOOD_LABEL_TENCENT_PRINTED_TEXT_ONLY": "false",
            "FOOD_LABEL_TENCENT_TABLE_ENABLED": "false",
            "FOOD_LABEL_TENCENT_TABLE_NEW_MODEL": "true",
            "FOOD_LABEL_TENCENT_MAX_CONCURRENCY": "4",
            "FOOD_LABEL_TENCENT_QUEUE_TIMEOUT_SECONDS": "3.5",
            "FOOD_LABEL_TENCENT_CIRCUIT_FAILURE_THRESHOLD": "2",
            "FOOD_LABEL_TENCENT_CIRCUIT_RECOVERY_SECONDS": "45",
        }
    )

    assert settings.provider == "tencent"
    assert settings.tencent_region == "ap-shanghai"
    assert settings.tencent_detect_split_enabled is False
    assert settings.tencent_printed_text_only is False
    assert settings.tencent_table_enabled is False
    assert settings.tencent_table_new_model is True
    assert settings.tencent_max_concurrency == 4
    assert settings.tencent_queue_timeout_seconds == 3.5
    assert settings.tencent_circuit_failure_threshold == 2
    assert settings.tencent_circuit_recovery_seconds == 45


def test_tencent_retryable_failures_open_local_circuit() -> None:
    class TencentLikeError(Exception):
        def get_code(self):
            return "InternalError.ProviderUnavailable"

    client = FakeClient()
    client.GeneralAccurateOCR = lambda request: (_ for _ in ()).throw(
        TencentLikeError("temporary failure")
    )
    service = provider(
        client,
        tencent_circuit_failure_threshold=1,
        tencent_circuit_recovery_seconds=60,
    )
    image = OCRInput(
        content=b"image-bytes",
        file_name="label.jpg",
        media_type="image/jpeg",
        width=1000,
        height=800,
    )

    with pytest.raises(OCRProviderError, match="暂时无法完成识别"):
        asyncio.run(service.analyze(image))
    with pytest.raises(OCRProviderError) as blocked:
        asyncio.run(service.analyze(image))

    assert blocked.value.code == "TencentCloud.CircuitOpen"
    assert blocked.value.retryable is True


def test_tencent_unknown_internal_failure_is_retryable() -> None:
    class TencentLikeError(Exception):
        def get_code(self):
            return "FailedOperation.UnKnowError"

    client = FakeClient()
    attempts = 0

    def fail_twice_then_succeed(request):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TencentLikeError("internal error")
        return FakeClient().GeneralAccurateOCR(request)

    client.GeneralAccurateOCR = fail_twice_then_succeed
    asyncio.run(
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

    assert attempts == 3


def test_tencent_unopened_service_is_translated_to_safe_operator_error() -> None:
    class TencentLikeError(Exception):
        def get_code(self):
            return "FailedOperation.UnOpenError"

    client = FakeClient()
    client.GeneralAccurateOCR = lambda request: (_ for _ in ()).throw(
        TencentLikeError("raw provider message")
    )

    with pytest.raises(OCRProviderError) as captured:
        asyncio.run(
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

    assert captured.value.code == "FailedOperation.UnOpenError"
    assert captured.value.retryable is False
    assert "服务尚未开通" in str(captured.value)


def test_complete_coordinate_table_is_verified_by_table_api() -> None:
    client = FakeClient()
    texts = [
        ("配料：生牛乳", (100, 100, 500, 135)),
        ("每100克", (500, 200, 650, 235)),
        ("能量", (100, 260, 240, 295)),
        ("271千焦", (500, 260, 650, 295)),
        ("蛋白质", (100, 310, 240, 345)),
        ("3.2克", (500, 310, 650, 345)),
        ("脂肪", (100, 360, 240, 395)),
        ("3.6克", (500, 360, 650, 395)),
        ("碳水化合物", (100, 410, 240, 445)),
        ("4.9克", (500, 410, 650, 445)),
        ("钠", (100, 460, 240, 495)),
        ("55毫克", (500, 460, 650, 495)),
    ]
    client.GeneralAccurateOCR = lambda request: SimpleNamespace(
        TextDetections=[detection(text, 99, box) for text, box in texts]
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

    indexed = {field.name: field for field in fields}
    assert client.table_request is not None
    assert "钠\t55毫克" in indexed["nutrition_table"].raw_text


def test_unavailable_table_api_degrades_to_partial_coordinate_evidence() -> None:
    class PackageRunOutError(Exception):
        def get_code(self):
            return "ResourceUnavailable.ResourcePackageRunOut"

    client = FakeClient()
    client.RecognizeTableAccurateOCR = lambda request: (_ for _ in ()).throw(
        PackageRunOutError("table package unavailable")
    )

    provider_instance = provider(client)
    fields = asyncio.run(
        provider_instance.analyze(
            OCRInput(
                content=b"image-bytes",
                file_name="label.jpg",
                media_type="image/jpeg",
                width=1000,
                height=800,
            )
        )
    )

    assert "nutrition_basis" in {field.name for field in fields}
    assert provider_instance.name == "tencentcloud-general-accurate+coordinate-table"


def test_incomplete_full_image_table_uses_review_only_nutrition_crop() -> None:
    class CropAwareClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.table_calls = 0

        def GeneralAccurateOCR(self, request):
            return SimpleNamespace(
                TextDetections=[
                    detection("配料：鸡肉、猪肉", 99, (100, 100, 500, 140)),
                    detection("营养成分表", 99, (280, 360, 440, 400)),
                    detection("每100g", 99, (330, 410, 450, 445)),
                    detection("781N", 99, (350, 450, 440, 485)),
                ]
            )

        def RecognizeTableAccurateOCR(self, request):
            self.table_calls += 1
            if self.table_calls == 1:
                return SimpleNamespace(TableDetections=[])
            rows = [
                (0, "项目", "每100g"),
                (1, "能量", "78.1kJ"),
                (2, "蛋白质", "13.5g"),
                (3, "脂肪", "11.0g"),
                (4, "氧化化合物", "8.5g"),
                (5, "钠", "880mg"),
            ]
            cells = [
                value
                for row, label, amount in rows
                for value in (cell(row, 0, label), cell(row, 1, amount))
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

    client = CropAwareClient()
    source = np.full((800, 1000, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", source)
    assert ok

    fields = asyncio.run(
        provider(client).analyze(
            OCRInput(
                content=encoded.tobytes(),
                file_name="label.jpg",
                media_type="image/jpeg",
                width=1000,
                height=800,
            )
        )
    )

    table = {field.name: field for field in fields}["nutrition_table"]
    assert client.table_calls == 2
    assert "能量\t781kJ" in table.raw_text
    assert "碳水化合物\t8.5g" in table.raw_text
    assert table.bounding_box is not None
    assert table.bounding_box.x >= 0.06
    assert table.requires_confirmation is True
    assert table.confidence <= 0.5
