"""Versioned clause store with a BM25 retrieval baseline."""

from __future__ import annotations

import re

from .bm25 import BM25Index
from .models import RegulationClause, RegulationSearchRequest, RegulationSearchResponse


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
        candidates = tuple(
            clause
            for clause in self._clauses
            if clause.jurisdiction == request.jurisdiction
            and clause.is_applicable(request.applicable_date)
            and (
                not requested_standards
                or _normalize_standard_number(clause.standard_number)
                in requested_standards
            )
        )
        documents = tuple(_searchable_text(clause) for clause in candidates)
        bm25_hits = BM25Index(documents).search(request.query) if documents else ()
        bm25_scores = {hit.index: hit.score for hit in bm25_hits}
        has_any_bm25_hit = bool(bm25_scores)
        requested_topics = {topic.casefold() for topic in request.topics}
        ranked: list[tuple[float, RegulationClause]] = []
        for index, clause in enumerate(candidates):
            topic_hits = len(requested_topics.intersection(clause.topics))
            raw_bm25 = bm25_scores.get(index, 0.0)
            standard_hit = clause.standard_number.casefold() in request.query.casefold()
            if (
                raw_bm25 <= 0
                and not standard_hit
                and (has_any_bm25_hit or not topic_hits)
            ):
                continue
            normalized_bm25 = raw_bm25 / (raw_bm25 + 1.0)
            score = min(
                1.0,
                normalized_bm25 * 0.7 + topic_hits * 0.12 + standard_hit * 0.2,
            )
            ranked.append((score, clause))
        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].authority_level,
                item[1].published_on,
            ),
            reverse=True,
        )
        results = [
            {
                **clause.to_search_result(
                    applicable_date=request.applicable_date,
                    retrieval_score=score,
                ),
                "retrieval_method": "bm25_v1",
            }
            for score, clause in ranked[: request.limit]
        ]
        return RegulationSearchResponse(
            status="found" if results else "unknown",
            query=request.query,
            jurisdiction=request.jurisdiction,
            applicable_date=request.applicable_date.isoformat(),
            retrieval_method="bm25_v1",
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
