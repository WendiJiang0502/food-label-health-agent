"""Discover official mainland product pages without promoting unreviewed labels."""

from __future__ import annotations

import hmac
import json
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .evidence_audit import audit_product_label, label_content_hash
from .models import ProductRecord
from .packaging_evidence import PackagingEvidenceStore

SOURCE_REGISTRY_PATH = Path(__file__).with_name("data") / "official_cn_sources.json"
_CORE_NUTRIENTS = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠")
_NUTRITION_KEYS = {
    "calories": "能量",
    "energy": "能量",
    "proteinContent": "蛋白质",
    "fatContent": "脂肪",
    "carbohydrateContent": "碳水化合物",
    "sodiumContent": "钠",
}
_GENERIC_PAGE_NAMES = (
    "产品中心",
    "主推产品",
    "原料",
    "送礼佳品",
    "跨界联名",
    "休闲零食",
    "主食杂粮",
)


def default_discovery_queue_path() -> Path:
    configured = os.getenv("FOOD_LABEL_DATA_DIR")
    base = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "share" / "food-label-health-agent"
    )
    return base / "official-product-discovery.json"


def default_approved_catalog_path() -> Path:
    return default_discovery_queue_path().with_name("official-reviewed-products.json")


def default_packaging_evidence_path() -> Path:
    return default_discovery_queue_path().with_name("packaging-evidence")


@dataclass(frozen=True, slots=True)
class DiscoveryRefreshResult:
    status: str
    summary: dict[str, Any]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "warnings": list(self.warnings),
        }


class OfficialProductDiscovery:
    """Crawl allowlisted official pages into a durable, non-recommendable queue."""

    def __init__(
        self,
        *,
        registry_path: str | Path = SOURCE_REGISTRY_PATH,
        queue_path: str | Path | None = None,
        approved_path: str | Path | None = None,
        packaging_store: PackagingEvidenceStore | None = None,
        fetch_text: Callable[[str, float], str] | None = None,
        timeout_seconds: float = 5.0,
        max_detail_pages: int = 24,
    ) -> None:
        self.registry_path = Path(registry_path)
        self.queue_path = Path(queue_path) if queue_path else default_discovery_queue_path()
        self.approved_path = (
            Path(approved_path) if approved_path else default_approved_catalog_path()
        )
        self.packaging_store = packaging_store or PackagingEvidenceStore(
            default_packaging_evidence_path()
        )
        self.fetch_text = fetch_text or _fetch_text
        self.timeout_seconds = timeout_seconds
        self.max_detail_pages = max_detail_pages

    def refresh(self, *, category: str | None = None) -> DiscoveryRefreshResult:
        sources = self._sources(category)
        if not sources:
            return DiscoveryRefreshResult(
                status="unsupported_category",
                summary=self.status(category=category),
                warnings=("no_official_source_configured_for_category",),
            )
        candidates: list[dict[str, Any]] = []
        warnings: list[str] = []
        refreshed_sources: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(4, len(sources))) as executor:
            futures = {executor.submit(self._discover_source, source): source for source in sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    candidates.extend(future.result())
                    refreshed_sources.append(source)
                except (OSError, TimeoutError, ValueError):
                    warnings.append(f"source_unavailable:{source['source_id']}")
        self._merge_queue(
            candidates,
            {str(source["source_id"]) for source in refreshed_sources},
            {str(source["category"]) for source in refreshed_sources},
        )
        summary = self.status(category=category)
        status = "completed" if not warnings else "partial"
        if warnings and len(warnings) == len(sources):
            status = "unavailable"
        return DiscoveryRefreshResult(status=status, summary=summary, warnings=tuple(warnings))

    def status(self, *, category: str | None = None) -> dict[str, Any]:
        items = self._read_json_list(self.queue_path)
        if category:
            items = [item for item in items if item.get("category") == category]
        sources = self._sources(category)
        source_brands = sorted(
            {str(source.get("brand") or "").strip() for source in sources}
            - {""}
        )
        review_target_fields = sorted(
            {
                str(field).strip()
                for source in sources
                for field in source.get("review_target_fields", [])
                if str(field).strip()
            }
        )
        priority_reasons = []
        if len(source_brands) < 2:
            priority_reasons.append("add_second_brand_official_source")
        if review_target_fields:
            priority_reasons.append("complete_target_comparison_fields")
        priority_reasons.append("capture_packaging_label_snapshot")
        items = [
            {
                **item,
                "priority_reasons": list(dict.fromkeys([
                    *priority_reasons,
                    *(item.get("priority_reasons") or []),
                ])),
            }
            for item in items
        ]
        counts = {
            "discovered_count": len(items),
            "needs_label_count": sum(
                item.get("review_status") == "evidence_incomplete" for item in items
            ),
            "ready_for_review_count": sum(
                item.get("review_status") == "ready_for_human_review" for item in items
            ),
            "approved_count": sum(item.get("review_status") == "approved" for item in items),
            "change_detected_count": sum(
                item.get("review_status") == "change_detected" for item in items
            ),
            "rejected_count": sum(item.get("review_status") == "rejected" for item in items),
        }
        return {
            **counts,
            "source_coverage": {
                "official_source_count": len(sources),
                "distinct_brand_count": len(source_brands),
                "brands": source_brands,
                "review_target_fields": review_target_fields,
                "priority_reasons": priority_reasons,
            },
            "last_refreshed_at": max(
                (str(item.get("last_seen_at") or "") for item in items), default=None
            )
            or None,
            "items": sorted(
                items,
                key=lambda item: (
                    {
                        "change_detected": 0,
                        "ready_for_human_review": 1,
                        "evidence_incomplete": 2,
                    }.get(
                        str(item.get("review_status")), 2
                    ),
                    str(item.get("display_name")),
                ),
            ),
        }

    def review(
        self,
        *,
        candidate_id: str,
        decision: str,
        review_token: str,
        product: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        expected = os.getenv("FOOD_LABEL_CATALOG_REVIEW_TOKEN", "")
        if not expected or not hmac.compare_digest(review_token, expected):
            raise PermissionError("Catalog review token is invalid")
        items = self._read_json_list(self.queue_path)
        candidate = next((item for item in items if item.get("candidate_id") == candidate_id), None)
        if candidate is None:
            raise KeyError(candidate_id)
        if decision == "reject":
            candidate["review_status"] = "rejected"
            candidate["reviewed_at"] = _now_iso()
            self._write_json_list(self.queue_path, items)
            return candidate
        if decision != "approve" or product is None:
            raise ValueError("批准时必须提供完整商品记录")
        record = ProductRecord.model_validate(product)
        if (
            record.label.source_url != candidate["source_url"]
            or record.label.source_type != candidate["source_type"]
        ):
            raise ValueError("审核记录必须沿用已发现的官方来源")
        audit = audit_product_label(record)
        label = record.label
        if (
            not audit["full_label_ready"]
            or not audit["complete_packaging_snapshot_ready"]
            or not record.sku
            or not record.specification
            or label.evidence_quality != "complete"
            or record.catalog_scope != "official_cn_catalog"
            or label.source_authority != "manufacturer"
            or label.source_access_region != "CN"
            or label.source_verified_at is None
            or label.content_hash != label_content_hash(record)
            or not all(
                self.packaging_store.verify_artifact(snapshot)
                for snapshot in label.packaging_snapshots
                if snapshot.review_status == "verified"
                and snapshot.artifact_type == "packaging_photo"
            )
        ):
            raise ValueError(
                "核心包装字段、SKU/规格或双人复核实物背标尚未补齐，不能进入推荐目录"
            )
        approved = self._read_json_list(self.approved_path)
        approved = [item for item in approved if item.get("product_id") != record.product_id]
        approved.append(record.model_dump(mode="json"))
        self._write_json_list(self.approved_path, approved)
        candidate["review_status"] = "approved"
        candidate["recommendation_eligible"] = True
        candidate["approved_product_id"] = record.product_id
        candidate["reviewed_at"] = _now_iso()
        self._write_json_list(self.queue_path, items)
        return candidate

    def _sources(self, category: str | None) -> list[dict[str, Any]]:
        sources = self._read_json_list(self.registry_path)
        return [source for source in sources if not category or source.get("category") == category]

    def _discover_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        allowed_hosts = {str(host).lower() for host in source["allowed_hosts"]}
        markers = tuple(str(value).lower() for value in source["product_path_markers"])
        pages: dict[str, _OfficialPage] = {}
        product_seed_urls = set(source.get("product_seed_urls", []))
        pending = [
            *((url, 0) for url in source["discovery_urls"]),
            *((url, 0) for url in product_seed_urls),
        ]
        seen: set[str] = set()
        while pending and len(pages) < self.max_detail_pages + len(source["discovery_urls"]):
            current_url, depth = pending.pop(0)
            if current_url in seen:
                continue
            seen.add(current_url)
            try:
                page = _parse_page(self.fetch_text(current_url, self.timeout_seconds))
            except (OSError, TimeoutError, ValueError):
                if depth == 0:
                    raise
                continue
            pages[current_url] = page
            if depth >= 2:
                continue
            for href in page.links:
                url = urljoin(current_url, href).split("#", 1)[0]
                parsed = urlparse(url)
                if (
                    parsed.scheme == "https"
                    and (parsed.hostname or "").lower() in allowed_hosts
                    and any(marker in parsed.path.lower() for marker in markers)
                    and url not in seen
                ):
                    pending.append((url, depth + 1))
        discovery_urls = set(source["discovery_urls"])
        candidates = []
        for url, page in pages.items():
            if (
                url in discovery_urls
                and next(_walk_products(page.json_ld or []), None) is None
            ):
                continue
            candidate = _candidate_from_page(
                source, url, page, allow_title=url in product_seed_urls
            )
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _merge_queue(
        self,
        discovered: list[dict[str, Any]],
        refreshed_source_ids: set[str],
        refreshed_categories: set[str],
    ) -> None:
        previous = {
            str(item.get("candidate_id")): item
            for item in self._read_json_list(self.queue_path)
            if (
                item.get("source_id") not in refreshed_source_ids
                and not (
                    not item.get("source_id")
                    and item.get("category") in refreshed_categories
                )
            )
            or item.get("review_status") in {"approved", "rejected"}
        }
        invalidated_product_ids: set[str] = set()
        for candidate in discovered:
            old = previous.get(candidate["candidate_id"], {})
            candidate["first_discovered_at"] = old.get(
                "first_discovered_at", candidate["first_discovered_at"]
            )
            source_changed = bool(
                old.get("source_fingerprint")
                and old.get("source_fingerprint") != candidate["source_fingerprint"]
            )
            if old.get("review_status") == "approved" and source_changed:
                candidate["review_status"] = "change_detected"
                candidate["recommendation_eligible"] = False
                candidate["approved_product_id"] = old.get("approved_product_id")
                if old.get("approved_product_id"):
                    invalidated_product_ids.add(str(old["approved_product_id"]))
            elif old.get("review_status") in {"approved", "rejected"}:
                candidate["review_status"] = old["review_status"]
                candidate["reviewed_at"] = old.get("reviewed_at")
                candidate["approved_product_id"] = old.get("approved_product_id")
                candidate["recommendation_eligible"] = old.get(
                    "recommendation_eligible", False
                )
            previous[candidate["candidate_id"]] = candidate
        self._write_json_list(self.queue_path, list(previous.values()))
        if invalidated_product_ids and self.approved_path.exists():
            approved = self._read_json_list(self.approved_path)
            approved = [
                item
                for item in approved
                if str(item.get("product_id")) not in invalidated_product_ids
            ]
            self._write_json_list(self.approved_path, approved)

    @staticmethod
    def _read_json_list(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise TypeError(f"Expected a JSON list in {path}")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _write_json_list(path: Path, payload: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)


@dataclass(slots=True)
class _OfficialPage:
    title: str = ""
    headings: list[str] | None = None
    text: str = ""
    links: list[str] | None = None
    metadata: dict[str, str] | None = None
    json_ld: list[dict[str, Any]] | None = None


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.metadata: dict[str, str] = {}
        self.json_ld_chunks: list[str] = []
        self._capture_title = False
        self._capture_heading = False
        self._capture_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        self._capture_title = tag == "title"
        self._capture_heading = tag in {"h1", "h2"}
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key and values.get("content"):
                self.metadata[key.lower()] = values["content"].strip()
        if (
            tag == "script"
            and (values.get("type") or "").lower() == "application/ld+json"
        ):
            self._capture_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._capture_title = False
        if tag in {"h1", "h2"}:
            self._capture_heading = False
        if tag == "script":
            self._capture_json_ld = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._capture_json_ld:
            self.json_ld_chunks.append(data)
            return
        self.text_parts.append(cleaned)
        if self._capture_title:
            self.title_parts.append(cleaned)
        if self._capture_heading:
            self.heading_parts.append(cleaned)


def _parse_page(html: str) -> _OfficialPage:
    parser = _PageParser()
    parser.feed(html)
    json_ld: list[dict[str, Any]] = []
    for chunk in parser.json_ld_chunks:
        try:
            payload = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        values = payload if isinstance(payload, list) else [payload]
        json_ld.extend(item for item in values if isinstance(item, dict))
    return _OfficialPage(
        title=" ".join(parser.title_parts),
        headings=parser.heading_parts,
        text=" ".join(parser.text_parts),
        links=parser.links,
        metadata=parser.metadata,
        json_ld=json_ld,
    )


def _candidate_from_page(
    source: dict[str, Any],
    url: str,
    page: _OfficialPage,
    *,
    allow_title: bool = False,
) -> dict[str, Any] | None:
    product = next(_walk_products(page.json_ld or []), None)
    product_name = _clean_value((product or {}).get("name"))
    heading = ((page.headings or [""])[0]).strip()
    name = str(
        product_name
        or heading
        or (page.metadata or {}).get("og:title")
        or page.title
    ).strip()
    specifically_identified = bool(
        product_name
        or heading
        or (allow_title and str(source["brand"]).lower() in name.lower())
    )
    if (
        not name
        or not specifically_identified
        or name == source["brand"]
        or any(marker in name for marker in _GENERIC_PAGE_NAMES)
    ):
        return None
    ingredients = _clean_value((product or {}).get("ingredients")) or _extract_labeled_text(
        page.text, ("配料表", "配料")
    )
    allergen = _extract_labeled_text(page.text, ("过敏原信息", "过敏原提示"))
    nutrition_rows, nutrition_basis = _extract_nutrition(product or {})
    sku = _clean_value((product or {}).get("sku"))
    specification = _clean_value((product or {}).get("size"))
    missing = []
    if not ingredients:
        missing.append("完整配料表文字")
    if not allergen:
        missing.append("包装过敏原提示")
    nutrient_names = {row[0] for row in nutrition_rows[1:]}
    absent = [name for name in _CORE_NUTRIENTS if name not in nutrient_names]
    if not nutrition_basis:
        missing.append("营养标示口径")
    if absent:
        missing.append(f"营养项目：{'、'.join(absent)}")
    if not sku:
        missing.append("SKU")
    if not specification:
        missing.append("规格")
    missing.extend(("双人复核实物包装配料图", "双人复核实物包装营养图"))
    complete = not missing
    now = _now_iso()
    extracted_fields = {
        "ingredients_text": ingredients,
        "allergen_statement": allergen,
        "nutrition_basis_text": nutrition_basis,
        "nutrition_rows": nutrition_rows,
    }
    source_fingerprint = sha256(
        json.dumps(
            {
                "name": name,
                "sku": sku,
                "specification": specification,
                **extracted_fields,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "candidate_id": f"official-discovery:{sha256(url.encode()).hexdigest()[:20]}",
        "source_id": source["source_id"],
        "display_name": name[:160],
        "brand": source["brand"],
        "category": source["category"],
        "region": "CN",
        "sku": sku,
        "specification": specification,
        "source_url": url,
        "source_type": source.get("source_type", "official_product_page"),
        "official_store_url": source.get("official_store_url"),
        "official_store_name": source.get("official_store_name"),
        "review_target_fields": source.get("review_target_fields", []),
        "extracted_fields": extracted_fields,
        "source_fingerprint": f"sha256:{source_fingerprint}",
        "missing_fields": missing,
        "review_status": (
            "ready_for_human_review" if complete else "evidence_incomplete"
        ),
        "recommendation_eligible": False,
        "capture_requirements": {
            "required_identity_fields": ["sku", "specification"],
            "required_physical_artifacts": [
                "ingredients_or_combined_packaging_photo",
                "nutrition_or_combined_packaging_photo",
            ],
            "minimum_distinct_reviewers": 2,
            "official_page_capture_is_sufficient": False,
            "content_hash_required": True,
        },
        "first_discovered_at": now,
        "last_seen_at": now,
    }


def _walk_products(values: list[dict[str, Any]]):
    for value in values:
        graph = value.get("@graph")
        if isinstance(graph, list):
            yield from _walk_products([item for item in graph if isinstance(item, dict)])
        item_type = value.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if "Product" in types:
            yield value


def _extract_labeled_text(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*[:：]\s*(.{{2,600}}?)(?=\s(?:营养成分|保质期|净含量|生产日期|{ '|'.join(map(re.escape, labels)) })\s*[:：]|$)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return " ".join(match.group(1).split())
    return None


def _extract_nutrition(product: dict[str, Any]) -> tuple[list[list[str]], str | None]:
    raw = product.get("nutrition")
    if not isinstance(raw, dict):
        return [], None
    basis = _clean_value(raw.get("servingSize"))
    rows = [["项目", basis or "官网标示口径"]]
    for raw_key, display in _NUTRITION_KEYS.items():
        value = _clean_value(raw.get(raw_key))
        if value and all(row[0] != display for row in rows):
            rows.append([display, value])
    return (rows if len(rows) > 1 else []), basis


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        cleaned = " ".join(str(value).split())
        return cleaned or None
    return None


def _fetch_text(url: str, timeout: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "LabelLensHealth/0.2 official-product-discovery",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read(2_000_000).decode(content_type, errors="replace")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
