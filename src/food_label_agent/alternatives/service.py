"""Deterministic discovery, comparison, and safety revalidation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, timedelta
from hashlib import sha256
from typing import Any

from food_label_agent.ingredients.api_models import SafetyEvaluationRequest
from food_label_agent.ingredients.service import evaluate_user_constraints_result

from .catalog import ProductCatalog, configured_catalog
from .models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductComparisonRequest,
    ProductRecord,
)

MAX_LABEL_AGE = timedelta(days=550)


def find_alternative_products(
    request: AlternativeSearchRequest,
    *,
    catalog: ProductCatalog | None = None,
) -> dict[str, Any]:
    """Find same-category candidates and reject incomplete or stale evidence."""

    store = catalog or configured_catalog()
    catalog_result = store.search(category=request.category, region=request.region)
    excluded_ids = set(request.exclude_product_ids)
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = list(catalog_result.rejected)
    seen_ids: set[str] = set()
    for product in catalog_result.records:
        if product.product_id in seen_ids:
            rejected.append(
                {
                    "product_id": product.product_id,
                    "display_name": product.display_name,
                    "reason_code": "DUPLICATE_PRODUCT_RECORD",
                    "evidence_ids": [product.label.evidence_id],
                }
            )
            continue
        seen_ids.add(product.product_id)
        if product.product_id in excluded_ids:
            continue
        rejection = _evidence_rejection(product, request.applicable_date)
        if rejection:
            rejected.append(
                {
                    "product_id": product.product_id,
                    "display_name": product.display_name,
                    "reason_code": rejection,
                    "evidence_ids": [product.label.evidence_id],
                }
            )
            continue
        candidates.append(product.model_dump(mode="json"))
        if len(candidates) >= request.limit:
            break
    return {
        "status": "candidates_found" if candidates else "unknown",
        "category": request.category,
        "region": request.region,
        "candidates": candidates,
        "rejected": rejected,
        "unknowns": [] if candidates else ["no_current_complete_candidate_labels"],
        "catalog_scope": catalog_result.provider,
        "catalog_status": catalog_result.status,
        "catalog_warnings": list(catalog_result.warnings),
        "selection_basis": {
            "source": catalog_result.provider,
            "category_match": "exact",
            "region_match": "exact",
            "evidence_requirements": [
                "complete",
                "current_for_applicable_date",
                "content_hash_verified",
            ],
            "constraint_evaluation": "independent_revalidation_required",
        },
    }


def revalidate_alternatives(request: AlternativeRevalidationRequest) -> dict[str, Any]:
    """Run the complete deterministic safety rules independently for every candidate."""

    results: list[dict[str, Any]] = []
    for index, product in enumerate(request.candidates, start=1):
        label = product.label
        confirmed_fields = {"ingredients": label.ingredients_text}
        if label.allergen_statement:
            confirmed_fields["allergen_statement"] = label.allergen_statement
        if label.nutrition_table_text:
            confirmed_fields["nutrition_table"] = label.nutrition_table_text
        if label.nutrition_basis_text:
            confirmed_fields["nutrition_basis"] = label.nutrition_basis_text
        evaluation = evaluate_user_constraints_result(
            SafetyEvaluationRequest(
                request_id=f"{request.request_id}:alternative:{index}",
                jurisdiction=request.jurisdiction,
                applicable_date=request.applicable_date.isoformat(),
                confirmed_fields=confirmed_fields,
                nutrition_rows=label.nutrition_rows,
                constraints=request.constraints,
            )
        )
        eligible = evaluation.overall_risk_level == "compatible"
        results.append(
            {
                "product_id": product.product_id,
                "display_name": product.display_name,
                "brand": product.brand,
                "category": product.category,
                "use_case": product.use_case,
                "catalog_scope": product.catalog_scope,
                "disposition": "eligible" if eligible else "excluded",
                "risk_level": evaluation.overall_risk_level,
                "reason_code": (
                    "INDEPENDENT_REVALIDATION_PASSED"
                    if eligible
                    else "INDEPENDENT_REVALIDATION_FAILED"
                ),
                "explanation": (
                    "在该候选当前已确认标签中未发现所选约束冲突；这不是绝对安全保证。"
                    if eligible
                    else "该候选重新运行完整约束规则后未通过硬过滤。"
                ),
                "revalidated": True,
                "label_confirmed_at": label.confirmed_at.isoformat(),
                "label_source_url": label.source_url,
                "label_source_provider": label.source_provider,
                "label_source_authority": label.source_authority,
                "label_source_record_version": label.source_record_version,
                "ingredients_image_url": label.ingredients_image_url,
                "nutrition_image_url": label.nutrition_image_url,
                "evidence_ids": [label.evidence_id],
                "normalized_label": evaluation.normalized_label,
                "findings": evaluation.findings,
            }
        )
    eligible_results = [item for item in results if item["disposition"] == "eligible"]
    ranked = sorted(
        eligible_results,
        key=lambda item: (
            -_authority_score(item["label_source_authority"]),
            -date.fromisoformat(item["label_confirmed_at"]).toordinal(),
            item["product_id"],
        ),
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
        item["ranking_reasons"] = [
            f"evidence_authority:{item['label_source_authority']}",
            f"label_confirmed_at:{item['label_confirmed_at']}",
        ]
    eligible_ids = {item["product_id"]: index for index, item in enumerate(ranked)}
    results.sort(
        key=lambda item: (
            0 if item["disposition"] == "eligible" else 1,
            eligible_ids.get(item["product_id"], 0),
            item["product_id"],
        )
    )
    return {
        "status": "eligible_candidates" if eligible_results else "unknown",
        "results": results,
        "eligible_count": len(eligible_results),
        "candidate_count": len(request.candidates),
        "revalidated_count": len(results),
        "revalidation_rate": 1.0,
        "unknowns": [] if eligible_results else ["no_candidate_passed_revalidation"],
    }


def compare_food_products(request: ProductComparisonRequest) -> dict[str, Any]:
    """Compare only nutrients sharing identical units and label bases."""

    comparisons: list[dict[str, Any]] = []
    unknowns: list[str] = []
    for nutrient_key in request.nutrient_keys:
        values = _nutrient_values(request.products, nutrient_key)
        if not values:
            continue
        bases = {item["basis"] for item in values}
        units = {item["unit"] for item in values}
        if len(values) != len(request.products) or len(bases) != 1 or len(units) != 1:
            unknowns.append(f"nutrition_basis_or_unit_not_comparable:{nutrient_key}")
            continue
        comparisons.append(
            {
                "nutrient": nutrient_key,
                "basis": values[0]["basis"],
                "unit": values[0]["unit"],
                "values": [
                    {
                        "product_id": item["product_id"],
                        "display_name": item["display_name"],
                        "value": item["value"],
                        "evidence_id": item["evidence_id"],
                    }
                    for item in values
                ],
            }
        )
    return {
        "status": "compared" if comparisons else "unknown",
        "comparisons": comparisons,
        "unknowns": unknowns or ([] if comparisons else ["no_comparable_nutrition"]),
    }


def _evidence_rejection(product: ProductRecord, applicable_date) -> str | None:
    label = product.label
    if label.evidence_quality != "complete":
        return "LABEL_EVIDENCE_INCOMPLETE"
    if label.content_hash != _label_content_hash(product):
        return "LABEL_EVIDENCE_HASH_MISMATCH"
    if label.valid_through and applicable_date > label.valid_through:
        return "LABEL_EVIDENCE_EXPIRED"
    if applicable_date < label.confirmed_at:
        return "LABEL_EVIDENCE_FROM_FUTURE"
    if applicable_date - label.confirmed_at > MAX_LABEL_AGE:
        return "LABEL_EVIDENCE_STALE"
    return None


def _label_content_hash(product: ProductRecord) -> str:
    label = product.label
    payload = {
        "ingredients_text": label.ingredients_text,
        "allergen_statement": label.allergen_statement or "",
        "nutrition_table_text": label.nutrition_table_text or "",
        "nutrition_basis_text": label.nutrition_basis_text or "",
        "nutrition_rows": label.nutrition_rows or [],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


def _authority_score(authority: str) -> int:
    return {"manufacturer": 3, "internal_review": 2, "community": 1}.get(authority, 0)


def _nutrient_values(
    products: Iterable[dict[str, Any]], nutrient_key: str
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for product in products:
        nutrients = (
            product.get("normalized_label", {})
            .get("nutrition", {})
            .get("nutrients", [])
        )
        nutrient = next(
            (item for item in nutrients if item.get("canonical_name") == nutrient_key),
            None,
        )
        if not nutrient:
            continue
        values.append(
            {
                "product_id": product["product_id"],
                "display_name": product["display_name"],
                "value": nutrient["value"],
                "unit": nutrient["unit"],
                "basis": nutrient["basis"],
                "evidence_id": nutrient["evidence_id"],
            }
        )
    return values
