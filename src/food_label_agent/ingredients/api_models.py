"""Validated request/response contracts for deterministic safety evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConstraintInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str = "allergy"
    canonical_value: str = Field(min_length=1, max_length=64)
    severity: str = Field(default="unspecified", max_length=32)


class SafetyEvaluationRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    applicable_date: str
    confirmed_fields: dict[str, str]
    constraints: list[ConstraintInput] = Field(min_length=1, max_length=8)

    @field_validator("confirmed_fields")
    @classmethod
    def require_ingredients(cls, fields: dict[str, str]) -> dict[str, str]:
        normalized = {key.strip(): value.strip() for key, value in fields.items()}
        if not normalized.get("ingredients"):
            raise ValueError("已确认配料表不能为空。")
        return normalized


class SafetyEvaluationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    status: str
    next_route: str
    overall_risk_level: str
    rule_set: dict
    normalized_label: dict
    findings: list[dict]
    message: str
