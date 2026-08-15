from __future__ import annotations

from pathlib import Path


STATIC_DIR = (
    Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"
)


def test_official_alternative_renders_confirmed_packaging_label() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "function renderAlternativePackagingLabel(item)" in script
    assert "查看已核对包装标签" in script
    assert 'appendAlternativeLabelFact(facts, "配料表"' in script
    assert '"过敏原提示"' in script
    assert 'table.className = "alternative-nutrition-table"' in script
    assert "请以实际到手包装为准" in script


def test_incomplete_official_products_show_verified_and_missing_fields() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "件已补齐全部包装字段" in script
    assert "件达到当前复核门槛" in script
    assert 'verified.className = "alternative-review-verified"' in script
    assert 'missing.className = "alternative-review-missing"' in script
    assert "查看品牌官方产品页" in script
