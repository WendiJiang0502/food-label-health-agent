import json

from food_label_agent.evaluation.yogurt_validation import DATA, evaluate


def test_fifty_explicit_oracles_and_no_false_passes():
    result = evaluate([])
    assert result["case_count"] == 50 and result["correct"] == 50
    assert result["expected_distribution"] == {
        "not_matched": 11,
        "matched": 18,
        "unknown": 20,
        "not_evaluated": 1,
    }
    assert result["false_passes"] == 0 and result["missed_conflicts"] == 0
    assert result["real_query_count"] == 48 and result["real_queries_with_matches"] == 0


def test_real_coverage_does_not_rewrite_stale_evidence():
    data = json.loads(DATA.read_text())
    item = data["reference_candidate"] | {"last_seen_at": "2020-01-01"}
    before = json.dumps(item, sort_keys=True)
    result = evaluate([item])
    assert result["real_queries_with_matches"] == 0
    assert json.dumps(item, sort_keys=True) == before
