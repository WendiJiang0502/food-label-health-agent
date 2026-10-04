from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from food_label_agent.alternatives.completion import (
    completion_snapshot,
    record_screening_gaps,
)
from food_label_agent.alternatives.ingredient_screening import (
    field_gap_state,
    ingredient_conflict,
)
from food_label_agent.alternatives.knowledge import ProductKnowledgeStore
from food_label_agent.alternatives.source_screening import screen_official_sources
from food_label_agent.ingredients.api_models import ConstraintInput


@pytest.mark.parametrize("text", ["生牛乳、白砂糖", "生牛乳(≥99%)、乳酸菌", "牛乳"])
def test_explicit_milk_conflict(text):
    r = ingredient_conflict(
        {"ingredients_text": text}, ConstraintInput(canonical_value="milk")
    )
    assert r and r["reason_code"] == "DIRECT_ALLERGEN_INGREDIENT"


@pytest.mark.parametrize(
    "text,key",
    [("乳酸菌、可可脂", "milk"), ("不含花生", "peanut"), ("生牛乳", "peanut")],
)
def test_no_absence_or_substring_inference(text, key):
    assert (
        ingredient_conflict(
            {"ingredients_text": text}, ConstraintInput(canonical_value=key)
        )
        is None
    )


def test_avoid_exact_and_precaution():
    c = ConstraintInput(kind="user_avoidance", canonical_value="白砂糖")
    assert ingredient_conflict({"ingredients_text": "生牛乳、白砂糖"}, c)
    assert ingredient_conflict({"ingredients_text": "不添加白砂糖"}, c) is None
    r = ingredient_conflict(
        {"ingredients_text": "大米", "allergen_statement": "可能含有花生"},
        ConstraintInput(canonical_value="peanut"),
    )
    assert r["reason_code"] == "PRECAUTIONARY_ALLERGEN_STATEMENT"


def test_not_declared_requires_version_bound_review_and_real_label():
    item = {
        "source_fingerprint": "v1",
        "label_field_reviews": {
            "sugars": {
                "status": "not_declared",
                "review_status": "verified",
                "full_label_checked": True,
                "source_fingerprint": "v1",
                "evidence_id": "label1",
                "reviewed_at": datetime.now(UTC).date().isoformat(),
            }
        },
    }
    assert field_gap_state(item, "sugars") == "needs_label"
    item["evidence_assets"] = [
        {
            "snapshot_id": "label1",
            "review_status": "verified",
            "artifact_type": "packaging_photo",
        }
    ]
    assert field_gap_state(item, "sugars") == "not_declared"
    assert field_gap_state(item, "sugars", flagged=True) == "needs_review"
    item["source_fingerprint"] = "v2"
    assert field_gap_state(item, "sugars") == "needs_review"


def test_conflict_excluded_and_missing_label_queue(tmp_path):
    item = {
        "candidate_id": "test",
        "display_name": "酸奶",
        "category": "dairy",
        "region": "CN",
        "source_id": "simplelove-public-products",
        "source_fingerprint": "v1",
        "last_seen_at": datetime.now(UTC).isoformat(),
        "extracted_fields": {"ingredients_text": "生牛乳、白砂糖"},
    }
    req = SimpleNamespace(
        category="dairy",
        region="CN",
        retrieval_query=None,
        health_concerns=[],
        constraints=[ConstraintInput(canonical_value="milk")],
    )
    result = screen_official_sources([item], req)
    assert result["counts"] == {"not_matched": 1}
    store = ProductKnowledgeStore(tmp_path / "db")
    assert record_screening_gaps(store, result, "r")["new_demand_events"] == 0
    item["source_quality_flags"] = ["口味与配料不一致"]
    assert screen_official_sources([item], req)["counts"] == {"unknown": 1}
    item.pop("source_quality_flags")
    req.constraints = [
        ConstraintInput(
            kind="nutrition_limit",
            canonical_value="sugars",
            operator="max",
            threshold=5,
            unit="g",
            basis="per_100g",
        )
    ]
    result = screen_official_sources([item], req)
    assert result["items"][0]["checks"][0]["gap_state"] == "needs_label"
    record_screening_gaps(store, result, "r")
    assert completion_snapshot(store)["items"][0]["status"] == "needs_label"


def test_not_declared_task_blocks_same_source_retry(tmp_path):
    store = ProductKnowledgeStore(tmp_path / "db")
    result = {
        "items": [
            {
                "candidate_id": "p",
                "display_name": "酸奶",
                "source_fingerprint": "v1",
                "status": "unknown",
                "checks": [
                    {
                        "field": "sugars",
                        "gap": "nutrition_field",
                        "gap_state": "not_declared",
                        "status": "unknown",
                    }
                ],
            }
        ]
    }
    record_screening_gaps(store, result, "r")
    task = completion_snapshot(store)["items"][0]
    assert (
        task["status"] == "not_declared" and task["same_source_retry_allowed"] is False
    )
