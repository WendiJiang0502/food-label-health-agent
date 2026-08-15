from __future__ import annotations

import json
from pathlib import Path

from food_label_agent.alternatives.catalog import OfficialChinaCatalog
from food_label_agent.alternatives.models import (
    AlternativeRevalidationRequest,
    AlternativeSearchRequest,
)
from food_label_agent.alternatives.service import (
    find_alternative_products,
    revalidate_alternatives,
)
from food_label_agent.ingredients.api_models import ConstraintInput


def test_official_catalog_exposes_verified_mainland_sources() -> None:
    result = OfficialChinaCatalog().search(category="dairy", region="CN")

    assert result.provider == "china_official_sources"
    assert [item.display_name for item in result.records] == ["伊利纯牛奶"]
    label = result.records[0].label
    assert label.source_type == "official_product_page"
    assert label.source_authority == "manufacturer"
    assert label.source_access_region == "CN"
    assert label.official_store_name == "伊利牛奶官方旗舰店"
    assert label.official_store_url and "jd.com" in label.official_store_url


def test_official_catalog_rejects_unreviewed_store_identity(tmp_path: Path) -> None:
    source = json.loads(
        Path(
            "src/food_label_agent/alternatives/data/official_cn_products.json"
        ).read_text(encoding="utf-8")
    )
    source[0]["label"]["official_store_verified_at"] = None
    path = tmp_path / "official-products.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    result = OfficialChinaCatalog(path).search(category="dairy", region="CN")

    assert result.records == ()
    assert result.rejected[0]["reason_code"] == "OFFICIAL_STORE_REVIEW_INCOMPLETE"


def test_official_candidate_is_independently_revalidated() -> None:
    constraint = ConstraintInput(
        kind="allergy", canonical_value="peanut", severity="severe"
    )
    search = find_alternative_products(
        AlternativeSearchRequest(
            category="dairy",
            applicable_date="2026-08-15",
            constraints=[constraint],
        ),
        catalog=OfficialChinaCatalog(),
    )
    result = revalidate_alternatives(
        AlternativeRevalidationRequest(
            request_id="official-cn-revalidation",
            applicable_date="2026-08-15",
            constraints=[constraint],
            candidates=search["candidates"],
        )
    )

    assert search["catalog_scope"] == "china_official_sources"
    assert result["eligible_count"] == 1
    eligible = result["results"][0]
    assert eligible["label_source_type"] == "official_product_page"
    assert eligible["official_store_name"] == "伊利牛奶官方旗舰店"
