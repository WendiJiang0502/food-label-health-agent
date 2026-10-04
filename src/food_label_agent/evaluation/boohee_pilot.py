"""Offline evidence assessment for the mainland food-data pilot.

Never treats provider zero defaults, recipe materials, or display images as
verified packaging evidence. This module does not modify the production catalog.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256


def assess_detail(response: dict) -> dict:
    if response.get("code") != 0 or not isinstance(response.get("data"), dict):
        return {"status": "provider_error", "recommendation_eligible": False}
    data = response["data"]
    nutrients = {}
    for key in ("calories", "protein", "fat", "carbohydrate"):
        if isinstance(data.get(key), dict):
            nutrients[key] = data[key]
    for row in data.get("ingredients") or []:
        if isinstance(row, dict) and row.get("key"):
            nutrients[row["key"]] = row
    observations = []
    for key, row in nutrients.items():
        value = row.get("value")
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= 0
        )
        observations.append(
            {
                "field": key,
                "value": value,
                "unit": row.get("unit"),
                "status": ("zero_unverified" if value == 0 else "source_unverified")
                if valid
                else "missing_or_invalid",
                "usable_for_recommendation": False,
            }
        )
    return {
        "status": "needs_review",
        "code": data.get("code"),
        "name": data.get("name"),
        "food_type": data.get("food_type"),
        "observations": observations,
        "ingredients_text": None,
        "materials_are_packaging_ingredients": False,
        "basis_note": "Search documentation uses per 100g; do not silently convert liquid values to per 100ml.",
        "recommendation_eligible": False,
    }


def stage_official_products(
    groups: list, *, captured_at: str, source_hash: str
) -> list:
    """Preserve official text and units verbatim, with no SKU/zero fabrication."""
    items = []
    for group in groups:
        for product in group.get("list", []):
            name = product.get("name", "")
            ingredients = product.get("ingredients", "")
            rows = product.get("component", [])
            flags = [
                "barcode_not_provided",
                "packaging_revision_unverified",
                "allergen_statement_not_provided",
            ]
            if not any(r.get("name") == "糖" for r in rows):
                flags.append("sugar_not_reported")
            if "草莓" in name and "草莓" not in ingredients and "蓝莓" in ingredients:
                flags.append("flavour_ingredient_conflict")
            if "嗜执" in ingredients:
                flags.append("source_text_typo_requires_review")
            if "牛奶" in name:
                flags.append("liquid_basis_requires_review")
            spec = re.search(r"\((\d+(?:\.\d+)?(?:千克|克|毫升))\)", name)
            if not spec:
                flags.append("package_size_not_provided_in_text")
            items.append(
                {
                    "id": "simplelove:"
                    + sha256((str(group["id"]) + "|" + name).encode()).hexdigest()[:16],
                    "name": "简爱 " + name,
                    "series": group.get("name"),
                    "category": "dairy",
                    "specification": spec.group(1) if spec else None,
                    "barcode": None,
                    "source_url": "https://simplelove.com.cn/product.html#series-"
                    + str(group["id"]),
                    "data_url": "https://simplelove.com.cn/data/product.json",
                    "source_hash": source_hash,
                    "captured_at": captured_at,
                    "ingredients_text": ingredients,
                    "nutrition_rows": rows,
                    "nutrition_basis_text": "每100克",
                    "basis_source": "Official product page table header",
                    "sugars": next(
                        (r.get("value") for r in rows if r.get("name") == "糖"), None
                    ),
                    "image_url": product.get("img"),
                    "review_status": "needs_review",
                    "missing_or_conflicting": flags,
                    "recommendation_eligible": False,
                }
            )
    return items


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
