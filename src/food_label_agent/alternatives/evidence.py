"""Versioned product evidence projection shared by retrieval and screening.

Source identity is kept intact: a name match never merges two SKUs. Projections
are rebuildable; discovery and reviewed packaging remain the source of truth.
"""

import json
from collections import Counter
from contextvars import ContextVar
from datetime import UTC, date, datetime
from hashlib import sha256

from food_label_agent.nutrition.normalization import normalize_nutrition_facts

from .field_evidence import observation, summarize_fields


def nutrition_facts(fields):
    parsed = normalize_nutrition_facts(
        None,
        basis_text=fields.get("nutrition_basis_text"),
        rows=fields.get("nutrition_rows"),
    )
    if not parsed or parsed.requires_confirmation:
        return {}
    counts = Counter(f.canonical_name for f in parsed.nutrients)
    return {
        f.canonical_name: f
        for f in parsed.nutrients
        if counts[f.canonical_name] == 1 and "菊粉" not in f.raw_name
    }


active_knowledge_store = ContextVar("active_product_knowledge_store", default=None)
active_official_items = ContextVar("active_official_items", default=None)
OFFICIAL_SOURCE_IDS = frozenset(
    {
        "simplelove-public-products",
        "classykiss-public-extract",
        "meiji-public-extract",
        "quaker-instant-oats",
        "quaker-snack-cereal",
    }
)


def source_flags(item, *, today=None):
    flags = list(item.get("source_quality_flags") or [])
    try:
        age = (
            (today or datetime.now(UTC).date())
            - date.fromisoformat(item.get("last_seen_at", "")[:10])
        ).days
        if not 0 <= age <= 35:
            flags.append("官网资料超过复查周期或日期异常")
    except (ValueError, TypeError):
        flags.append("官网资料日期缺失")
    if item.get("review_status") == "change_detected":
        flags.append("来源变化待核实")
    return flags


def official_evidence(item):
    fields = item.get("extracted_fields") or {}
    version = (
        item.get("source_fingerprint")
        or sha256(
            json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )
    source = {
        "source_url": item.get("source_url"),
        "version": version,
        "tier": "official_unverified",
        "observed_at": item.get("last_seen_at"),
    }
    observations = []
    for field, key in (
        ("ingredients", "ingredients_text"),
        ("allergen_statement", "allergen_statement"),
    ):
        if fields.get(key):
            observations.append(
                observation(field, fields[key], span=fields[key], **source)
            )
    for field, fact in nutrition_facts(fields).items():
        observations.append(
            observation(
                field,
                fact.value,
                unit=fact.unit,
                basis=fact.basis,
                span=fact.source_span,
                **source,
            )
        )
    return {
        "schema_version": 1,
        "identity": {
            "product_id": item["candidate_id"],
            "source_id": item.get("source_id"),
            "sku": item.get("sku"),
            "barcode": item.get("barcode"),
            "specification": item.get("specification"),
            "region": item.get("region"),
            "category": item.get("category"),
            "identity_verified": False,
        },
        "provenance": {
            "source_url": item.get("source_url"),
            "source_version": version,
            "observed_at": item.get("last_seen_at"),
            "verified_at": None,
        },
        "tier": "official_unverified",
        "review_status": item.get("review_status"),
        "quality_flags": source_flags(item),
        "fields": summarize_fields(observations),
        "recommendation_eligible": False,
    }


def sync_official_evidence(store, items):
    """Replace the complete projection atomically; removed/rejected rows vanish."""
    payloads = [
        (i["candidate_id"], json.dumps(i, ensure_ascii=False))
        for i in items
        if i.get("source_id") in OFFICIAL_SOURCE_IDS
        and i.get("review_status") not in {"rejected", "approved"}
    ]
    with store.connect() as db:
        db.execute("DELETE FROM official_evidence")
        db.executemany("INSERT INTO official_evidence VALUES (?,?)", payloads)
    return {"status": "synchronized", "count": len(payloads)}
