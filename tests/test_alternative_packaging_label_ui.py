from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"


def test_official_alternative_renders_confirmed_packaging_label() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "function renderAlternativePackagingLabel(item)" in script
    assert "查看已核对包装标签" in script
    assert 'appendAlternativeLabelFact(facts, "配料表"' in script
    assert '"过敏原提示"' in script
    assert 'table.className = "alternative-nutrition-table"' in script
    assert "请以实际到手包装为准" in script
    assert "function renderAlternativeEvidenceStatus(item)" in script
    assert 'appendAlternativeLabelFact(block, "证据状态"' in script
    assert 'appendAlternativeLabelFact(block, "包装版本"' in script
    assert "function comparisonBasisText(basis)" in script
    assert "function alternativeComparisonCopy(comparison)" in script
    assert "比当前商品" in script
    assert "不声称更健康" in script


def test_incomplete_official_products_show_verified_and_missing_fields() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "件完整核验" in script
    assert "件满足本次硬约束所需字段" in script
    assert "件仍需补齐安全判断字段" in script
    assert "自动发现队列另有" in script
    assert "同配方包装规格" in script
    assert "/api/v1/alternatives/discovery/refresh" in script
    assert 'verified.className = "alternative-review-verified"' in script
    assert 'missing.className = "alternative-review-missing"' in script
    assert "contextCoverage.missing_required_fields" in script
    assert "本次仍需补齐" in script
    assert "该候选因其他证据规则暂不推荐" in script
    assert "查看品牌官方产品页" in script
