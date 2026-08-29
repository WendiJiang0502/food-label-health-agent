"""Run the confirmed-fact internal pilot dataset through the real workflow.

OCR is intentionally out of scope here: dataset label_facts are treated as
user-confirmed facts. Provider outages are reported separately from business
decisions so an unavailable evidence provider cannot masquerade as a label
finding.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from food_label_agent.domain.types import AnalysisStatus
from food_label_agent.graph.runtime import run_agent_graph
from food_label_agent.graph.workflows import (
    evidence_payload,
    prepare_evaluation_state,
    run_regulatory_workflow,
)
from food_label_agent.ingredients.api_models import (
    ConstraintInput,
    SafetyEvaluationRequest,
)
from food_label_agent.observability.trace import RunTrace, aggregate_traces

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "docs/evaluation/internal_pilot_dataset_v1.json"
GENERAL_CASE_IDS = {"case_010", "case_012", "case_013", "case_014", "case_015"}
ALTERNATIVE_CASE_IDS = {"case_016", "case_017", "case_018", "case_019"}


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
    if nutrient.endswith("_mg"):
        nutrient = nutrient.removesuffix("_mg")
        unit = "mg"
    elif nutrient.endswith("_g"):
        nutrient = nutrient.removesuffix("_g")
        unit = "g"
    else:
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
    fields: dict[str, str] = {}
    if ingredients:
        fields["ingredients"] = ingredients
    if facts.get("allergen_statement") is not None:
        fields["allergen_statement"] = str(facts["allergen_statement"])
    if facts.get("claims"):
        fields["claims"] = "、".join(facts["claims"])
    nutrition = facts.get("nutrition") or {}
    nutrition_rows: list[list[str]] | None = None
    if nutrition:
        basis = str(nutrition.get("basis", ""))
        fields["nutrition_basis"] = basis
        basis_label = {
            "per_100g": "每100克",
            "per_100ml": "每100毫升",
            "per_serving": "每份",
        }.get(basis, basis)
        nutrition_rows = [["项目", basis_label, "NRV%"]]
        rendered_rows = []
        for name, value in nutrition.items():
            if name == "basis":
                continue
            unit = "mg" if name == "sodium_mg" else "g"
            label = {"sugars_g": "糖", "sodium_mg": "钠"}.get(name, name)
            rendered_rows.append(f"{label} {value}{unit}")
            nutrition_rows.append([label, f"{value}{unit}", ""])
        fields["nutrition_table"] = "\n".join(
            [f"项目\t{basis_label}\tNRV%", *rendered_rows]
        )

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
        applicable_date=datetime.now(UTC).date().isoformat(),
        confirmed_fields=fields,
        nutrition_rows=nutrition_rows,
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
    risk_priority = {"compatible": 0, "unknown": 1, "caution": 2, "avoid": 3}
    risk_levels = [finding.risk_level.value for finding in state["risk_findings"]]
    overall_risk = max(risk_levels, key=risk_priority.get) if risk_levels else "unknown"
    business_status = {
        "avoid": "blocked",
        "caution": "needs_confirmation",
        "unknown": "unknown",
        "compatible": "compatible",
    }[overall_risk]
    finding_codes = [finding.reason_code for finding in state["risk_findings"]]
    confirmation_codes = {
        "LABEL_NOT_CONFIRMED",
        "INGREDIENT_PARSE_UNCERTAIN",
        "NUTRITION_BASIS_MISMATCH",
        "NUTRITION_FACTS_UNCERTAIN",
        "NUTRITION_UNIT_MISMATCH",
    }
    if state["status"] is AnalysisStatus.NEEDS_CONFIRMATION or any(
        code in confirmation_codes for code in finding_codes
    ):
        business_status = "needs_confirmation"
    public_material = json.dumps(
        {
            "risk_findings": [asdict(finding) for finding in state["risk_findings"]],
            "ingredient_explanations": state["ingredient_explanations"],
            "claim_interpretations": state["claim_interpretations"],
            "warnings": state["warnings"],
            "unknowns": state["unknowns"],
        },
        ensure_ascii=False,
    )
    return {
        "actual_workflow_status": state["status"].value,
        "actual_business_status": business_status,
        "overall_risk_level": overall_risk,
        "evidence_status": evidence["status"],
        "business_blocked": state["status"] is AnalysisStatus.BLOCKED and bool(business_errors),
        "provider_unavailable": bool(provider_unavailable),
        "provider_errors": provider_unavailable,
        "business_errors": business_errors,
        "finding_codes": finding_codes,
        "workflow_trace": [item.node_name for item in state["workflow_trace"]],
        "node_timings": [
            {"node": item.node_name, "duration_ms": item.detail.get("duration_ms", 0), "outcome": item.outcome}
            for item in state["workflow_trace"]
        ],
        "tool_stats": tool_stats,
        "public_material": public_material,
    }


def run_case_workflow(case: dict[str, Any]):
    request = build_request(case)
    if case.get("label_facts", {}).get("confirmation_status") != "pending":
        return run_regulatory_workflow(request)
    working = prepare_evaluation_state(request)
    ingredients = working["label_fields"].get("ingredients")
    if ingredients:
        working["label_fields"]["ingredients"] = replace(
            ingredients, confirmed_by_user=False
        )
    state = run_agent_graph(working)
    return evidence_payload(state), state


def run(dataset: Path) -> dict[str, Any]:
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    results = []
    traces = []
    for case in payload["cases"]:
        if case["case_id"] in GENERAL_CASE_IDS | ALTERNATIVE_CASE_IDS:
            continue
        trace = RunTrace(run_id=f"pilot-{case['case_id']}", lane="personal_constraints", case_id=case["case_id"])
        try:
            evidence, state = run_case_workflow(case)
            result = classify_result(evidence, state)
            forbidden = [
                claim
                for claim in case.get("must_not_claim", [])
                if claim and claim in result["public_material"]
            ]
            result.update(
                {
                    "case_id": case["case_id"],
                    "expected_status": case["expected_status"],
                    "business_status_matches": result["actual_business_status"]
                    == case["expected_status"],
                    "forbidden_claim_violations": forbidden,
                    "case_passed": result["actual_business_status"]
                    == case["expected_status"]
                    and not forbidden,
                }
            )
            trace.increment("workflow_runs")
            trace.increment("tool_calls", len(state["tool_trace"]))
            for tool, stats in result.get("tool_stats", {}).items():
                trace.increment(f"tool:{tool}:calls", stats["calls"])
                trace.increment(f"tool:{tool}:failures", stats["failures"])
                trace.increment(f"tool:{tool}:retries", stats["retries"])
            trace.outcome["node_timings"] = result.get("node_timings", [])
            trace.finish(status=state["status"].value, outcome={"expected_status": case["expected_status"], "actual_status": result["actual_business_status"]})
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - surfaced in report
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
        "business_status_mismatches": [
            {
                "case_id": item["case_id"],
                "expected": item["expected_status"],
                "actual": item.get("actual_business_status", "adapter_error"),
            }
            for item in results
            if not item.get("business_status_matches", False)
        ],
        "forbidden_claim_violation_cases": [
            item["case_id"]
            for item in results
            if item.get("forbidden_claim_violations")
        ],
        "evaluation_passed": all(item.get("case_passed", False) for item in results),
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
