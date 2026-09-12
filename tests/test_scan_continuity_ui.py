from pathlib import Path

STATIC = Path(__file__).parents[1] / "src/food_label_agent/web/static"


def test_scan_review_restores_text_without_claiming_to_store_the_image() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'id="resume-draft"' in html
    assert 'id="workflow-progress"' in html
    assert 'data-workflow-step="upload"' in html
    assert 'data-workflow-step="review"' in html
    assert 'data-workflow-step="evaluate"' in html
    assert 'const SCAN_DRAFT_SESSION_KEY = "food-label-agent.scan-draft.v1"' in script
    assert "const SCAN_DRAFT_MAX_AGE_MS = 2 * 60 * 60 * 1000" in script
    assert "function saveScanDraft(stage" in script
    assert "function restoreScanDraft()" in script
    assert "function sameDraftFile(file, expected)" in script
    assert "原图没有保存" in script
    assert 'elements.confirmButton.disabled = true' in script
    assert 'saveScanDraft("review")' in script
    assert 'saveScanDraft("evaluate")' in script


def test_alternative_states_use_plain_language_and_progressive_disclosure() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'class="alternative-tier-key"' in html
    assert "完整核验" in html
    assert "证据有限" in html
    assert "待核验" in html
    assert "同一 SKU 背标已双人核对" in html
    assert "缺关键字段，不推荐" in html
    assert 'class="alternative-source-disclosure"' in html
    assert '"现在能判断"' in script
    assert '"还缺什么"' in script
    assert '"你需要做"' in script
    assert '"购买状态"' in script
    assert "官方商店链接只用于自行核对" in script
    assert 'conditionally_verified: "证据有限"' in script


def test_first_viewport_uses_compact_privacy_status_with_details_available() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'data-privacy-status="compact"' in html
    assert 'class="privacy-disclosure"' in html
    assert "数据如何处理" in html
    assert "function compactPrivacyStatus(message)" in script
    assert "校对文字草稿只保留在当前标签页，最长 2 小时" in script
