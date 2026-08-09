"""Versioned official-regulation evidence and deterministic retrieval."""

from .models import (
    RegulationClause,
    RegulationSearchRequest,
    RegulationSearchResponse,
    StandardDocument,
)
from .registry import STANDARD_DOCUMENTS
from .service import search_regulations

__all__ = [
    "STANDARD_DOCUMENTS",
    "RegulationClause",
    "RegulationSearchRequest",
    "RegulationSearchResponse",
    "StandardDocument",
    "search_regulations",
]
