from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from food_label_agent.alternatives.catalog import PRODUCT_CATEGORIES


def test_physical_review_batch_has_two_distinct_brands_per_category() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs/evaluation/alternative_physical_review_batch_v1.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources_path = (
        Path(__file__).parents[1]
        / "src/food_label_agent/alternatives/data/official_cn_sources.json"
    )
    sources = {
        item["source_id"]: item
        for item in json.loads(sources_path.read_text(encoding="utf-8"))
    }
    assert payload["schema_version"] == "alternative_physical_review_batch_v1"
    assert payload["status"] == "awaiting_physical_packages"
    assert payload["review_policy"]["reviewers_required"] == 2
    assert payload["review_policy"]["reviewers_must_be_distinct"] is True

    slots = payload["slots"]
    assert len(slots) == 28
    assert len({slot["slot_id"] for slot in slots}) == 28
    counts = Counter(slot["category"] for slot in slots)
    assert counts == Counter({category: 2 for category in PRODUCT_CATEGORIES})

    source_path = (
        Path(__file__).parents[1]
        / "src/food_label_agent/alternatives/data/official_cn_sources.json"
    )
    sources = {
        source["source_id"]: source
        for source in json.loads(source_path.read_text(encoding="utf-8"))
    }
    brands: dict[str, set[str]] = defaultdict(set)
    for slot in slots:
        brands[slot["category"]].add(slot["brand"])
        source = sources[slot["source_id"]]
        assert source["category"] == slot["category"]
        assert source["brand"] == slot["brand"]
        assert slot["target_product"]
        assert slot["status"] == "awaiting_physical_package"
    assert all(len(category_brands) == 2 for category_brands in brands.values())


def test_physical_review_batch_requires_comparison_nutrition_fields() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs/evaluation/alternative_physical_review_batch_v1.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload["required_nutrition_fields"]) >= {
        "energy",
        "protein",
        "fat",
        "carbohydrate",
        "sodium",
        "sugars",
        "saturated_fat",
    }
    assert payload["review_policy"]["missing_field_policy"] == (
        "record_absent_on_label_never_infer"
    )
