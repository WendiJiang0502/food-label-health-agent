"""Field-level provenance; observations never confer recommendation eligibility."""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256

from food_label_agent.nutrition.normalization import normalize_nutrition_facts

OFF_FIELDS = {
    "sugars_100g": ("sugars", "g"),
    "proteins_100g": ("protein", "g"),
    "fat_100g": ("fat", "g"),
    "saturated-fat_100g": ("saturated_fat", "g"),
    "carbohydrates_100g": ("carbohydrate", "g"),
    "fiber_100g": ("dietary_fiber", "g"),
    "sodium_100g": ("sodium", "mg"),
    "energy-kj_100g": ("energy", "kJ"),
}


def observation(
    field,
    value,
    *,
    unit=None,
    basis=None,
    source_url,
    version,
    tier,
    span,
    observed_at=None,
    status=None,
):
    item = {
        "field": field,
        "value": value,
        "unit": unit,
        "basis": basis,
        "source_url": source_url,
        "source_version": version,
        "tier": tier,
        "source_span": span,
        "observed_at": observed_at,
        "review_status": status
        or ("ocr_draft" if tier == "ocr_draft" else "unverified"),
    }
    # Dates reflect fetch time, not a new observation version.
    content = {k: v for k, v in item.items() if k != "observed_at"}
    item["evidence_id"] = (
        "field:"
        + sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()[:32]
    )
    return item


def nutrition_observations(raw_text, rows, basis_text, **source):
    parsed = normalize_nutrition_facts(raw_text, rows=rows, basis_text=basis_text)
    if not parsed or parsed.requires_confirmation or not parsed.basis:
        return []
    basis = parsed.basis
    if basis.unit not in {"g", "ml"} or basis.amount <= 0:
        return []
    factor = 100 / basis.amount
    return [
        observation(
            f.canonical_name,
            f.value * factor,
            unit=f.unit,
            basis=f"per_100{basis.unit}",
            span=f.source_span,
            **source,
        )
        for f in parsed.nutrients
    ]


def external_field_evidence(raw, draft, *, version, checked_at):
    source = {
        "source_url": f"https://world.openfoodfacts.org/product/{raw['code']}",
        "version": version,
        "tier": "external_unverified",
        "observed_at": checked_at,
    }
    items = []
    ingredients = raw.get("ingredients_text_zh") or raw.get("ingredients_text")
    if ingredients:
        items.append(
            observation("ingredients", ingredients, span=ingredients, **source)
        )
    # OFF _100g fields may describe liquids per 100ml; do not infer a basis.
    basis = raw.get("nutrition_data_per")
    basis = {"100g": "per_100g", "100ml": "per_100ml"}.get(
        basis, "source_100g_or_100ml"
    )
    for key, (name, unit) in OFF_FIELDS.items():
        value = (raw.get("nutriments") or {}).get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            continue
        items.append(
            observation(
                name,
                value * 1000 if name == "sodium" else value,
                unit=unit,
                basis=basis,
                span=f"{key}={value}",
                **source,
            )
        )
    for image in (draft or {}).get("images", {}).values():
        src = {
            "source_url": image.get("source_url"),
            "version": image.get("image_sha256"),
            "tier": "ocr_draft",
            "observed_at": image.get("captured_at"),
        }
        fields = image.get("fields", [])
        basis_text = next(
            (f.get("raw_text") for f in fields if f.get("name") == "nutrition_basis"),
            None,
        )
        for field in fields:
            text = field.get("raw_text") or ""
            if field.get("name") in {"ingredients", "allergen_statement"} and text:
                items.append(observation(field["name"], text, span=text, **src))
            if field.get("name") == "nutrition_table":
                items.extend(
                    nutrition_observations(
                        text,
                        (field.get("nutrition_table") or {}).get("rows"),
                        basis_text,
                        **src,
                    )
                )
    return summarize_fields(items)


def catalog_field_evidence(product):
    from .evidence_audit import audit_product_label

    audit = audit_product_label(product)
    label = product.label
    src = {
        "source_url": label.source_url,
        "version": label.content_hash,
        "tier": "catalog_evidence",
        "observed_at": str(label.source_verified_at or label.confirmed_at),
    }
    items = [
        observation(
            "ingredients", label.ingredients_text, span=label.ingredients_text, **src
        )
    ]
    if label.allergen_statement:
        items.append(
            observation(
                "allergen_statement",
                label.allergen_statement,
                span=label.allergen_statement,
                **src,
            )
        )
    items.extend(
        nutrition_observations(
            label.nutrition_table_text,
            label.nutrition_rows,
            label.nutrition_basis_text,
            **src,
        )
    )
    snapshots = {
        s.snapshot_id: s
        for s in label.packaging_snapshots
        if s.review_status == "verified"
        and s.artifact_type != "official_page_capture"
        and s.sku == product.sku
        and s.specification == product.specification
    }
    reviews = {
        r.canonical_name: r
        for r in label.nutrition_field_reviews
        if r.review_status == "verified" and r.snapshot_id in snapshots
    }
    for item in items:
        review = reviews.get(item["field"])
        if review and item["field"] in audit["packaging_verified_nutrition_fields"]:
            snapshot = snapshots[review.snapshot_id]
            item["review_status"] = "verified"
            item["snapshot_id"] = snapshot.snapshot_id
            item["reviewed_at"] = str(review.reviewed_at)
            item["review_source_url"] = snapshot.source_url
        elif item["field"] == "ingredients" and audit["ingredient_snapshot_ready"]:
            item["review_status"] = "verified"
        else:
            item["review_status"] = "catalog_transcription"
    return summarize_fields(items)


def summarize_fields(items):
    by_field = {}
    for item in items:
        by_field.setdefault(item["field"], []).append(item)
    conflicts = []
    for field, values in by_field.items():
        groups = {}
        for item in values:
            value = item["value"]
            normalized = (
                re.sub(r"\s+", "", value).casefold()
                if isinstance(value, str)
                else round(value, 6)
            )
            groups.setdefault((item["unit"], item["basis"]), set()).add(normalized)
        if any(len(variants) > 1 for variants in groups.values()):
            conflicts.append(field)
    return {
        "observations": items,
        "conflicts": sorted(conflicts),
        "status": "conflict" if conflicts else "recorded",
    }
