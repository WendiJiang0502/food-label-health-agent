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
