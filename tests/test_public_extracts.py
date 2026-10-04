from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from food_label_agent.alternatives.public_extracts import candidates_from_extract
from food_label_agent.alternatives.source_screening import screen_official_sources
from food_label_agent.ingredients.api_models import ConstraintInput


def payload():
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "capture_method": "official_page_text_via_web_retrieval",
        "products": [
            {
                "source_id": "classykiss-public-extract",
                "brand": "卡士",
                "name": "断糖日记 原味",
                "source_url": "https://www.classykiss.cn/wap/SugarDiary/index.html",
                "source_section": "原味",
                "product_type": "yogurt",
                "specification": None,
                "ingredients": "生牛乳、乳酸菌",
                "nutrition_rows": [["项目", "每100克"], ["脂肪", "5.0克"]],
            }
        ],
    }


def test_preserves_missing_sugar_and_capture_time():
    p = payload()
    result = candidates_from_extract(p)[0]
    assert result["last_seen_at"] == p["captured_at"]
    assert result["sku"] is None and result["barcode"] is None
    assert result["recommendation_eligible"] is False
    assert "糖含量未公开" in result["missing_fields"]
    request = SimpleNamespace(
        category="dairy",
        region="CN",
        retrieval_query=None,
        health_concerns=[],
        constraints=[
            ConstraintInput(
                kind="nutrition_limit",
                canonical_value="sugars",
                operator="max",
                threshold=5,
                unit="g",
                basis="per_100g",
            )
        ],
    )
    assert screen_official_sources([result], request)["counts"] == {"unknown": 1}
    request.constraints[0] = request.constraints[0].model_copy(
        update={"canonical_value": "fat"}
    )
    assert screen_official_sources([result], request)["counts"] == {"matched": 1}
    result["last_seen_at"] = "2020-01-01"
    assert screen_official_sources([result], request)["counts"] == {"unknown": 1}


def test_identity_dedup_and_changed_evidence():
    p = payload()
    first = candidates_from_extract(p)[0]
    changed = deepcopy(p)
    changed["products"][0]["nutrition_rows"][1][1] = "4.0克"
    second = candidates_from_extract(changed)[0]
    assert first["candidate_id"] == second["candidate_id"]
    assert first["source_fingerprint"] != second["source_fingerprint"]
    p["products"].append(deepcopy(p["products"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        candidates_from_extract(p)


def test_rejects_wrong_source():
    p = payload()
    p["products"][0]["source_url"] = "https://example.com/not-official"
    with pytest.raises(ValueError, match="mismatch"):
        candidates_from_extract(p)
