"""Repeatable simulated yogurt queries; isolated from real-user demand statistics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from food_label_agent.alternatives.completion import (
    completion_snapshot,
    record_screening_gaps,
)
from food_label_agent.alternatives.knowledge import ProductKnowledgeStore
from food_label_agent.alternatives.source_screening import screen_official_sources
from food_label_agent.ingredients.api_models import ConstraintInput


def cases():
    def limit(key, value, unit="g", basis="per_100g"):
        return {
            "kind": "nutrition_limit",
            "canonical_value": key,
            "operator": "max",
            "threshold": value,
            "unit": unit,
            "basis": basis,
        }

    return [
        {
            "id": "fat_max",
            "title": "脂肪每100克不超过5克",
            "constraints": [limit("fat", 5)],
        },
        {
            "id": "sugar_max",
            "title": "糖每100克不超过5克",
            "constraints": [limit("sugars", 5)],
        },
        {
            "id": "protein_more",
            "title": "蛋白质比每100克3克更多",
            "query": "蛋白质更多",
            "baseline": [["项目", "每100克"], ["蛋白质", "3克"]],
        },
        {
            "id": "fat_less",
            "title": "脂肪比每100克4克更少",
            "query": "脂肪更少",
            "baseline": [["项目", "每100克"], ["脂肪", "4克"]],
        },
        {
            "id": "fat_and_sugar",
            "title": "脂肪与糖双上限",
            "constraints": [limit("fat", 5), limit("sugars", 5)],
        },
        {
            "id": "fat_and_allergy",
            "title": "脂肪上限并限制花生",
            "constraints": [
                limit("fat", 5),
                {"kind": "allergy", "canonical_value": "peanut"},
            ],
        },
        {
            "id": "avoid_ingredient",
            "title": "回避指定配料",
            "constraints": [{"kind": "avoid", "canonical_value": "白砂糖"}],
        },
        {
            "id": "missing_baseline",
            "title": "蛋白质更多但没有原商品数值",
            "query": "蛋白质更多",
        },
        {
            "id": "different_basis",
            "title": "按每100毫升限制脂肪",
            "constraints": [limit("fat", 5, basis="per_100ml")],
        },
        {
            "id": "sodium_max",
            "title": "钠每100克不超过50毫克",
            "constraints": [limit("sodium", 50, unit="mg")],
        },
    ]


def run(input_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    items = json.loads(Path(input_path).read_text())
    # Explicit name matching avoids silently treating milk or pudding as yogurt.
    yogurts = [
        x
        for x in items
        if x.get("category") == "dairy"
        and ("酸奶" in x.get("display_name", "") or x.get("product_type") == "yogurt")
    ]
    store = ProductKnowledgeStore(output / "simulated-demand.sqlite3")
    results = []
    for case in cases():
        req = SimpleNamespace(
            category="dairy",
            region="CN",
            retrieval_query=case.get("query"),
            constraints=[ConstraintInput(**x) for x in case.get("constraints", [])],
            health_concerns=[],
            nutrition_rows=case.get("baseline"),
        )
        result = screen_official_sources(yogurts, req)
        record_screening_gaps(store, result, "simulation:yogurt-v1:" + case["id"])
        results.append({"case": case, "result": result})
    report = {
        "scope": "simulated_queries_not_real_users",
        "dataset": "yogurt-v1",
        "product_count": len(yogurts),
        "query_count": len(results),
        "queries_with_preliminary_match": sum(
            bool(r["result"]["counts"].get("matched")) for r in results
        ),
        "results": results,
        "completion_queue": completion_snapshot(store),
    }
    (output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "queries.json").write_text(
        json.dumps(cases(), ensure_ascii=False, indent=2) + "\n"
    )
    lines = [
        "# 酸奶模拟查询基线",
        "",
        f"纳入名称或官网明确归为酸奶的 {len(yogurts)} 个官网记录；不将鲜奶、布丁混入酸奶样本。",
        "模拟数值仅测试程序，不是健康建议。结果反映官网资料的初步条件匹配，不等于包装已核验或真实推荐成功率。",
        "",
        "| 场景 | 官网数值符合 | 不符合 | 待核实 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for r in results:
        c = r["result"]["counts"]
        lines.append(
            f"| {r['case']['title']} | {c.get('matched', 0)} | {c.get('not_matched', 0)} | {c.get('unknown', 0)} |"
        )
    lines += [
        "",
        f"去重后补齐任务：{report['completion_queue']['total']} 项。模拟任务仅存于本报告目录的数据库，不计入真实用户需求。",
        "优先级先看是否只差一项证据，再看出现频次。缺原商品数值和计量口径不兼容不会触发无效商品抓取。",
        "任务只记录商品、字段及缺口类型，不存用户身份、原始查询或具体过敏项。",
        "",
        "后续照片：同一商品的正面、配料表、营养表及过敏原提示可用于匹配；条码有助于识别规格版本。OCR结果需核实后才能关闭任务。",
        "",
        "这是补齐前基线；提供照片并核实字段后，用同一 queries.json 再跑一次，比较匹配覆盖及未知数量。当前没有声称前后提升。",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run(args.input, args.output)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "product_count",
                    "query_count",
                    "queries_with_preliminary_match",
                )
            }
        )
    )
