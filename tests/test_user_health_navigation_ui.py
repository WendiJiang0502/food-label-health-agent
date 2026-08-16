from __future__ import annotations

from pathlib import Path

STATIC_DIR = (
    Path(__file__).parents[1] / "src" / "food_label_agent" / "web" / "static"
)


def test_result_stage_exposes_three_primary_app_views() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="app-tabbar"' in html
    assert 'data-app-view="scan"' in html
    assert 'data-app-view="history"' in html
    assert 'data-app-view="user"' in html
    assert "拍照识别" in html
    assert "历史记录" in html
    assert "我的" in html
    assert 'id="history-view"' in html
    assert 'id="user-view"' in html


def test_scan_history_keeps_summary_without_image_data() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'const SCAN_HISTORY_STORAGE_KEY = "food-label-agent.scan-history.v1"' in script
    assert "function saveScanHistory({ outcome, riskLevel, nutrition })" in script
    assert "productName: currentProductName()" in script
    assert "nutritionFacts: compactNutritionFacts(nutrition)" in script
    assert "state.scanHistory = [record" in script
    assert "previewUrl:" not in script[script.index("function saveScanHistory"):script.index("function updateCurrentScanHistoryOutcome")]


def test_user_page_records_health_changes_with_explicit_local_consent() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="health-entry-form"' in html
    assert 'id="health-storage-consent"' in html
    assert "数据不会用于自动诊断" in html
    assert "不判断“变好”或“变差”" in html
    assert 'const HEALTH_HISTORY_STORAGE_KEY = "food-label-agent.health-changes.v1"' in script
    assert "function saveHealthEntry(event)" in script
    assert "function renderHealthHistory()" in script
    assert "较上次 ${formatSignedNumber" in script
    assert "state.healthHistoryConsent" in script


def test_bottom_navigation_and_health_views_have_mobile_rules() -> None:
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".app-tabbar" in styles
    assert ".app-tabbar button[aria-current=\"page\"]" in styles
    assert ".health-change-layout" in styles
    assert ".health-trend-row" in styles
    assert "grid-template-columns: 1fr" in styles


def test_user_page_uses_neutral_health_dashboard_statistics() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert 'id="health-statistics-title">记录统计' in html
    assert 'data-health-period="week"' in html
    assert 'data-health-period="month"' in html
    assert 'data-health-period="year"' in html
    assert "不表示风险、达标或健康程度" in html
    assert "function renderHealthDashboard" in script
    assert "function buildHealthActivityBins" in script
    assert ".dashboard-metric--scan" in styles
    assert ".health-ring-chart" in styles
