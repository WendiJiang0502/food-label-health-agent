"""Stable enums for the food-label analysis domain."""

from enum import StrEnum


class AnalysisStatus(StrEnum):
    RECEIVED = "received"
    IN_PROGRESS = "in_progress"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class WorkflowStage(StrEnum):
    INPUT_VALIDATION = "input_validation"
    OCR_EXTRACTION = "ocr_extraction"
    HUMAN_CONFIRMATION = "human_confirmation"
    LABEL_NORMALIZATION = "label_normalization"
    SAFETY_EVALUATION = "safety_evaluation"
    REGULATORY_RETRIEVAL = "regulatory_retrieval"
    INTERPRETATION = "interpretation"
    ALTERNATIVE_SEARCH = "alternative_search"
    FINAL_SAFETY_GATE = "final_safety_gate"
    COMPLETED = "completed"


class RiskLevel(StrEnum):
    AVOID = "avoid"
    CAUTION = "caution"
    COMPATIBLE = "compatible"
    UNKNOWN = "unknown"


class ConstraintKind(StrEnum):
    ALLERGY = "allergy"
    INTOLERANCE = "intolerance"
    DIET = "diet"
    USER_AVOIDANCE = "user_avoidance"
    NUTRITION_LIMIT = "nutrition_limit"
