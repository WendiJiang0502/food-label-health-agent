---
version: 1
slug: "src-food-label-agent-web-static-index-html"
primary_target: "src/food_label_agent/web/static/index.html"
related_targets: ["src/food_label_agent/web/static/styles.css","src/food_label_agent/web/static/app.js","src/food_label_agent/web/static/assets/label-pouch.png"]
---

# Personal profile, label confirmation, and safety workbench

- Mode: Operate; audience is consumers checking packaged food at purchase time or at home.
- Primary job: declare allergens and plain-language health concerns, preview how those choices change label reading, confirm the active profile, then photograph, correct, and evaluate a label.
- Sequence: personal profile → short analysis-focus preview → profile confirmation beside upload → OCR correction → deterministic allergen result and independently revalidated alternatives.
- Required truth: health concerns adjust explanation priority but do not silently become medical thresholds; unsupported free-text items remain visible and require human confirmation; the active OCR provider and remote-processing boundary remain disclosed.
- Critical states: new profile, validation error, saved profile, advice preview, profile edit, empty upload, processing, low confidence, confirmed, avoid, caution, compatible, unknown, alternative loading, no eligible alternative, invalid file, and server error.
- Direction: inherit the warm editorial utility Bento. The memorable moment is the analysis-focus sheet translating familiar health concerns into the exact label facts the product will prioritize.
- Constraints: mobile capture, keyboard access, explicit consent for durable profile memory, one task per state, no health score, diagnosis, medical assurance, invented intake limit, or internal Agent terminology.
- Open decisions: authenticated multi-device profiles, clinically governed health-to-threshold rules, production OCR provider, persistent object storage, and deployment platform.
