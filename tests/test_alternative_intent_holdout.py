from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import replace
from importlib.resources import files

import pytest

from food_label_agent.alternatives.catalog import (
    PRODUCT_CATEGORIES,
    OfficialChinaCatalog,
)
from food_label_agent.evaluation.alternatives import (
    evaluate_alternative_intent_holdout,
    load_alternative_intent_holdout,
)


def _normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def test_holdout_has_fourteen_balanced_categories_and_real_user_intents() -> None:
    cases = load_alternative_intent_holdout()
    counts = Counter(case.expected_category for case in cases)

    assert len(cases) == 140
    assert set(counts) == set(PRODUCT_CATEGORIES)
    assert set(counts.values()) == {10}
    assert len({case.case_id for case in cases}) == len(cases)
    assert len({_normalized(case.utterance) for case in cases}) == len(cases)
    intent_markers = (
        "换",
        "替代",
        "备选",
        "同类",
        "其他",
        "找",
        "选",
        "挑",
        "比较",
        "有没",
        "合适",
        "别的",
    )
    assert all(any(marker in case.utterance for marker in intent_markers) for case in cases)


def test_holdout_is_declared_independent_and_does_not_reuse_catalog_names() -> None:
    data_path = files("food_label_agent.evaluation").joinpath(
        "data/alternative_intent_holdout_v1.json"
    )
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    catalog_names = {
        _normalized(record.display_name) for record in OfficialChinaCatalog().records()
    }
    holdout_names = {
        _normalized(case.confirmed_fields.get("product_name", ""))
        for case in load_alternative_intent_holdout()
    }

    assert payload["split"] == "holdout"
    assert payload["construction_source"] == "independent_scenario_authoring"
    assert "不得用于新增或调整分类规则" in "".join(payload["construction_notes"])
    assert holdout_names.isdisjoint(catalog_names)


def test_independent_intent_holdout_meets_release_floor() -> None:
    result = evaluate_alternative_intent_holdout(
        expected_categories=tuple(PRODUCT_CATEGORIES)
    )

    assert result.dataset_scope == (
        "independent_user_intent_holdout_not_catalog_regression"
    )
    assert result.sample_count == 140
    assert result.category_count == 14
    assert result.top1_recall >= 0.85
    assert result.macro_recall >= 0.85
    assert result.automatic_precision >= 0.85
    assert min(result.per_category_recall.values()) >= 0.85
    assert result.evaluation_passed is True
    assert result.release_blockers == ()


def test_holdout_evaluator_rejects_duplicate_or_thin_data() -> None:
    cases = load_alternative_intent_holdout()
    duplicate = replace(cases[1], case_id=cases[0].case_id)

    with pytest.raises(ValueError, match="case_id values must be unique"):
        evaluate_alternative_intent_holdout(
            (cases[0], duplicate, *cases[2:]),
            expected_categories=tuple(PRODUCT_CATEGORIES),
        )
    with pytest.raises(ValueError, match="too few cases"):
        evaluate_alternative_intent_holdout(
            cases[:-1],
            expected_categories=tuple(PRODUCT_CATEGORIES),
        )
