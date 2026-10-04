"""Import dated, explicitly sourced public-page extracts without renewing their age."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from urllib.parse import urlparse

from .discovery import _candidate_from_page, _OfficialPage

ALLOWED_SOURCES = {
    "classykiss-public-extract": ("卡士", "www.classykiss.cn"),
    "meiji-public-extract": ("明治", "www.meiji.com.cn"),
}


def candidates_from_extract(payload):
    captured = datetime.fromisoformat(payload["captured_at"])
    if captured.tzinfo is None:
        raise ValueError("Capture timestamp must be timezone aware")
    output = []
    for record in payload["products"]:
        brand, host = ALLOWED_SOURCES[record["source_id"]]
        url = urlparse(record["source_url"])
        if record["brand"] != brand or url.scheme != "https" or url.hostname != host:
            raise ValueError("Public extract source mismatch")
        source = {"source_id": record["source_id"], "brand": brand, "category": "dairy"}
        fingerprint = sha256(
            json.dumps(record, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        page = _OfficialPage(
            json_ld=[
                {
                    "@type": "Product",
                    "name": record["name"],
                    "ingredients": record["ingredients"],
                }
            ]
        )
        item = _candidate_from_page(
            source,
            record["source_url"],
            page,
            identity={
                "display_name": record["name"],
                "specification": record["specification"],
            },
            source_page_fingerprint=fingerprint,
        )
        reference = (
            record["source_id"]
            + "|"
            + record["name"]
            + "|"
            + str(record["specification"] or "")
        )
        item.update(
            candidate_id="official-public:"
            + sha256(reference.encode()).hexdigest()[:20],
            source_fingerprint="sha256:" + fingerprint,
            barcode=None,
            sku=None,
            product_type=record["product_type"],
            first_discovered_at=captured.isoformat(),
            last_seen_at=captured.isoformat(),
            source_quality_flags=[],
            acquisition={
                "method": payload["capture_method"],
                "source_section": record["source_section"],
                "captured_at": captured.isoformat(),
                "refresh_mode": "manual_recheck_required",
                "package_verified": False,
            },
            recommendation_eligible=False,
            review_status="evidence_incomplete",
        )
        item["extracted_fields"] = {
            "ingredients_text": record["ingredients"],
            "allergen_statement": None,
            "nutrition_basis_text": "每100克" if record["nutrition_rows"] else None,
            "nutrition_rows": record["nutrition_rows"],
        }
        item["missing_fields"] = [
            "SKU/商品条码",
            "包装过敏原提示",
            "包装版本与完整标签复核",
            "糖含量未公开",
        ]
        if not record["specification"]:
            item["missing_fields"].append("净含量规格")
        if not record["ingredients"]:
            item["missing_fields"].append("完整配料表文字")
        if not record["nutrition_rows"]:
            item["missing_fields"].append("营养表")
        output.append(item)
    if len({x["candidate_id"] for x in output}) != len(output):
        raise ValueError("Duplicate public extract identity")
    return output
