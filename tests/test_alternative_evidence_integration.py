"""Cross-boundary tests: demand -> source update -> retrieval -> screening."""

import json
from datetime import UTC, datetime

from food_label_agent.alternatives.application import AlternativeEvidenceService
from food_label_agent.alternatives.completion import completion_snapshot
from food_label_agent.alternatives.discovery import OfficialProductDiscovery
from food_label_agent.alternatives.evidence import (
    active_knowledge_store,
    active_official_items,
)
from food_label_agent.alternatives.knowledge import ProductKnowledgeStore
from food_label_agent.alternatives.models import (
    AlternativeSearchRequest,
    AlternativeWorkflowRequest,
)
from food_label_agent.alternatives.rag import ProductRAG


def candidate():
    return {
        "candidate_id": "official:test:200g",
        "display_name": "测试酸奶",
        "brand": "测试",
        "category": "dairy",
        "region": "CN",
        "source_id": "simplelove-public-products",
        "source_url": "https://www.jianai.com/test",
        "source_fingerprint": "v1",
        "specification": "200g",
        "review_status": "evidence_incomplete",
        "last_seen_at": datetime.now(UTC).isoformat(),
        "extracted_fields": {
            "ingredients_text": "生牛乳、白砂糖",
            "nutrition_rows": [["项目", "每100克"], ["蛋白质", "4克"]],
        },
    }


def request():
    return AlternativeWorkflowRequest(
        request_id="evidence-integration",
        resume_token="x" * 32,
        category="dairy",
        applicable_date=datetime.now(UTC).date(),
        confirmed_fields={"ingredients": "燕麦"},
        constraints=[
            {
                "kind": "nutrition_limit",
                "canonical_value": "sugars",
                "operator": "max",
                "threshold": 5,
                "unit": "g",
                "basis": "per_100g",
            }
        ],
        retrieval_query="酸奶糖更少",
    )


def service(tmp_path):
    discovery = OfficialProductDiscovery(
        queue_path=tmp_path / "queue.json", approved_path=tmp_path / "approved.json"
    )
    discovery.queue_path.write_text(json.dumps([candidate()], ensure_ascii=False))
    return AlternativeEvidenceService(
        discovery, ProductKnowledgeStore(tmp_path / "evidence.sqlite3")
    )


def write_item(svc, item):
    svc.discovery.queue_path.write_text(json.dumps([item], ensure_ascii=False))


def search(svc):
    return ProductRAG(svc.store, profile="bm25").search(
        AlternativeSearchRequest(
            category="dairy",
            applicable_date=datetime.now(UTC).date(),
            retrieval_query="测试酸奶",
        ),
        [],
    )


def test_demand_source_update_retrieval_and_reopen(tmp_path):
    svc = service(tmp_path)
    req = request().model_copy(update={"retrieval_query": None})
    snapshot = svc.prepare()
    result = svc.enrich({}, req, snapshot)
    assert result["source_screening"]["items"][0]["status"] == "unknown"
    assert completion_snapshot(svc.store)["items"][0]["status"] == "needs_label"
    before = search(svc)["items"][0]
    assert before["tier"] == "official_unverified"
    assert not before["recommendation_eligible"]
    # The official task is NOT accidentally routed to the OFF-only worker queue.
    with svc.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM completion_queue").fetchone()[0] == 0
    updated = candidate()
    updated["source_fingerprint"] = "v2"
    updated["extracted_fields"]["nutrition_rows"].append(["糖", "3克"])
    write_item(svc, updated)
    snapshot = svc.prepare()
    assert completion_snapshot(svc.store)["items"][0]["status"] == "source_available"
    after = search(svc)["items"][0]
    assert after["evidence_id"] != before["evidence_id"]
    result = svc.enrich({}, req, snapshot)
    item = result["source_screening"]["items"][0]
    assert item["status"] == "matched" and not item["recommendation_eligible"]
    assert item["evidence"] == after["evidence"]
    # Repeating reconciliation does not create duplicate history.
    svc.prepare()
    with svc.store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM official_completion_transitions"
            ).fetchone()[0]
            == 1
        )
    write_item(svc, candidate() | {"source_fingerprint": "v3"})
    svc.prepare()
    assert completion_snapshot(svc.store)["items"][0]["status"] == "needs_label"


def test_rejection_removal_and_unknown_never_become_recommendations(tmp_path):
    svc = service(tmp_path)
    svc.enrich({}, request(), svc.prepare())
    write_item(svc, candidate() | {"review_status": "rejected"})
    svc.prepare()
    assert search(svc)["items"] == []
    assert completion_snapshot(svc.store)["items"][0]["status"] == "rejected"
    svc.discovery.queue_path.write_text("[]")
    svc.prepare()
    assert completion_snapshot(svc.store)["items"][0]["status"] == "source_missing"


def test_snapshot_isolated_and_failure_cannot_reuse_stale_official_index(tmp_path):
    svc = service(tmp_path)
    snapshot = svc.prepare()
    with svc.scope(snapshot["summary"]["items"]):
        svc.discovery.queue_path.write_text("[]")
        svc.synchronize()
        assert ProductRAG(profile="bm25").search(
            AlternativeSearchRequest(
                category="dairy",
                applicable_date=datetime.now(UTC).date(),
                retrieval_query="酸奶",
            ),
            [],
        )["items"]
    assert active_knowledge_store.get() is None and active_official_items.get() is None
    svc.discovery.queue_path.write_text("invalid json")
    failed = svc.prepare()
    assert failed["status"] == "unavailable"
    with svc.scope(failed["summary"]["items"]):
        assert search(svc)["items"] == []


def test_web_and_chat_share_the_workflow_enrichment(tmp_path, monkeypatch):
    from food_label_agent.conversation.service import ConversationAgent
    from food_label_agent.domain.models import LabelField
    from food_label_agent.graph import workflows

    svc = service(tmp_path)
    req = request().model_copy(update={"retrieval_query": "酸奶"})
    monkeypatch.setattr(workflows, "run_agent_graph", lambda state: state)
    monkeypatch.setattr(
        workflows,
        "alternative_payload",
        lambda *args: {"status": "completed", "eligible": []},
    )
    import asyncio

    import httpx

    from food_label_agent.graph.state import create_initial_state
    from food_label_agent.persistence.sqlite import SQLiteCheckpointStore
    from food_label_agent.web.app import create_app

    monkeypatch.setenv("FOOD_LABEL_PRODUCT_RAG_DB", str(svc.store.path))
    checkpoints = SQLiteCheckpointStore(tmp_path / "workflow.sqlite3")
    saved = checkpoints.save(
        create_initial_state(
            request_id=req.request_id,
            jurisdiction="CN",
            applicable_date=req.applicable_date.isoformat(),
        )
    )
    req = req.model_copy(update={"resume_token": saved.resume_token})
    app = create_app(discovery_service=svc.discovery, checkpoint_store=checkpoints)

    async def http_search():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/alternatives/search", json=req.model_dump(mode="json")
            )
            assert response.status_code == 200, response.text
            return response.json()

    payload = asyncio.run(http_search())
    state = {
        "request_id": req.request_id,
        "applicable_date": req.applicable_date.isoformat(),
        "jurisdiction": "CN",
        "label_fields": {"ingredients": LabelField("ingredients", "燕麦", 1, True)},
        "user_constraints": [workflows._constraint(c) for c in req.constraints],
        "alternative_request": {},
    }
    # Full canonical state is constructed by the shared workflow as for HTTP.
    original = workflows.prepare_evaluation_state
    monkeypatch.setattr(
        workflows,
        "prepare_evaluation_state",
        lambda request, **kwargs: original(request),
    )
    agent = ConversationAgent(evidence_service=svc)
    chat = agent._invoke_tool(
        "search_product_alternatives",
        {"category": "dairy", "query": "酸奶"},
        state,
        None,
    )
    assert chat["status"] == payload["status"]
    assert chat["source_screening"]["items"] == payload["source_screening"]["items"]
    assert chat["source_screening"]["counts"] == payload["source_screening"]["counts"]
    assert completion_snapshot(svc.store)["items"][0]["demand_count"] == 1


def test_not_declared_is_version_bound(tmp_path):
    svc = service(tmp_path)
    item = candidate()
    item["evidence_assets"] = [
        {
            "snapshot_id": "label",
            "review_status": "verified",
            "artifact_type": "packaging_photo",
        }
    ]
    item["label_field_reviews"] = {
        "sugars": {
            "status": "not_declared",
            "review_status": "verified",
            "full_label_checked": True,
            "source_fingerprint": "v1",
            "evidence_id": "label",
            "reviewed_at": datetime.now(UTC).date().isoformat(),
        }
    }
    write_item(svc, item)
    svc.enrich({}, request(), svc.prepare())
    svc.prepare()
    row = completion_snapshot(svc.store)["items"][0]
    assert row["status"] == "not_declared" and not row["same_source_retry_allowed"]
    item["source_fingerprint"] = "v2"
    write_item(svc, item)
    svc.prepare()
    assert completion_snapshot(svc.store)["items"][0]["status"] == "needs_review"


def test_worker_consumes_local_updates_between_monthly_fetches(tmp_path):
    from food_label_agent.alternatives.refresh import KnowledgeRefreshWorker

    svc = service(tmp_path)
    svc.enrich({}, request(), svc.prepare())
    item = candidate()
    item["source_fingerprint"] = "v2"
    item["extracted_fields"]["nutrition_rows"].append(["糖", "3克"])
    write_item(svc, item)
    for job in ("openfoodfacts:dairy", "official_sources", "product_details"):
        svc.store.record_run(job, "completed", {})
    worker = KnowledgeRefreshWorker(
        svc.store,
        svc.discovery,
        categories=["dairy"],
        fetch_json=lambda *args: (_ for _ in ()).throw(
            AssertionError("network not due")
        ),
    )
    assert worker.run_once()["jobs"] == {"official_completion": "completed"}
    assert completion_snapshot(svc.store)["items"][0]["status"] == "source_available"
    assert search(svc)["items"][0]["source_version"] == "v2"
