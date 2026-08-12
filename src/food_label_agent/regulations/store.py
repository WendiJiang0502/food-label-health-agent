"""Versioned official-clause store with RAG 1.0 and RAG 2.0 profiles."""

from __future__ import annotations

import re

from .bm25 import BM25Index
from .models import RegulationClause, RegulationSearchRequest, RegulationSearchResponse
from .semantic import DenseEmbeddingProvider, IndependentReranker, cosine_similarity
from .vector import TfidfVectorIndex

BM25_RETRIEVAL_METHOD = "bm25_v1"
HYBRID_RETRIEVAL_METHOD = "hybrid_bm25_tfidf_rerank_v1"
DENSE_RETRIEVAL_METHOD = "hybrid_bm25_dense_rrf_v2"
RAG2_RETRIEVAL_METHOD = "hybrid_bm25_dense_independent_rerank_v2"
SUPPORTED_PROFILES = frozenset(
    {"bm25", "hybrid_tfidf", "hybrid_dense", "hybrid_dense_rerank"}
)


class RegulationStore:
    def __init__(
        self,
        clauses: tuple[RegulationClause, ...],
        *,
        dense_provider: DenseEmbeddingProvider | None = None,
        reranker: IndependentReranker | None = None,
        default_profile: str = "hybrid_tfidf",
    ) -> None:
        evidence_ids = [clause.evidence_id for clause in clauses]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Regulation evidence IDs must be unique")
        if default_profile not in SUPPORTED_PROFILES:
            raise ValueError("Unsupported regulation retrieval profile")
        self._clauses = clauses
        self._dense_provider = dense_provider
        self._reranker = reranker
        self._default_profile = default_profile

    @property
    def clauses(self) -> tuple[RegulationClause, ...]:
        return self._clauses

    @property
    def default_profile(self) -> str:
        return self._default_profile

    def with_clauses(
        self, additional_clauses: tuple[RegulationClause, ...]
    ) -> RegulationStore:
        return RegulationStore(
            (*self._clauses, *additional_clauses),
            dense_provider=self._dense_provider,
            reranker=self._reranker,
            default_profile=self._default_profile,
        )

    def search(
        self,
        request: RegulationSearchRequest,
        *,
        profile: str | None = None,
    ) -> RegulationSearchResponse:
        selected_profile = profile or self._default_profile
        if selected_profile not in SUPPORTED_PROFILES:
            raise ValueError("Unsupported regulation retrieval profile")
        candidates, requested_topics = self._applicable_candidates(request)
        documents = tuple(_searchable_text(clause) for clause in candidates)
        if selected_profile == "hybrid_tfidf":
            ranked = _rank_rag1(request, candidates, documents, requested_topics)
            method = HYBRID_RETRIEVAL_METHOD
        elif selected_profile == "bm25":
            ranked = _rank_bm25(request, candidates, documents, requested_topics)
            method = BM25_RETRIEVAL_METHOD
        else:
            if self._dense_provider is None:
                raise RuntimeError(
                    "Dense retrieval profile requires an embedding provider"
                )
            ranked = _rank_dense(
                request,
                candidates,
                documents,
                requested_topics,
                self._dense_provider,
            )
            method = DENSE_RETRIEVAL_METHOD
            if selected_profile == "hybrid_dense_rerank":
                if self._reranker is None:
                    raise RuntimeError(
                        "RAG 2.0 profile requires an independent reranker"
                    )
                ranked = _independent_rerank(request, ranked, self._reranker)
                method = RAG2_RETRIEVAL_METHOD
        results = [
            clause.to_search_result(
                applicable_date=request.applicable_date,
                retrieval_score=score,
                retrieval_method=method,
                retrieval_signals=signals,
            )
            for score, clause, signals in ranked[: request.limit]
        ]
        return RegulationSearchResponse(
            status="found" if results else "unknown",
            query=request.query,
            jurisdiction=request.jurisdiction,
            applicable_date=request.applicable_date.isoformat(),
            retrieval_method=method,
            results=results,
            unknowns=[] if results else ["no_applicable_official_clause"],
        )

    def _applicable_candidates(
        self, request: RegulationSearchRequest
    ) -> tuple[tuple[RegulationClause, ...], set[str]]:
        requested_standards = {
            _normalize_standard_number(value)
            for value in re.findall(
                r"GB\s*\d+(?:\.\d+)?\s*[-—]\s*\d{4}",
                request.query,
                flags=re.IGNORECASE,
            )
        }
        requested_topics = {topic.casefold() for topic in request.topics}
        return (
            tuple(
                clause
                for clause in self._clauses
                if clause.jurisdiction == request.jurisdiction
                and clause.is_applicable(request.applicable_date)
                and (
                    not requested_topics or requested_topics.intersection(clause.topics)
                )
                and (
                    not requested_standards
                    or _normalize_standard_number(clause.standard_number)
                    in requested_standards
                )
            ),
            requested_topics,
        )


RankedClause = tuple[float, RegulationClause, dict[str, float | int | bool | str]]


def _rank_bm25(
    request: RegulationSearchRequest,
    candidates: tuple[RegulationClause, ...],
    documents: tuple[str, ...],
    requested_topics: set[str],
) -> list[RankedClause]:
    hits = BM25Index(documents).search(request.query) if documents else ()
    maximum = max((hit.score for hit in hits), default=0.0)
    ranked = []
    for hit in hits:
        clause = candidates[hit.index]
        score = hit.score / maximum if maximum else 0.0
        ranked.append(
            (
                score,
                clause,
                {
                    "bm25_score": round(hit.score, 8),
                    "bm25_normalized": round(score, 8),
                    "topic_hits": len(requested_topics.intersection(clause.topics)),
                },
            )
        )
    return ranked


def _rank_rag1(
    request: RegulationSearchRequest,
    candidates: tuple[RegulationClause, ...],
    documents: tuple[str, ...],
    requested_topics: set[str],
) -> list[RankedClause]:
    bm25_hits = BM25Index(documents).search(request.query) if documents else ()
    vector_hits = TfidfVectorIndex(documents).search(request.query) if documents else ()
    bm25_scores = {hit.index: hit.score for hit in bm25_hits}
    vector_scores = {hit.index: hit.score for hit in vector_hits}
    max_bm25 = max(bm25_scores.values(), default=0.0)
    has_hit = bool(bm25_scores or vector_scores)
    ranked = []
    for index, clause in enumerate(candidates):
        raw_bm25 = bm25_scores.get(index, 0.0)
        vector_score = vector_scores.get(index, 0.0)
        topic_hits = len(requested_topics.intersection(clause.topics))
        standard_hit = clause.standard_number.casefold() in request.query.casefold()
        if (
            raw_bm25 <= 0
            and vector_score <= 0
            and not standard_hit
            and (has_hit or not topic_hits)
        ):
            continue
        normalized_bm25 = raw_bm25 / max_bm25 if max_bm25 else 0.0
        topic_score = topic_hits / len(requested_topics) if requested_topics else 0.0
        authority_score = _authority_score(clause.authority_level)
        score = min(
            1.0,
            normalized_bm25 * 0.45
            + vector_score * 0.35
            + topic_score * 0.10
            + float(standard_hit) * 0.07
            + authority_score * 0.03,
        )
        ranked.append(
            (
                score,
                clause,
                {
                    "bm25_score": round(raw_bm25, 8),
                    "bm25_normalized": round(normalized_bm25, 8),
                    "vector_score": round(vector_score, 8),
                    "topic_hits": topic_hits,
                    "standard_hit": standard_hit,
                    "authority_score": authority_score,
                    "rerank_score": round(score, 8),
                },
            )
        )
    ranked.sort(key=_rank_key, reverse=True)
    return ranked


def _rank_dense(
    request: RegulationSearchRequest,
    candidates: tuple[RegulationClause, ...],
    documents: tuple[str, ...],
    requested_topics: set[str],
    provider: DenseEmbeddingProvider,
) -> list[RankedClause]:
    if not documents:
        return []
    vectors = provider.embed((request.query, *documents))
    query_vector, document_vectors = vectors[0], vectors[1:]
    dense_scores = {
        index: cosine_similarity(query_vector, vector)
        for index, vector in enumerate(document_vectors)
    }
    bm25_hits = BM25Index(documents).search(request.query)
    bm25_ranks = {hit.index: rank for rank, hit in enumerate(bm25_hits, start=1)}
    dense_order = sorted(dense_scores, key=dense_scores.get, reverse=True)
    dense_ranks = {index: rank for rank, index in enumerate(dense_order, start=1)}
    ranked = []
    for index, clause in enumerate(candidates):
        dense_score = dense_scores[index]
        if index not in bm25_ranks and dense_score < 0.15:
            continue
        rrf = (1 / (60 + bm25_ranks[index]) if index in bm25_ranks else 0.0) + 1 / (
            60 + dense_ranks[index]
        )
        ranked.append(
            (
                rrf,
                clause,
                {
                    "bm25_rank": bm25_ranks.get(index, 0),
                    "dense_rank": dense_ranks[index],
                    "dense_score": round(dense_score, 8),
                    "rrf_score": round(rrf, 8),
                    "topic_hits": len(requested_topics.intersection(clause.topics)),
                    "embedding_provider": provider.provider,
                    "embedding_model": provider.model,
                },
            )
        )
    ranked.sort(key=_rank_key, reverse=True)
    return ranked


def _independent_rerank(
    request: RegulationSearchRequest,
    ranked: list[RankedClause],
    reranker: IndependentReranker,
) -> list[RankedClause]:
    pool = ranked[:20]
    summaries = [
        {
            "evidence_id": clause.evidence_id,
            "section": clause.section,
            "text": clause.evidence_text[:1200],
        }
        for _, clause, _ in pool
    ]
    order = reranker.rank(request.query, summaries)
    by_id = {clause.evidence_id: item for item in pool for clause in (item[1],)}
    reranked = []
    for rank, evidence_id in enumerate(order, start=1):
        score, clause, signals = by_id[evidence_id]
        reranked.append(
            (
                1 / rank,
                clause,
                {
                    **signals,
                    "reranker_rank": rank,
                    "reranker_provider": reranker.provider,
                    "reranker_model": reranker.model,
                    "pre_rerank_score": round(score, 8),
                },
            )
        )
    return reranked


def _rank_key(item: RankedClause) -> tuple[float, float, str, str]:
    return (
        item[0],
        _authority_score(item[1].authority_level),
        item[1].published_on,
        item[1].evidence_id,
    )


def _searchable_text(clause: RegulationClause) -> str:
    return " ".join(
        (
            clause.standard_number,
            clause.title,
            clause.section,
            clause.evidence_text,
            *clause.topics,
            *clause.keywords,
        )
    )


def _normalize_standard_number(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("—", "-")).upper()


def _authority_score(level: str) -> float:
    return {"A": 1.0, "B": 0.7, "C": 0.4}.get(level.upper(), 0.0)
