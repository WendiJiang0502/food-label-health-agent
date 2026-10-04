"""Read-only domestic barcode pilot; never promotes supplier responses into catalog."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from food_label_agent.alternatives.batch import barcode_valid, normalized_specification

ENDPOINT = "https://route.showapi.com/66-22"


def prepare(db_path: Path, per_category=8):
    with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT id,category,payload,content_hash FROM candidates ORDER BY id"
        ).fetchall()
    groups = {}
    excluded = 0
    for row in rows:
        raw = json.loads(row["payload"])
        if not barcode_valid(row["id"]):
            excluded += 1
            continue
        baseline = {
            "name": raw.get("product_name_zh") or raw.get("product_name") or "",
            "brand": raw.get("brands") or "",
            "specification": raw.get("quantity") or "",
            "ingredients": raw.get("ingredients_text_zh")
            or raw.get("ingredients_text")
            or "",
            "sugars": (raw.get("nutriments") or {}).get("sugars_100g"),
        }
        gaps = [
            k
            for k in ("name", "brand", "specification")
            if not str(baseline[k]).strip()
        ]
        item = {
            "barcode": row["id"],
            "category": row["category"],
            "source_version": row["content_hash"],
            "baseline": baseline,
            "identity_gaps": gaps,
            "group": "identity_gap" if gaps else "identity_control",
            "source_url": f"https://world.openfoodfacts.org/product/{row['id']}",
        }
        groups.setdefault(row["category"], []).append(item)
    sample = []
    for category in sorted(groups):
        values = groups[category]
        gaps = [v for v in values if v["identity_gaps"]]
        controls = [v for v in values if not v["identity_gaps"]]
        chosen = gaps[: per_category - 2] + controls[:2]
        ids = {v["barcode"] for v in chosen}
        chosen += [v for v in values if v["barcode"] not in ids][
            : per_category - len(chosen)
        ]
        sample.extend(chosen)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "design": "up to 6 identity-gap + 2 identity-control per category; deterministic barcode order",
        "scope": "Existing China-tagged OFF candidates; not representative of mainland retail coverage. Barcode prefix is not country of manufacture.",
        "excluded_invalid_barcodes": excluded,
        "population_count": len(rows),
        "sample_count": len(sample),
        "items": sample,
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def query_showapi(code, key):
    request = Request(
        ENDPOINT + "?" + urlencode({"appKey": key}),
        data=urlencode({"code": code}).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "FoodLabelAgent-domestic-pilot/1.0",
        },
    )
    with build_opener(NoRedirect).open(request, timeout=20) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("Response too large")
    return json.loads(payload)


def assess(item, response):
    body = response.get("showapi_res_body") or {}
    if not isinstance(body, dict):
        return {"status": "malformed_response"}
    if str(response.get("showapi_res_code")) != "0":
        return {"status": "provider_error"}
    if str(body.get("ret_code")) != "0":
        return {"status": "not_found_or_rejected"}
    returned = str(body.get("code") or "").strip()
    if not barcode_valid(returned) or returned.zfill(14) != item["barcode"].zfill(14):
        return {"status": "barcode_mismatch"}

    def clean(value):
        text = str(value).strip()[:2000] if isinstance(value, (str, int, float)) else ""
        if any(
            token in text for token in ("未公开", "未披露", "暂无", "****")
        ) or text.lower() in {"null", "none", "unknown", "n/a", "-"}:
            return ""
        return text

    fields = {
        "name": clean(body.get("goodsName")),
        "brand": clean(body.get("trademark")),
        "specification": clean(body.get("spec")),
    }
    proposed = [k for k in item["identity_gaps"] if fields[k]]
    differences = []
    for key, value in fields.items():
        old = item["baseline"][key]
        if old and value:
            left, right = (
                (
                    normalized_specification(
                        re.sub(r"[()]", "", unicodedata.normalize("NFKC", old))
                    ),
                    normalized_specification(
                        re.sub(r"[()]", "", unicodedata.normalize("NFKC", value))
                    ),
                )
                if key == "specification"
                else (
                    "".join(old.split()).casefold(),
                    "".join(value.split()).casefold(),
                )
            )
            if left != right:
                differences.append(key)
    urls = []
    image_references = 0
    for key in ("img", "imgList"):
        value = body.get(key)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            image_references += sum(
                isinstance(v, str) and v.startswith(("http://", "https://"))
                for v in value
            )
            urls.extend(
                v for v in value if isinstance(v, str) and v.startswith("https://")
            )
    return {
        "status": "matched_barcode",
        "fields": fields,
        "proposed_identity_fills": proposed,
        "identity_differences": differences,
        "image_urls": list(dict.fromkeys(urls))[:10],
        "image_reference_count": image_references,
        "usable_identity_data": any(fields.values()),
        "ingredients_available": None,
        "nutrition_available": None,
        "label_note": "Public barcode contract does not guarantee ingredient/nutrition fields; generic images are not confirmed back labels.",
        "recommendation_eligible": False,
    }


def run_pilot(manifest, *, key=None, query=query_showapi, delay=1.0):
    rows = []
    if key:
        for i, item in enumerate(manifest["items"]):
            if i:
                time.sleep(delay)
            started = time.monotonic()
            try:
                result = assess(item, query(item["barcode"], key))
            except Exception as exc:  # noqa: BLE001 - never expose credential-bearing transport errors
                result = {"status": "request_error", "error_type": type(exc).__name__}
            rows.append(
                {
                    "barcode": item["barcode"],
                    "category": item["category"],
                    "group": item["group"],
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    **result,
                }
            )
            # Credentials and account failures should not consume the rest of a batch.
            if result["status"] == "provider_error":
                break
    matched = [r for r in rows if r["status"] == "matched_barcode"]
    return {
        "status": "awaiting_credentials"
        if not key
        else (
            "completed"
            if len(rows) == len(manifest["items"])
            else "stopped_on_provider_error"
        ),
        "provider": "showapi_66_22",
        "sample_count": len(manifest["items"]),
        "attempted": len(rows),
        "matched_barcode_count": len(matched),
        "usable_identity_count": sum(r["usable_identity_data"] for r in matched)
        if rows
        else None,
        "match_rate": len(matched) / len(rows) if rows else None,
        "products_with_proposed_identity_fills": sum(
            bool(r["proposed_identity_fills"]) for r in matched
        )
        if rows
        else None,
        "products_with_identity_differences": sum(
            bool(r["identity_differences"]) for r in matched
        )
        if rows
        else None,
        "verified_label_fill_count": 0 if rows else None,
        "new_recommendable_products": 0 if rows else None,
        "results": rows,
        "note": "Identity fills are proposals requiring SKU/variant review. No production database writes; images not fetched; no complete-label claim.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path.home()
        / ".local/share/food-label-health-agent/product-knowledge.sqlite3",
    )
    parser.add_argument(
        "--directory", type=Path, default=Path("artifacts/domestic-pilot")
    )
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    manifest_path = args.directory / "sample.json"
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else prepare(args.database)
    )
    if len(manifest["items"]) > 30:
        raise ValueError("Pilot is capped at 30 requests")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    key = os.getenv("FOOD_LABEL_SHOWAPI_APPKEY") if args.run else None
    report = run_pilot(manifest, key=key)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if key:
        output = output.replace(key, "[redacted]")
    (args.directory / "report.json").write_text(output + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "sample_count": manifest["sample_count"],
                "attempted": report["attempted"],
                "categories": dict(Counter(v["category"] for v in manifest["items"])),
                "groups": dict(Counter(v["group"] for v in manifest["items"])),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
