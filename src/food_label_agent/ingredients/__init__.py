"""Deterministic ingredient normalization and allergen evaluation."""

from .allergens import ALLERGEN_CATEGORIES, RULESET_METADATA, evaluate_constraints
from .normalization import normalize_ingredients
from .service import evaluate_user_constraints_result, normalize_food_label_result

__all__ = [
    "ALLERGEN_CATEGORIES",
    "RULESET_METADATA",
    "evaluate_constraints",
    "evaluate_user_constraints_result",
    "normalize_food_label_result",
    "normalize_ingredients",
]
