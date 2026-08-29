"""Validated contracts for evidence-backed product alternatives."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from food_label_agent.ingredients.api_models import ConstraintInput


class PackagingSnapshotEvidence(BaseModel):
    """Immutable image evidence tied to one concrete package/SKU.

    An official web-page capture may preserve provenance for transcribed text, but
    only ``packaging_photo`` represents the physical package and can satisfy a
    packaging safety gate.
    """

    model_config = ConfigDict(frozen=True)

    snapshot_id: str = Field(min_length=8, max_length=200)
    evidence_kind: Literal["ingredients", "nutrition", "combined"]
    artifact_type: Literal["packaging_photo", "official_page_capture"]
    source_url: str = Field(min_length=8, max_length=1_000)
    captured_at: date
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    byte_size: int = Field(gt=0, le=20_000_000)
    pixel_width: int = Field(gt=0, le=50_000)
    pixel_height: int = Field(gt=0, le=50_000)
    sharpness_score: float = Field(ge=0)
    contrast_score: float = Field(ge=0)
    artifact_path: str = Field(min_length=8, max_length=500)
    sku: str = Field(min_length=1, max_length=120)
    specification: str = Field(min_length=1, max_length=160)
    review_status: Literal["pending_second_review", "verified", "rejected"]
    primary_reviewer_id: str = Field(min_length=3, max_length=120)
    secondary_reviewer_id: str | None = Field(default=None, min_length=3, max_length=120)
    reviewed_at: date | None = None

    @model_validator(mode="after")
    def enforce_independent_dual_review(self):
        if min(self.pixel_width, self.pixel_height) < 480 or max(
            self.pixel_width, self.pixel_height
        ) < 640:
            raise ValueError("Packaging evidence resolution is too low")
        if self.sharpness_score < 20 or self.contrast_score < 8:
            raise ValueError("Packaging evidence quality is below review threshold")
        if (
            self.secondary_reviewer_id
            and self.secondary_reviewer_id == self.primary_reviewer_id
        ):
            raise ValueError("Packaging evidence requires two distinct reviewers")
        if self.review_status == "verified" and (
            not self.secondary_reviewer_id or self.reviewed_at is None
        ):
            raise ValueError("Verified packaging evidence requires a second review")
        if self.review_status == "pending_second_review" and self.secondary_reviewer_id:
            raise ValueError("Pending packaging evidence cannot have a second reviewer")
        return self


class ProductLabelEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(min_length=8, max_length=160)
    ingredients_text: str = Field(min_length=1, max_length=20_000)
    allergen_statement: str | None = Field(default=None, max_length=4_000)
    nutrition_table_text: str | None = Field(default=None, max_length=10_000)
    nutrition_basis_text: str | None = Field(default=None, max_length=200)
    nutrition_rows: list[list[str]] | None = None
    confirmed_by: Literal[
        "human_review", "manufacturer_label", "external_community_review"
    ]
    confirmed_at: date
    valid_through: date | None = None
    source_url: str = Field(min_length=8, max_length=1_000)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_quality: Literal["complete", "partial"] = "complete"
    source_provider: str = Field(default="internal", min_length=2, max_length=80)
    source_type: Literal[
        "official_product_page",
        "official_flagship_store",
        "internal_review",
        "community",
    ] = "internal_review"
    source_verified_at: date | None = None
    source_language: Literal["zh-CN", "other"] = "zh-CN"
    source_access_region: Literal["CN", "unknown"] = "unknown"
    source_record_version: str | None = Field(default=None, max_length=100)
    ingredients_image_url: str | None = Field(default=None, max_length=1_000)
    nutrition_image_url: str | None = Field(default=None, max_length=1_000)
    sugars_review_status: Literal[
        "declared", "not_declared", "source_insufficient", "not_reviewed"
    ] = "not_reviewed"
    sugars_reviewed_at: date | None = None
    sugars_review_note: str | None = Field(default=None, max_length=500)
    official_store_url: str | None = Field(default=None, max_length=1_000)
    official_store_name: str | None = Field(default=None, max_length=160)
    official_store_verified_at: date | None = None
    source_authority: Literal["manufacturer", "internal_review", "community"] = (
        "internal_review"
    )
    packaging_snapshots: list[PackagingSnapshotEvidence] = Field(
        default_factory=list, max_length=8
    )


class ProductRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: str = Field(min_length=3, max_length=128)
    display_name: str = Field(min_length=1, max_length=160)
    brand: str = Field(min_length=1, max_length=100)
    sku: str | None = Field(default=None, min_length=1, max_length=120)
    specification: str | None = Field(default=None, min_length=1, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    region: str = Field(default="CN", min_length=2, max_length=12)
    use_case: str = Field(min_length=2, max_length=160)
    substitution_match: Literal["exact", "same_use"] | None = None
    substitution_reason: str | None = Field(default=None, max_length=200)
    catalog_scope: Literal[
        "official_cn_catalog",
        "curated_verification_catalog",
        "live_open_food_facts",
    ]
    label: ProductLabelEvidence


class AlternativeSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str = Field(min_length=2, max_length=80)
    substitute_categories: list[str] = Field(default_factory=list, max_length=6)
    applicable_date: date
    constraints: list[ConstraintInput] = Field(default_factory=list, max_length=16)
    health_concerns: list[str] = Field(default_factory=list, max_length=16)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    region: str = Field(default="CN", min_length=2, max_length=12)
    exclude_product_ids: list[str] = Field(default_factory=list, max_length=50)
    current_product_name: str | None = Field(default=None, min_length=2, max_length=200)
    limit: int = Field(default=8, ge=1, le=50)


class AlternativeRevalidationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1, max_length=128)
    applicable_date: date
    constraints: list[ConstraintInput] = Field(default_factory=list, max_length=16)
    health_concerns: list[str] = Field(default_factory=list, max_length=16)
    source_category: str | None = Field(default=None, min_length=2, max_length=80)
    current_nutrition_rows: list[list[str]] | None = None
    candidates: list[ProductRecord] = Field(max_length=50)
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
    constraints: list[ConstraintInput] = Field(default_factory=list, max_length=16)
    health_concerns: list[str] = Field(default_factory=list, max_length=16)
    category: str = Field(min_length=2, max_length=80)
    substitute_categories: list[str] = Field(default_factory=list, max_length=6)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    region: str = Field(default="CN", min_length=2, max_length=12)
    current_product_id: str | None = Field(default=None, min_length=3, max_length=128)
    nutrition_rows: list[list[str]] | None = None
    resume_token: str = Field(min_length=32, max_length=256)
