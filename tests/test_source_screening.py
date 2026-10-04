from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

from food_label_agent.alternatives.source_screening import screen_official_sources
from food_label_agent.ingredients.api_models import ConstraintInput


def candidate():
    return {
        "candidate_id": "test",
        "display_name": "官网酸奶",
        "category": "dairy",
        "region": "CN",
        "source_id": "simplelove-public-products",
        "review_status": "evidence_incomplete",
        "last_seen_at": datetime.now(UTC).date().isoformat(),
        "extracted_fields": {
            "nutrition_basis_text": "每100克",
            "nutrition_rows": [["项目", "每100克"], ["蛋白质", "4克"], ["脂肪", "3克"]],
        },
    }


def request(**kwargs):
    return (
        SimpleNamespace(
            category="dairy",
            region="CN",
            retrieval_query=None,
            constraints=kwargs.get("constraints", []),
            health_concerns=[],
            nutrition_rows=kwargs.get("nutrition_rows"),
        )
        if "query" not in kwargs
        else SimpleNamespace(
            category="dairy",
            region="CN",
            retrieval_query=kwargs["query"],
            constraints=[],
            health_concerns=[],
            nutrition_rows=kwargs.get("nutrition_rows"),
        )
    )


def limit(key="fat", threshold=4, basis="per_100g", unit="g"):
    return ConstraintInput(
        kind="nutrition_limit",
        canonical_value=key,
        operator="max",
        threshold=threshold,
        basis=basis,
        unit=unit,
    )


def status(item, req):
    return screen_official_sources([item], req)["items"][0]["status"]


def test_nutrition_constraint_pass_fail_missing_and_no_promotion():
    item = candidate()
    before = deepcopy(item)
    assert status(item, request(constraints=[limit()])) == "matched"
    assert status(item, request(constraints=[limit(threshold=2)])) == "not_matched"
    assert status(item, request(constraints=[limit("sugars")])) == "unknown"
    assert status(item, request(constraints=[limit(basis="per_100ml")])) == "unknown"
    assert item == before
    assert (
        screen_official_sources([item], request(constraints=[limit()]))["items"][0][
            "recommendation_eligible"
        ]
        is False
    )


def test_allergy_missing_blocks_combined_pass_and_empty_is_not_pass():
    assert (
        status(
            candidate(),
            request(constraints=[limit(), ConstraintInput(canonical_value="milk")]),
        )
        == "unknown"
    )
    assert status(candidate(), request()) == "not_evaluated"


def test_flagged_stale_duplicate_and_rejected():
    for patch in [
        {"source_quality_flags": ["官网口味与配料不一致"]},
        {"last_seen_at": "2020-01-01"},
        {"review_status": "change_detected"},
    ]:
        assert status(candidate() | patch, request(constraints=[limit()])) == "unknown"
    item = candidate()
    item["extracted_fields"]["nutrition_rows"].append(["脂肪", "0克"])
    assert status(item, request(constraints=[limit()])) == "unknown"
    assert (
        screen_official_sources(
            [candidate() | {"review_status": "rejected"}], request()
        )["total"]
        == 0
    )


def test_relative_comparison_needs_baseline_and_matching_basis():
    assert status(candidate(), request(query="蛋白质更多")) == "unknown"
    rows = [["项目", "每100克"], ["蛋白质", "2克"]]
    assert (
        status(candidate(), request(query="蛋白质更多", nutrition_rows=rows))
        == "matched"
    )
    assert (
        status(candidate(), request(query="蛋白质更少", nutrition_rows=rows))
        == "not_matched"
    )
    rows[0][1] = "每100毫升"
    assert (
        status(candidate(), request(query="蛋白质更多", nutrition_rows=rows))
        == "unknown"
    )


def test_real_search_response_includes_official_screening(tmp_path, monkeypatch):
    import asyncio
    import json

    import httpx

    from food_label_agent.alternatives.discovery import OfficialProductDiscovery
    from food_label_agent.persistence.sqlite import (
        SQLiteCheckpointStore,
        SQLiteMemoryStore,
    )
    from food_label_agent.web.app import create_app

    monkeypatch.setenv("FOOD_LABEL_PRODUCT_CATALOG", "curated")
    path = tmp_path / "queue.json"
    path.write_text(json.dumps([candidate()]))
    app = create_app(
        checkpoint_store=SQLiteCheckpointStore(tmp_path / "db.sqlite"),
        memory_store=SQLiteMemoryStore(tmp_path / "db.sqlite"),
        discovery_service=OfficialProductDiscovery(queue_path=path),
    )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            body = {
                "request_id": "source-screen-integration",
                "jurisdiction": "CN",
                "applicable_date": datetime.now(UTC).date().isoformat(),
                "confirmed_fields": {"ingredients": "生牛乳"},
                "constraints": [limit().model_dump()],
            }
            evaluated = await client.post("/api/v1/labels/evaluate", json=body)
            assert evaluated.status_code == 200
            response = await client.post(
                "/api/v1/alternatives/search",
                json={
                    **body,
                    "category": "dairy",
                    "resume_token": evaluated.json()["checkpoint"]["resume_token"],
                },
            )
            assert response.status_code == 200
            result = response.json()
            assert result["source_screening"]["counts"] == {"matched": 1}
            assert all(x.get("product_id") != "test" for x in result["eligible"])

    asyncio.run(run())
