from pathlib import Path

STATIC = Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"


def test_review_explains_multiline_allergen_evidence_and_missing_state() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "先核对过敏原声明" in html
    assert "未识别到声明，不代表包装证明没有过敏原" in html
    assert 'name: "allergen_statement"' in script
    assert "当前图片中没有识别到声明。请查看原图补录" in script
    assert "不能据此排除过敏风险" in script


def test_allergen_lines_are_individually_highlighted_and_confirmed() -> None:
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "renderAllergenEvidence(field)" in script
    assert "marker.dataset.lineIndex = String(lineIndex)" in script
    assert 'marker.classList.add("annotation--allergen-line")' in script
    assert "checkbox.dataset.confirmField = field.name" in script
    assert "请先逐行核对过敏原声明，再继续" in script
