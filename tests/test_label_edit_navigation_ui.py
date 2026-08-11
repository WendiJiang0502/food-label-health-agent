from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"


def test_constraint_step_offers_accessible_return_to_label_editing() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="edit-label"' in html
    assert 'type="button"' in html
    assert "返回编辑标签" in html
    assert html.index('id="edit-label"') < html.index('id="constraint-form"')


def test_return_to_label_editing_restores_fields_and_invalidates_stale_facts() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert (
        'elements.editLabel.addEventListener("click", returnToLabelEditing)' in script
    )
    assert "elements.form.hidden = false" in script
    assert "state.confirmedFields = null" in script
    assert "state.normalizedLabel = null" in script
    assert 'elements.proofState.textContent = "待重新确认"' in script
    assert 'elements.fieldList.querySelector("textarea")?.focus()' in script
