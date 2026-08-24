"""Unified Milestone 6 evaluation runner and release report CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from food_label_agent.alternatives.catalog import JsonProductCatalog
from food_label_agent.regulations.service import (
    clear_regulation_caches,
    get_default_regulation_store,
)

from .agent_benchmark import evaluate_agent_benchmark
from .alternatives import evaluate_alternative_benchmark
from .benchmarks import ALTERNATIVE_BENCHMARK, RAG_BENCHMARK
from .evidence_routing import evaluate_evidence_routing
from .failures import evaluate_failure_corpus
from .ocr import evaluate_directory
from .planner import evaluate_planner_ablation
from .rag import evaluate_rag_benchmark
from .rag_ablation import evaluate_rag2_ablation
from .rules import evaluate_allergen_rules
from .safety import evaluate_final_safety_gate
from .versions import VersionSnapshot, build_version_snapshot

REPORT_SCHEMA_VERSION = "milestone6_evaluation_report_v1"
RELEASE_MINIMUM_OCR_SAMPLES = 50
RELEASE_MINIMUM_SUPERVISED_OCR_SAMPLES = 30


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    schema_version: str
    profile: str
    evaluation_passed: bool
    release_ready: bool
    release_blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    versions: dict[str, Any]
    components: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        result["warnings"] = list(self.warnings)
        return result


def run_evaluation(
    *,
    profile: Literal["development", "release"] = "development",
    ocr_images: Path | None = None,
    version_snapshot: VersionSnapshot | None = None,
) -> EvaluationReport:
    if profile not in {"development", "release"}:
        raise ValueError("Unsupported evaluation profile")
    versions = version_snapshot or build_version_snapshot()
    with _offline_rag_profile():
        components = {
            "rules": evaluate_allergen_rules().to_dict(),
            "rag": evaluate_rag_benchmark(
                get_default_regulation_store(), RAG_BENCHMARK, k=5
            ).to_dict(),
            "rag2_ablation": evaluate_rag2_ablation(
                get_default_regulation_store()
            ).to_dict(),
            "evidence_routing": evaluate_evidence_routing().to_dict(),
            "agent": evaluate_agent_benchmark().to_dict(),
            "planner_ablation": evaluate_planner_ablation().to_dict(),
            "alternatives": evaluate_alternative_benchmark(
                ALTERNATIVE_BENCHMARK,
                catalog=JsonProductCatalog(),
            ).to_dict(),
            "safety_gate": evaluate_final_safety_gate().to_dict(),
            "failure_corpus": evaluate_failure_corpus().to_dict(),
        }
    warnings = []
    if ocr_images is None:
        components["ocr"] = {
            "status": "not_run",
            "reason": "private_ocr_dataset_not_provided",
            "evaluation_passed": None if profile == "development" else False,
            "release_blockers": (
                []
                if profile == "development"
                else ["private_ocr_benchmark_required_for_release"]
            ),
        }
        warnings.append("OCR 私有真实标签集未运行；开发报告不能代表 OCR 发布质量。")
    else:
        if not ocr_images.is_dir():
            raise ValueError("OCR benchmark path must be a directory")
        ocr_report = asyncio.run(evaluate_directory(ocr_images))
        components["ocr"] = _evaluate_ocr_release(ocr_report, profile=profile)

    blockers = []
    for component_name, result in components.items():
        blockers.extend(
            f"{component_name}:{value}" for value in result.get("release_blockers", [])
        )
    if profile == "release" and versions.git_dirty:
        blockers.append("versions:git_worktree_dirty")
    blockers = list(dict.fromkeys(blockers))
    passed = not blockers
    return EvaluationReport(
        schema_version=REPORT_SCHEMA_VERSION,
        profile=profile,
        evaluation_passed=passed,
        release_ready=profile == "release" and passed,
        release_blockers=tuple(blockers),
        warnings=tuple(warnings),
        versions=versions.to_dict(),
        components=components,
    )


@contextmanager
def _offline_rag_profile():
    """Prevent the unified offline suite from calling the production RAG provider."""

    previous = os.environ.get("FOOD_LABEL_RAG_PROFILE")
    os.environ["FOOD_LABEL_RAG_PROFILE"] = "hybrid_tfidf"
    clear_regulation_caches()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("FOOD_LABEL_RAG_PROFILE", None)
        else:
            os.environ["FOOD_LABEL_RAG_PROFILE"] = previous
        clear_regulation_caches()


def render_markdown(report: EvaluationReport) -> str:
    status = "通过" if report.evaluation_passed else "阻断"
    lines = [
        "# Milestone 6 统一评测报告",
        "",
        f"- 配置：`{report.profile}`",
        f"- 结果：**{status}**",
        f"- 可发布：`{str(report.release_ready).lower()}`",
        f"- Git：`{report.versions['git_commit']}`",
        f"- 生成时间：`{report.versions['generated_at']}`",
        "",
        "## 分层结果",
        "",
        "| 评测层 | 状态 | 样本/案例 | 发布阻断 |",
        "|---|---:|---:|---|",
    ]
    for name, result in report.components.items():
        component_status = (
            "未运行"
            if result.get("status") == "not_run"
            else "通过"
            if result.get("evaluation_passed") is True
            else "未通过"
        )
        count = result.get(
            "case_count",
            result.get("sample_count", result.get("explicit_case_count", "—")),
        )
        blockers = ", ".join(result.get("release_blockers", [])) or "—"
        lines.append(f"| `{name}` | {component_status} | {count} | {blockers} |")
    lines.extend(["", "## 发布阻断", ""])
    if report.release_blockers:
        lines.extend(f"- `{item}`" for item in report.release_blockers)
    else:
        lines.append("- 无")
    if report.warnings:
        lines.extend(["", "## 警告", ""])
        lines.extend(f"- {item}" for item in report.warnings)
    lines.extend(
        [
            "",
            "## 版本快照",
            "",
            "```json",
            json.dumps(report.versions, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _evaluate_ocr_release(report: dict[str, Any], *, profile: str) -> dict[str, Any]:
    blockers = []
    metrics = report.get("aggregate_metrics", {})
    if report.get("provider_error_count", 0):
        blockers.append("ocr_provider_error_detected")
    if profile == "release":
        if report.get("sample_count", 0) < RELEASE_MINIMUM_OCR_SAMPLES:
            blockers.append("ocr_sample_count_below_release_threshold")
        if report.get("supervised_count", 0) < RELEASE_MINIMUM_SUPERVISED_OCR_SAMPLES:
            blockers.append("ocr_supervised_count_below_release_threshold")
        if metrics.get("allergen_recall") != 1.0:
            blockers.append("ocr_allergen_recall_below_release_threshold")
        if metrics.get("numeric_token_recall") != 1.0:
            blockers.append("ocr_numeric_recall_below_release_threshold")
        if metrics.get("nutrient_value_alignment_accuracy") != 1.0:
            blockers.append("ocr_nutrition_alignment_below_release_threshold")
        if report.get("low_quality_block_recall") != 1.0:
            blockers.append("ocr_low_quality_block_recall_below_release_threshold")
    return {
        **report,
        "evaluation_passed": not blockers,
        "release_blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run unified OCR, rules, RAG, Agent, alternatives and safety evaluation."
    )
    parser.add_argument(
        "--profile", choices=("development", "release"), default="development"
    )
    parser.add_argument(
        "--ocr-images", type=Path, help="Private annotated OCR directory"
    )
    parser.add_argument("--json", type=Path, dest="json_output")
    parser.add_argument("--markdown", type=Path, dest="markdown_output")
    args = parser.parse_args()
    report = run_evaluation(profile=args.profile, ocr_images=args.ocr_images)
    serialized = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(serialized, encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(serialized, end="")
    raise SystemExit(0 if report.evaluation_passed else 1)


if __name__ == "__main__":
    main()
