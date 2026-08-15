"""Evidence-first product alternative discovery and revalidation."""

from .discovery import OfficialProductDiscovery
from .service import (
    compare_food_products,
    find_alternative_products,
    revalidate_alternatives,
)

__all__ = [
    "OfficialProductDiscovery",
    "compare_food_products",
    "find_alternative_products",
    "revalidate_alternatives",
]
