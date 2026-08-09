---
version: 2
slug: "src-food-label-agent-web-static-index-html"
primary_target: "src/food_label_agent/web/static/index.html"
related_targets: ["src/food_label_agent/web/static/styles.css","src/food_label_agent/web/static/app.js","src/food_label_agent/web/static/assets/label-pouch.png"]
---

# Label confirmation and safety workbench

- Mode: Operate
- Audience: consumers checking a packaged food at purchase time or at home
- Primary job: upload a label image, confirm label facts, select hard allergen constraints, and understand the deterministic safety result
- Primary action before OCR: upload or photograph the label
- Primary action after OCR: confirm recognized text, then check selected allergen constraints
- Required truth: OCR is demonstration data and must remain visibly labeled
- Critical states: empty, drag-over, processing, low confidence, confirmed, constraint selection, avoid, caution, compatible, unknown, invalid file, and server error
- Direction: warm editorial utility Bento adapted from the pinned Nova Benefits reference
- Memorable moment: the uploaded label stays visible while the review rail advances from correction to personal constraints and a three-fact safety result
- Constraints: mobile capture, keyboard access, one task per state, no health score, no medical assurance, no internal Agent terminology
- Open decisions: production OCR provider, persistent object storage, authentication, and deployment platform
