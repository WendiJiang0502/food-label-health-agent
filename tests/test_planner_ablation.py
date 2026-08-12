from __future__ import annotations

from food_label_agent.evaluation.planner import (
    PLANNER_ABLATION_BENCHMARK,
    evaluate_planner_ablation,
    load_planner_benchmark,
)
from food_label_agent.graph.planner import ModelPlannerError, PlannerProposal


class OracleProposer:
    provider = "test-model"
    model = "planner-test-v1"

    def propose(self, *, context: dict, candidates: tuple[dict, ...]):
        case_name = context["task"]["request_id"].removeprefix("ablation-")
        expected = next(
            case.expected_action_id
            for case in PLANNER_ABLATION_BENCHMARK
            if case.name == case_name
        )
        return PlannerProposal(
            action_id=expected,
            provider=self.provider,
            model=self.model,
        )


class IllegalActionProposer:
    provider = "test-model"
    model = "planner-adversarial-v1"

    def propose(self, *, context: dict, candidates: tuple[dict, ...]):
        return PlannerProposal(
            action_id="UNAPPROVED_TOOL_ACTION",
            provider=self.provider,
            model=self.model,
        )


class UnavailableProposer:
    provider = "test-model"
    model = "planner-unavailable-v1"

    def propose(self, *, context: dict, candidates: tuple[dict, ...]):
        raise ModelPlannerError("planner_provider_unavailable", retryable=True)


def test_offline_ablation_records_deterministic_baseline_without_remote_call() -> None:
    result = evaluate_planner_ablation()

    assert result.schema_version == "planner_benchmark_v2"
    assert result.case_count == 16
    assert result.category_count == 4
    assert result.deterministic_action_accuracy < 1.0
    assert result.model_status == "not_run"
    assert result.evaluation_passed is True


def test_benchmark_is_valid_and_contains_nontrivial_reordering_cases() -> None:
    schema, cases = load_planner_benchmark()

    assert schema == "planner_benchmark_v2"
    assert len(cases) == 16
    assert {case.category for case in cases} == {
        "safety_priority",
        "conflict_resolution",
        "evidence_gap",
        "multi_constraint",
    }
    assert any(
        case.candidates[0]["action_id"] != case.expected_action_id for case in cases
    )


def test_guarded_model_can_outperform_deterministic_baseline() -> None:
    result = evaluate_planner_ablation(OracleProposer())

    assert result.raw_model_action_accuracy == 1.0
    assert result.guarded_model_action_accuracy == 1.0
    assert result.guarded_model_policy_violation_rate == 0.0
    assert result.guarded_fallback_rate == 0.0
    assert result.guarded_model_lift is not None
    assert result.guarded_model_lift > 0
    assert all(
        metrics["guarded_model_action_accuracy"] == 1.0
        for metrics in result.category_metrics.values()
    )
    assert result.evaluation_passed is True


def test_policy_guard_blocks_illegal_model_action_and_uses_fallback() -> None:
    result = evaluate_planner_ablation(IllegalActionProposer())

    assert result.raw_model_policy_violation_rate == 1.0
    assert result.guarded_model_policy_violation_rate == 0.0
    assert result.guarded_fallback_rate == 1.0
    assert result.guarded_model_action_accuracy == result.deterministic_action_accuracy
    assert "guarded_model_accuracy_below_threshold" in result.release_blockers


def test_provider_failure_is_observed_and_falls_back_without_policy_violation() -> None:
    result = evaluate_planner_ablation(UnavailableProposer())

    assert result.model_status == "failed"
    assert result.guarded_fallback_rate == 1.0
    assert result.guarded_model_policy_violation_rate == 0.0
    assert "model_planner_provider_failure" in result.release_blockers
