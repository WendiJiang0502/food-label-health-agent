---
version: 2
slug: "src-food-label-agent-web-static-index-html"
primary_target: "src/food_label_agent/web/static/index.html"
related_targets: ["src/food_label_agent/web/static/styles.css","src/food_label_agent/web/static/app.js","src/food_label_agent/web/static/assets/label-pouch.png"]
---

# Upload and confirmation workbench

- Mode: Operate
- Audience: consumers checking a packaged food at purchase time or at home
- Primary job: upload a label image, inspect OCR output, correct uncertain fields, and confirm label facts
- Primary action before OCR: upload or photograph the label
- Primary action after OCR: confirm recognized text
- Required truth: OCR is demonstration data and must remain visibly labeled
- Critical states: empty, drag-over, processing, low confidence, confirmed, invalid file, and server error
- Direction: warm editorial utility Bento adapted from the pinned Nova Benefits reference
- Memorable moment: a tactile example package yields to the user's real label, then the workspace expands into synchronized image and correction panels
- Constraints: mobile capture, keyboard access, one task per state, no health score, no medical assurance, no internal Agent terminology
- Open decisions: production OCR provider, persistent object storage, authentication, and deployment platform
