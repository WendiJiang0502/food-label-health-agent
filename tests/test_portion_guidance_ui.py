from __future__ import annotations

from pathlib import Path

STATIC_DIR = (
    Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"
)


def test_result_page_labels_portion_as_a_suggestion() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert "建议食用量" in html
    assert "不作为医疗处方" in html
    assert 'data-portion-multiplier="0.5"' in html
    assert 'data-portion-multiplier="2"' in html
    assert 'id="portion-amount"' in html


def test_portion_guidance_has_safe_category_defaults_and_label_math() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'snack: { amount: 25, unit: "g", label: "25克/次" }' in script
    assert 'label: "10克/次"' in script
    assert "Number(fact.value) * reference.amount / 100" in script
    assert "不建议用减少份量代替风险判断" in script
    assert "不是国家规定份量或个体化医疗处方" in script
    assert "function updatePortionAmount(amount)" in script
    assert "Number(fact.value) * (factor ?? 1)" in script
    assert 'elements.portionControls.hidden = true' in script
