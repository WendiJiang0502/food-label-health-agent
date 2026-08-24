"""Deterministic discovery, comparison, and safety revalidation."""

from __future__ import annotations

import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

from food_label_agent.ingredients.api_models import SafetyEvaluationRequest
from food_label_agent.ingredients.service import evaluate_user_constraints_result
from food_label_agent.nutrition.normalization import normalize_nutrition_facts

from .catalog import ProductCatalog, configured_catalog
from .evidence_audit import (
    assess_product_eligibility,
    audit_product_label,
    label_content_hash,
    summarize_context_eligibility,
    summarize_label_coverage,
)
from .models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
    ProductComparisonRequest,
    ProductRecord,
)

MAX_LABEL_AGE = timedelta(days=550)

_HEALTH_RANKING_FOCUS = {
    "blood_sugar": (("sugars", "lower"), ("carbohydrate", "lower")),
    "sugar_control": (("sugars", "lower"), ("carbohydrate", "lower")),
    "blood_lipids": (("saturated_fat", "lower"), ("fat", "lower")),
    "blood_pressure": (("sodium", "lower"),),
    "weight": (("energy", "lower"),),
    "gut": (("dietary_fiber", "higher"),),
    "child": (("sugars", "lower"), ("sodium", "lower")),
}

_NUTRIENT_DISPLAY_NAMES = {
    "energy": "能量",
    "fat": "脂肪",
    "saturated_fat": "饱和脂肪",
    "carbohydrate": "碳水化合物",
    "sugars": "糖",
    "dietary_fiber": "膳食纤维",
    "sodium": "钠",
}

_SAME_USE_SIGNALS = {
    ("seafood", "canned_food"): (
        "鱼",
        "虾",
        "蟹",
        "贝",
        "金枪鱼",
        "沙丁鱼",
        "tuna",
        "thon",
        "shrimp",
    ),
}

_ALLOWED_SAME_USE_PAIRS = {
    ("biscuit", "snack"),
    ("biscuit", "confectionery"),
    ("bread", "breakfast_cereal"),
    ("breakfast_cereal", "bread"),
    ("instant_noodles", "prepared_meal"),
    ("prepared_meal", "instant_noodles"),
    ("drink", "dairy"),
    ("dairy", "drink"),
    ("snack", "biscuit"),
    ("confectionery", "snack"),
    ("confectionery", "biscuit"),
    ("seafood", "canned_food"),
    ("canned_food", "processed_meat"),
    ("canned_food", "seafood"),
}

_SAME_USE_REASONS = {
    ("bread", "breakfast_cereal"): "同属早餐主食，可替换一次早餐中的主食位置",
    ("breakfast_cereal", "bread"): "同属早餐主食，可替换一次早餐中的主食位置",
    ("instant_noodles", "prepared_meal"): "同属快速正餐，可替换需要快速解决的一餐",
    ("prepared_meal", "instant_noodles"): "同属快速正餐，可替换需要快速解决的一餐",
    ("biscuit", "snack"): "同属便携零食，可替换两餐之间的一次加餐",
    ("snack", "biscuit"): "同属便携零食，可替换两餐之间的一次加餐",
    ("confectionery", "snack"): "同属便携零食，可替换一次甜食或加餐",
    ("seafood", "canned_food"): "属于明确含鱼虾的罐装食品，可替换常温即食海鲜",
}

_CATEGORY_ROLE_SIGNALS = {
    "drink": (
        ("alcoholic", ("啤酒", "beer", "tequila", "酒精")),
        ("water", ("纯净水", "矿泉水", "饮用水", "water")),
        ("tea", ("茶饮", "茶饮料", "绿茶", "红茶", "乌龙茶", "tea")),
        ("soda", ("可乐", "汽水", "soda", "cola")),
        ("juice", ("果汁", "橙汁", "苹果汁", "果味饮料", "juice")),
        ("plant_drink", ("豆奶", "豆乳", "燕麦奶", "植物蛋白", "soy", "oat")),
        ("milk_drink", ("含乳饮料", "乳饮料", "milk drink")),
    ),
    "dairy": (
        ("yogurt", ("酸奶", "发酵乳", "yogurt")),
        ("cheese", ("奶酪", "芝士", "cheese")),
        ("milk", ("纯牛奶", "牛奶", "生牛乳", "milk")),
    ),
    "frozen_food": (
        ("frozen_dessert", ("冰淇淋", "雪糕", "圣代", "ice cream", "sundae")),
        ("dumpling", ("水饺", "饺子", "馄饨", "云吞", "dumpling", "wonton")),
        ("rice_noodle_meal", ("炒饭", "面条", "意面", "rice", "noodle", "pasta")),
    ),
    "processed_meat": (
        ("sausage", ("香肠", "烤肠", "sausage")),
        ("ham_bacon", ("火腿", "培根", "ham", "bacon")),
        ("luncheon_meat", ("午餐肉", "luncheon meat")),
        ("meat_snack", ("鸡胸肉", "肉干", "肉脯", "jerky")),
    ),
    "seafood": (
        ("shrimp", ("虾", "shrimp", "prawn")),
        ("fish", ("鱼", "金枪鱼", "沙丁鱼", "fish", "tuna", "thon")),
        ("shellfish", ("蟹", "贝", "crab", "shellfish")),
    ),
    "canned_food": (
        ("seafood", ("鱼", "虾", "金枪鱼", "沙丁鱼", "tuna", "thon")),
        ("meat", ("午餐肉", "牛肉", "猪肉", "鸡肉", "beef", "pork", "chicken")),
        ("fruit", ("黄桃", "水果", "fruit", "peach")),
        ("vegetable", ("豆", "蔬菜", "芽菜", "pea", "vegetable")),
    ),
    "snack": (
        ("chips", ("薯片", "脆片", "膨化", "锅巴", "虾条", "chip", "crisp")),
        ("nuts", ("坚果", "果仁", "瓜子", "nuts")),
        ("dried_fruit", ("冻干", "果干", "dried fruit")),
        (
            "sweet_snack",
            (
                "软糖",
                "巧克力",
                "奥利奥",
                "饼干",
                "gummi",
                "oreo",
                "snickers",
                "biscotti",
            ),
        ),
    ),
}

_ROLE_SENSITIVE_CATEGORIES = {
    "drink",
    "dairy",
    "frozen_food",
    "processed_meat",
    "seafood",
    "canned_food",
    "snack",
}


def find_alternative_products(
    request: AlternativeSearchRequest,
    *,
    catalog: ProductCatalog | None = None,
) -> dict[str, Any]:
    """Find exact and same-use candidates, then reject unsafe evidence."""

    store = catalog or configured_catalog()
    requested_categories = list(
        dict.fromkeys([request.category, *request.substitute_categories])
    )
    if len(requested_categories) == 1:
        category = requested_categories[0]
        catalog_results = [
            (category, store.search(category=category, region=request.region))
        ]
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(requested_categories))) as pool:
            futures = {
                category: pool.submit(
                    store.search,
                    category=category,
                    region=request.region,
                )
                for category in requested_categories
            }
            catalog_results = [
                (category, futures[category].result())
                for category in requested_categories
            ]
    category_records = [
        product
        for _category, result in catalog_results
        for product in result.records
    ]
    excluded_ids = set(request.exclude_product_ids)
    current_family = _product_family_key(request.current_product_name)
    current_role = _substitution_role(
        request.category,
        request.current_product_name or "",
    )
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = [
        {**item, "searched_category": category}
        for category, result in catalog_results
        for item in result.rejected
    ]
    seen_ids: set[str] = set()
    seen_label_hashes: set[str] = set()
    equivalent_package_variants_collapsed = 0
    for searched_category, catalog_result in catalog_results:
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
            if current_family and _product_family_key(product.display_name) == current_family:
                continue
            if (
                searched_category == request.category
                and current_role
                and request.category in _ROLE_SENSITIVE_CATEGORIES
            ):
                candidate_role = _substitution_role(
                    searched_category,
                    f"{product.display_name} {product.label.ingredients_text}",
                )
                if candidate_role and candidate_role != current_role:
                    rejected.append(
                        {
                            "product_id": product.product_id,
                            "display_name": product.display_name,
                            "reason_code": "DIFFERENT_USE_WITHIN_CATEGORY",
                            "evidence_ids": [product.label.evidence_id],
                        }
                    )
                    continue
            if searched_category != request.category and not _same_use_candidate(
                request.category,
                searched_category,
                product,
                current_product_name=request.current_product_name,
            ):
                rejected.append(
                    {
                        "product_id": product.product_id,
                        "display_name": product.display_name,
                        "reason_code": "NOT_A_GENUINE_SAME_USE_SUBSTITUTE",
                        "evidence_ids": [product.label.evidence_id],
                    }
                )
                continue
            eligibility = assess_product_eligibility(
                product,
                constraints=request.constraints,
                health_concerns=request.health_concerns,
            )
            evidence_status = _evidence_status(
                product,
                request.applicable_date,
                eligibility=eligibility,
            )
            rejection = _evidence_rejection(
                product,
                request.applicable_date,
                eligibility=eligibility,
            )
            if rejection:
                rejected.append(
                    {
                        "product_id": product.product_id,
                        "display_name": product.display_name,
                        "reason_code": rejection,
                        "evidence_ids": [product.label.evidence_id],
                        "label_coverage": {
                            **audit_product_label(product),
                            "context_eligibility": eligibility,
                            "evidence_status": evidence_status,
                        },
                    }
                )
                continue
            # Several pack sizes can share one formula. Count the formula once
            # so package variants cannot hide genuinely different substitutes.
            if product.label.content_hash in seen_label_hashes:
                equivalent_package_variants_collapsed += 1
                continue
            seen_label_hashes.add(product.label.content_hash)
            candidates.append(
                {
                    **product.model_dump(mode="json"),
                    "catalog_eligibility": eligibility,
                    "evidence_status": evidence_status,
                    "substitution_match": (
                        "exact"
                        if searched_category == request.category
                        else "same_use"
                    ),
                    "substitution_reason": (
                        "与当前商品属于同一类别"
                        if searched_category == request.category
                        else _same_use_reason(request.category, searched_category)
                    ),
                }
            )
            if len(candidates) >= request.limit:
                break
        if len(candidates) >= request.limit:
            break
    evidence_requirements = [
        "required_fields_for_hard_constraints",
        "current_for_applicable_date",
        "content_hash_verified",
        "health_comparison_fields_rank_but_do_not_block",
    ]
    providers = list(dict.fromkeys(result.provider for _, result in catalog_results))
    if "china_official_sources" in providers:
        evidence_requirements.extend(
            [
                "official_source_manually_verified",
                "mainland_accessible_chinese_source",
            ]
        )
    catalog_coverage = {
        **summarize_label_coverage(category_records),
        **summarize_context_eligibility(
            category_records,
            constraints=request.constraints,
            health_concerns=request.health_concerns,
        ),
    }
    if equivalent_package_variants_collapsed:
        catalog_coverage["equivalent_package_variants_collapsed"] = (
            equivalent_package_variants_collapsed
        )
    return {
        "status": "candidates_found" if candidates else "unknown",
        "category": request.category,
        "region": request.region,
        "candidates": candidates,
        "rejected": rejected,
        "unknowns": [] if candidates else ["no_current_complete_candidate_labels"],
        "catalog_scope": providers[0] if len(providers) == 1 else "mixed_sources",
        "catalog_status": (
            "degraded"
            if any(result.status != "ok" for _, result in catalog_results)
            else "ok"
        ),
        "catalog_warnings": list(
            dict.fromkeys(
                warning
                for _, result in catalog_results
                for warning in result.warnings
            )
        ),
        "catalog_coverage": catalog_coverage,
        "selection_basis": {
            "source": providers[0] if len(providers) == 1 else "mixed_sources",
            "category_match": (
                "exact" if len(requested_categories) == 1 else "same_use_scope"
            ),
            "source_category": request.category,
            "searched_categories": requested_categories,
            "region_match": "exact",
            "evidence_requirements": evidence_requirements,
            "constraint_evaluation": "independent_revalidation_required",
            "health_concerns": request.health_concerns,
            "health_data_policy": "ranking_only_unless_explicit_limit",
        },
    }


def _same_use_candidate(
    source_category: str,
    candidate_category: str,
    product: ProductRecord,
    *,
    current_product_name: str | None,
) -> bool:
    if (source_category, candidate_category) not in _ALLOWED_SAME_USE_PAIRS:
        return False
    if (source_category, candidate_category) == ("dairy", "drink"):
        return _substitution_role("drink", product.display_name) == "plant_drink"
    if (source_category, candidate_category) == ("drink", "dairy"):
        current_role = _substitution_role("drink", current_product_name or "")
        if current_role not in {"plant_drink", "milk_drink"}:
            return False
    signals = _SAME_USE_SIGNALS.get((source_category, candidate_category))
    if not signals:
        return True
    text = (
        f"{product.display_name} {product.use_case} "
        f"{product.label.ingredients_text}"
    ).lower()
    return any(signal.lower() in text for signal in signals)


def _substitution_role(category: str, text: str) -> str | None:
    normalized = text.lower()
    for role, signals in _CATEGORY_ROLE_SIGNALS.get(category, ()):
        if any(signal.lower() in normalized for signal in signals):
            return role
    return None


def _same_use_reason(source_category: str, candidate_category: str) -> str:
    return _SAME_USE_REASONS.get(
        (source_category, candidate_category),
        "属于相近食用场景，作为同用途备选",
    )


def revalidate_alternatives(request: AlternativeRevalidationRequest) -> dict[str, Any]:
    """Run the complete deterministic safety rules independently for every candidate."""

    results: list[dict[str, Any]] = []
    for index, product in enumerate(request.candidates, start=1):
        label = product.label
        eligibility = assess_product_eligibility(
            product,
            constraints=request.constraints,
            health_concerns=request.health_concerns,
        )
        evidence_status = _evidence_status(
            product,
            request.applicable_date,
            eligibility=eligibility,
        )
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
        rule_risk_level = (
            evaluation.overall_risk_level if request.constraints else "compatible"
        )
        eligible = (
            eligibility["eligible_for_current_context"]
            and rule_risk_level == "compatible"
        )
        results.append(
            {
                "product_id": product.product_id,
                "display_name": product.display_name,
                "brand": product.brand,
                "category": product.category,
                "use_case": product.use_case,
                "catalog_scope": product.catalog_scope,
                "catalog_tier": eligibility["status"],
                "substitution_match": product.substitution_match or (
                    "exact"
                    if not request.source_category
                    or product.category == request.source_category
                    else "same_use"
                ),
                "substitution_reason": product.substitution_reason or (
                    "与当前商品属于同一类别"
                    if not request.source_category
                    or product.category == request.source_category
                    else "属于相近食用场景，作为同用途备选"
                ),
                "catalog_eligibility": eligibility,
                "evidence_status": evidence_status,
                "disposition": "eligible" if eligible else "excluded",
                "risk_level": rule_risk_level,
                "reason_code": (
                    "INDEPENDENT_REVALIDATION_PASSED"
                    if eligible
                    else (
                        "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
                        if not eligibility["eligible_for_current_context"]
                        else "INDEPENDENT_REVALIDATION_FAILED"
                    )
                ),
                "explanation": (
                    "安全判断所需字段已经核对，且未发现所选硬性约束冲突；健康关注数据仅用于排序，这不是绝对安全保证。"
                    if eligible
                    else (
                        "当前关注项所需包装字段尚未齐全，因此不进入推荐。"
                        if not eligibility["eligible_for_current_context"]
                        else "该候选重新运行完整约束规则后未通过硬过滤。"
                    )
                ),
                "revalidated": True,
                "label_confirmed_at": label.confirmed_at.isoformat(),
                "label_source_url": label.source_url,
                "label_source_provider": label.source_provider,
                "label_source_type": label.source_type,
                "label_source_verified_at": (
                    label.source_verified_at.isoformat()
                    if label.source_verified_at
                    else None
                ),
                "label_source_authority": label.source_authority,
                "label_source_record_version": label.source_record_version,
                "ingredients_image_url": label.ingredients_image_url,
                "nutrition_image_url": label.nutrition_image_url,
                "official_store_url": label.official_store_url,
                "official_store_name": label.official_store_name,
                "official_store_verified_at": (
                    label.official_store_verified_at.isoformat()
                    if label.official_store_verified_at
                    else None
                ),
                "packaging_label": {
                    "ingredients_text": label.ingredients_text,
                    "allergen_statement": label.allergen_statement,
                    "nutrition_basis_text": label.nutrition_basis_text,
                    "nutrition_rows": label.nutrition_rows or [],
                    "evidence_quality": label.evidence_quality,
                    "evidence_id": label.evidence_id,
                    "record_version": label.source_record_version,
                    "confirmed_at": label.confirmed_at.isoformat(),
                    "source_verified_at": (
                        label.source_verified_at.isoformat()
                        if label.source_verified_at
                        else None
                    ),
                    "valid_through": (
                        label.valid_through.isoformat()
                        if label.valid_through
                        else None
                    ),
                },
                "evidence_ids": [label.evidence_id],
                "normalized_label": evaluation.normalized_label,
                "findings": evaluation.findings,
            }
        )
    eligible_results = [item for item in results if item["disposition"] == "eligible"]
    ranked = _rank_eligible_results(
        eligible_results,
        health_concerns=request.health_concerns,
        current_nutrition_rows=request.current_nutrition_rows,
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
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
        "ranking_method": {
            "layers": [
                "same_category_use",
                "allergen_and_constraint_safety",
                "health_concern_nutrition",
                "purchase_and_portion_usability",
            ],
            "health_concerns": request.health_concerns,
            "current_product_comparison": bool(request.current_nutrition_rows),
        },
    }


def _rank_eligible_results(
    products: list[dict[str, Any]],
    *,
    health_concerns: list[str],
    current_nutrition_rows: list[list[str]] | None,
) -> list[dict[str, Any]]:
    focuses = _ranking_focuses(health_concerns)
    current_values = _normalized_nutrient_values_from_rows(current_nutrition_rows)
    product_values = {
        item["product_id"]: _normalized_nutrient_values(
            item.get("normalized_label", {}).get("nutrition")
        )
        for item in products
    }
    points = {item["product_id"]: 0 for item in products}
    comparable_counts = {item["product_id"]: 0 for item in products}
    for nutrient, direction in focuses:
        available = [
            (item["product_id"], product_values[item["product_id"]].get(nutrient))
            for item in products
        ]
        available = [(product_id, value) for product_id, value in available if value]
        available.sort(key=lambda pair: pair[1][0], reverse=direction == "higher")
        distinct_values = list(dict.fromkeys(value[0] for _, value in available))
        value_points = {
            value: len(distinct_values) - position
            for position, value in enumerate(distinct_values)
        }
        for product_id, value in available:
            points[product_id] += value_points[value[0]]
            comparable_counts[product_id] += 1

    for item in products:
        product_id = item["product_id"]
        values = product_values[product_id]
        health_reasons: list[str] = []
        health_comparisons: list[dict[str, Any]] = []
        for nutrient, direction in focuses:
            candidate = values.get(nutrient)
            if not candidate:
                continue
            current = current_values.get(nutrient)
            label = _NUTRIENT_DISPLAY_NAMES.get(nutrient, nutrient)
            if current and candidate[1:] == current[1:]:
                difference = candidate[0] - current[0]
                improved = difference < 0 if direction == "lower" else difference > 0
                outcome = "improved" if improved else (
                    "same" if difference == 0 else "not_improved"
                )
                health_comparisons.append(
                    {
                        "nutrient": nutrient,
                        "label": label,
                        "candidate_value": candidate[0],
                        "current_value": current[0],
                        "unit": candidate[1],
                        "basis": candidate[2],
                        "direction": direction,
                        "outcome": outcome,
                    }
                )
                if improved:
                    verb = "更低" if direction == "lower" else "更高"
                    health_reasons.append(
                        "与当前商品同口径比较，"
                        f"{label}{_format_measure(candidate[0], candidate[1])}，"
                        f"{verb}于当前的{_format_measure(current[0], current[1])}"
                    )
                elif difference == 0:
                    health_reasons.append(
                        f"{label}{_format_measure(candidate[0], candidate[1])}，"
                        "与当前商品同口径相当"
                    )
            elif len(products) > 1:
                preference = "越低越优先" if direction == "lower" else "越高越优先"
                health_reasons.append(f"按{label}{preference}排序")

        nutrition = item.get("normalized_label", {}).get("nutrition") or {}
        basis = nutrition.get("basis") or {}
        portion_ready = basis.get("type") == "per_serving" and basis.get("unit") in {
            "g",
            "ml",
        }
        store_ready = bool(item.get("official_store_url"))
        experience_score = int(store_ready) + int(portion_ready)
        exact_match = item.get("substitution_match") != "same_use"
        ranking_reasons = [
            "与当前商品同类别" if exact_match else "相近食用场景的同用途备选",
            "已通过过敏原与个人约束复核",
        ]
        ranking_reasons.extend(health_reasons[:2])
        if portion_ready:
            ranking_reasons.append("包装提供可用的每份口径")
        if store_ready:
            ranking_reasons.append("可前往中国大陆官方旗舰店核对")
        item["ranking_reasons"] = ranking_reasons
        item["health_comparisons"] = health_comparisons
        item["ranking_summary"] = (
            "；".join(ranking_reasons[2:4])
            if len(ranking_reasons) > 2
            else "同类且通过了当前个人约束复核"
        )
        item["ranking_layers"] = {
            "same_category_use": exact_match,
            "same_use_fallback": not exact_match,
            "constraint_safety": True,
            "health_focus_points": points[product_id],
            "health_metrics_compared": comparable_counts[product_id],
            "official_store_available": store_ready,
            "portion_basis_available": portion_ready,
        }
        item["_ranking_key"] = (
            -int(exact_match),
            -points[product_id],
            -comparable_counts[product_id],
            -_catalog_tier_score(item["catalog_tier"]),
            -experience_score,
            -_authority_score(item["label_source_authority"]),
            -date.fromisoformat(item["label_confirmed_at"]).toordinal(),
            product_id,
        )
    ranked = sorted(products, key=lambda item: item["_ranking_key"])
    for item in ranked:
        item.pop("_ranking_key", None)
    return ranked


def _ranking_focuses(health_concerns: list[str]) -> list[tuple[str, str]]:
    focuses: list[tuple[str, str]] = []
    for concern in health_concerns:
        for focus in _HEALTH_RANKING_FOCUS.get(concern, ()):
            if focus not in focuses:
                focuses.append(focus)
    return focuses


def _product_family_key(value: str | None) -> str:
    """Collapse pack counts while preserving flavour and formula distinctions."""

    text = str(value or "").lower()
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:条|只|袋|盒|支|瓶)装", "", text)
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:克|g|毫升|ml)", "", text)
    return re.sub(r"[\s\-_·・,，/]+", "", text).strip()


def _normalized_nutrient_values_from_rows(
    rows: list[list[str]] | None,
) -> dict[str, tuple[float, str, str]]:
    if not rows:
        return {}
    normalized = normalize_nutrition_facts(None, rows=rows)
    return _normalized_nutrient_values(normalized.to_dict() if normalized else None)


def _normalized_nutrient_values(
    nutrition: dict[str, Any] | None,
) -> dict[str, tuple[float, str, str]]:
    if not nutrition or not nutrition.get("basis"):
        return {}
    basis = nutrition["basis"]
    basis_type = basis.get("type")
    basis_amount = float(basis.get("amount") or 0)
    basis_unit = str(basis.get("unit") or "")
    if basis_type in {"per_100g", "per_100ml"}:
        factor = 1.0
        comparison_basis = basis_type
    elif basis_type == "per_serving" and basis_amount > 0 and basis_unit in {"g", "ml"}:
        factor = 100.0 / basis_amount
        comparison_basis = f"per_100{basis_unit}"
    else:
        return {}
    return {
        str(item["canonical_name"]): (
            float(item["value"]) * factor,
            str(item["unit"]),
            comparison_basis,
        )
        for item in nutrition.get("nutrients", [])
        if item.get("canonical_name") and item.get("value") is not None
    }


def _format_measure(value: float, unit: str) -> str:
    return f"{value:g}{unit}"


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


def _evidence_rejection(
    product: ProductRecord,
    applicable_date,
    *,
    eligibility: dict[str, Any],
) -> str | None:
    label = product.label
    if not eligibility["eligible_for_current_context"]:
        return "LABEL_FIELDS_INSUFFICIENT_FOR_CONTEXT"
    if label.content_hash != label_content_hash(product):
        return "LABEL_EVIDENCE_HASH_MISMATCH"
    if label.valid_through and applicable_date > label.valid_through:
        return "LABEL_EVIDENCE_EXPIRED"
    if applicable_date < label.confirmed_at:
        return "LABEL_EVIDENCE_FROM_FUTURE"
    if applicable_date - label.confirmed_at > MAX_LABEL_AGE:
        return "LABEL_EVIDENCE_STALE"
    return None


def _evidence_status(
    product: ProductRecord,
    applicable_date: date,
    *,
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    """Expose one consumer-readable evidence state without weakening release gates."""

    label = product.label
    source_date = label.source_verified_at or label.confirmed_at
    if label.valid_through and applicable_date > label.valid_through:
        status = "expired"
    elif applicable_date < label.confirmed_at:
        status = "review_required"
    elif applicable_date - source_date > MAX_LABEL_AGE:
        status = "stale"
    elif (
        label.content_hash != label_content_hash(product)
        or not eligibility["eligible_for_current_context"]
    ):
        status = "review_required"
    elif eligibility["status"] == "fully_verified":
        status = "complete"
    else:
        status = "partially_verified"
    return {
        "status": status,
        "label": {
            "complete": "证据完整",
            "partially_verified": "部分证据，本次所需字段已核对",
            "review_required": "需要补齐或复核",
            "stale": "可能已过期，需要复核",
            "expired": "已过有效期",
        }[status],
        "confirmed_at": label.confirmed_at.isoformat(),
        "source_verified_at": source_date.isoformat(),
        "valid_through": label.valid_through.isoformat() if label.valid_through else None,
        "record_version": label.source_record_version,
        "source_type": label.source_type,
        "source_authority": label.source_authority,
        "source_language": label.source_language,
        "source_access_region": label.source_access_region,
    }


def _authority_score(authority: str) -> int:
    return {"manufacturer": 3, "internal_review": 2, "community": 1}.get(authority, 0)


def _catalog_tier_score(tier: str) -> int:
    return {"fully_verified": 2, "conditionally_verified": 1}.get(tier, 0)


def _nutrient_values(
    products: Iterable[dict[str, Any]], nutrient_key: str
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for product in products:
        nutrition = product.get("normalized_label", {}).get("nutrition") or {}
        nutrients = nutrition.get("nutrients", [])
        nutrient = next(
            (item for item in nutrients if item.get("canonical_name") == nutrient_key),
            None,
        )
        if not nutrient:
            continue
        basis = nutrition.get("basis") or {}
        basis_type = basis.get("type") or nutrient.get("basis")
        basis_amount = float(basis.get("amount") or 0)
        basis_unit = str(basis.get("unit") or "")
        if basis_type in {"per_100g", "per_100ml"}:
            factor = 1.0
            comparison_basis = basis_type
        elif (
            basis_type == "per_serving"
            and basis_amount > 0
            and basis_unit in {"g", "ml"}
        ):
            factor = 100.0 / basis_amount
            comparison_basis = f"per_100{basis_unit}"
        else:
            continue
        values.append(
            {
                "product_id": product["product_id"],
                "display_name": product["display_name"],
                "value": float(nutrient["value"]) * factor,
                "unit": nutrient["unit"],
                "basis": comparison_basis,
                "evidence_id": nutrient["evidence_id"],
                "source_basis": basis_type,
            }
        )
    return values
