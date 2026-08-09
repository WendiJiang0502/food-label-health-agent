"""Versioned official-clause store with deterministic hybrid retrieval."""

from __future__ import annotations

import re

from .bm25 import BM25Index
from .models import RegulationClause, RegulationSearchRequest, RegulationSearchResponse
from .vector import TfidfVectorIndex

HYBRID_RETRIEVAL_METHOD = "hybrid_bm25_tfidf_rerank_v1"


class RegulationStore:
    def __init__(self, clauses: tuple[RegulationClause, ...]) -> None:
        evidence_ids = [clause.evidence_id for clause in clauses]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Regulation evidence IDs must be unique")
        self._clauses = clauses

    @property
    def clauses(self) -> tuple[RegulationClause, ...]:
        return self._clauses

    def with_clauses(
        self, additional_clauses: tuple[RegulationClause, ...]
    ) -> RegulationStore:
        return RegulationStore((*self._clauses, *additional_clauses))

    def search(self, request: RegulationSearchRequest) -> RegulationSearchResponse:
        requested_standards = {
            _normalize_standard_number(value)
            for value in re.findall(
                r"GB\s*\d+(?:\.\d+)?\s*[-—]\s*\d{4}",
                request.query,
                flags=re.IGNORECASE,
            )
        }
        requested_topics = {topic.casefold() for topic in request.topics}
        candidates = tuple(
            clause
            for clause in self._clauses
            if clause.jurisdiction == request.jurisdiction
            and clause.is_applicable(request.applicable_date)
            and (not requested_topics or requested_topics.intersection(clause.topics))
            and (
                not requested_standards
                or _normalize_standard_number(clause.standard_number)
                in requested_standards
            )
        )
        documents = tuple(_searchable_text(clause) for clause in candidates)
        bm25_hits = BM25Index(documents).search(request.query) if documents else ()
        vector_hits = (
            TfidfVectorIndex(documents).search(request.query) if documents else ()
        )
        bm25_scores = {hit.index: hit.score for hit in bm25_hits}
        vector_scores = {hit.index: hit.score for hit in vector_hits}
        max_bm25 = max(bm25_scores.values(), default=0.0)
        has_any_retrieval_hit = bool(bm25_scores or vector_scores)
        ranked: list[
            tuple[float, float, float, RegulationClause, dict[str, float | int | bool]]
        ] = []
        for index, clause in enumerate(candidates):
            topic_hits = len(requested_topics.intersection(clause.topics))
            raw_bm25 = bm25_scores.get(index, 0.0)
            vector_score = vector_scores.get(index, 0.0)
            standard_hit = clause.standard_number.casefold() in request.query.casefold()
            if (
                raw_bm25 <= 0
                and vector_score <= 0
                and not standard_hit
                and (has_any_retrieval_hit or not topic_hits)
            ):
                continue
            normalized_bm25 = raw_bm25 / max_bm25 if max_bm25 else 0.0
            topic_score = (
                topic_hits / len(requested_topics) if requested_topics else 0.0
            )
            authority_score = _authority_score(clause.authority_level)
            score = min(
                1.0,
                normalized_bm25 * 0.45
                + vector_score * 0.35
                + topic_score * 0.10
                + float(standard_hit) * 0.07
                + authority_score * 0.03,
            )
            signals: dict[str, float | int | bool] = {
                "bm25_score": round(raw_bm25, 8),
                "bm25_normalized": round(normalized_bm25, 8),
                "vector_score": round(vector_score, 8),
                "topic_hits": topic_hits,
                "standard_hit": standard_hit,
                "authority_score": authority_score,
                "rerank_score": round(score, 8),
            }
            ranked.append((score, normalized_bm25, vector_score, clause, signals))
        ranked.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                _authority_score(item[3].authority_level),
                item[3].published_on,
                item[3].evidence_id,
            ),
            reverse=True,
        )
        results = [
            {
                **clause.to_search_result(
                    applicable_date=request.applicable_date,
                    retrieval_score=score,
                    retrieval_method=HYBRID_RETRIEVAL_METHOD,
                    retrieval_signals=signals,
                ),
            }
            for score, _, _, clause, signals in ranked[: request.limit]
        ]
        return RegulationSearchResponse(
            status="found" if results else "unknown",
            query=request.query,
            jurisdiction=request.jurisdiction,
            applicable_date=request.applicable_date.isoformat(),
            retrieval_method=HYBRID_RETRIEVAL_METHOD,
            results=results,
            unknowns=[] if results else ["no_applicable_official_clause"],
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
