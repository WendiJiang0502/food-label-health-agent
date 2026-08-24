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
    assert 'id="portion-kind"' in html
    assert 'id="portion-package-note"' in html
    assert 'id="portion-confidence"' in html
    assert 'id="portion-category"' in html
    assert '先确认这是哪类食品' in html
    assert "包装信息" in html
    assert "建议依据" in html


def test_portion_guidance_has_safe_category_defaults_and_label_math() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'snack: { amount: 25, range: [15, 30], unit: "g", label: "25克/次" }' in script
    assert 'label: "10克/次"' in script
    assert "Number(fact.value) * reference.amount / 100" in script
    assert "不建议用减少份量代替风险判断" in script
    assert "不是国家规定份量或个体化医疗处方" in script
    assert "function updatePortionAmount(amount)" in script
    assert "Number(fact.value) * (factor ?? 1)" in script
    assert 'elements.portionControls.hidden = true' in script
    assert 'elements.portionKind.textContent = "包装明确标示的一份"' in script
    assert 'elements.portionKind.textContent = "系统建议的一次食用量"' in script
    assert 'elements.portionKind.textContent = "标签数值已可用"' in script
    assert '确认食品类别后即可估算一次食用量' in script
    assert 'function applyConfirmedPortionCategory(category)' in script
    assert 'heading: "未发现与当前设置冲突"' in script
    assert 'elements.safetyTitle.textContent = "标签重点已整理"' in script
    assert "context.healthFocusOnly" in script
    assert "function extractPackageQuantity(text)" in script
    assert "function conservativeStartingAmount(amount, unit)" in script
    assert "${portionReferenceBasis(reference)} + 你的健康关注 + 当前标签数值" in script
    assert "function portionAmountAssessment(reference, amount)" in script
    assert "系统同类换算参考" in script
    assert "包装独立食用单元" in script
    assert 'elements.portionAssessment.dataset.state = assessment.state' in script


def test_result_page_uses_four_clear_decision_outcomes() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "非常建议食用（仅按当前设置）" not in script
    assert 'heading: "符合你设置的营养上限"' in script
    assert 'heading: "不建议食用"' in script
    assert 'heading: "需要确认包装信息"' in script
    assert 'heading: "未发现与当前设置冲突"' in script


def test_evaluation_button_exposes_staged_progress() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert 'role="progressbar"' in html
    assert 'aria-label="结论评估进度"' in html
    assert "function startEvaluationProgress()" in script
    assert "正在运行安全规则" in script
    assert "正在核对判断依据" in script
    assert "evaluation-progress__fill" not in html
    assert ".evaluation-progress {" in styles
    assert "inset: 0" in styles


def test_result_page_follows_decision_first_reading_order() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert html.index('id="safety-title"') < html.index('class="portion-guidance"')
    assert html.index('class="portion-guidance"') < html.index("为什么是这个结论")
    assert html.index("为什么是这个结论") < html.index('id="evidence-panel"')
    assert html.index('id="evidence-panel"') < html.index('id="alternative-discovery"')
