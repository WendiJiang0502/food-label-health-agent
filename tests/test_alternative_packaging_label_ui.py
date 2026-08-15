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
