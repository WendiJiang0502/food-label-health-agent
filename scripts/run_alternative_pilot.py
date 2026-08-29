"""Run alternative-product pilot cases through search, revalidation, and compare."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from food_label_agent.alternatives.catalog import (
    PRODUCT_CATEGORIES,
    OfficialChinaCatalog,
)
from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductComparisonRequest,
)
from food_label_agent.alternatives.service import (
    compare_food_products,
    find_alternative_products,
    revalidate_alternatives,
)
from food_label_agent.evaluation.alternatives import (
    AlternativeAvailabilityCase,
    evaluate_alternative_availability,
)
from food_label_agent.ingredients.api_models import ConstraintInput
from food_label_agent.observability.trace import RunTrace, aggregate_traces

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "docs/evaluation/internal_pilot_dataset_v1.json"
ALT_IDS = {"case_016", "case_017", "case_018", "case_019"}
EXPECTED_SAFE_OUTCOMES = {
    "case_016": "abstained",
    "case_017": "eligible",
    "case_018": "all_excluded",
    "case_019": "abstained",
}


def constraints(case: dict) -> list[ConstraintInput]:
    profile = case.get("user_profile", {})
    result = [
        ConstraintInput(
            kind="allergy",
            canonical_value=x,
            severity=profile.get("severity", "unspecified"),
        )
        for x in profile.get("allergens", [])
    ]
    for key, threshold in profile.get("limits", {}).items():
        raw = key.removesuffix("_max").split("_per_")
        nutrient, basis = raw
        result.append(
            ConstraintInput(
                kind="nutrition_limit",
                canonical_value=nutrient,
                operator="max",
                threshold=threshold,
                unit="mg" if nutrient == "sodium" else "g",
                basis=f"per_{basis}",
            )
        )
    return result


def rows(case: dict) -> list[list[str]] | None:
    nutrition = case["label_facts"].get("nutrition") or {}
    if not nutrition:
        return None
    result = [["项目", nutrition.get("basis", "")]]
    for key, value in nutrition.items():
        if key != "basis":
            result.append(
                [{"sugars_g": "糖", "sodium_mg": "钠"}.get(key, key), str(value)]
            )
    return result


def run_case(case: dict) -> dict:
    cs = constraints(case)
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="biscuit",
            applicable_date="2026-08-21",
            constraints=cs,
            health_concerns=["blood_sugar"]
            if any(
                "sugars" in str(x)
                for x in case.get("user_profile", {}).get("limits", {})
            )
            else [],
            region="CN",
            exclude_product_ids=[],
            limit=10,
        )
    )
    revalidated = revalidate_alternatives(
        AlternativeRevalidationRequest(
            request_id=f"alternative-pilot-{case['case_id']}",
            applicable_date="2026-08-21",
            constraints=cs,
            health_concerns=[],
            current_nutrition_rows=rows(case),
            candidates=search["candidates"],
        )
    )
    eligible = [
        item for item in revalidated["results"] if item["disposition"] == "eligible"
    ]
    comparison = (
        compare_food_products(ProductComparisonRequest(products=eligible))
        if eligible
        else {
            "status": "not_compared",
            "unknowns": ["no_eligible_revalidated_candidate"],
        }
    )
    outcome = (
        "eligible"
        if eligible
        else "all_excluded"
        if revalidated["results"]
        and all(item["disposition"] == "excluded" for item in revalidated["results"])
        else "abstained"
    )
    expected_outcome = EXPECTED_SAFE_OUTCOMES[case["case_id"]]
    return {
        "case_id": case["case_id"],
        "search_status": search["status"],
        "candidate_count": len(search["candidates"]),
        "revalidated_count": revalidated["revalidated_count"],
        "revalidation_rate": revalidated["revalidation_rate"],
        "eligible_product_ids": [item["product_id"] for item in eligible],
        "excluded_product_ids": [
            item["product_id"]
            for item in revalidated["results"]
            if item["disposition"] == "excluded"
        ],
        "comparison_status": comparison.get("status"),
        "catalog_warnings": search.get("catalog_warnings", []),
        "safe_outcome": outcome,
        "expected_safe_outcome": expected_outcome,
        "safe_outcome_passed": outcome == expected_outcome,
    }


def availability_matrix(*, health_concerns: tuple[str, ...] = ()) -> dict:
    applicable_date = datetime.now(UTC).date().isoformat()
    cases = tuple(
        AlternativeAvailabilityCase(
            name=f"catalog-{category}",
            category=category,
            applicable_date=applicable_date,
            minimum_eligible=3,
            health_concerns=health_concerns,
            minimum_target_comparable_rate=0.5 if health_concerns else 0.0,
            minimum_effective_display_rate=0.5 if health_concerns else 0.0,
            minimum_distinct_brands=2,
        )
        for category in PRODUCT_CATEGORIES
    )
    return evaluate_alternative_availability(
        cases, catalog=OfficialChinaCatalog()
    ).to_dict()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    traces = []
    results = []
    for case in data["cases"]:
        if case["case_id"] not in ALT_IDS:
            continue
        trace = RunTrace(
            run_id=f"pilot-{case['case_id']}",
            lane="alternatives",
            case_id=case["case_id"],
        )
        result = run_case(case)
        trace.increment("candidate_searches")
        trace.increment("candidate_revalidations", result["revalidated_count"])
        trace.increment("comparisons", int(result["comparison_status"] == "compared"))
        trace.finish(
            status="completed",
            outcome={
                "eligible_count": len(result["eligible_product_ids"]),
                "comparison_status": result["comparison_status"],
            },
        )
        results.append(result)
        traces.append(trace.to_dict())
    availability = availability_matrix()
    blood_sugar_availability = availability_matrix(
        health_concerns=("blood_sugar",)
    )
    safety_passed = sum(item["safe_outcome_passed"] for item in results)
    print(
        json.dumps(
            {
                "schema_version": "alternative_pilot_v2",
                "case_count": len(results) + availability["case_count"],
                "historical_safety_case_count": len(results),
                "catalog_availability_case_count": availability["case_count"],
                "results": results,
                "safety_gate": {
                    "passed_case_count": safety_passed,
                    "case_count": len(results),
                    "evaluation_passed": safety_passed == len(results),
                },
                "catalog_availability": availability,
                "blood_sugar_availability": blood_sugar_availability,
                "evaluation_passed": (
                    safety_passed == len(results) and availability["evaluation_passed"]
                ),
                "traces": traces,
                "metrics": aggregate_traces(traces),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
