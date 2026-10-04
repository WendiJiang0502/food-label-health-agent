from __future__ import annotations

import json

from food_label_agent.alternatives.catalog import JsonProductCatalog
from food_label_agent.alternatives.knowledge import ProductKnowledgeStore
from food_label_agent.alternatives.models import AlternativeRevalidationRequest
from food_label_agent.alternatives.service import revalidate_alternatives
from food_label_agent.evaluation.product_rag import run_product_rag_evaluation
from food_label_agent.ingredients.api_models import ConstraintInput


def test_curated_scenarios_pass():
    report = run_product_rag_evaluation()
    assert report["case_count"] >= 37
    assert report["evaluation_passed"], [
        r for r in report["results"] if not r["passed"]
    ]


def test_history_survives_source_change_and_ocr_conflicts_are_not_promoted(tmp_path):
    store = ProductKnowledgeStore(tmp_path / "evidence.sqlite3")
    raw = {
        "code": "123",
        "product_name": "燕麦",
        "ingredients_text": "燕麦",
        "nutrition_data_per": "100g",
        "nutriments": {"sugars_100g": 5},
    }
    store.ingest(raw, "breakfast_cereal")
    with store.connect() as db:
        digest = db.execute("SELECT content_hash FROM candidates").fetchone()[0]
    store.save_ocr_draft(
        "123",
        {
            "images": {
                "nutrition": {
                    "source_url": "https://images.openfoodfacts.org/label.jpg",
                    "image_sha256": "snapshot",
                    "fields": [
                        {"name": "nutrition_table", "raw_text": "每100克\n糖 8克"}
                    ],
                }
            }
        },
        expected_hash=digest,
    )
    fields = store.field_evidence("123")
    assert fields["conflicts"] == ["sugars"]
    assert {x["review_status"] for x in fields["observations"]} == {
        "unverified",
        "ocr_draft",
    }
    raw["nutriments"]["sugars_100g"] = 3
    store.ingest(raw, "breakfast_cereal")
    current = store.field_evidence("123")
    assert not current["conflicts"]
    assert [v["value"] for v in current["observations"] if v["field"] == "sugars"] == [
        3
    ]
    with store.connect() as db:
        values = [
            json.loads(r[0])
            for r in db.execute("SELECT payload FROM field_observations")
        ]
    assert {v["value"] for v in values if v["field"] == "sugars"} == {3, 5, 8}


def test_actual_revalidation_obeys_relative_goal_and_allergy():
    records = list(JsonProductCatalog().search(category="biscuit", region="CN").records)
    base = AlternativeRevalidationRequest(
        request_id="intent-comparison",
        applicable_date="2026-10-03",
        candidates=records,
        retrieval_query="糖更少",
        current_nutrition_rows=[["项目", "每100克"], ["糖", "6克"]],
    )
    result = revalidate_alternatives(base)
    eligible = [r for r in result["results"] if r["disposition"] == "eligible"]
    assert [r["product_id"] for r in eligible] == ["fixture-biscuit-milk-cracker"]
    assert eligible[0]["health_comparisons"][0]["outcome"] == "improved"
    assert eligible[0]["field_evidence"]["observations"]
    no_base = revalidate_alternatives(
        base.model_copy(update={"current_nutrition_rows": None})
    )
    assert no_base["eligible_count"] == 0
    allergy = revalidate_alternatives(
        base.model_copy(
            update={
                "constraints": [
                    ConstraintInput(
                        kind="allergy", canonical_value="milk", severity="severe"
                    )
                ]
            }
        )
    )
    assert allergy["eligible_count"] == 0


def test_serving_conversion_and_mass_volume_are_respected():
    records = list(JsonProductCatalog().search(category="biscuit", region="CN").records)
    base = AlternativeRevalidationRequest(
        request_id="serving-comparison",
        applicable_date="2026-10-03",
        candidates=records,
        retrieval_query="糖更少",
        current_nutrition_rows=[["项目", "每份50克"], ["糖", "3克"]],
    )
    assert revalidate_alternatives(base)["eligible_count"] == 1
    assert (
        revalidate_alternatives(
            base.model_copy(
                update={
                    "current_nutrition_rows": [["项目", "每100毫升"], ["糖", "10克"]]
                }
            )
        )["eligible_count"]
        == 0
    )


def test_workflow_transmits_query_to_revalidation(monkeypatch):
    from food_label_agent.alternatives.models import AlternativeWorkflowRequest
    from food_label_agent.graph.workflows import run_alternative_workflow

    monkeypatch.setenv("FOOD_LABEL_PRODUCT_CATALOG", "curated")
    req = AlternativeWorkflowRequest(
        request_id="intent-workflow",
        applicable_date="2026-10-03",
        category="biscuit",
        confirmed_fields={"ingredients": "燕麦", "nutrition_table": "每100克\n糖 6克"},
        nutrition_rows=[["项目", "每100克"], ["糖", "6克"]],
        retrieval_query="糖更少",
        resume_token="test-token-that-is-long-enough-for-workflow",
    )
    payload, _ = run_alternative_workflow(req)
    assert payload["search_intent"]["nutrition_goals"][0]["nutrient"] == "sugars"
    assert [r["product_id"] for r in payload["eligible"]] == [
        "fixture-biscuit-milk-cracker"
    ]
    assert payload["display_metrics"]["target_comparison_requested"]
