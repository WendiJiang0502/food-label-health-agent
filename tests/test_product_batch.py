import asyncio

import httpx
import pytest

from food_label_agent.alternatives.batch import (
    BatchKnowledge,
    StaleBatchError,
    barcode_valid,
    normalized_specification,
)
from food_label_agent.alternatives.knowledge import ProductKnowledgeStore


def setup_batch(tmp_path):
    store = ProductKnowledgeStore(tmp_path / "batch.sqlite3")
    raw = {
        "code": "4006381333931",
        "brands": "测试品牌",
        "product_name": "原味燕麦",
        "quantity": "500g",
        "nutrition_data_per": "100g",
        "ingredients_text": "燕麦",
        "nutriments": {"sugars_100g": 5},
    }
    store.ingest(raw, "breakfast_cereal")
    batch = BatchKnowledge(store)
    batch.assess_all()
    return store, batch, raw


def selection(item, field="identity"):
    result = {"id": item["id"], "revision": item["revision"]}
    if field != "identity":
        result["evidence_id"] = next(
            v["evidence_id"]
            for v in item["field_evidence"]["observations"]
            if v["field"] == field
        )
    return result


def test_identity_normalization():
    assert barcode_valid("4006381333931")
    assert not barcode_valid("4006381333932")
    assert (
        normalized_specification("0.5 kg")
        == normalized_specification("500克")
        == "500g"
    )
    assert normalized_specification("1L") == "1000ml"
    assert normalized_specification("500ml") != "500g"


def test_review_capabilities_do_not_imply_recommendation(tmp_path):
    _, batch, _ = setup_batch(tmp_path)
    item = batch.snapshot()["items"][0]
    assert item["capabilities"]["source_numeric_fields"] == ["sugars"]
    assert not item["capabilities"]["nutrition_comparison_fields"]
    batch.review(
        [selection(item)], action="adopt", field="identity", reviewer="reviewer-a"
    )
    batch.review(
        [selection(item, "sugars")],
        action="adopt",
        field="sugars",
        reviewer="reviewer-a",
    )
    current = batch.snapshot()["items"][0]
    assert current["capabilities"]["nutrition_comparison_fields"] == ["sugars"]
    assert not current["capabilities"]["strict_restriction_judgment"]
    assert not current["capabilities"]["recommendation_eligible"]


def test_stale_batch_is_atomic_and_reviews_expire_with_version(tmp_path):
    store, batch, raw = setup_batch(tmp_path)
    item = batch.snapshot()["items"][0]
    batch.review(
        [selection(item)], action="adopt", field="identity", reviewer="reviewer-a"
    )
    store.ingest({**raw, "quantity": "250g"}, "breakfast_cereal")
    with pytest.raises(StaleBatchError):
        batch.review(
            [selection(item, "sugars")],
            action="adopt",
            field="sugars",
            reviewer="reviewer-a",
        )
    new = batch.item(raw["code"])
    assert new["identity"]["changed_since_previous_version"]
    assert new["approved_fields"] == []
    assert not new["capabilities"]["source_numeric_fields"]


def test_conflicts_cannot_be_bulk_adopted(tmp_path):
    store, batch, raw = setup_batch(tmp_path)
    with store.connect() as db:
        digest = db.execute("SELECT content_hash FROM candidates").fetchone()[0]
    store.save_ocr_draft(
        raw["code"],
        {
            "images": {
                "nutrition": {
                    "source_url": "https://images.openfoodfacts.org/example.jpg",
                    "image_sha256": "image",
                    "fields": [
                        {"name": "nutrition_table", "raw_text": "每100克\n糖 8克"}
                    ],
                }
            }
        },
        expected_hash=digest,
    )
    store.ingest({**raw, "code": "12345670"}, "breakfast_cereal")
    items = batch.snapshot()["items"]
    with pytest.raises(ValueError, match="不能批量采用"):
        batch.review(
            [selection(i, "sugars") for i in items],
            action="adopt",
            field="sugars",
            reviewer="reviewer-a",
        )
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM knowledge_reviews").fetchone()[0] == 0


def test_failed_image_is_not_repeated_until_version_changes(tmp_path):
    _, batch, _ = setup_batch(tmp_path)
    batch.record_attempt(
        "123",
        "ingredients",
        "version-a",
        status="permanent_failure",
        error_code="ImageQualityError",
    )
    assert not batch.attempt_due("123", "ingredients", "version-a")
    assert batch.attempt_due("123", "ingredients", "version-b")
    batch.record_attempt("123", "nutrition", "version-a", status="transient_failure")
    assert not batch.attempt_due("123", "nutrition", "version-a")


def test_admin_protection_and_origin(tmp_path, monkeypatch):
    from food_label_agent.web.app import create_app

    monkeypatch.setenv("FOOD_LABEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FOOD_LABEL_DISCOVERY_ADMIN_TOKEN", "test-admin-key")

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            assert (await client.get("/api/v1/alternatives/batch")).status_code == 403
            headers = {"Authorization": "Bearer test-admin-key"}
            assert (
                await client.get("/api/v1/alternatives/batch", headers=headers)
            ).status_code == 200
            response = await client.post(
                "/api/v1/alternatives/batch",
                json={},
                headers={**headers, "Origin": "https://other.example"},
            )
            assert response.status_code == 403
            assert (
                await client.post(
                    "/api/v1/alternatives/batch",
                    json={"selections": "bad"},
                    headers=headers,
                )
            ).status_code == 422

    asyncio.run(run())


def test_ocr_cache_survives_api_changes_without_reinterpreting_image(tmp_path):
    from types import SimpleNamespace

    from food_label_agent.alternatives.refresh import KnowledgeRefreshWorker

    store, batch, raw = setup_batch(tmp_path)
    url = "https://images.openfoodfacts.org/400/638/133/3931/ingredients_zh.1.full.jpg"
    image = {
        "source_url": url,
        "image_sha256": "same-image",
        "fields": [{"name": "ingredients", "raw_text": "燕麦"}],
    }
    batch.cache_image_text(image)
    store.ingest(
        {**raw, "ingredients_text": "API 新文字", "image_ingredients_url": url},
        "breakfast_cereal",
    )
    worker = KnowledgeRefreshWorker(
        store=store,
        ocr_service=SimpleNamespace(provider=SimpleNamespace(synthetic=False)),
        fetch_image=lambda _: pytest.fail("unchanged image should use cached draft"),
    )
    result = worker._enrich_images()
    assert result["attempted_count"] == 0
    assert store.field_evidence(raw["code"])["conflicts"] == ["ingredients"]
