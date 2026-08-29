from __future__ import annotations

import re
from pathlib import Path

from food_label_agent.alternatives.catalog import CATEGORY_TAGS


def test_alternative_category_options_match_catalog_adapters() -> None:
    html = (
        Path(__file__).parents[1] / "src/food_label_agent/web/static/index.html"
    ).read_text(encoding="utf-8")
    category_select = re.search(
        r'<select id="alternative-category">(.*?)</select>', html, re.DOTALL
    )
    assert category_select is not None
    option_values = set(
        re.findall(r'<option value="([^\"]*)"', category_select.group(1))
    ) - {""}

    assert option_values == set(CATEGORY_TAGS)
    assert len(option_values) == 14


def test_alternative_copy_never_claims_unproven_health_superiority() -> None:
    html = (
        Path(__file__).parents[1] / "src/food_label_agent/web/static/index.html"
    ).read_text(encoding="utf-8")

    assert "通过约束复核的同用途备选" in html
    assert "可同口径比较的营养信息" in html
    assert "更适合你的同类选择" not in html
    assert "为什么更符合你的关注" not in html

    script = (
        Path(__file__).parents[1] / "src/food_label_agent/web/static/app.js"
    ).read_text(encoding="utf-8")
    assert "与当前商品的可比变化" in script
    assert "为什么更符合你的关注" not in script


def test_alternative_results_expose_metrics_and_show_more_control() -> None:
    root = Path(__file__).parents[1] / "src/food_label_agent/web/static"
    html = (root / "index.html").read_text(encoding="utf-8")
    script = (root / "app.js").read_text(encoding="utf-8")

    assert 'id="alternative-show-more"' in html
    assert "payload.display_metrics" in script
    assert "可显示率" in script
    assert "目标营养可比率" in script
    assert "有效显示率" in script
    assert "visibleCount + pageSize" in script
