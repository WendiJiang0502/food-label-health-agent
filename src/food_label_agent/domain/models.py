"""Dependency-free value objects used in the Agent state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .types import ConstraintKind, RiskLevel


@dataclass(frozen=True, slots=True)
class ImageInput:
    uri: str
    side: str
    media_type: str = "image/jpeg"


@dataclass(frozen=True, slots=True)
class LabelField:
    name: str
    raw_text: str
    confidence: float
    confirmed_by_user: bool = False
    bounding_box: tuple[int, int, int, int] | None = None

    def is_reliable(self, threshold: float) -> bool:
        return self.confirmed_by_user or self.confidence >= threshold


@dataclass(frozen=True, slots=True)
class UserConstraint:
    kind: ConstraintKind
    canonical_value: str
    severity: str = "unspecified"
    source: str = "user_declared"
    operator: str | None = None
    threshold: float | None = None
    unit: str | None = None
    basis: str | None = None


@dataclass(frozen=True, slots=True)
class Evidence:
    source_id: str
    title: str
    jurisdiction: str
    section: str | None = None
    source_url: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    authority_level: str = "A"
    standard_number: str | None = None
    evidence_text: str | None = None
    content_hash: str | None = None
    retrieval_score: float | None = None
    retrieval_method: str | None = None
    source_type: str | None = None
    document_hash: str | None = None
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True, slots=True)
class RiskFinding:
    risk_level: RiskLevel
    constraint: str
    matched_text: str | None
    reason_code: str
    explanation: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: str
    actor: str
    detail: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )
