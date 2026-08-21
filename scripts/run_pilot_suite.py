"""Run both internal-pilot lanes and emit one regression-oriented report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from food_label_agent.observability.trace import aggregate_traces

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> dict:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    python = sys.executable
    personal = _run([python, "scripts/run_internal_pilot.py", "--json", "/tmp/personal-pilot-suite.json"])
    general = _run([python, "scripts/run_general_explanations.py"])
    alternatives = _run([python, "scripts/run_alternative_pilot.py"])
    traces = [*personal.get("traces", []), *general.get("traces", []), *alternatives.get("traces", [])]
    report = {
        "schema_version": "internal_pilot_suite_v1",
        "lanes": {"personal_constraints": personal, "general_explanations": general, "alternatives": alternatives},
        "regression_summary": {
            "adapter_errors": personal["adapter_errors"],
            "provider_unavailable_cases": personal["provider_unavailable_cases"],
            "general_case_count": general["case_count"],
            "alternative_case_count": alternatives["case_count"],
            "alternative_revalidation_failures": [
                item["case_id"] for item in alternatives["results"]
                if item["revalidated_count"] and item["revalidation_rate"] < 1.0
            ],
            "general_status_mismatches": [
                {"case_id": item["case_id"], "expected": item["expected_status"], "actual": item["actual_status"]}
                for item in general["results"]
                if item["expected_status"] != item["actual_status"]
            ],
        },
        "traces": traces,
        "metrics": aggregate_traces(traces),
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.json:
        args.json.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
