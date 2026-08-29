"""Validated request/response contracts for deterministic safety evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConstraintInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str = "allergy"
    canonical_value: str = Field(min_length=1, max_length=64)
    severity: str = Field(default="unspecified", max_length=32)
    operator: str | None = Field(default=None, max_length=16)
    threshold: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=16)
    basis: str | None = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def validate_nutrition_limit(self):
        if self.kind == "nutrition_limit":
            if self.operator != "max" or self.threshold is None:
                raise ValueError("营养约束必须提供 max 和非负数值上限。")
            if not self.unit or self.basis not in {
                "per_100g",
                "per_100ml",
                "per_serving",
            }:
                raise ValueError("营养约束必须提供单位和有效比较口径。")
        return self


class SafetyEvaluationRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    applicable_date: str
    confirmed_fields: dict[str, str]
    nutrition_rows: list[list[str]] | None = None
    constraints: list[ConstraintInput] = Field(default_factory=list, max_length=16)
    resume_token: str | None = Field(default=None, min_length=32, max_length=256)

    @field_validator("confirmed_fields")
    @classmethod
    def normalize_fields(cls, fields: dict[str, str]) -> dict[str, str]:
        return {key.strip(): value.strip() for key, value in fields.items()}

    @model_validator(mode="after")
    def require_ingredients_for_ingredient_constraints(self):
        needs_ingredients = any(
            item.kind != "nutrition_limit" for item in self.constraints
        )
        if needs_ingredients and not self.confirmed_fields.get("ingredients"):
            raise ValueError("过敏原或配料约束需要已确认的配料表。")
        if (
            not self.confirmed_fields.get("ingredients")
            and not self.nutrition_rows
            and not self.confirmed_fields.get("nutrition_table")
        ):
            raise ValueError("至少需要已确认的配料表或营养成分表。")
        return self


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
