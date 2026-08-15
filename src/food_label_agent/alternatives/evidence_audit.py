"""Field-level coverage audits for official product-label evidence."""

from __future__ import annotations

from typing import Any

from .models import ProductRecord

_PLACEHOLDER_MARKERS = (
    "待核验",
    "待确认",
    "以实际包装为准",
    "官网已确认",
    "混合坚果与果干",
)
_CORE_NUTRIENTS = {
    "能量": "能量",
    "蛋白质": "蛋白质",
    "脂肪": "脂肪",
    "碳水化合物": "碳水化合物",
    "钠": "钠",
}


def audit_product_label(product: ProductRecord) -> dict[str, Any]:
    """Describe verified and missing packaging fields without guessing values."""

    label = product.label
    ingredients_ready = _is_verified_text(label.ingredients_text)
    allergen_ready = _is_verified_text(label.allergen_statement)
    nutrient_names = {
        str(row[0]).strip()
        for row in (label.nutrition_rows or [])[1:]
        if row and str(row[0]).strip()
    }
    nutrition_basis_ready = bool(label.nutrition_basis_text)
    present_core = [
        display for raw, display in _CORE_NUTRIENTS.items() if raw in nutrient_names
    ]
    missing_core = [
        display for raw, display in _CORE_NUTRIENTS.items() if raw not in nutrient_names
    ]

    verified_fields: list[str] = []
    missing_fields: list[str] = []
    if ingredients_ready:
        verified_fields.append("完整配料表文字")
    else:
        missing_fields.append("完整配料表文字")
    if allergen_ready:
        verified_fields.append("包装过敏原提示")
    else:
        missing_fields.append("包装过敏原提示")
    if nutrition_basis_ready:
        verified_fields.append("营养标示口径")
    else:
        missing_fields.append("营养标示口径")
    if present_core:
        verified_fields.append(f"营养项目：{'、'.join(present_core)}")
    if missing_core:
        missing_fields.append(f"营养项目：{'、'.join(missing_core)}")

    full_label_ready = ingredients_ready and allergen_ready and not missing_core
    return {
        "status": "complete" if full_label_ready else "needs_review",
        "full_label_ready": full_label_ready,
        "current_evidence_gate_passed": label.evidence_quality == "complete",
        "verified_fields": verified_fields,
        "missing_fields": missing_fields,
        "source_url": label.source_url,
        "official_store_url": label.official_store_url,
        "official_store_name": label.official_store_name,
        "review_priority": _review_priority(ingredients_ready, allergen_ready, missing_core),
    }


def summarize_label_coverage(products: list[ProductRecord]) -> dict[str, Any]:
    audits = [audit_product_label(product) for product in products]
    complete = sum(item["full_label_ready"] for item in audits)
    gate_passed = sum(item["current_evidence_gate_passed"] for item in audits)
    return {
        "total": len(products),
        "full_label_count": complete,
        "evidence_gate_count": gate_passed,
        "needs_review_count": len(products) - complete,
        "coverage_rate": complete / len(products) if products else 0.0,
    }


def _is_verified_text(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return not any(marker in value for marker in _PLACEHOLDER_MARKERS)


def _review_priority(
    ingredients_ready: bool, allergen_ready: bool, missing_core: list[str]
) -> str:
    if not ingredients_ready or not allergen_ready:
        return "high"
    if missing_core:
        return "medium"
    return "complete"
