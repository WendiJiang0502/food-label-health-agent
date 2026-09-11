"""Browser regression for 200% text resize and primary mobile disclosures."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(args.url, wait_until="networkidle")
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        page.wait_for_timeout(250)
        dimensions = page.evaluate(
            """() => ({
                viewport: document.documentElement.clientWidth,
                content: document.documentElement.scrollWidth
            })"""
        )
        if dimensions["content"] > dimensions["viewport"] + 1:
            offenders = page.evaluate(
                """() => [...document.querySelectorAll('body *')]
                    .map((element) => {
                        const rect = element.getBoundingClientRect();
                        return {
                            tag: element.tagName,
                            id: element.id,
                            className: String(element.className || ''),
                            left: Math.round(rect.left),
                            right: Math.round(rect.right),
                            width: Math.round(rect.width)
                        };
                    })
                    .filter((item) => item.right > document.documentElement.clientWidth + 1)
                    .slice(0, 10)"""
            )
            raise SystemExit(
                "200% text resize creates horizontal overflow: "
                f"{dimensions['content']}px > {dimensions['viewport']}px; "
                f"offenders={offenders}"
            )
        privacy = page.locator("[data-privacy-status]")
        if privacy.count() and not privacy.first.is_visible():
            raise SystemExit("Processing disclosure is hidden in the mobile layout")
        page.locator(".skip-link").focus()
        if not page.locator(".skip-link").is_visible():
            raise SystemExit("Skip link is not visible when keyboard-focused")
        browser.close()


if __name__ == "__main__":
    main()
