"""Field-level coverage audits for official product-label evidence."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from food_label_agent.ingredients.api_models import ConstraintInput

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

_NUTRIENT_ALIASES = {
    "energy": ("能量",),
    "protein": ("蛋白质",),
    "fat": ("脂肪", "总脂肪"),
    "saturated_fat": ("饱和脂肪", "饱和脂肪酸"),
    "trans_fat": ("反式脂肪", "反式脂肪酸"),
    "carbohydrate": ("碳水化合物",),
    "sugars": ("糖", "糖类"),
    "dietary_fiber": ("膳食纤维",),
    "sodium": ("钠",),
}

_FIELD_LABELS = {
    "ingredients": "完整配料表文字",
    "allergen_statement": "包装过敏原及交叉接触提示",
    "nutrition_basis": "营养标示口径",
    "energy": "能量",
    "protein": "蛋白质",
    "fat": "脂肪",
    "saturated_fat": "饱和脂肪",
    "trans_fat": "反式脂肪",
    "carbohydrate": "碳水化合物",
    "sugars": "糖",
    "dietary_fiber": "膳食纤维",
    "sodium": "钠",
    "packaging_snapshot": "可复核的包装配料/过敏原图片",
}

_HEALTH_REQUIREMENTS = {
    "blood_sugar": {"ingredients", "nutrition_basis", "carbohydrate", "sugars"},
    "sugar_control": {"ingredients", "nutrition_basis", "carbohydrate", "sugars"},
    "blood_lipids": {"ingredients", "nutrition_basis", "fat", "saturated_fat"},
    "blood_pressure": {"ingredients", "nutrition_basis", "sodium"},
    "weight": {"ingredients", "nutrition_basis", "energy"},
    "uric_acid": {"ingredients"},
    "gut": {"ingredients"},
    "child": {
        "ingredients",
        "allergen_statement",
        "nutrition_basis",
        "energy",
        "sugars",
        "sodium",
    },
}


def label_content_hash(product: ProductRecord) -> str:
    """Return the canonical hash used to detect reviewed label mutations."""

    label = product.label
    payload = {
        "ingredients_text": label.ingredients_text,
        "allergen_statement": label.allergen_statement or "",
        "nutrition_table_text": label.nutrition_table_text or "",
        "nutrition_basis_text": label.nutrition_basis_text or "",
        "nutrition_rows": label.nutrition_rows or [],
    }
    if label.packaging_snapshots:
        payload["packaging_snapshots"] = sorted(
            (
                snapshot.model_dump(mode="json")
                for snapshot in label.packaging_snapshots
            ),
            key=lambda item: str(item["snapshot_id"]),
        )
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


def audit_product_label(product: ProductRecord) -> dict[str, Any]:
    """Describe verified and missing packaging fields without guessing values."""

    label = product.label
    ingredients_ready = _is_verified_text(label.ingredients_text)
    allergen_ready = _is_verified_text(label.allergen_statement)
    nutrient_names = _nutrient_names(product)
    nutrition_basis_ready = bool(label.nutrition_basis_text)
    present_core = [
        display for raw, display in _CORE_NUTRIENTS.items() if raw in nutrient_names
    ]
    missing_core = [
        display for raw, display in _CORE_NUTRIENTS.items() if raw not in nutrient_names
    ]

    verified_fields: list[str] = []
    missing_fields: list[str] = []
    if product.sku:
        verified_fields.append("SKU/条码")
    else:
        missing_fields.append("SKU/条码")
    if product.specification:
        verified_fields.append("商品规格")
    else:
        missing_fields.append("商品规格")
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

    transcribed_label_ready = ingredients_ready and allergen_ready and not missing_core
    verified_packaging_kinds = _verified_packaging_kinds(product)
    ingredient_snapshot_ready = bool(
        verified_packaging_kinds & {"ingredients", "combined"}
    )
    nutrition_snapshot_ready = bool(
        verified_packaging_kinds & {"nutrition", "combined"}
    )
    complete_packaging_snapshot_ready = (
        ingredient_snapshot_ready and nutrition_snapshot_ready
    )
    # Keep the legacy field as the text-table completeness signal. Consumers must
    # use complete_packaging_snapshot_ready for physical-package verification.
    full_label_ready = transcribed_label_ready
    if not ingredient_snapshot_ready:
        missing_fields.append("双人复核实物包装配料图")
    if not nutrition_snapshot_ready:
        missing_fields.append("双人复核实物包装营养图")
    base_evidence_status = (
        "complete"
        if transcribed_label_ready and complete_packaging_snapshot_ready
        else "review_required"
    )
    return {
        "status": (
            "fully_verified"
            if transcribed_label_ready and complete_packaging_snapshot_ready
            else "needs_review"
        ),
        "full_label_ready": full_label_ready,
        "transcribed_label_ready": transcribed_label_ready,
        "current_evidence_gate_passed": label.evidence_quality == "complete",
        "transcription_gate_passed": (
            label.evidence_quality == "complete" and transcribed_label_ready
        ),
        "verified_fields": verified_fields,
        "missing_fields": missing_fields,
        "source_url": label.source_url,
        "official_store_url": label.official_store_url,
        "official_store_name": label.official_store_name,
        "ingredients_image_url": label.ingredients_image_url,
        "nutrition_image_url": label.nutrition_image_url,
        "packaging_snapshot_ready": ingredient_snapshot_ready,
        "ingredient_snapshot_ready": ingredient_snapshot_ready,
        "nutrition_snapshot_ready": nutrition_snapshot_ready,
        "complete_packaging_snapshot_ready": complete_packaging_snapshot_ready,
        "official_page_snapshot_count": sum(
            snapshot.review_status == "verified"
            and snapshot.artifact_type == "official_page_capture"
            for snapshot in label.packaging_snapshots
        ),
        "evidence_status": {
            "status": base_evidence_status,
            "label": (
                "证据完整" if base_evidence_status == "complete" else "需要补齐或复核"
            ),
            "confirmed_at": label.confirmed_at.isoformat(),
            "source_verified_at": (
                label.source_verified_at or label.confirmed_at
            ).isoformat(),
            "valid_through": (
                label.valid_through.isoformat() if label.valid_through else None
            ),
            "record_version": label.source_record_version,
            "source_type": label.source_type,
            "source_authority": label.source_authority,
            "source_language": label.source_language,
            "source_access_region": label.source_access_region,
        },
        "review_priority": (
            "high"
            if not ingredient_snapshot_ready
            else _review_priority(ingredients_ready, allergen_ready, missing_core)
        ),
    }


def assess_product_eligibility(
    product: ProductRecord,
    *,
    constraints: list[ConstraintInput] | tuple[ConstraintInput, ...] = (),
    health_concerns: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return the product's field-level eligibility for one user context.

    Official provenance, recency and hash checks remain separate release gates. This
    assessment only answers whether the confirmed package fields are sufficient for
    the user's active constraints and supported health concerns.
    """

    audit = audit_product_label(product)
    safety_required = {"ingredients"}
    comparison_requested: set[str] = set()
    supported_concerns: list[str] = []
    unsupported_concerns: list[str] = []
    for concern in dict.fromkeys(health_concerns):
        fields = _HEALTH_REQUIREMENTS.get(concern)
        if fields is None:
            unsupported_concerns.append(concern)
            continue
        supported_concerns.append(concern)
        comparison_requested.update(fields - {"ingredients", "allergen_statement"})
    for constraint in constraints:
        if constraint.kind == "nutrition_limit":
            safety_required.update({"nutrition_basis", constraint.canonical_value})
        else:
            safety_required.update({"ingredients", "allergen_statement"})
            if (
                product.catalog_scope == "official_cn_catalog"
                and constraint.severity == "severe"
            ):
                safety_required.add("packaging_snapshot")

    available = _available_fields(product)
    missing = sorted(safety_required - available, key=_field_sort_key)
    missing_comparison = sorted(comparison_requested - available, key=_field_sort_key)
    verified_comparison = sorted(comparison_requested & available, key=_field_sort_key)
    full_label_ready = bool(audit["full_label_ready"])
    physical_package_ready = bool(audit["complete_packaging_snapshot_ready"])
    eligible = not missing
    if not eligible:
        tier = "needs_review"
    elif full_label_ready and physical_package_ready:
        tier = "fully_verified"
    else:
        tier = "conditionally_verified"
    return {
        "status": tier,
        "eligible_for_current_context": eligible,
        "required_fields": [
            _FIELD_LABELS.get(item, item)
            for item in sorted(safety_required, key=_field_sort_key)
        ],
        "verified_required_fields": [
            _FIELD_LABELS.get(item, item)
            for item in sorted(safety_required & available, key=_field_sort_key)
        ],
        "missing_required_fields": [_FIELD_LABELS.get(item, item) for item in missing],
        "comparison_requested_fields": [
            _FIELD_LABELS.get(item, item)
            for item in sorted(comparison_requested, key=_field_sort_key)
        ],
        "verified_comparison_fields": [
            _FIELD_LABELS.get(item, item) for item in verified_comparison
        ],
        "missing_comparison_fields": [
            _FIELD_LABELS.get(item, item) for item in missing_comparison
        ],
        "health_comparison_available": bool(verified_comparison),
        "sugars_review_status": product.label.sugars_review_status,
        "sugars_reviewed_at": (
            product.label.sugars_reviewed_at.isoformat()
            if product.label.sugars_reviewed_at
            else None
        ),
        "sugars_review_note": product.label.sugars_review_note,
        "supported_health_concerns": supported_concerns,
        "unsupported_health_concerns": unsupported_concerns,
        "full_label_ready": full_label_ready,
    }


def summarize_label_coverage(products: list[ProductRecord]) -> dict[str, Any]:
    audits = [audit_product_label(product) for product in products]
    complete = sum(item["full_label_ready"] for item in audits)
    gate_passed = sum(item["current_evidence_gate_passed"] for item in audits)
    return {
        "total": len(products),
        "sku_count": sum(bool(product.sku) for product in products),
        "specification_count": sum(
            bool(product.specification) for product in products
        ),
        "full_label_count": complete,
        "transcribed_label_count": sum(
            item["transcribed_label_ready"] for item in audits
        ),
        "evidence_gate_count": gate_passed,
        "packaging_snapshot_count": sum(
            item["packaging_snapshot_ready"] for item in audits
        ),
        "nutrition_snapshot_count": sum(
            item["nutrition_snapshot_ready"] for item in audits
        ),
        "complete_packaging_snapshot_count": sum(
            item["complete_packaging_snapshot_ready"] for item in audits
        ),
        "official_page_snapshot_count": sum(
            item["official_page_snapshot_count"] for item in audits
        ),
        "packaging_needs_review_count": len(products)
        - sum(item["complete_packaging_snapshot_ready"] for item in audits),
        "packaging_coverage_rate": (
            sum(item["complete_packaging_snapshot_ready"] for item in audits)
            / len(products)
            if products
            else 0.0
        ),
        "needs_review_count": len(products) - complete,
        "coverage_rate": complete / len(products) if products else 0.0,
    }


def summarize_context_eligibility(
    products: list[ProductRecord],
    *,
    constraints: list[ConstraintInput] | tuple[ConstraintInput, ...] = (),
    health_concerns: list[str] | tuple[str, ...] = (),
) -> dict[str, int]:
    assessments = [
        assess_product_eligibility(
            product,
            constraints=constraints,
            health_concerns=health_concerns,
        )
        for product in products
    ]
    return {
        "fully_verified_count": sum(
            item["status"] == "fully_verified" for item in assessments
        ),
        "conditionally_verified_count": sum(
            item["status"] == "conditionally_verified" for item in assessments
        ),
        "context_needs_review_count": sum(
            item["status"] == "needs_review" for item in assessments
        ),
    }


def _available_fields(product: ProductRecord) -> set[str]:
    label = product.label
    available: set[str] = set()
    if _is_verified_text(label.ingredients_text):
        available.add("ingredients")
    if _is_verified_text(label.allergen_statement):
        available.add("allergen_statement")
    if _is_verified_text(label.nutrition_basis_text):
        available.add("nutrition_basis")
    if _verified_packaging_kinds(product) & {"ingredients", "combined"}:
        available.add("packaging_snapshot")
    nutrient_names = _nutrient_names(product)
    for canonical, aliases in _NUTRIENT_ALIASES.items():
        if any(alias in nutrient_names for alias in aliases):
            available.add(canonical)
    return available


def _nutrient_names(product: ProductRecord) -> set[str]:
    return {
        str(row[0]).strip()
        for row in (product.label.nutrition_rows or [])[1:]
        if row and str(row[0]).strip()
    }


def _verified_packaging_kinds(product: ProductRecord) -> set[str]:
    """Return physical-package evidence kinds bound to this exact SKU/spec."""

    if not product.sku or not product.specification:
        return set()
    return {
        snapshot.evidence_kind
        for snapshot in product.label.packaging_snapshots
        if snapshot.review_status == "verified"
        and snapshot.artifact_type == "packaging_photo"
        and snapshot.sku == product.sku
        and snapshot.specification == product.specification
        and snapshot.secondary_reviewer_id
        and snapshot.secondary_reviewer_id != snapshot.primary_reviewer_id
    }


def _field_sort_key(value: str) -> tuple[int, str]:
    order = tuple(_FIELD_LABELS)
    return (order.index(value) if value in order else len(order), value)


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
