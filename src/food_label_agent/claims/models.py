"""Validated contracts for packaging-claim tools."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ClaimType(StrEnum):
    SUGAR_FREE = "sugar_free"
    LOW_SUGAR = "low_sugar"
    NO_SUCROSE = "no_sucrose"
    NO_ADDED_SUGAR = "no_added_sugar"
    NO_ADDED_SUCROSE = "no_added_sucrose"
    UNKNOWN = "unknown"


class ClaimInterpretationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_text: str = Field(min_length=1, max_length=2_000)
    regulatory_evidence: list[dict] = Field(default_factory=list, max_length=20)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    applicable_date: date


class ClaimInterpretationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    claims: list[dict]
    unknowns: list[str]


class ClaimConsistencyRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    claims: list[dict] = Field(min_length=1, max_length=30)
    ingredients_text: str | None = Field(default=None, max_length=20_000)
    nutrition_values: dict = Field(default_factory=dict)
    regulatory_evidence: list[dict] = Field(default_factory=list, max_length=20)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    applicable_date: date


class ClaimConsistencyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    findings: list[dict]
    unknowns: list[str]
