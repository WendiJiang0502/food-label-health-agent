from playwright.sync_api import sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://127.0.0.1:8010/developer")
    page.wait_for_load_state("networkidle")
    assert page.locator("h1").inner_text() == "Agent 运行轨迹"
    assert page.locator("#load").count() == 1
    response = page.request.get("http://127.0.0.1:8010/api/developer-traces")
    assert response.status == 403
    page.locator("#token").fill("test-token")
    page.locator("#load").click()
    page.wait_for_timeout(200)
    assert page.locator("#runs tr").count() > 0
    assert "平均延迟" in page.locator("body").inner_text()
    browser.close()
print("developer_page_ok")
