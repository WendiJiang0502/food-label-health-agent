"""Cross-model comparison over the same conversation release cases."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .conversation import evaluate_conversation_agent


@dataclass(frozen=True, slots=True)
class ModelComparisonReport:
    baseline_model: str
    candidate_model: str
    production_model: str
    production_model_changed: bool
    results: dict[str, dict[str, Any]]
    evaluation_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "conversation_model_comparison_v1",
            "baseline_model": self.baseline_model,
            "candidate_model": self.candidate_model,
            "production_model": self.production_model,
            "production_model_changed": self.production_model_changed,
            "results": self.results,
            "evaluation_passed": self.evaluation_passed,
        }


def compare_models(
    baseline: str = "gpt-5.6-terra",
    candidate: str = "gpt-5.6-luna",
) -> ModelComparisonReport:
    reports = {
        model: evaluate_conversation_agent(live=True, model=model)
        for model in (baseline, candidate)
    }
    summaries = {
        model: {
            "case_count": report.case_count,
            "passed_count": report.passed_count,
            "pass_rate": report.passed_count / report.case_count,
            "evidence_grounding_rate": report.safety_metrics["evidence_grounding_rate"],
            **report.operational_metrics,
            "release_blockers": list(report.release_blockers),
            "failed_cases": [
                {"id": item["id"], "failures": item["failures"]}
                for item in report.cases
                if not item["passed"]
            ],
        }
        for model, report in reports.items()
    }
    # Model replacement is a separate reviewed release decision. A comparison never
    # mutates deployment configuration automatically.
    return ModelComparisonReport(
        baseline_model=baseline,
        candidate_model=candidate,
        production_model=baseline,
        production_model_changed=False,
        results=summaries,
        evaluation_passed=reports[baseline].evaluation_passed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare conversation models on one fixed dataset")
    parser.add_argument("--baseline", default="gpt-5.6-terra")
    parser.add_argument("--candidate", default="gpt-5.6-luna")
    parser.add_argument("--json", type=Path, dest="json_output")
    args = parser.parse_args()
    report = compare_models(args.baseline, args.candidate)
    serialized = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    raise SystemExit(0 if report.evaluation_passed else 1)


if __name__ == "__main__":
    main()
