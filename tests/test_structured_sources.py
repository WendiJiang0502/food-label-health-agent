import json

import pytest

from food_label_agent.alternatives.structured_sources import structured_candidates


def source(adapter="simplelove_public_json"):
    return {
        "source_id": "test",
        "brand": "简爱",
        "category": "dairy",
        "adapter": adapter,
        "data_url": "https://simplelove.com.cn/data/product.json",
        "discovery_urls": ["https://simplelove.com.cn/product.html"],
    }


def test_manufacturer_reference_is_not_a_barcode_or_sku():
    raw = json.dumps(
        [
            {
                "id": 1,
                "name": "酸奶",
                "list": [
                    {
                        "name": "原味(230克)",
                        "ingredients": "生牛乳、白砂糖",
                        "component": [{"name": "蛋白质", "value": "3克"}],
                        "img": "https://simplelove.com.cn/a.png",
                    }
                ],
            }
        ]
    )
    item = structured_candidates(source(), lambda *_: raw, 1)[0]
    assert item["specification"] == "230克"
    assert item["sku"] is None and item["barcode"] is None
    assert not item["recommendation_eligible"]
    assert "糖含量未公开" in item["missing_fields"]
    assert item["evidence_assets"] == []
    assert item["extracted_fields"]["nutrition_rows"] == [
        ["项目", "每100克"],
        ["蛋白质", "3克"],
    ]
    changed = structured_candidates(source(), lambda *_: raw.replace("3\\u514b", "4\\u514b"), 1)[
        0
    ]
    assert changed["candidate_id"] == item["candidate_id"]
    assert changed["source_fingerprint"] != item["source_fingerprint"]


def test_static_html_excludes_commented_products_and_never_promotes_listing_ids():
    s = source("quaker_public_html")
    s.update(series="即食", brand="桂格")
    raw = """seriesTitle:'即食', list:[
      // {img:'old.png',title:'旧款'},
      {img:'a.png',title:'新品',jdLink:'https://item.jd.com/123.html'},
    ]"""
    items = structured_candidates(s, lambda *_: raw, 1)
    assert len(items) == 1
    assert items[0]["store_listing_urls"] == ["https://item.jd.com/123.html"]
    assert items[0]["barcode"] is None and items[0]["sku"] is None
    with pytest.raises(ValueError):
        structured_candidates(s, lambda *_: "layout changed", 1)
