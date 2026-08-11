from __future__ import annotations

from food_label_agent.evaluation.planner import evaluate_planner_ablation
from food_label_agent.graph.planner import PlannerProposal


class FirstCandidateProposer:
    provider = "test-model"
    model = "planner-test-v1"

    def propose(self, *, context: dict, candidates: tuple[dict, ...]):
        return PlannerProposal(
            action_id=candidates[0]["action_id"],
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


def test_offline_ablation_records_deterministic_baseline_without_remote_call() -> None:
    result = evaluate_planner_ablation()

    assert result.deterministic_action_accuracy == 1.0
    assert result.model_status == "not_run"
    assert result.evaluation_passed is True


def test_guarded_model_matches_baseline_on_benchmark() -> None:
    result = evaluate_planner_ablation(FirstCandidateProposer())

    assert result.raw_model_action_accuracy == 1.0
    assert result.guarded_model_action_accuracy == 1.0
    assert result.guarded_model_policy_violation_rate == 0.0
    assert result.guarded_fallback_rate == 0.0
    assert result.evaluation_passed is True


def test_policy_guard_blocks_illegal_model_action_and_uses_fallback() -> None:
    result = evaluate_planner_ablation(IllegalActionProposer())

    assert result.raw_model_policy_violation_rate == 1.0
    assert result.guarded_model_policy_violation_rate == 0.0
    assert result.guarded_fallback_rate == 1.0
    assert result.guarded_model_action_accuracy == 1.0
    assert result.evaluation_passed is True
