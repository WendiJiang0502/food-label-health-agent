from copy import deepcopy

from food_label_agent.alternatives.completion import (
    completion_snapshot,
    record_screening_gaps,
)
from food_label_agent.alternatives.knowledge import ProductKnowledgeStore


def result(status="unknown"):
    return {
        "items": [
            {
                "candidate_id": "p1",
                "display_name": "酸奶",
                "source_url": "https://example.com/product",
                "source_fingerprint": "version1",
                "status": status,
                "checks": [
                    {"field": "fat", "status": "matched", "gap": None},
                    {"field": "sugars", "status": "unknown", "gap": "nutrition_field"},
                    {"field": "sugars", "status": "unknown", "gap": "nutrition_field"},
                ],
            }
        ]
    }


def test_dedup_prioritize_and_do_not_mutate(tmp_path):
    store = ProductKnowledgeStore(tmp_path / "db")
    data = result()
    before = deepcopy(data)
    assert record_screening_gaps(store, data, "request1")["new_demand_events"] == 1
    assert record_screening_gaps(store, data, "request1")["new_demand_events"] == 0
    record_screening_gaps(store, data, "request2")
    q = completion_snapshot(store)
    assert q["total"] == 1
    assert q["items"][0]["demand_count"] == 2
    assert q["items"][0]["near_match_count"] == 2
    assert data == before


def test_skip_failed_and_non_product_gaps(tmp_path):
    store = ProductKnowledgeStore(tmp_path / "db")
    assert (
        record_screening_gaps(store, result("not_matched"), "r")["new_demand_events"]
        == 0
    )
    data = result()
    data["items"][0]["checks"] = [
        {"field": "protein", "status": "unknown", "gap": None}
    ]
    assert record_screening_gaps(store, data, "r")["new_demand_events"] == 0
    assert completion_snapshot(store)["total"] == 0


def test_allergy_values_not_stored(tmp_path):
    store = ProductKnowledgeStore(tmp_path / "db")
    data = result()
    data["items"][0]["checks"] = [
        {"field": "peanut", "status": "unknown", "gap": "packaging_review"}
    ]
    record_screening_gaps(store, data, "private-request")
    q = completion_snapshot(store)
    assert q["items"][0]["field"] == "packaging_review"
    assert "peanut" not in str(q) and "private-request" not in str(q)


def test_simulated_pilot_is_repeatable_and_excludes_milk(tmp_path):
    import json
    from datetime import UTC, datetime

    from food_label_agent.evaluation.yogurt_pilot import run

    item = {
        "candidate_id": "p1",
        "display_name": "测试酸奶",
        "category": "dairy",
        "region": "CN",
        "source_id": "simplelove-public-products",
        "source_fingerprint": "v1",
        "last_seen_at": datetime.now(UTC).isoformat(),
        "extracted_fields": {
            "nutrition_rows": [
                ["项目", "每100克"],
                ["蛋白质", "4克"],
                ["脂肪", "3克"],
                ["钠", "40毫克"],
            ]
        },
    }
    path = tmp_path / "input.json"
    path.write_text(
        json.dumps([item, item | {"candidate_id": "milk", "display_name": "鲜牛奶"}])
    )
    report = run(path, tmp_path / "simulation")
    assert report["product_count"] == 1 and report["query_count"] == 10
    assert report["queries_with_preliminary_match"] == 4
    assert report["completion_queue"]["total"] == 2
    again = run(path, tmp_path / "simulation")
    assert report["completion_queue"] == again["completion_queue"]
    outcomes = {x["case"]["id"]: x["result"]["counts"] for x in report["results"]}
    assert outcomes["fat_max"] == {"matched": 1}
    assert outcomes["fat_and_allergy"] == {"unknown": 1}
    assert outcomes["sugar_max"] == {"unknown": 1}
