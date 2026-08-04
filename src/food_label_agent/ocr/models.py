"""Validated external models for OCR and human confirmation APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoundingBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class OCRLineEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox | None = None


class NutritionValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    message: str
    row_index: int | None = None


class NutritionTableData(BaseModel):
    model_config = ConfigDict(frozen=True)

    rows: list[list[str]]
    issues: list[NutritionValidationIssue] = Field(default_factory=list)


class OCREvidenceIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    message: str
    field_name: str | None = None


class OCREvidenceReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    issues: list[OCREvidenceIssue] = Field(default_factory=list)


class OCRFieldResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    raw_text: str
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool
    bounding_box: BoundingBox | None = None
    evidence_lines: list[OCRLineEvidence] = Field(default_factory=list)
    nutrition_table: NutritionTableData | None = None


class OCRAnalysisResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    provider: str
    synthetic: bool
    file_name: str
    fields: list[OCRFieldResult]
    evidence_quality: OCREvidenceReport
    warnings: list[str] = Field(default_factory=list)
    next_route: str


class ConfirmLabelRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    jurisdiction: str = Field(default="CN", min_length=2, max_length=12)
    applicable_date: str
    fields: dict[str, str]

    @field_validator("fields")
    @classmethod
    def normalize_fields(cls, fields: dict[str, str]) -> dict[str, str]:
        normalized = {key.strip(): value.strip() for key, value in fields.items()}
        if not normalized.get("ingredients"):
            raise ValueError("配料表不能为空，请重新拍摄或手动补充。")
        return normalized


class ConfirmLabelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    status: str
    next_route: str
    confirmed_fields: list[str]
    message: str
