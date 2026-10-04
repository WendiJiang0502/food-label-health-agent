from types import SimpleNamespace

import pytest

from food_label_agent.alternatives.knowledge import ProductKnowledgeStore
from food_label_agent.alternatives.refresh import (
    KnowledgeRefreshWorker,
    fetch_label_image,
)


def raw(**changes):
    return {
        "code": "123",
        "product_name": "测试麦片",
        "ingredients_text": "燕麦",
        "last_modified_t": 1700000000,
        **changes,
    }


def store(tmp_path):
    return ProductKnowledgeStore(tmp_path / "knowledge.sqlite3")


def test_incomplete_product_is_searchable_but_never_promoted(tmp_path):
    db = store(tmp_path)
    db.ingest(raw(ingredients_text=""), "breakfast_cereal")
    result = db.snapshot(category="breakfast_cereal", query="麦片")
    item = result["items"][0]
    assert "ingredients_text" in item["missing_fields"]
    assert item["verified_at"] is None
    assert item["recommendation_eligible"] is False
    assert db.snapshot(category="dairy")["items"] == []
    assert db.snapshot(query="not present")["items"] == []


def test_recheck_does_not_refresh_review_or_change_time(tmp_path):
    db = store(tmp_path)
    db.ingest(raw(), "breakfast_cereal", checked_at="2026-01-01T00:00:00+00:00")
    db.ingest(
        raw(last_modified_t=1700000001),
        "breakfast_cereal",
        checked_at="2026-02-01T00:00:00+00:00",
    )
    with db.connect() as conn:
        item = dict(conn.execute("SELECT * FROM candidates").fetchone())
    assert item["last_changed_at"].startswith("2026-01-01")
    assert item["last_checked_at"].startswith("2026-02-01")
    assert item["verified_at"] is None
    assert item["review_status"] == "needs_label"


def test_changed_label_invalidates_ocr_and_stays_flagged(tmp_path):
    db = store(tmp_path)
    db.ingest(raw(), "breakfast_cereal")
    with db.connect() as conn:
        digest = conn.execute("SELECT content_hash FROM candidates").fetchone()[0]
    db.save_ocr_draft("123", {"text": "燕麦"}, expected_hash=digest)
    db.ingest(raw(ingredients_text="燕麦、花生"), "breakfast_cereal")
    db.ingest(raw(ingredients_text="燕麦、花生"), "breakfast_cereal")
    item = db.snapshot()["items"][0]
    assert item["review_status"] == "change_detected"
    assert not item["has_ocr_draft"]
    with pytest.raises(ValueError):
        db.save_ocr_draft("123", {}, expected_hash=digest)


def test_failed_run_retains_last_success_and_retries_in_hour(tmp_path):
    db = store(tmp_path)
    db.record_run(
        "off",
        "completed",
        {},
        interval_hours=24,
        attempted_at="2026-01-01T00:00:00+00:00",
    )
    db.record_run(
        "off",
        "unavailable",
        {},
        interval_hours=24,
        attempted_at="2026-01-02T00:00:00+00:00",
    )
    run = db.snapshot()["runs"][0]
    assert run["last_success_at"] == "2026-01-01T00:00:00+00:00"
    assert run["next_check_at"] == "2026-01-02T01:00:00+00:00"
    assert not db.due("off", now="2026-01-02T00:30:00+00:00")
    assert db.due("off", now="2026-01-02T01:00:00+00:00")


def official():
    return SimpleNamespace(
        status=lambda: {"items": []},
        approved_products=list,
        refresh=lambda: SimpleNamespace(
            status="completed", summary={"discovered_count": 0}
        )
    )


def test_worker_completes_partial_text_and_obeys_schedule(tmp_path):
    db = store(tmp_path)
    calls = []

    def fetch(url, *_):
        calls.append(url)
        if "/search?" in url:
            return {"products": [raw()]}
        return {
            "product": raw(
                ingredients_text="燕麦、食盐", states_tags=["en:ingredients-completed"]
            )
        }

    worker = KnowledgeRefreshWorker(
        db,
        official(),
        fetch_json=fetch,
        request_delay=0,
        categories=["breakfast_cereal"],
    )
    assert worker.run_once()["status"] == "completed"
    assert len(calls) == 3
    assert db.snapshot()["items"][0]["review_status"] == "needs_review"
    assert worker.run_once()["jobs"] == {"official_completion": "completed"}
    worker.run_once(force=True)
    assert (
        db.snapshot()["items"][0]["review_status"] == "needs_review"
    )  # no search/detail oscillation


def test_worker_preserves_all_incomplete_hits_and_failed_source(tmp_path):
    db = store(tmp_path)

    def fetch(url, *_):
        if "/search?" in url:
            return {"products": [raw(code=str(index)) for index in range(9)]}
        raise OSError("offline")

    worker = KnowledgeRefreshWorker(
        db,
        official(),
        fetch_json=fetch,
        request_delay=0,
        categories=["breakfast_cereal"],
    )
    assert worker.run_once()["status"] == "partial"
    assert db.snapshot()["candidate_count"] == 9
    worker.fetch_json = lambda *_: (_ for _ in ()).throw(OSError("offline"))
    assert worker.run_once(force=True)["status"] == "partial"
    assert db.snapshot()["candidate_count"] == 9


def test_worker_does_not_claim_success_for_invalid_api_response(tmp_path):
    worker = KnowledgeRefreshWorker(
        store(tmp_path),
        official(),
        fetch_json=lambda *_: {"error": "rate limit"},
        request_delay=0,
        categories=["dairy"],
    )
    assert worker.run_once()["jobs"]["openfoodfacts:dairy"] == "unavailable"


@pytest.mark.parametrize(
    "url",
    [
        "http://images.openfoodfacts.org/a",
        "https://localhost/a",
        "https://images.openfoodfacts.org.evil.test/a",
        "https://images.openfoodfacts.org:444/a",
    ],
)
def test_image_fetch_rejects_untrusted_origin(url):
    with pytest.raises(ValueError):
        fetch_label_image(url)


def test_synthetic_ocr_cannot_enter_knowledge_store(tmp_path):
    with pytest.raises(ValueError, match="Synthetic"):
        KnowledgeRefreshWorker(
            store(tmp_path),
            ocr_service=SimpleNamespace(provider=SimpleNamespace(synthetic=True)),
        )


def test_ocr_enrichment_saves_draft_without_certifying_label(tmp_path):
    db = store(tmp_path)
    db.ingest(
        raw(
            selected_images={
                "ingredients": {
                    "display": {"zh": "https://images.openfoodfacts.org/a.jpg"}
                }
            }
        ),
        "breakfast_cereal",
    )

    async def analyze(**_):
        return SimpleNamespace(
            fields=[
                SimpleNamespace(
                    model_dump=lambda **_: {"name": "ingredients", "raw_text": "燕麦"}
                )
            ]
        )

    service = SimpleNamespace(
        provider=SimpleNamespace(synthetic=False), analyze=analyze
    )
    worker = KnowledgeRefreshWorker(
        db,
        official(),
        ocr_service=service,
        fetch_image=lambda _: (b"image", "image/jpeg"),
    )
    assert worker._enrich_images()["failed_count"] == 0
    item = db.snapshot()["items"][0]
    assert item["has_ocr_draft"]
    assert item["verified_at"] is None
    assert not item["recommendation_eligible"]


def test_run_lock_prevents_duplicate_workers(tmp_path):
    import fcntl

    db = store(tmp_path)
    with db.path.with_suffix(".worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert (
            KnowledgeRefreshWorker(db, official()).run_once()["status"]
            == "already_running"
        )


def test_product_keeps_membership_in_multiple_categories(tmp_path):
    db = store(tmp_path)
    db.ingest(raw(), "drink")
    db.ingest(raw(), "dairy")
    assert db.snapshot(category="drink")["candidate_count"] == 1
    assert db.snapshot(category="dairy")["candidate_count"] == 1


def test_retained_product_outside_search_page_is_rechecked(tmp_path):
    db = store(tmp_path)
    db.ingest(raw(code="999"), "dairy", checked_at="2020-01-01T00:00:00+00:00")
    calls = []

    def fetch(url, *_):
        calls.append(url)
        return {"products": []} if "/search?" in url else {"product": raw(code="999")}

    worker = KnowledgeRefreshWorker(
        db, official(), fetch_json=fetch, request_delay=0, categories=["dairy"]
    )
    worker.run_once()
    assert any("product/999" in url for url in calls)
    assert not db.snapshot()["items"][0]["last_checked_at"].startswith("2020")


def test_failed_ocr_run_never_updates_last_success(tmp_path):
    db = store(tmp_path)
    db.ingest(
        raw(
            selected_images={
                "ingredients": {
                    "display": {"zh": "https://images.openfoodfacts.org/a.jpg"}
                }
            }
        ),
        "dairy",
    )
    db.record_run("openfoodfacts:dairy", "completed", {}, interval_hours=24)
    db.record_run("official_sources", "completed", {}, interval_hours=168)
    db.record_run("product_details", "completed", {}, interval_hours=24)
    service = SimpleNamespace(provider=SimpleNamespace(synthetic=False))

    def unavailable(_):
        raise OSError("image unavailable")

    worker = KnowledgeRefreshWorker(
        db,
        official(),
        categories=["dairy"],
        ocr_service=service,
        fetch_image=unavailable,
    )
    assert worker.run_once()["jobs"]["packaging_ocr"] == "partial"
    run = next(item for item in db.snapshot()["runs"] if item["job"] == "packaging_ocr")
    assert run["last_success_at"] is None
    assert run["summary"]["failed_count"] == 1


@pytest.mark.parametrize(
    "arguments,environment,expected",
    [
        ([], None, True),
        (["--no-ocr"], None, False),
        ([], "0", False),
        (["--ocr"], "0", True),
    ],
)
def test_worker_cli_defaults_to_existing_tencent_ocr(
    monkeypatch, arguments, environment, expected
):
    import os

    from food_label_agent.alternatives import refresh
    from food_label_agent.ocr import paddle_provider

    monkeypatch.setenv("FOOD_LABEL_OCR_PROVIDER", "tencent")
    monkeypatch.delenv("FOOD_LABEL_OCR_PROVIDER")
    monkeypatch.delenv("FOOD_LABEL_KNOWLEDGE_OCR", raising=False)
    if environment is not None:
        monkeypatch.setenv("FOOD_LABEL_KNOWLEDGE_OCR", environment)
    monkeypatch.setattr("sys.argv", ["refresh", "--once", *arguments])
    provider = SimpleNamespace(synthetic=False)
    monkeypatch.setattr(paddle_provider, "create_ocr_provider", lambda: provider)
    received = {}

    def worker(**kwargs):
        received.update(kwargs)
        return SimpleNamespace(run_once=lambda **_: {"status": "completed"})

    monkeypatch.setattr(refresh, "KnowledgeRefreshWorker", worker)
    monkeypatch.setattr(refresh.signal, "signal", lambda *_: None)
    refresh.main()
    assert (received["ocr_service"] is not None) == expected
    if expected:
        assert received["ocr_service"].provider is provider
        assert os.environ["FOOD_LABEL_OCR_PROVIDER"] == "tencent"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-10-03T02:12:45+00:00", "2026-11-03T02:12:45+00:00"),
        ("2026-01-31T10:00:00+08:00", "2026-02-28T10:00:00+08:00"),
        ("2028-01-31T10:00:00+08:00", "2028-02-29T10:00:00+08:00"),
        ("2026-12-03T02:12:45+00:00", "2027-01-03T02:12:45+00:00"),
    ],
)
def test_calendar_month_schedule(value, expected):
    from food_label_agent.alternatives.knowledge import next_calendar_month

    assert next_calendar_month(value) == expected


@pytest.mark.parametrize("status", ["completed", "partial", "unavailable"])
def test_monthly_job_does_not_revert_to_hourly_retry(tmp_path, status):
    db = store(tmp_path)
    db.record_run("monthly", status, {}, attempted_at="2026-10-03T02:12:45+00:00")
    run = db.snapshot()["runs"][0]
    assert run["next_check_at"] == "2026-11-03T02:12:45+00:00"
    assert (run["last_success_at"] is not None) == (status == "completed")


def test_ocr_uses_full_resolution_without_switching_revision():
    from food_label_agent.alternatives.refresh import full_label_image

    value = raw(
        selected_images={
            "ingredients": {
                "display": {
                    "zh": "https://images.openfoodfacts.org/images/products/123/ingredients_zh.7.400.jpg"
                }
            }
        }
    )
    assert (
        full_label_image(value, "ingredients")
        == "https://images.openfoodfacts.org/images/products/123/ingredients_zh.7.full.jpg"
    )


def test_ocr_processes_all_seven_images_not_just_five(tmp_path):
    db = store(tmp_path)
    for index in range(7):
        db.ingest(
            raw(
                code=str(index),
                selected_images={
                    "ingredients": {
                        "display": {
                            "zh": f"https://images.openfoodfacts.org/{index}/ingredients_zh.1.400.jpg"
                        }
                    }
                },
            ),
            "dairy",
        )

    async def analyze(**_):
        return SimpleNamespace(
            fields=[
                SimpleNamespace(
                    model_dump=lambda **_: {"name": "ingredients", "raw_text": "燕麦"}
                )
            ]
        )

    service = SimpleNamespace(
        provider=SimpleNamespace(synthetic=False), analyze=analyze
    )
    worker = KnowledgeRefreshWorker(
        db,
        official(),
        ocr_service=service,
        fetch_image=lambda _: (b"image", "image/jpeg"),
    )
    assert worker._enrich_images()["attempted_count"] == 7
    assert all(item["has_ocr_draft"] for item in db.snapshot()["items"])


def test_ocr_empty_result_never_counts_as_completed_draft(tmp_path):
    db = store(tmp_path)
    db.ingest(
        raw(image_ingredients_url="https://images.openfoodfacts.org/a.jpg"), "dairy"
    )

    async def analyze(**_):
        return SimpleNamespace(fields=[])

    worker = KnowledgeRefreshWorker(
        db,
        official(),
        ocr_service=SimpleNamespace(
            provider=SimpleNamespace(synthetic=False), analyze=analyze
        ),
        fetch_image=lambda _: (b"image", "image/jpeg"),
    )
    assert worker._enrich_images()["failed_count"] == 1
    assert not db.snapshot()["items"][0]["has_ocr_draft"]


def test_detail_completion_rejects_different_barcode(tmp_path):
    db = store(tmp_path)
    db.ingest(raw(), "dairy")
    worker = KnowledgeRefreshWorker(
        db,
        official(),
        fetch_json=lambda *_: {"product": raw(code="999")},
        request_delay=0,
    )
    assert worker._complete_candidates()["failed_count"] == 1
    assert db.snapshot()["candidate_count"] == 1
    assert db.snapshot()["items"][0]["id"] == "123"


def test_coverage_preserves_zero_nutrients_and_never_equates_presence_to_review(
    tmp_path,
):
    db = store(tmp_path)
    db.ingest(
        raw(
            nutriments={
                key: 0
                for key in [
                    "energy-kj_100g",
                    "proteins_100g",
                    "fat_100g",
                    "carbohydrates_100g",
                    "sodium_100g",
                    "sugars_100g",
                ]
            }
        ),
        "dairy",
    )
    report = db.coverage()
    assert report["counts"]["core_nutrition_present"] == 1
    assert report["counts"]["reviewed"] == 0
    assert "reviewed" in report["gaps"][0]["missing"]
