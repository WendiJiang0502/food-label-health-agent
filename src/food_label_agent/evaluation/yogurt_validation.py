"""Separate explicit synthetic correctness oracles from real-source query coverage."""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from food_label_agent.alternatives.source_screening import screen_official_sources
from food_label_agent.ingredients.api_models import ConstraintInput

DATA = Path(__file__).with_name("data") / "yogurt_queries_v2.json"


def evaluate(items):
    data = json.loads(DATA.read_text())
    actual = [
        x
        for x in items
        if x.get("category") == "dairy"
        and ("酸奶" in x.get("display_name", "") or x.get("product_type") == "yogurt")
    ]
    results = []
    for case in data["cases"]:
        request = SimpleNamespace(
            category="dairy",
            region="CN",
            retrieval_query=case.get("query"),
            constraints=[ConstraintInput(**c) for c in case.get("constraints", [])],
            health_concerns=[],
            nutrition_rows=case.get("baseline"),
        )
        candidate = (
            data["reference_candidate"]
            | {"last_seen_at": datetime.now(UTC).isoformat()}
            | case.get("candidate_override", {})
        )
        oracle = screen_official_sources([candidate], request)["items"][0]
        # Do not alter real records to manufacture source defects or freshness.
        coverage = screen_official_sources(actual, request)
        results.append(
            {
                "id": case["id"],
                "title": case["title"],
                "expected": case["expected"],
                "observed": oracle["status"],
                "correct": oracle["status"] == case["expected"],
                "false_pass": oracle["status"] == "matched"
                and case["expected"] != "matched",
                "missed_conflict": case["expected"] == "not_matched"
                and oracle["status"] != "not_matched",
                "real_counts": coverage["counts"],
                "synthetic_only": bool(case.get("candidate_override")),
            }
        )
    return {
        "version": data["version"],
        "simulated": True,
        "case_count": len(results),
        "product_records": len(actual),
        "correct": sum(x["correct"] for x in results),
        "false_passes": sum(x["false_pass"] for x in results),
        "missed_conflicts": sum(x["missed_conflict"] for x in results),
        "expected_distribution": dict(Counter(x["expected"] for x in results)),
        "real_query_count": sum(not x["synthetic_only"] for x in results),
        "real_queries_with_matches": sum(
            not x["synthetic_only"] and x["real_counts"].get("matched", 0) > 0
            for x in results
        ),
        "cases": results,
        "limitations": "固定合成样本的规则回归，不是人工标注真实商品的准确率；不写入真实需求队列。",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    r = evaluate(json.loads(Path(args.input).read_text()))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in r.items() if k != "cases"}, ensure_ascii=False))
    raise SystemExit(0 if r["correct"] == r["case_count"] else 1)
