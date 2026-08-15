"""Product catalog adapters for reviewed and live product-label evidence."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .evidence_audit import audit_product_label, summarize_label_coverage
from .models import ProductRecord

DATA_PATH = Path(__file__).with_name("data") / "curated_products.json"
OFFICIAL_CN_DATA_PATH = Path(__file__).with_name("data") / "official_cn_products.json"
OFF_BASE_URL = "https://world.openfoodfacts.org"
OFFICIAL_PRODUCT_HOSTS = {
    "china.lkk.com.cn",
    "www.yili.com",
    "yili.com",
    "www.seamild.com.cn",
    "seamild.com.cn",
    "www.vvfood.cn",
    "vvfood.cn",
    "www.wolons.com",
    "wolons.com",
}
OFFICIAL_STORE_HOST_SUFFIXES = (".jd.com", ".tmall.com")
OFF_FIELDS = (
    "code,product_name,product_name_zh,brands,ingredients_text,ingredients_text_zh,"
    "allergens,traces,nutriments,nutrition_data_per,serving_size,selected_images,"
    "last_modified_t,states_tags,completeness,checked"
)
PRODUCT_CATEGORIES = {
    "biscuit": ("biscuits", "饼干与曲奇", "饼干与便携谷物零食"),
    "bread": ("breads", "面包与烘焙食品", "面包与烘焙主食"),
    "breakfast_cereal": (
        "breakfast-cereals",
        "早餐谷物与麦片",
        "冲调或直接食用的早餐谷物",
    ),
    "instant_noodles": ("instant-noodles", "方便面与即食面", "快速烹调的面制主食"),
    "drink": ("beverages", "饮品", "直接饮用的常温或冷藏饮品"),
    "dairy": ("dairy-products", "乳制品", "牛奶、酸奶与其他乳制品"),
    "snack": ("snacks", "膨化零食与脆片", "膨化或油炸的便携零食"),
    "confectionery": ("confectioneries", "糖果与巧克力", "糖果、巧克力与甜食"),
    "prepared_meal": ("meals", "方便食品与预制菜", "加热或简单处理后食用的成品餐食"),
    "frozen_food": ("frozen-foods", "速冻食品", "需冷冻保存的预包装食品"),
    "processed_meat": ("processed-meat", "肉制品", "香肠、火腿与其他肉制品"),
    "seafood": ("seafood", "水产制品", "鱼类、甲壳类与其他水产制品"),
    "sauce_condiment": ("condiments", "酱料与调味品", "烹调或佐餐用酱料与调味品"),
    "canned_food": ("canned-foods", "罐头食品", "密封容器中保存的常温食品"),
}
CATEGORY_TAGS = {key: value[0] for key, value in PRODUCT_CATEGORIES.items()}
CATEGORY_LABELS = {key: value[1] for key, value in PRODUCT_CATEGORIES.items()}
USE_CASES = {key: value[2] for key, value in PRODUCT_CATEGORIES.items()}
ALLERGEN_LABELS = {
    "milk": "乳",
    "gluten": "含麸质谷物",
    "eggs": "蛋",
    "egg": "蛋",
    "peanuts": "花生",
    "peanut": "花生",
    "soybeans": "大豆",
    "soy": "大豆",
    "nuts": "坚果",
    "fish": "鱼",
    "crustaceans": "甲壳类动物",
}


@dataclass(frozen=True, slots=True)
class CatalogSearchResult:
    records: tuple[ProductRecord, ...]
    rejected: tuple[dict[str, Any], ...] = ()
    provider: str = "curated_verification_catalog"
    status: str = "ok"
    warnings: tuple[str, ...] = ()


class CatalogUnavailable(RuntimeError):
    """Raised when a live catalog cannot return a trustworthy response."""


class ProductCatalog(Protocol):
    def search(self, *, category: str, region: str) -> CatalogSearchResult: ...


class JsonProductCatalog:
    """Read a small reviewed catalog; production adapters keep this boundary."""

    def __init__(self, path: str | Path = DATA_PATH) -> None:
        self.path = Path(path)

    def search(self, *, category: str, region: str) -> CatalogSearchResult:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = tuple(ProductRecord.model_validate(item) for item in payload)
        return CatalogSearchResult(
            records=tuple(
                item
                for item in records
                if item.category == category and item.region == region
            )
        )


class OfficialChinaCatalog:
    """Serve only manually verified mainland-accessible official sources."""

    def __init__(self, path: str | Path = OFFICIAL_CN_DATA_PATH) -> None:
        self.path = Path(path)

    def search(self, *, category: str, region: str) -> CatalogSearchResult:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = tuple(ProductRecord.model_validate(item) for item in payload)
        accepted: list[ProductRecord] = []
        rejected: list[dict[str, Any]] = []
        for item in records:
            if item.category != category or item.region != region:
                continue
            reason = _official_source_rejection(item)
            if reason:
                rejected.append(
                    {
                        "product_id": item.product_id,
                        "display_name": item.display_name,
                        "reason_code": reason,
                        "evidence_ids": [item.label.evidence_id],
                        "label_coverage": audit_product_label(item),
                    }
                )
                continue
            accepted.append(item)
        return CatalogSearchResult(
            records=tuple(accepted),
            rejected=tuple(rejected),
            provider="china_official_sources",
            status="ok",
            warnings=("official_sources_require_periodic_human_reverification",),
        )

    def coverage(self, *, category: str | None = None, region: str = "CN") -> dict[str, Any]:
        """Return a read-only review queue for every discovered official record."""

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = [ProductRecord.model_validate(item) for item in payload]
        selected = [
            product
            for product in records
            if product.region == region and (category is None or product.category == category)
        ]
        items = []
        for product in selected:
            audit = audit_product_label(product)
            items.append(
                {
                    "product_id": product.product_id,
                    "display_name": product.display_name,
                    "brand": product.brand,
                    "category": product.category,
                    "source_rejection": _official_source_rejection(product),
                    "label_coverage": audit,
                }
            )
        items.sort(
            key=lambda item: (
                {"high": 0, "medium": 1, "complete": 2}.get(
                    item["label_coverage"]["review_priority"], 3
                ),
                item["display_name"],
            )
        )
        return {**summarize_label_coverage(selected), "items": items}


class OpenFoodFactsCatalog:
    """Discover real products while retaining source and label-image evidence."""

    def __init__(
        self,
        *,
        base_url: str = OFF_BASE_URL,
        user_agent: str | None = None,
        timeout_seconds: float = 8.0,
        cache_ttl_seconds: int = 300,
        page_size: int = 20,
        fetch_json: Callable[[str, dict[str, str], float], dict[str, Any]]
        | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent or os.getenv(
            "FOOD_LABEL_OPENFOODFACTS_USER_AGENT",
            "LabelLensHealth/0.1 (local-development)",
        )
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.page_size = page_size
        self.fetch_json = fetch_json or _fetch_json
        self._cache: dict[tuple[str, str], tuple[float, CatalogSearchResult]] = {}

    def search(self, *, category: str, region: str) -> CatalogSearchResult:
        key = (category, region)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] <= self.cache_ttl_seconds:
            return cached[1]
        tag = CATEGORY_TAGS.get(category)
        if tag is None or region != "CN":
            return CatalogSearchResult(
                records=(),
                provider="open_food_facts",
                status="unsupported_query",
                warnings=("live_catalog_category_or_region_unsupported",),
            )
        query = urlencode(
            {
                "countries_tags_en": "china",
                "categories_tags_en": tag,
                "sort_by": "completeness",
                "page": 1,
                "page_size": self.page_size,
                "fields": OFF_FIELDS,
            }
        )
        url = f"{self.base_url}/api/v2/search?{query}"
        try:
            payload = self.fetch_json(
                url, {"User-Agent": self.user_agent}, self.timeout_seconds
            )
        except Exception as exc:
            raise CatalogUnavailable("Open Food Facts catalog unavailable") from exc
        records: list[ProductRecord] = []
        rejected: list[dict[str, Any]] = []
        details_needed: list[dict[str, Any]] = []
        for raw in payload.get("products", []):
            mapped, rejection = _map_open_food_facts_product(raw, category)
            if mapped is not None:
                records.append(mapped)
            elif raw.get("code"):
                details_needed.append(raw)
            elif rejection is not None:
                rejected.append(rejection)
        if details_needed:
            detailed_records, detail_rejections = self._fetch_details(
                details_needed, category
            )
            records.extend(detailed_records)
            rejected.extend(detail_rejections)
        result = CatalogSearchResult(
            records=tuple(records),
            rejected=tuple(rejected),
            provider="open_food_facts",
            status="ok",
            warnings=("community_catalog_requires_label_evidence_review",),
        )
        self._cache[key] = (time.monotonic(), result)
        return result

    def _fetch_details(
        self, search_records: list[dict[str, Any]], category: str
    ) -> tuple[list[ProductRecord], list[dict[str, Any]]]:
        records: list[ProductRecord] = []
        rejected: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(5, len(search_records))) as executor:
            futures = {
                executor.submit(self._fetch_detail, str(item["code"])): item
                for item in search_records
            }
            for future in as_completed(futures):
                search_record = futures[future]
                code = str(search_record["code"])
                try:
                    detail = future.result()
                except (CatalogUnavailable, OSError, TypeError, ValueError):
                    rejected.append(
                        {
                            "product_id": f"off:{code}",
                            "display_name": str(
                                search_record.get("product_name_zh")
                                or search_record.get("product_name")
                                or "Open Food Facts 未命名商品"
                            ),
                            "reason_code": "LIVE_CATALOG_RECORD_UNAVAILABLE",
                            "evidence_ids": [f"off.product.{code}.label"],
                        }
                    )
                    continue
                mapped, rejection = _map_open_food_facts_product(detail, category)
                if mapped is not None:
                    records.append(mapped)
                elif rejection is not None:
                    rejected.append(rejection)
        records.sort(key=lambda item: item.product_id)
        rejected.sort(key=lambda item: item["product_id"])
        return records, rejected

    def _fetch_detail(self, code: str) -> dict[str, Any]:
        query = urlencode({"fields": OFF_FIELDS})
        url = f"{self.base_url}/api/v2/product/{code}?{query}"
        payload = self.fetch_json(
            url, {"User-Agent": self.user_agent}, self.timeout_seconds
        )
        product = payload.get("product")
        if isinstance(product, dict):
            return product
        products = payload.get("products")
        if isinstance(products, list) and products and isinstance(products[0], dict):
            return products[0]
        raise CatalogUnavailable(f"Open Food Facts product {code} unavailable")


class HybridProductCatalog:
    """Prefer live discovery and fall back to deterministic reviewed fixtures."""

    def __init__(
        self,
        live: ProductCatalog | None = None,
        fallback: ProductCatalog | None = None,
    ) -> None:
        self.live = live or OpenFoodFactsCatalog()
        self.fallback = fallback or JsonProductCatalog()

    def search(self, *, category: str, region: str) -> CatalogSearchResult:
        try:
            live = self.live.search(category=category, region=region)
            if live.records:
                return live
            fallback = self.fallback.search(category=category, region=region)
            return CatalogSearchResult(
                records=fallback.records,
                rejected=live.rejected,
                provider="open_food_facts_with_curated_fallback",
                status="degraded",
                warnings=tuple(
                    dict.fromkeys(
                        [*live.warnings, "live_catalog_returned_no_eligible_records"]
                    )
                ),
            )
        except CatalogUnavailable:
            fallback = self.fallback.search(category=category, region=region)
            return CatalogSearchResult(
                records=fallback.records,
                provider="open_food_facts_with_curated_fallback",
                status="degraded",
                warnings=("live_catalog_unavailable_used_curated_fallback",),
            )


def configured_catalog(mode: str | None = None) -> ProductCatalog:
    selected = (mode or os.getenv("FOOD_LABEL_PRODUCT_CATALOG", "official_cn")).strip()
    return _catalog_for_mode(selected)


@lru_cache(maxsize=4)
def _catalog_for_mode(selected: str) -> ProductCatalog:
    if selected == "official_cn":
        return OfficialChinaCatalog()
    if selected == "openfoodfacts":
        return OpenFoodFactsCatalog()
    if selected == "hybrid":
        return HybridProductCatalog()
    if selected == "curated":
        return JsonProductCatalog()
    raise ValueError(f"Unsupported product catalog: {selected}")


def _official_source_rejection(product: ProductRecord) -> str | None:
    label = product.label
    if product.catalog_scope != "official_cn_catalog":
        return "OFFICIAL_CATALOG_SCOPE_INVALID"
    if label.source_type not in {
        "official_product_page",
        "official_flagship_store",
    }:
        return "OFFICIAL_SOURCE_TYPE_REQUIRED"
    if label.source_authority != "manufacturer":
        return "OFFICIAL_SOURCE_AUTHORITY_REQUIRED"
    if (
        label.source_verified_at is None
        or label.source_language != "zh-CN"
        or label.source_access_region != "CN"
    ):
        return "OFFICIAL_SOURCE_REVIEW_INCOMPLETE"
    source_host = _url_host(label.source_url)
    if label.source_type == "official_product_page":
        if source_host not in OFFICIAL_PRODUCT_HOSTS:
            return "OFFICIAL_PRODUCT_HOST_NOT_ALLOWLISTED"
    elif not _is_official_store_host(source_host):
        return "OFFICIAL_STORE_HOST_NOT_ALLOWLISTED"
    if label.official_store_url and (
        not _is_official_store_host(_url_host(label.official_store_url))
        or not label.official_store_name
        or label.official_store_verified_at is None
    ):
        return "OFFICIAL_STORE_REVIEW_INCOMPLETE"
    return None


def _url_host(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https":
        return ""
    return (parsed.hostname or "").lower()


def _is_official_store_host(host: str) -> bool:
    return any(host == suffix[1:] or host.endswith(suffix) for suffix in OFFICIAL_STORE_HOST_SUFFIXES)


def _map_open_food_facts_product(
    raw: dict[str, Any], category: str
) -> tuple[ProductRecord | None, dict[str, Any] | None]:
    code = str(raw.get("code") or "").strip()
    name = str(raw.get("product_name_zh") or raw.get("product_name") or "").strip()
    ingredients = str(
        raw.get("ingredients_text_zh") or raw.get("ingredients_text") or ""
    ).strip()
    ingredients_image = _selected_image(raw, "ingredients")
    last_modified = raw.get("last_modified_t")
    states = set(raw.get("states_tags") or [])
    evidence_id = f"off.product.{code}.label" if code else "off.product.unknown.label"
    missing: list[str] = []
    if not code:
        missing.append("barcode")
    if not name:
        missing.append("product_name")
    if not ingredients:
        missing.append("ingredients_text")
    if not ingredients_image:
        missing.append("ingredients_image")
    if not last_modified:
        missing.append("source_record_version")
    if "en:ingredients-completed" not in states:
        missing.append("ingredients_review_state")
    if missing:
        return None, {
            "product_id": f"off:{code or 'unknown'}",
            "display_name": name or "Open Food Facts 未命名商品",
            "reason_code": "LIVE_LABEL_EVIDENCE_INCOMPLETE",
            "missing_fields": missing,
            "evidence_ids": [evidence_id],
        }
    confirmed_at = datetime.fromtimestamp(int(last_modified), tz=UTC).date()
    ingredients_text, embedded_allergen = _split_embedded_sections(ingredients)
    allergen_statement = embedded_allergen or _allergen_statement(raw)
    nutrition_rows = _nutrition_rows(raw)
    nutrition_basis = "每100克" if nutrition_rows else None
    label_payload = {
        "ingredients_text": ingredients_text,
        "allergen_statement": allergen_statement or "",
        "nutrition_table_text": "",
        "nutrition_basis_text": nutrition_basis or "",
        "nutrition_rows": nutrition_rows or [],
    }
    digest = sha256(
        json.dumps(
            label_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    product = ProductRecord(
        product_id=f"off:{code}",
        display_name=name,
        brand=str(raw.get("brands") or "品牌未提供").strip(),
        category=category,
        region="CN",
        use_case=USE_CASES[category],
        catalog_scope="live_open_food_facts",
        label={
            "evidence_id": evidence_id,
            "ingredients_text": ingredients_text,
            "allergen_statement": allergen_statement,
            "nutrition_basis_text": nutrition_basis,
            "nutrition_rows": nutrition_rows,
            "confirmed_by": "external_community_review",
            "confirmed_at": confirmed_at,
            "source_url": f"{OFF_BASE_URL}/product/{code}",
            "content_hash": f"sha256:{digest}",
            "evidence_quality": "complete",
            "source_provider": "open_food_facts",
            "source_record_version": str(last_modified),
            "ingredients_image_url": ingredients_image,
            "nutrition_image_url": _selected_image(raw, "nutrition"),
            "source_authority": "community",
        },
    )
    return product, None


def _split_embedded_sections(text: str) -> tuple[str, str | None]:
    markers = ("过敏原信息:", "过敏原信息：")
    for marker in markers:
        if marker in text:
            ingredients, remainder = text.split(marker, 1)
            allergen = remainder.split("营养成分表", 1)[0].strip()
            return ingredients.strip(" 。,，"), allergen or None
    return text.split("营养成分表", 1)[0].strip(" 。,，"), None


def _allergen_statement(raw: dict[str, Any]) -> str | None:
    direct = _translated_tags(str(raw.get("allergens") or ""))
    traces = _translated_tags(str(raw.get("traces") or ""))
    parts: list[str] = []
    if direct:
        parts.append(f"本产品含有{'、'.join(direct)}")
    if traces:
        parts.append(f"可能含有{'、'.join(traces)}")
    return "；".join(parts) or None


def _translated_tags(value: str) -> list[str]:
    result: list[str] = []
    for token in value.split(","):
        key = token.strip().lower().removeprefix("en:")
        label = ALLERGEN_LABELS.get(key)
        if label and label not in result:
            result.append(label)
    return result


def _selected_image(raw: dict[str, Any], kind: str) -> str | None:
    variants = (raw.get("selected_images") or {}).get(kind, {}).get("display", {})
    return (
        variants.get("zh") or variants.get("en") or next(iter(variants.values()), None)
    )


def _nutrition_rows(raw: dict[str, Any]) -> list[list[str]] | None:
    if raw.get("nutrition_data_per") != "100g":
        return None
    nutrients = raw.get("nutriments") or {}
    rows: list[list[str]] = [["项目", "每100克"]]
    mappings = (
        ("energy-kj", "能量", "千焦", 1.0),
        ("proteins", "蛋白质", "克", 1.0),
        ("fat", "脂肪", "克", 1.0),
        ("sugars", "糖", "克", 1.0),
        ("sodium", "钠", "毫克", 1000.0),
    )
    for key, label, unit, multiplier in mappings:
        value = nutrients.get(f"{key}_100g")
        if isinstance(value, int | float):
            rows.append([label, f"{value * multiplier:g}{unit}"])
    return rows if len(rows) > 1 else None


def _fetch_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
