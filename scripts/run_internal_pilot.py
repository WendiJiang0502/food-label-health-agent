"""Run the confirmed-fact internal pilot dataset through the real workflow.

OCR is intentionally out of scope here: dataset label_facts are treated as
user-confirmed facts. Provider outages are reported separately from business
decisions so an unavailable evidence provider cannot masquerade as a label
finding.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from food_label_agent.domain.types import AnalysisStatus
from food_label_agent.graph.workflows import run_regulatory_workflow
from food_label_agent.ingredients.api_models import ConstraintInput, SafetyEvaluationRequest
from food_label_agent.observability.trace import RunTrace, aggregate_traces


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "docs/evaluation/internal_pilot_dataset_v1.json"
GENERAL_CASE_IDS = {"case_010", "case_012", "case_013", "case_014", "case_015"}


def _flatten_ingredients(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "、".join(_flatten_ingredients(item) for item in value)
    if isinstance(value, dict):
        name = str(value.get("name", ""))
        children = value.get("subingredients")
        return name + (f"（{_flatten_ingredients(children)}）" if children else "")
    return str(value)


def _nutrition_constraint(key: str, threshold: float) -> ConstraintInput:
    """Parse e.g. sugars_g_per_100g_max without treating max as the basis."""
    parts = key.removesuffix("_max").split("_per_")
    if len(parts) != 2:
        raise ValueError(f"Unsupported nutrition limit key: {key}")
    nutrient, basis = parts
    unit = "mg" if nutrient in {"sodium", "salt"} else "g"
    return ConstraintInput(
        kind="nutrition_limit",
        canonical_value=nutrient,
        operator="max",
        threshold=threshold,
        unit=unit,
        basis=f"per_{basis}",
    )


def build_request(case: dict[str, Any]) -> SafetyEvaluationRequest:
    facts = case["label_facts"]
    ingredients = _flatten_ingredients(facts.get("ingredients", []))
    # The production request contract requires an ingredients field even for
    # a nutrition-only pilot case. This sentinel is explicit absence, not an
    # ingredient claim, and prevents the adapter from inventing a product fact.
    fields: dict[str, str] = {"ingredients": ingredients or "（配料表未提供）"}
    if facts.get("allergen_statement") is not None:
        fields["allergen_statement"] = str(facts["allergen_statement"])
    if facts.get("claims"):
        fields["claims"] = "、".join(facts["claims"])
    nutrition = facts.get("nutrition") or {}
    if nutrition:
        basis = str(nutrition.get("basis", ""))
        fields["nutrition_basis"] = basis
        rows = []
        for name, value in nutrition.items():
            if name == "basis":
                continue
            unit = "mg" if name == "sodium_mg" else "g"
            label = {"sugars_g": "糖", "sodium_mg": "钠"}.get(name, name)
            rows.append(f"{label} {value}{unit}")
        fields["nutrition_table"] = "\n".join(rows)

    profile = case.get("user_profile", {})
    constraints = [
        ConstraintInput(
            kind="allergy",
            canonical_value=value,
            severity=profile.get("severity", "unspecified"),
        )
        for value in profile.get("allergens", [])
    ]
    constraints.extend(
        _nutrition_constraint(key, value)
        for key, value in profile.get("limits", {}).items()
    )
    return SafetyEvaluationRequest(
        request_id=f"internal-pilot-{case['case_id']}",
        jurisdiction="CN",
        applicable_date="2026-08-21",
        confirmed_fields=fields,
        constraints=constraints,
    )


def classify_result(evidence: dict[str, Any], state: Any) -> dict[str, Any]:
    errors = list(state["errors"])
    provider_unavailable = [
        error for error in errors if "mcp_tool_failed" in error or "provider" in error.lower()
    ]
    business_errors = [error for error in errors if error not in provider_unavailable]
    tool_events = [item for item in state["tool_trace"] if item.tool_name]
    tool_stats = {}
    for item in tool_events:
        stat = tool_stats.setdefault(item.tool_name, {"calls": 0, "successes": 0, "failures": 0, "retries": 0})
        stat["calls"] += 1
        stat["successes"] += int(item.outcome in {"succeeded", "recovered"})
        stat["failures"] += int(item.outcome == "failed")
        stat["retries"] += int(item.outcome == "retry_scheduled")
    return {
        "actual_workflow_status": state["status"].value,
        "evidence_status": evidence["status"],
        "business_blocked": state["status"] is AnalysisStatus.BLOCKED and bool(business_errors),
        "provider_unavailable": bool(provider_unavailable),
        "provider_errors": provider_unavailable,
        "business_errors": business_errors,
        "finding_codes": [finding.reason_code for finding in state["risk_findings"]],
        "workflow_trace": [item.node_name for item in state["workflow_trace"]],
        "node_timings": [
            {"node": item.node_name, "duration_ms": item.detail.get("duration_ms", 0), "outcome": item.outcome}
            for item in state["workflow_trace"]
        ],
        "tool_stats": tool_stats,
    }


def run(dataset: Path) -> dict[str, Any]:
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    results = []
    traces = []
    for case in payload["cases"]:
        if case["case_id"] in GENERAL_CASE_IDS:
            continue
        trace = RunTrace(run_id=f"pilot-{case['case_id']}", lane="personal_constraints", case_id=case["case_id"])
        try:
            evidence, state = run_regulatory_workflow(build_request(case))
            result = classify_result(evidence, state)
            result.update({"case_id": case["case_id"], "expected_status": case["expected_status"]})
            trace.increment("workflow_runs")
            trace.increment("tool_calls", len(state["tool_trace"]))
            for tool, stats in result.get("tool_stats", {}).items():
                trace.increment(f"tool:{tool}:calls", stats["calls"])
                trace.increment(f"tool:{tool}:failures", stats["failures"])
                trace.increment(f"tool:{tool}:retries", stats["retries"])
            trace.outcome["node_timings"] = result.get("node_timings", [])
            trace.finish(status=state["status"].value, outcome={"expected_status": case["expected_status"], "actual_status": state["status"].value})
        except Exception as exc:  # pragma: no cover - surfaced in report
            result = {
                "case_id": case["case_id"],
                "expected_status": case["expected_status"],
                "actual_workflow_status": "adapter_error",
                "adapter_error": f"{type(exc).__name__}: {exc}",
            }
            trace.finish(status="adapter_error", outcome={"error": type(exc).__name__})
        results.append(result)
        traces.append(trace.to_dict())
    return {
        "dataset_id": payload["dataset_id"],
        "dataset_version": payload["version"],
        "case_count": len(results),
        "results": results,
        "adapter_errors": sum("adapter_error" in item for item in results),
        "provider_unavailable_cases": sum(item.get("provider_unavailable", False) for item in results),
        "traces": traces,
        "metrics": aggregate_traces(traces),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = run(args.dataset)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.json:
        args.json.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
