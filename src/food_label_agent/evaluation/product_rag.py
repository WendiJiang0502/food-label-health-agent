"""Reproducible product RAG scenarios; isolated from production and network."""

from __future__ import annotations

import json
from datetime import date
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from food_label_agent.alternatives.catalog import JsonProductCatalog
from food_label_agent.alternatives.field_evidence import external_field_evidence
from food_label_agent.alternatives.intent import evaluate_intent, parse_product_intent
from food_label_agent.alternatives.knowledge import ProductKnowledgeStore
from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
)
from food_label_agent.alternatives.rag import ProductRAG
from food_label_agent.alternatives.service import revalidate_alternatives


def run_product_rag_evaluation() -> dict:
    dataset = json.loads(
        files("food_label_agent.evaluation")
        .joinpath("data/product_rag_scenarios_v1.json")
        .read_text()
    )
    outcomes = []
    retrieved = hits = reciprocal = 0
    with TemporaryDirectory() as folder:
        rag = ProductRAG(
            ProductKnowledgeStore(Path(folder) / "evaluation.sqlite3"),
            profile="hybrid_tfidf",
        )
        for case in dataset["cases"]:
            kind = case["kind"]
            if kind == "intent":
                value = parse_product_intent(case["query"])
                value["goals"] = [
                    [g["nutrient"], g["direction"], g["reference"]]
                    for g in value["nutrition_goals"]
                ]
                actual = {k: value[k] for k in case["expected"]}
            elif kind == "comparison":
                intent = parse_product_intent(case["query"])
                result = evaluate_intent(
                    intent,
                    {"sugars": case["current"]} if case["current"] else {},
                    {"sugars": case["candidate"]} if case["candidate"] else {},
                    description=case.get("description", ""),
                    conflicts=case.get("conflicts", []),
                )
                actual = result["checks"][0]["outcome"]
            elif kind == "fields":
                result = external_field_evidence(
                    {
                        "code": "123",
                        "nutrition_data_per": case["raw_basis"],
                        "nutriments": {"sugars_100g": case["raw_value"]},
                    },
                    {
                        "images": {
                            "nutrition": {
                                "source_url": "https://images.openfoodfacts.org/example.jpg",
                                "image_sha256": "fixture-image",
                                "fields": [
                                    {
                                        "name": "nutrition_table",
                                        "raw_text": f"每100克\n糖 {case['ocr_value']}克",
                                    }
                                ],
                            }
                        }
                    },
                    version="fixture-api",
                    checked_at="2026-10-03",
                )
                actual = result["conflicts"]
            elif kind == "revalidation":
                records = list(
                    JsonProductCatalog().search(category="biscuit", region="CN").records
                )
                result = revalidate_alternatives(
                    AlternativeRevalidationRequest(
                        request_id=case["id"],
                        applicable_date="2026-10-03",
                        candidates=records,
                        retrieval_query=case["query"],
                        constraints=case["constraints"],
                        current_nutrition_rows=[
                            ["项目", "每100克"],
                            ["糖", f"{case['baseline']}克"],
                        ]
                        if case["baseline"] is not None
                        else None,
                    )
                )
                actual = sorted(
                    r["product_id"]
                    for r in result["results"]
                    if r["disposition"] == "eligible"
                )
            else:
                req = AlternativeSearchRequest(
                    category=case["category"],
                    retrieval_query=case["query"],
                    applicable_date=date(2026, 10, 3),
                )
                records = list(
                    JsonProductCatalog()
                    .search(category=req.category, region="CN")
                    .records
                )
                result = rag.search(req, records)
                ids = result["ranked_product_ids"] if result["items"] else []
                actual = ids[0] if ids else None
                if case["expected"]:
                    retrieved += 1
                    if case["expected"] in ids[:3]:
                        hits += 1
                        reciprocal += 1 / (ids.index(case["expected"]) + 1)
            outcomes.append(
                {
                    "id": case["id"],
                    "kind": kind,
                    "passed": actual == case["expected"],
                    "expected": case["expected"],
                    "actual": actual,
                }
            )
    passed = sum(r["passed"] for r in outcomes)
    return {
        "suite": "product_rag_scenarios_v1",
        "scope": dataset["scope"],
        "profile": "hybrid_tfidf",
        "case_count": len(outcomes),
        "passed": passed,
        "evaluation_passed": passed == len(outcomes),
        "retrieval_recall_at_3": hits / retrieved if retrieved else None,
        "retrieval_mrr": reciprocal / retrieved if retrieved else None,
        "unexpected_recommendation_count": sum(
            len(set(r["actual"]) - set(r["expected"]))
            for r in outcomes
            if r["kind"] == "revalidation"
        ),
        "results": outcomes,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_product_rag_evaluation()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "results"}, ensure_ascii=False
        )
    )
    raise SystemExit(0 if report["evaluation_passed"] else 1)
