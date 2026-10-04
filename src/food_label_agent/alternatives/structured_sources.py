"""Read public manufacturer datasets into the existing unapproved discovery queue."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urljoin


def structured_candidates(source, fetch_text, timeout):
    from .discovery import _candidate_from_page, _OfficialPage

    raw = fetch_text(source["data_url"], timeout)
    digest = sha256(raw.encode()).hexdigest()
    records = []
    if source["adapter"] == "simplelove_public_json":
        groups = json.loads(raw)
        if not isinstance(groups, list) or not groups:
            raise ValueError("Unexpected official product schema")
        for group in groups:
            for p in group["list"]:
                records.append(
                    {
                        "name": p["name"],
                        "series": group["name"],
                        "reference": str(group["id"]) + "|" + p["name"],
                        "ingredients": p["ingredients"],
                        "rows": p["component"],
                        "basis": "每100克",
                        "image": p["img"],
                        "store_urls": [],
                        "url": source["discovery_urls"][0]
                        + "#series-"
                        + str(group["id"]),
                    }
                )
    elif source["adapter"] == "quaker_public_html":
        # Static literals only. Never execute remote JavaScript, and exclude commented rows.
        raw_active = "\n".join(
            line for line in raw.splitlines() if not line.lstrip().startswith("//")
        )
        series = re.search(
            r"seriesTitle\s*:\s*'"
            + re.escape(source["series"])
            + r"'\s*,\s*list\s*:\s*\[(.*?)\n\s*\]",
            raw_active,
            re.DOTALL,
        )
        if not series:
            raise ValueError("Official product series missing")
        for line in series.group(1).splitlines():
            pairs = dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", line))
            if not pairs.get("title") or not pairs.get("img"):
                continue
            name = pairs["title"]
            records.append(
                {
                    "name": name,
                    "series": source["series"],
                    "reference": source["series"] + "|" + name,
                    "ingredients": None,
                    "rows": [],
                    "basis": None,
                    "image": urljoin(source["data_url"], pairs["img"]),
                    "store_urls": [
                        pairs[k].strip()
                        for k in ("tmLink", "jdLink")
                        if pairs.get(k, "").strip()
                    ],
                    "url": source["discovery_urls"][0],
                }
            )
    else:
        raise ValueError("Unsupported structured source")
    if not records:
        raise ValueError("Empty structured source; preserve previous queue")
    candidates = []
    for p in records:
        spec = re.search(r"\((\d+(?:\.\d+)?(?:千克|克|毫升))\)", p["name"])
        name = p["name"]
        if source["brand"] not in name:
            name = source["brand"] + " " + name
        if p["name"] in {"袋装", "罐装", "便携装"}:
            name = source["brand"] + " " + p["series"] + " " + p["name"]
        identity = {
            "display_name": name,
            "specification": spec.group(1) if spec else None,
        }
        page = _OfficialPage(
            json_ld=[
                {"@type": "Product", "name": name, "ingredients": p["ingredients"]}
            ]
        )
        item = _candidate_from_page(
            source, p["url"], page, identity=identity, source_page_fingerprint=digest
        )
        item["candidate_id"] = (
            "official-structured:"
            + sha256((source["source_id"] + "|" + p["reference"]).encode()).hexdigest()[
                :20
            ]
        )
        item["series"] = p["series"]
        item["manufacturer_record_reference"] = p["reference"]
        item["barcode"] = None
        item["data_url"] = source["data_url"]
        item["display_image_url"] = p["image"]
        item["store_listing_urls"] = p["store_urls"]
        item["identity_evidence"]["identity_fields"] = ["display_name"] + (
            ["specification"] if spec else []
        )
        item["extracted_fields"]["nutrition_basis_text"] = p["basis"]
        item["extracted_fields"]["nutrition_rows"] = (
            ([["项目", p["basis"]]] + [[r["name"], r["value"]] for r in p["rows"]])
            if p["rows"]
            else []
        )
        missing = ["SKU/商品条码", "包装过敏原提示", "包装版本与完整标签复核"]
        if not spec:
            missing.append("净含量规格")
        if not p["ingredients"]:
            missing.append("完整配料表文字")
        core = {"能量", "蛋白质", "脂肪", "碳水化合物", "钠"}
        present = {r["name"] for r in p["rows"]}
        if core - present:
            missing.append("营养项目：" + "、".join(sorted(core - present)))
        if "糖" not in present:
            missing.append("糖含量未公开")
        flags = []
        if (
            "草莓" in p["name"]
            and "蓝莓" in (p["ingredients"] or "")
            and "草莓" not in p["ingredients"]
        ):
            flags.append("官网口味与配料不一致")
        if "嗜执" in (p["ingredients"] or ""):
            flags.append("官网菌种文字疑似错字")
        if "牛奶" in p["name"] and p["basis"] == "每100克":
            flags.append("液体每100克口径需核实")
        item["missing_fields"] = missing + flags
        item["source_quality_flags"] = flags
        item["review_status"] = "evidence_incomplete"
        item["recommendation_eligible"] = False
        # Include the full row so nutrition/identity changes invalidate prior review.
        item["source_fingerprint"] = (
            "sha256:"
            + sha256(
                json.dumps(p, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
        )
        if source["adapter"] == "simplelove_public_json":
            supplements_path = (
                Path(__file__).with_name("data") / "simplelove_identity_evidence.json"
            )
            supplements = (
                json.loads(supplements_path.read_text())
                if supplements_path.exists()
                else {}
            )
            proof = supplements.get(item["candidate_id"])
            if (
                proof
                and proof["source_fingerprint"] == item["source_fingerprint"]
                and proof["source_url"] == item["display_image_url"]
                and datetime.now(UTC).date().isoformat() <= proof["valid_through"]
            ):
                item["specification"] = proof["specification"]
                item["specification_evidence"] = proof
                item["missing_fields"] = [
                    m for m in item["missing_fields"] if m != "净含量规格"
                ]
                item["identity_evidence"]["identity_fields"].append("specification")
        candidates.append(item)
    return candidates
