from __future__ import annotations

from datetime import date

import cv2
import numpy as np
import pytest

from food_label_agent.alternatives.evidence_audit import (
    audit_product_label,
    label_content_hash,
)
from food_label_agent.alternatives.models import ProductRecord
from food_label_agent.alternatives.packaging_evidence import (
    PackagingEvidenceStore,
    attach_verified_snapshot,
)


def _png() -> bytes:
    image = np.full((800, 640, 3), 255, dtype=np.uint8)
    for index, text in enumerate(("INGREDIENTS", "NUTRITION", "SKU-1", "100G")):
        cv2.putText(
            image,
            text,
            (40, 120 + index * 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.6,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_low_resolution_or_blank_image_is_not_reviewable(tmp_path) -> None:
    ok, encoded = cv2.imencode(
        ".png", np.full((800, 640, 3), 255, dtype=np.uint8)
    )
    assert ok
    with pytest.raises(ValueError, match="contrast"):
        PackagingEvidenceStore(tmp_path).ingest(
            encoded.tobytes(),
            evidence_kind="combined",
            artifact_type="packaging_photo",
            source_url="capture://store/blank",
            captured_at=date(2026, 8, 30),
            sku="SKU-1",
            specification="100克",
            reviewer_id="reviewer-one",
        )


def _product(snapshot: dict | None = None) -> ProductRecord:
    payload = {
        "product_id": "cn-official:test:sku-1",
        "display_name": "测试商品",
        "brand": "测试品牌",
        "sku": "SKU-1",
        "specification": "100克",
        "category": "snack",
        "region": "CN",
        "use_case": "加餐",
        "catalog_scope": "official_cn_catalog",
        "label": {
            "evidence_id": "evidence.test.sku-1",
            "ingredients_text": "燕麦",
            "allergen_statement": "本产品含麸质谷物",
            "nutrition_basis_text": "每100克",
            "nutrition_rows": [
                ["项目", "每100克"],
                ["能量", "1000千焦"],
                ["蛋白质", "10克"],
                ["脂肪", "5克"],
                ["碳水化合物", "60克"],
                ["钠", "100毫克"],
            ],
            "confirmed_by": "human_review",
            "confirmed_at": "2026-08-29",
            "source_url": "https://brand.example/product/sku-1",
            "content_hash": f"sha256:{'0' * 64}",
            "source_authority": "manufacturer",
            "source_access_region": "CN",
            "packaging_snapshots": [snapshot] if snapshot else [],
        },
    }
    provisional = ProductRecord.model_validate(payload)
    payload["label"]["content_hash"] = label_content_hash(provisional)
    return ProductRecord.model_validate(payload)


def test_content_addressed_snapshot_requires_independent_second_review(tmp_path) -> None:
    store = PackagingEvidenceStore(tmp_path)
    pending = store.ingest(
        _png(),
        evidence_kind="combined",
        artifact_type="packaging_photo",
        source_url="capture://store/sku-1",
        captured_at=date(2026, 8, 29),
        sku="SKU-1",
        specification="100克",
        reviewer_id="reviewer-one",
    )

    assert pending.review_status == "pending_second_review"
    assert store.verify_artifact(pending)
    with pytest.raises(ValueError, match="independent"):
        store.add_second_review(
            pending,
            reviewer_id="reviewer-one",
            reviewed_at=date(2026, 8, 29),
        )

    verified = store.add_second_review(
        pending,
        reviewer_id="reviewer-two",
        reviewed_at=date(2026, 8, 29),
    )
    audit = audit_product_label(_product(verified.model_dump(mode="json")))
    assert audit["ingredient_snapshot_ready"] is True
    assert audit["nutrition_snapshot_ready"] is True
    assert audit["complete_packaging_snapshot_ready"] is True

    attached = attach_verified_snapshot(_product(), verified)
    assert attached.label.content_hash == label_content_hash(attached)
    assert attached.label.packaging_snapshots == [verified]


def test_snapshot_cannot_be_attached_to_a_different_sku(tmp_path) -> None:
    store = PackagingEvidenceStore(tmp_path)
    pending = store.ingest(
        _png(),
        evidence_kind="combined",
        artifact_type="packaging_photo",
        source_url="capture://store/other-sku",
        captured_at=date(2026, 8, 29),
        sku="OTHER-SKU",
        specification="100克",
        reviewer_id="reviewer-one",
    )
    verified = store.add_second_review(
        pending,
        reviewer_id="reviewer-two",
        reviewed_at=date(2026, 8, 29),
    )

    with pytest.raises(ValueError, match="does not match"):
        attach_verified_snapshot(_product(), verified)


def test_official_page_capture_and_legacy_url_do_not_count_as_package_photo(
    tmp_path,
) -> None:
    store = PackagingEvidenceStore(tmp_path)
    pending = store.ingest(
        _png(),
        evidence_kind="combined",
        artifact_type="official_page_capture",
        source_url="https://brand.example/product/sku-1",
        captured_at=date(2026, 8, 29),
        sku="SKU-1",
        specification="100克",
        reviewer_id="reviewer-one",
        allowed_hosts={"brand.example"},
    )
    verified = store.add_second_review(
        pending,
        reviewer_id="reviewer-two",
        reviewed_at=date(2026, 8, 29),
    )
    payload = verified.model_dump(mode="json")
    product = _product(payload)
    product = product.model_copy(
        update={
            "label": product.label.model_copy(
                update={"ingredients_image_url": "https://brand.example/label.jpg"}
            )
        }
    )

    audit = audit_product_label(product)
    assert audit["official_page_snapshot_count"] == 1
    assert audit["packaging_snapshot_ready"] is False


def test_artifact_tampering_prevents_second_review(tmp_path) -> None:
    store = PackagingEvidenceStore(tmp_path)
    pending = store.ingest(
        _png(),
        evidence_kind="ingredients",
        artifact_type="packaging_photo",
        source_url="capture://store/sku-1",
        captured_at=date(2026, 8, 29),
        sku="SKU-1",
        specification="100克",
        reviewer_id="reviewer-one",
    )
    (tmp_path / pending.artifact_path).write_bytes(b"changed")

    with pytest.raises(ValueError, match="changed"):
        store.add_second_review(
            pending,
            reviewer_id="reviewer-two",
            reviewed_at=date(2026, 8, 29),
        )
