"""Jurisdiction- and date-filtered regulation retrieval service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .corpus import OFFICIAL_CLAUSES
from .models import RegulationSearchRequest, RegulationSearchResponse
from .semantic import RAG2Settings, RAGProviderError, create_semantic_providers
from .serialization import load_clause_index
from .store import RegulationStore

DATA_DIR = Path(__file__).with_name("data")


@lru_cache(maxsize=1)
def get_default_regulation_store() -> RegulationStore:
    settings = RAG2Settings.from_environment()
    clauses = list(OFFICIAL_CLAUSES)
    if DATA_DIR.exists():
        for index_path in sorted(DATA_DIR.glob("*.json")):
            clauses.extend(load_clause_index(index_path))
    dense_provider, reranker = create_semantic_providers(settings)
    return RegulationStore(
        tuple(clauses),
        dense_provider=dense_provider,
        reranker=reranker,
        default_profile=settings.profile,
    )


def search_regulations(
    request: RegulationSearchRequest,
) -> RegulationSearchResponse:
    """Search the official store without mixing inapplicable versions."""
    return _search_regulations_cached(
        request.query,
        request.jurisdiction,
        request.applicable_date.isoformat(),
        tuple(request.topics),
        request.limit,
    )


@lru_cache(maxsize=512)
def _search_regulations_cached(
    query: str,
    jurisdiction: str,
    applicable_date: str,
    topics: tuple[str, ...],
    limit: int,
) -> RegulationSearchResponse:
    request = RegulationSearchRequest(
        query=query,
        jurisdiction=jurisdiction,
        applicable_date=applicable_date,
        topics=list(topics),
        limit=limit,
    )
    store = get_default_regulation_store()
    try:
        return store.search(request)
    except RAGProviderError as exc:
        # Dense embeddings and the independent reranker are optional
        # accelerators. The local BM25/TF-IDF index remains the authoritative
        # offline path; it applies the same jurisdiction/date/topic filters.
        fallback = store.search(request, profile="hybrid_tfidf")
        return fallback.model_copy(
            update={
                "unknowns": [
                    *fallback.unknowns,
                    f"rag_provider_unavailable_fallback_used:{exc}",
                ]
            }
        )


def clear_regulation_caches() -> None:
    get_default_regulation_store.cache_clear()
    _search_regulations_cached.cache_clear()
