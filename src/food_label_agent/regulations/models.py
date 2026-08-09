"""Validated models for dated, clause-level regulatory evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True, slots=True)
class RegulationClause:
    evidence_id: str
    source_id: str
    standard_number: str
    title: str
    section: str
    evidence_text: str
    jurisdiction: str
    published_on: str
    effective_from: str
    effective_to: str | None
    source_url: str
    authority_level: str
    source_type: str
    topics: tuple[str, ...]
    keywords: tuple[str, ...]
    document_hash: str | None = None
    page_start: int | None = None
    page_end: int | None = None

    @property
    def content_hash(self) -> str:
        content = f"{self.source_id}\n{self.section}\n{self.evidence_text}".encode()
        return sha256(content).hexdigest()

    def is_applicable(self, applicable_date: date) -> bool:
        start = date.fromisoformat(self.effective_from)
        end = date.fromisoformat(self.effective_to) if self.effective_to else None
        return start <= applicable_date and (end is None or applicable_date <= end)

    def to_search_result(
        self,
        *,
        applicable_date: date,
        retrieval_score: float,
        retrieval_method: str,
        retrieval_signals: dict[str, float | int | bool],
    ) -> dict:
        result = asdict(self)
        result.update(
            {
                "content_hash": self.content_hash,
                "applicable_date": applicable_date.isoformat(),
                "applicability_status": "applicable",
                "retrieval_score": retrieval_score,
                "retrieval_method": retrieval_method,
                "retrieval_signals": retrieval_signals,
            }
        )
        return result


class RegulationSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=2_000)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    applicable_date: date
    topics: list[str] = Field(default_factory=list, max_length=12)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        compact = " ".join(value.split())
        if not compact:
            raise ValueError("法规检索问题不能为空。")
        return compact


class RegulationSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    query: str
    jurisdiction: str
    applicable_date: str
    retrieval_method: str
    results: list[dict]
    unknowns: list[str]


@dataclass(frozen=True, slots=True)
class StandardDocument:
    document_id: str
    standard_number: str
    title: str
    jurisdiction: str
    publisher: str
    published_on: str
    effective_from: str
    effective_to: str | None
    official_page_url: str
    pdf_url: str | None
    authority_level: str
    source_type: str
    topics: tuple[str, ...]
    replaces: str | None = None
    replaced_by: str | None = None

    def is_applicable(self, applicable_date: date) -> bool:
        start = date.fromisoformat(self.effective_from)
        end = date.fromisoformat(self.effective_to) if self.effective_to else None
        return start <= applicable_date and (end is None or applicable_date <= end)
