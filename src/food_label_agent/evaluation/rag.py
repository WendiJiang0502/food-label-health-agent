"""Release-oriented evaluation for versioned regulation retrieval."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

from food_label_agent.regulations.models import RegulationSearchRequest
from food_label_agent.regulations.store import (
    BM25_RETRIEVAL_METHOD,
    DENSE_RETRIEVAL_METHOD,
    HYBRID_RETRIEVAL_METHOD,
    RAG2_RETRIEVAL_METHOD,
    RegulationStore,
)


@dataclass(frozen=True, slots=True)
class RAGBenchmarkCase:
    name: str
    query: str
    applicable_date: str
    topics: tuple[str, ...]
    relevant_standard_numbers: tuple[str, ...] = ()
    relevant_evidence_ids: tuple[str, ...] = ()
    allowed_standard_numbers: tuple[str, ...] = ()
    expect_unknown: bool = False


@dataclass(frozen=True, slots=True)
class RAGEvaluation:
    profile: str
    case_count: int
    recall_at_k: float
    mean_reciprocal_rank: float
    ndcg_at_k: float
    top1_accuracy: float
    hybrid_method_rate: float
    official_evidence_rate: float
    unknown_refusal_accuracy: float
    version_violation_count: int
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_rag_benchmark(
    store: RegulationStore,
    cases: tuple[RAGBenchmarkCase, ...],
    *,
    k: int = 5,
    minimum_recall: float = 1.0,
    profile: str = "hybrid_tfidf",
) -> RAGEvaluation:
    """Evaluate retrieval quality and fail closed on release-critical errors."""

    if not cases:
        raise ValueError("RAG benchmark requires at least one case")
    if k < 1:
        raise ValueError("k must be positive")
    if not 0 <= minimum_recall <= 1:
        raise ValueError("minimum_recall must be between 0 and 1")
    if any(
        not case.expect_unknown
        and not (case.relevant_standard_numbers or case.relevant_evidence_ids)
        for case in cases
    ):
        raise ValueError("non-unknown cases require relevant standards")

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcg_scores: list[float] = []
    top1_checks: list[bool] = []
    method_checks: list[bool] = []
    official_checks: list[bool] = []
    refusal_checks: list[bool] = []
    version_violations = 0

    for case in cases:
        response = store.search(
            RegulationSearchRequest(
                query=case.query,
                jurisdiction="CN",
                applicable_date=case.applicable_date,
                topics=list(case.topics),
                limit=k,
            ),
            profile=profile,
        )
        method_checks.append(
            response.retrieval_method
            == {
                "bm25": BM25_RETRIEVAL_METHOD,
                "hybrid_tfidf": HYBRID_RETRIEVAL_METHOD,
                "hybrid_dense": DENSE_RETRIEVAL_METHOD,
                "hybrid_dense_rerank": RAG2_RETRIEVAL_METHOD,
            }[profile]
        )
        if case.expect_unknown:
            refusal_checks.append(response.status == "unknown" and not response.results)
            continue

        expected = set(case.relevant_standard_numbers)
        expected_ids = set(case.relevant_evidence_ids)
        allowed = set(case.allowed_standard_numbers) or expected
        retrieved = [item["standard_number"] for item in response.results[:k]]
        retrieved_ids = [item["evidence_id"] for item in response.results[:k]]
        relevance_values = retrieved_ids if expected_ids else retrieved
        relevance_expected = expected_ids or expected
        seen_relevant = set()
        relevance = []
        for value in relevance_values:
            is_relevant = value in relevance_expected and value not in seen_relevant
            relevance.append(is_relevant)
            if is_relevant:
                seen_relevant.add(value)
        denominator = len(expected_ids or expected)
        recalls.append(len(seen_relevant) / denominator)
        first_rank = next(
            (index for index, relevant in enumerate(relevance, start=1) if relevant),
            None,
        )
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        top1_checks.append(bool(relevance and relevance[0]))
        dcg = sum(
            1.0 / math.log2(rank + 1)
            for rank, relevant in enumerate(relevance, start=1)
            if relevant
        )
        ideal_count = min(denominator, k)
        ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
        ndcg_scores.append(dcg / ideal if ideal else 1.0)
        for item in response.results:
            official_checks.append(
                item.get("authority_level") == "A"
                and _is_official_source(str(item.get("source_url", "")))
                and bool(item.get("content_hash"))
            )
            if (
                item.get("applicability_status") != "applicable"
                or item.get("standard_number") not in allowed
                or not _date_is_applicable(item, case.applicable_date)
            ):
                version_violations += 1

    recall_at_k = sum(recalls) / len(recalls) if recalls else 1.0
    mean_reciprocal_rank = (
        sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 1.0
    )
    ndcg_at_k = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 1.0
    top1_accuracy = sum(top1_checks) / len(top1_checks) if top1_checks else 1.0
    hybrid_rate = sum(method_checks) / len(method_checks)
    official_rate = (
        sum(official_checks) / len(official_checks) if official_checks else 1.0
    )
    refusal_accuracy = (
        sum(refusal_checks) / len(refusal_checks) if refusal_checks else 1.0
    )
    blockers: list[str] = []
    if recall_at_k < minimum_recall:
        blockers.append("rag_recall_below_release_threshold")
    if hybrid_rate < 1.0:
        blockers.append("non_hybrid_retrieval_path_detected")
    if official_rate < 1.0:
        blockers.append("untraceable_or_non_official_evidence")
    if refusal_accuracy < 1.0:
        blockers.append("unknown_refusal_failed")
    if version_violations:
        blockers.append("inapplicable_regulation_retrieved")
    return RAGEvaluation(
        profile=profile,
        case_count=len(cases),
        recall_at_k=recall_at_k,
        mean_reciprocal_rank=mean_reciprocal_rank,
        ndcg_at_k=ndcg_at_k,
        top1_accuracy=top1_accuracy,
        hybrid_method_rate=hybrid_rate,
        official_evidence_rate=official_rate,
        unknown_refusal_accuracy=refusal_accuracy,
        version_violation_count=version_violations,
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )


def _is_official_source(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").casefold()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in ("nhc.gov.cn", "samr.gov.cn")
    )


def _date_is_applicable(item: dict, applicable_date: str) -> bool:
    target = date.fromisoformat(applicable_date)
    start = date.fromisoformat(str(item["effective_from"]))
    raw_end = item.get("effective_to")
    end = date.fromisoformat(str(raw_end)) if raw_end else None
    return start <= target and (end is None or target <= end)
