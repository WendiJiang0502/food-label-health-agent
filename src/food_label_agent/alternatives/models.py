"""Validated contracts for evidence-backed product alternatives."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from food_label_agent.ingredients.api_models import ConstraintInput


class ProductLabelEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(min_length=8, max_length=160)
    ingredients_text: str = Field(min_length=1, max_length=20_000)
    allergen_statement: str | None = Field(default=None, max_length=4_000)
    nutrition_table_text: str | None = Field(default=None, max_length=10_000)
    nutrition_basis_text: str | None = Field(default=None, max_length=200)
    nutrition_rows: list[list[str]] | None = None
    confirmed_by: Literal["human_review", "manufacturer_label"]
    confirmed_at: date
    valid_through: date | None = None
    source_url: str = Field(min_length=8, max_length=1_000)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_quality: Literal["complete", "partial"] = "complete"


class ProductRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: str = Field(min_length=3, max_length=128)
    display_name: str = Field(min_length=1, max_length=160)
    brand: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=2, max_length=80)
    region: str = Field(default="CN", min_length=2, max_length=12)
    use_case: str = Field(min_length=2, max_length=160)
    catalog_scope: Literal["curated_verification_catalog"]
    label: ProductLabelEvidence


class AlternativeSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str = Field(min_length=2, max_length=80)
    applicable_date: date
    constraints: list[ConstraintInput] = Field(min_length=1, max_length=16)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    region: str = Field(default="CN", min_length=2, max_length=12)
    exclude_product_ids: list[str] = Field(default_factory=list, max_length=50)
    limit: int = Field(default=5, ge=1, le=20)


class AlternativeRevalidationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1, max_length=128)
    applicable_date: date
    constraints: list[ConstraintInput] = Field(min_length=1, max_length=16)
    candidates: list[ProductRecord] = Field(max_length=20)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)


class ProductComparisonRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    products: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    nutrient_keys: list[str] = Field(
        default_factory=lambda: ["energy", "protein", "fat", "sugars", "sodium"],
        max_length=20,
    )

    @model_validator(mode="after")
    def require_revalidated_products(self):
        if any(
            item.get("revalidated") is not True
            or item.get("disposition") != "eligible"
            or item.get("risk_level") != "compatible"
            for item in self.products
        ):
            raise ValueError(
                "Only eligible, independently revalidated products can be compared"
            )
        return self


class AlternativeWorkflowRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1, max_length=128)
    applicable_date: date
    confirmed_fields: dict[str, str]
    constraints: list[ConstraintInput] = Field(min_length=1, max_length=16)
    category: str = Field(min_length=2, max_length=80)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    region: str = Field(default="CN", min_length=2, max_length=12)
    nutrition_rows: list[list[str]] | None = None
    resume_token: str = Field(min_length=32, max_length=256)
