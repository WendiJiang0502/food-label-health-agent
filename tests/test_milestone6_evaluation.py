from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from food_label_agent.evaluation.failures import evaluate_failure_corpus
from food_label_agent.evaluation.rules import evaluate_allergen_rules
from food_label_agent.evaluation.safety import evaluate_final_safety_gate
from food_label_agent.evaluation.suite import render_markdown, run_evaluation
from food_label_agent.evaluation.versions import build_version_snapshot


def test_allergen_dictionary_is_a_release_blocking_complete_recall_corpus() -> None:
    result = evaluate_allergen_rules()

    assert result.category_count == 8
    assert result.alias_count > 0
    assert result.explicit_case_count == result.alias_count * 2
    assert result.explicit_recall == 1.0
    assert result.severe_miss_rate == 0.0
    assert result.evidence_traceability_rate == 1.0
    assert result.ambiguous_unknown_accuracy == 1.0
    assert result.evaluation_passed is True


def test_known_failure_corpus_is_permanent_release_regression() -> None:
    result = evaluate_failure_corpus()

    assert result.schema_version == "failure_corpus_v1"
    assert result.case_count >= 6
    assert result.passed_count == result.case_count
    assert result.failed_case_ids == ()
    assert result.evaluation_passed is True


def test_final_safety_gate_blocks_all_adversarial_bypasses() -> None:
    result = evaluate_final_safety_gate()

    assert result.case_count == 4
    assert result.safety_gate_bypass_rate == 0.0
    assert result.hard_risk_preservation_rate == 1.0
    assert result.invalid_evidence_block_rate == 1.0
    assert result.missing_fact_refusal_rate == 1.0
    assert result.evaluation_passed is True


@pytest.fixture(scope="module")
def clean_version_snapshot():
    return replace(build_version_snapshot(), git_dirty=False)


def test_development_report_is_green_but_never_claims_ocr_release_readiness(
    clean_version_snapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOOD_LABEL_RAG_PROFILE", "hybrid_dense_rerank")
    report = run_evaluation(
        profile="development", version_snapshot=clean_version_snapshot
    )

    assert report.evaluation_passed is True
    assert report.release_ready is False
    assert report.release_blockers == ()
    assert os.environ["FOOD_LABEL_RAG_PROFILE"] == "hybrid_dense_rerank"
    assert report.components["ocr"]["status"] == "not_run"
    assert report.warnings
    assert set(report.components) == {
        "rules",
        "rag",
        "rag2_ablation",
        "agent",
        "planner_ablation",
        "alternatives",
        "safety_gate",
        "failure_corpus",
        "ocr",
    }
    markdown = render_markdown(report)
    assert "Milestone 6 统一评测报告" in markdown
    assert "版本快照" in markdown
    assert "private_ocr_dataset_not_provided" not in markdown


def test_release_profile_fails_closed_without_private_ocr_dataset(
    clean_version_snapshot,
) -> None:
    report = run_evaluation(profile="release", version_snapshot=clean_version_snapshot)

    assert report.evaluation_passed is False
    assert report.release_ready is False
    assert "ocr:private_ocr_benchmark_required_for_release" in report.release_blockers


def test_release_profile_accepts_only_a_complete_ocr_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clean_version_snapshot,
) -> None:
    async def complete_ocr_report(_path: Path):
        return {
            "schema_version": "1.0",
            "provider": "tencent",
            "sample_count": 50,
            "recognized_count": 40,
            "blocked_count": 10,
            "provider_error_count": 0,
            "supervised_count": 30,
            "aggregate_metrics": {
                "ingredients_cer": 0.01,
                "allergen_recall": 1.0,
                "numeric_token_recall": 1.0,
                "nutrient_value_alignment_accuracy": 1.0,
            },
            "expected_low_quality_count": 10,
            "low_quality_block_recall": 1.0,
            "blocking_issue_counts": {},
            "samples": [],
        }

    monkeypatch.setattr(
        "food_label_agent.evaluation.suite.evaluate_directory",
        complete_ocr_report,
    )
    report = run_evaluation(
        profile="release",
        ocr_images=tmp_path,
        version_snapshot=clean_version_snapshot,
    )

    assert report.evaluation_passed is True
    assert report.release_ready is True
    assert report.release_blockers == ()


def test_release_profile_records_dirty_worktree_as_a_blocker() -> None:
    dirty = replace(build_version_snapshot(), git_dirty=True)
    report = run_evaluation(profile="release", version_snapshot=dirty)

    assert "versions:git_worktree_dirty" in report.release_blockers
