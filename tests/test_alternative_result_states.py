from food_label_agent.graph.workflows import (
    _alternative_result_summary,
    _with_alternative_result_state,
)


def test_missing_declared_sugar_becomes_actionable_same_use_state() -> None:
    item = {
        "display_name": "未单列糖的候选",
        "disposition": "eligible",
        "catalog_eligibility": {
            "missing_comparison_fields": ["糖"],
            "sugars_review_status": "not_declared",
        },
    }

    result = _with_alternative_result_state(
        item,
        health_comparison_requested=True,
    )["result_state"]

    assert result["state"] == "same_use_evidence_limited"
    assert "不能判断是否符合你的糖上限" in result["detail"]
    assert "可以继续查看碳水化合物" in result["next_action"]
    assert "不能宣称它更适合控糖" in result["next_action"]


def test_no_results_use_no_trusted_candidate_without_inventing_a_count() -> None:
    result = _alternative_result_summary(
        eligible=[],
        excluded=[],
        evidence_rejected=[],
    )

    assert result["primary_state"] == "no_trusted_candidate"
    assert result["primary"]["label"] == "当前没有可信候选"
    assert result["counts"] == {
        "comparable": 0,
        "same_use_evidence_limited": 0,
        "packaging_review_required": 0,
        "constraint_conflict": 0,
    }
    assert result["safety_gate_held"] is True
