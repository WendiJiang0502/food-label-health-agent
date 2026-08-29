from __future__ import annotations

from pathlib import Path

STATIC_DIR = (
    Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"
)


def test_result_page_labels_portion_as_neutral_label_math() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert "食用量换算" in html
    assert "不提供个体化食用量建议" in html
    assert 'data-portion-multiplier="0.5"' in html
    assert 'data-portion-multiplier="2"' in html
    assert 'id="portion-amount"' in html
    assert 'id="portion-kind"' in html
    assert 'id="portion-package-note"' in html
    assert 'id="portion-confidence"' in html
    assert 'id="portion-category"' in html
    assert '替代品食品类别' in html
    assert "包装信息" in html
    assert "换算依据" in html


def test_portion_guidance_uses_only_packaging_basis_for_label_math() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "不建议用减少份量代替风险判断" in script
    assert "function updatePortionAmount(amount)" in script
    assert "Number(fact.value) * (factor ?? 1)" in script
    assert 'elements.portionControls.hidden = true' in script
    assert 'elements.portionKind.textContent = "包装明确标示的一份"' in script
    assert 'elements.portionKind.textContent = "按标签标示口径换算"' in script
    assert 'elements.portionKind.textContent = "无法换算食用量"' in script
    assert 'function applyConfirmedPortionCategory(category)' in script
    assert 'heading: "未发现与当前设置冲突"' in script
    assert 'elements.safetyTitle.textContent = "标签重点已整理"' in script
    assert "context.healthFocusOnly" in script
    assert "function portionAmountAssessment(reference, amount)" in script
    assert 'elements.portionAssessment.dataset.state = assessment.state' in script
    assert "portionReferences" not in script
    assert "系统建议的一次食用量" not in script
    assert "conservativeStartingAmount" not in script
    assert "系统同类换算参考" not in script


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
