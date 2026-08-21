"""Run label explanations without entering the personal-constraint workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from food_label_agent.claims.models import ClaimConsistencyRequest, ClaimInterpretationRequest
from food_label_agent.claims.service import interpret_claim, verify_claim_consistency
from food_label_agent.ingredients.explanations import IngredientExplanationRequest, explain_ingredient_with_evidence
from food_label_agent.ingredients.service import normalize_food_label_result
from food_label_agent.regulations.models import RegulationSearchRequest
from food_label_agent.regulations.service import search_regulations
from food_label_agent.observability.trace import RunTrace, aggregate_traces

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "docs/evaluation/internal_pilot_general_explanations_v1.json"


def run_case(case: dict) -> dict:
    facts = case["label_facts"]
    ingredients = "、".join(facts.get("ingredients", []))
    normalized = normalize_food_label_result(ingredients)
    evidence = []
    if facts.get("claims"):
        result = search_regulations(RegulationSearchRequest(
            query="食品标签 声称 糖",
            jurisdiction="CN", applicable_date="2026-08-21",
            topics=["nutrition_labeling"], limit=5,
        ))
        evidence = result.results
        interpreted = interpret_claim(ClaimInterpretationRequest(
            claim_text="、".join(facts["claims"]), regulatory_evidence=evidence,
            applicable_date="2026-08-21",
        ))
        consistency = verify_claim_consistency(ClaimConsistencyRequest(
            claims=interpreted.claims, ingredients_text=ingredients,
            nutrition_values=facts.get("nutrition", {}), regulatory_evidence=evidence,
            applicable_date="2026-08-21",
        ))
        return {"case_id": case["case_id"], "entrypoint": "claims_and_consistency",
                "actual_status": consistency.status, "interpretation_status": interpreted.status,
                "findings": consistency.findings, "unknowns": list(dict.fromkeys([*interpreted.unknowns, *consistency.unknowns])),
                "evidence_count": len(evidence), "expected_status": case["expected_status"]}
    item = next((item for item in normalized["ingredients"] if item.get("raw_name") == "山梨酸钾"), None)
    if item is None:
        return {"case_id": case["case_id"], "entrypoint": "ingredient_explanation",
                "actual_status": "unknown", "unknowns": ["ingredient_identity_or_regulatory_evidence_missing"],
                "evidence_count": 0, "expected_status": case["expected_status"]}
    explanation = explain_ingredient_with_evidence(IngredientExplanationRequest(
        ingredient=item, risk_finding=None, regulatory_evidence=[], jurisdiction="CN",
        applicable_date="2026-08-21",
    ))
    return {"case_id": case["case_id"], "entrypoint": "ingredient_explanation",
            "actual_status": explanation.status, "unknowns": explanation.unknowns,
            "evidence_count": 0, "expected_status": case["expected_status"]}


def run_with_trace(case: dict) -> tuple[dict, dict]:
    trace = RunTrace(run_id=f"pilot-{case['case_id']}", lane="general_explanations", case_id=case["case_id"])
    try:
        result = run_case(case)
        trace.increment("workflow_runs")
        trace.increment("evidence_queries", int(result.get("evidence_count", 0) > 0))
        trace.finish(status=result["actual_status"], outcome={"expected_status": case["expected_status"], "actual_status": result["actual_status"]})
    except Exception as exc:
        trace.finish(status="error", outcome={"error": type(exc).__name__})
        raise
    return result, trace.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    pairs = [run_with_trace(case) for case in data["cases"]]
    results = [pair[0] for pair in pairs]
    traces = [pair[1] for pair in pairs]
    print(json.dumps({"dataset_id": data["dataset_id"], "case_count": len(results), "results": results, "traces": traces, "metrics": aggregate_traces(traces)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
