---
version: 1
slug: "src-food-label-agent-web-static-index-html"
primary_target: "src/food_label_agent/web/static/index.html"
related_targets: ["src/food_label_agent/web/static/styles.css","src/food_label_agent/web/static/app.js"]
---

# Upload and confirmation workbench

- Mode: Operate
- Audience: consumers checking a packaged food at purchase time or at home
- Primary job: upload label images, inspect OCR output, correct uncertain fields, and submit confirmed label facts to the Agent workflow
- Primary action: confirm the ingredient text and continue analysis
- Required truth: this milestone uses a demonstration OCR provider and must label synthetic output clearly
- Critical states: empty, drag-over, uploading, OCR processing, low confidence, confirmed, invalid file, and server error
- Direction: Distilled optical workspace, retaining the supplied reference's spaciousness without decorative Bento repetition
- Memorable moment: one upload room becomes a synchronized image-and-correction workspace only after OCR succeeds
- Constraints: mobile-first capture, keyboard access, no absolute health score, no medical assurance, risk cannot rely on color alone
- Open decisions: production OCR provider, persistent object storage, authentication, and deployment platform
