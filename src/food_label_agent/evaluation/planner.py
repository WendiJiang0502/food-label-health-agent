"""Ablation metrics for deterministic, raw-model and policy-guarded planners."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.graph.planner import (
    ActionProposer,
    ModelPlannerError,
    create_action_proposer,
)


@dataclass(frozen=True, slots=True)
class PlannerAblationCase:
    name: str
    context: dict[str, Any]
    candidates: tuple[dict[str, str], ...]
    expected_action_id: str


@dataclass(frozen=True, slots=True)
class PlannerAblationEvaluation:
    case_count: int
    deterministic_action_accuracy: float
    model_status: str
    raw_model_action_accuracy: float | None
    raw_model_policy_violation_rate: float | None
    guarded_model_action_accuracy: float | None
    guarded_model_policy_violation_rate: float | None
    guarded_fallback_rate: float | None
    provider: str | None
    model: str | None
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def _candidate(action_id: str, tool_name: str) -> dict[str, str]:
    return {
        "action_id": action_id,
        "tool_name": tool_name,
        "purpose": "select the next required evidence operation",
    }


PLANNER_ABLATION_BENCHMARK = (
    PlannerAblationCase(
        name="allergen-before-independent-evidence",
        context={"risk": "avoid", "missing": ["allergen_rule", "additive_rule"]},
        candidates=(
            _candidate("RETRIEVE_ALLERGEN_RULES", "search_food_regulations"),
            _candidate("RETRIEVE_ADDITIVE_RULES", "search_food_regulations"),
        ),
        expected_action_id="RETRIEVE_ALLERGEN_RULES",
    ),
    PlannerAblationCase(
        name="additive-evidence",
        context={"risk": "compatible", "missing": ["additive_rule", "claim_rule"]},
        candidates=(
            _candidate("RETRIEVE_ADDITIVE_RULES", "search_food_regulations"),
            _candidate("RETRIEVE_CLAIM_RULES", "search_food_regulations"),
        ),
        expected_action_id="RETRIEVE_ADDITIVE_RULES",
    ),
    PlannerAblationCase(
        name="hard-risk-explanation",
        context={"risk": "avoid", "evidence_ready": True},
        candidates=(
            _candidate("EXPLAIN_RISK:label.ingredients.item.1", "explain_ingredient"),
            _candidate(
                "EXPLAIN_ADDITIVE:label.ingredients.item.2", "explain_ingredient"
            ),
        ),
        expected_action_id="EXPLAIN_RISK:label.ingredients.item.1",
    ),
    PlannerAblationCase(
        name="claim-interpretation",
        context={"confirmed_claim": "低糖", "claim_interpreted": False},
        candidates=(_candidate("INTERPRET_CONFIRMED_CLAIMS", "interpret_label_claim"),),
        expected_action_id="INTERPRET_CONFIRMED_CLAIMS",
    ),
    PlannerAblationCase(
        name="claim-consistency",
        context={"claim_interpreted": True, "consistency_checked": False},
        candidates=(
            _candidate("VERIFY_CLAIM_AGAINST_FACTS", "verify_label_consistency"),
        ),
        expected_action_id="VERIFY_CLAIM_AGAINST_FACTS",
    ),
)


def evaluate_planner_ablation(
    proposer: ActionProposer | None = None,
    cases: tuple[PlannerAblationCase, ...] = PLANNER_ABLATION_BENCHMARK,
) -> PlannerAblationEvaluation:
    if not cases:
        raise ValueError("Planner ablation requires at least one case")
    deterministic_correct = sum(
        case.candidates[0]["action_id"] == case.expected_action_id for case in cases
    )
    deterministic_accuracy = deterministic_correct / len(cases)
    blockers = []
    if deterministic_accuracy < 1.0:
        blockers.append("deterministic_planner_regression")
    if proposer is None:
        return PlannerAblationEvaluation(
            case_count=len(cases),
            deterministic_action_accuracy=deterministic_accuracy,
            model_status="not_run",
            raw_model_action_accuracy=None,
            raw_model_policy_violation_rate=None,
            guarded_model_action_accuracy=None,
            guarded_model_policy_violation_rate=None,
            guarded_fallback_rate=None,
            provider=None,
            model=None,
            evaluation_passed=not blockers,
            release_blockers=tuple(blockers),
        )

    raw_correct = 0
    raw_violations = 0
    guarded_correct = 0
    fallback_count = 0
    failures = 0
    for case in cases:
        legal = {item["action_id"] for item in case.candidates}
        try:
            proposal = proposer.propose(
                context={
                    "task": {"request_id": f"ablation-{case.name}"},
                    **case.context,
                },
                candidates=case.candidates,
            )
            proposed_id = proposal.action_id
        except ModelPlannerError:
            failures += 1
            proposed_id = "__PROVIDER_FAILURE__"
        is_legal = proposed_id in legal
        raw_violations += not is_legal
        raw_correct += proposed_id == case.expected_action_id
        guarded_id = proposed_id if is_legal else case.candidates[0]["action_id"]
        fallback_count += not is_legal
        guarded_correct += guarded_id == case.expected_action_id

    count = len(cases)
    raw_violation_rate = raw_violations / count
    guarded_accuracy = guarded_correct / count
    if failures:
        blockers.append("model_planner_provider_failure")
    if guarded_accuracy < 1.0:
        blockers.append("guarded_model_action_regression")
    return PlannerAblationEvaluation(
        case_count=count,
        deterministic_action_accuracy=deterministic_accuracy,
        model_status="completed" if not failures else "failed",
        raw_model_action_accuracy=raw_correct / count,
        raw_model_policy_violation_rate=raw_violation_rate,
        guarded_model_action_accuracy=guarded_accuracy,
        guarded_model_policy_violation_rate=0.0,
        guarded_fallback_rate=fallback_count / count,
        provider=getattr(proposer, "provider", "unknown"),
        model=getattr(proposer, "model", "unknown"),
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare deterministic, raw-model and guarded model planners."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the configured remote model; otherwise report it as not run.",
    )
    args = parser.parse_args()
    proposer = create_action_proposer() if args.live else None
    if args.live and proposer is None:
        raise SystemExit(
            "Set FOOD_LABEL_PLANNER_PROVIDER=openai and OPENAI_API_KEY first."
        )
    result = evaluate_planner_ablation(proposer)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.evaluation_passed else 1)


if __name__ == "__main__":
    main()
