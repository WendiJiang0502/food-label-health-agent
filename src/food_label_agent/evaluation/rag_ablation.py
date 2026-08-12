"""Four-way RAG 2.0 ablation over clause-level Chinese queries."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.regulations.semantic import (
    DenseEmbeddingProvider,
    IndependentReranker,
    RAG2Settings,
    create_semantic_providers,
)
from food_label_agent.regulations.store import RegulationStore

from .benchmarks import RAG2_BENCHMARK
from .rag import RAGBenchmarkCase, evaluate_rag_benchmark


@dataclass(frozen=True, slots=True)
class RAG2AblationEvaluation:
    schema_version: str
    case_count: int
    profiles: dict[str, dict[str, Any]]
    dense_status: str
    reranker_status: str
    final_recall_lift: float | None
    final_mrr_lift: float | None
    final_ndcg_lift: float | None
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_rag2_ablation(
    store: RegulationStore,
    cases: tuple[RAGBenchmarkCase, ...] = RAG2_BENCHMARK,
    *,
    dense_provider: DenseEmbeddingProvider | None = None,
    reranker: IndependentReranker | None = None,
) -> RAG2AblationEvaluation:
    profiles = {}
    blockers = []
    baseline_store = RegulationStore(store.clauses)
    for profile in ("bm25", "hybrid_tfidf"):
        profiles[profile] = _timed_evaluation(baseline_store, cases, profile)
    if dense_provider is None:
        profiles["hybrid_dense"] = {"status": "not_run"}
        profiles["hybrid_dense_rerank"] = {"status": "not_run"}
        return RAG2AblationEvaluation(
            schema_version="rag2_ablation_v1",
            case_count=len(cases),
            profiles=profiles,
            dense_status="not_run",
            reranker_status="not_run",
            final_recall_lift=None,
            final_mrr_lift=None,
            final_ndcg_lift=None,
            evaluation_passed=not _safety_blockers(profiles),
            release_blockers=tuple(_safety_blockers(profiles)),
        )
    dense_store = RegulationStore(
        store.clauses, dense_provider=dense_provider, reranker=reranker
    )
    profiles["hybrid_dense"] = _timed_evaluation(dense_store, cases, "hybrid_dense")
    if reranker is None:
        profiles["hybrid_dense_rerank"] = {"status": "not_run"}
        blockers.extend(_safety_blockers(profiles))
        blockers.append("rag2_independent_reranker_not_run")
        return RAG2AblationEvaluation(
            schema_version="rag2_ablation_v1",
            case_count=len(cases),
            profiles=profiles,
            dense_status="completed",
            reranker_status="not_run",
            final_recall_lift=None,
            final_mrr_lift=None,
            final_ndcg_lift=None,
            evaluation_passed=False,
            release_blockers=tuple(dict.fromkeys(blockers)),
        )
    profiles["hybrid_dense_rerank"] = _timed_evaluation(
        dense_store, cases, "hybrid_dense_rerank"
    )
    blockers.extend(_safety_blockers(profiles))
    rag1 = profiles["hybrid_tfidf"]
    dense = profiles["hybrid_dense"]
    final = profiles["hybrid_dense_rerank"]
    if dense["recall_at_k"] < rag1["recall_at_k"]:
        blockers.append("dense_recall_regressed_vs_rag1")
    if final["recall_at_k"] < dense["recall_at_k"]:
        blockers.append("reranker_recall_regressed_vs_dense")
    if final["mean_reciprocal_rank"] < dense["mean_reciprocal_rank"]:
        blockers.append("reranker_mrr_regressed_vs_dense")
    improved = any(
        final[key] > rag1[key]
        for key in (
            "recall_at_k",
            "mean_reciprocal_rank",
            "ndcg_at_k",
            "top1_accuracy",
        )
    )
    if not improved:
        blockers.append("rag2_no_measured_quality_improvement")
    return RAG2AblationEvaluation(
        schema_version="rag2_ablation_v1",
        case_count=len(cases),
        profiles=profiles,
        dense_status="completed",
        reranker_status="completed",
        final_recall_lift=final["recall_at_k"] - rag1["recall_at_k"],
        final_mrr_lift=final["mean_reciprocal_rank"] - rag1["mean_reciprocal_rank"],
        final_ndcg_lift=final["ndcg_at_k"] - rag1["ndcg_at_k"],
        evaluation_passed=not blockers,
        release_blockers=tuple(dict.fromkeys(blockers)),
    )


def _timed_evaluation(
    store: RegulationStore,
    cases: tuple[RAGBenchmarkCase, ...],
    profile: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = evaluate_rag_benchmark(
        store, cases, k=5, minimum_recall=0.0, profile=profile
    ).to_dict()
    result["status"] = "completed"
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def _safety_blockers(profiles: dict[str, dict[str, Any]]) -> list[str]:
    blockers = []
    for profile, result in profiles.items():
        if result.get("status") == "not_run":
            continue
        if result.get("official_evidence_rate") != 1.0:
            blockers.append(f"{profile}:unofficial_evidence")
        if result.get("unknown_refusal_accuracy") != 1.0:
            blockers.append(f"{profile}:unknown_refusal_regression")
        if result.get("version_violation_count"):
            blockers.append(f"{profile}:version_violation")
    return blockers


def main() -> None:
    parser = argparse.ArgumentParser(description="Run four-way RAG 2.0 ablation")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    from food_label_agent.regulations.service import get_default_regulation_store

    dense = reranker = None
    if args.live:
        settings = RAG2Settings.from_environment()
        settings = RAG2Settings(
            profile="hybrid_dense_rerank",
            embedding_model=settings.embedding_model,
            embedding_dimensions=settings.embedding_dimensions,
            reranker_model=settings.reranker_model,
            timeout_seconds=settings.timeout_seconds,
            api_key=settings.api_key,
        )
        dense, reranker = create_semantic_providers(settings)
    result = evaluate_rag2_ablation(
        get_default_regulation_store(),
        dense_provider=dense,
        reranker=reranker,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.evaluation_passed else 1)


if __name__ == "__main__":
    main()
