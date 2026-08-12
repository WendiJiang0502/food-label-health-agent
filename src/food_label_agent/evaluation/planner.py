"""Ablation metrics for deterministic, raw-model and policy-guarded planners."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from food_label_agent.graph.planner import (
    ActionProposer,
    ModelPlannerError,
    create_action_proposer,
)


@dataclass(frozen=True, slots=True)
class PlannerAblationCase:
    name: str
    category: str
    difficulty: str
    context: dict[str, Any]
    candidates: tuple[dict[str, str], ...]
    expected_action_id: str


@dataclass(frozen=True, slots=True)
class PlannerAblationEvaluation:
    schema_version: str
    case_count: int
    category_count: int
    category_metrics: dict[str, dict[str, int | float | None]]
    deterministic_action_accuracy: float
    model_status: str
    raw_model_action_accuracy: float | None
    raw_model_policy_violation_rate: float | None
    guarded_model_action_accuracy: float | None
    guarded_model_policy_violation_rate: float | None
    guarded_fallback_rate: float | None
    guarded_model_lift: float | None
    case_results: tuple[dict[str, Any], ...]
    provider: str | None
    model: str | None
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


BENCHMARK_PATH = Path(__file__).with_name("data") / "planner_cases.json"
MIN_GUARDED_MODEL_ACCURACY = 0.85


def load_planner_benchmark(
    path: Path = BENCHMARK_PATH,
) -> tuple[str, tuple[PlannerAblationCase, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version", ""))
    if schema_version != "planner_benchmark_v2":
        raise ValueError("Unsupported planner benchmark schema")
    cases = []
    names = set()
    for item in payload.get("cases", []):
        name = str(item["name"])
        if name in names:
            raise ValueError(f"Duplicate planner benchmark case: {name}")
        names.add(name)
        candidates = tuple(item["candidates"])
        expected = str(item["expected_action_id"])
        if not candidates or expected not in {
            str(candidate["action_id"]) for candidate in candidates
        }:
            raise ValueError(f"Invalid candidates for planner benchmark case: {name}")
        cases.append(
            PlannerAblationCase(
                name=name,
                category=str(item["category"]),
                difficulty=str(item["difficulty"]),
                context=dict(item["context"]),
                candidates=candidates,
                expected_action_id=expected,
            )
        )
    if not cases:
        raise ValueError("Planner benchmark requires at least one case")
    return schema_version, tuple(cases)


PLANNER_BENCHMARK_SCHEMA, PLANNER_ABLATION_BENCHMARK = load_planner_benchmark()


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
    case_results = [
        {
            "name": case.name,
            "category": case.category,
            "difficulty": case.difficulty,
            "expected_action_id": case.expected_action_id,
            "deterministic_action_id": case.candidates[0]["action_id"],
            "deterministic_correct": (
                case.candidates[0]["action_id"] == case.expected_action_id
            ),
            "model_action_id": None,
            "model_action_legal": None,
            "guarded_action_id": None,
            "guarded_correct": None,
            "fallback_used": None,
        }
        for case in cases
    ]
    if proposer is None:
        return PlannerAblationEvaluation(
            schema_version=PLANNER_BENCHMARK_SCHEMA,
            case_count=len(cases),
            category_count=len({case.category for case in cases}),
            category_metrics=_category_metrics(cases, case_results),
            deterministic_action_accuracy=deterministic_accuracy,
            model_status="not_run",
            raw_model_action_accuracy=None,
            raw_model_policy_violation_rate=None,
            guarded_model_action_accuracy=None,
            guarded_model_policy_violation_rate=None,
            guarded_fallback_rate=None,
            guarded_model_lift=None,
            case_results=tuple(case_results),
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
    for index, case in enumerate(cases):
        legal = {item["action_id"] for item in case.candidates}
        try:
            benchmark_context = {
                **case.context,
                "task": {
                    **case.context.get("task", {}),
                    "request_id": f"ablation-{case.name}",
                },
            }
            proposal = proposer.propose(
                context=benchmark_context,
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
        case_results[index].update(
            {
                "model_action_id": proposed_id,
                "model_action_legal": is_legal,
                "guarded_action_id": guarded_id,
                "guarded_correct": guarded_id == case.expected_action_id,
                "fallback_used": not is_legal,
            }
        )

    count = len(cases)
    raw_violation_rate = raw_violations / count
    guarded_accuracy = guarded_correct / count
    if failures:
        blockers.append("model_planner_provider_failure")
    if guarded_accuracy < MIN_GUARDED_MODEL_ACCURACY:
        blockers.append("guarded_model_accuracy_below_threshold")
    if guarded_accuracy < deterministic_accuracy:
        blockers.append("guarded_model_action_regression")
    return PlannerAblationEvaluation(
        schema_version=PLANNER_BENCHMARK_SCHEMA,
        case_count=count,
        category_count=len({case.category for case in cases}),
        category_metrics=_category_metrics(cases, case_results),
        deterministic_action_accuracy=deterministic_accuracy,
        model_status="completed" if not failures else "failed",
        raw_model_action_accuracy=raw_correct / count,
        raw_model_policy_violation_rate=raw_violation_rate,
        guarded_model_action_accuracy=guarded_accuracy,
        guarded_model_policy_violation_rate=0.0,
        guarded_fallback_rate=fallback_count / count,
        guarded_model_lift=guarded_accuracy - deterministic_accuracy,
        case_results=tuple(case_results),
        provider=getattr(proposer, "provider", "unknown"),
        model=getattr(proposer, "model", "unknown"),
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )


def _category_metrics(
    cases: tuple[PlannerAblationCase, ...],
    case_results: list[dict[str, Any]],
) -> dict[str, dict[str, int | float | None]]:
    metrics = {}
    for category in sorted({case.category for case in cases}):
        selected = [
            result
            for case, result in zip(cases, case_results, strict=True)
            if case.category == category
        ]
        guarded = [item["guarded_correct"] for item in selected]
        metrics[category] = {
            "case_count": len(selected),
            "deterministic_action_accuracy": sum(
                bool(item["deterministic_correct"]) for item in selected
            )
            / len(selected),
            "guarded_model_action_accuracy": (
                sum(bool(value) for value in guarded) / len(guarded)
                if all(value is not None for value in guarded)
                else None
            ),
        }
    return metrics


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
