"""Run axe-core against the rendered application using Playwright Chromium."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("axe_script", type=Path)
    args = parser.parse_args()
    if not args.axe_script.is_file():
        raise SystemExit(f"axe-core script not found: {args.axe_script}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            bypass_csp=True, viewport={"width": 390, "height": 844}
        )
        page = context.new_page()
        page.goto(args.url, wait_until="networkidle")
        page.add_script_tag(path=str(args.axe_script))
        results = page.evaluate(
            """async () => await axe.run(document, {
                runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}
            })"""
        )
        browser.close()
    violations = results["violations"]
    if violations:
        summary = [
            {
                "id": item["id"],
                "impact": item["impact"],
                "help": item["help"],
                "targets": [node["target"] for node in item["nodes"]],
            }
            for item in violations
        ]
        raise SystemExit("axe violations:\n" + json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
