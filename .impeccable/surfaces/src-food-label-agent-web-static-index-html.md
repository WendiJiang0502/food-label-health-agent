---
version: 1
slug: "src-food-label-agent-web-static-index-html"
primary_target: "src/food_label_agent/web/static/index.html"
related_targets: ["src/food_label_agent/web/static/styles.css","src/food_label_agent/web/static/app.js","src/food_label_agent/web/static/assets/label-pouch.png"]
---

# Personal profile, label confirmation, history, and health-change workspace

- Mode: Operate; audience is consumers checking packaged food at purchase time or at home and returning to review prior decisions.
- Primary job: declare allergens and plain-language health concerns, confirm a label, receive a traceable result, then revisit privacy-preserving scan summaries or self-entered health changes.
- Sequence: personal profile → analysis-focus preview → upload and OCR correction → deterministic result and alternatives → persistent three-destination navigation for scan, history, and user profile.
- Required truth: scan history stores structured summaries but never uploaded images; health-change records require explicit on-device consent, compare only the same metric, and never label a change as better or worse.
- Critical states: new profile, saved profile, upload, OCR correction, all four result outcomes, empty and populated scan history, health-record consent, invalid/future health entry, one-entry and multi-entry metric trends, and clear-history confirmation.
- Direction: inherit the warm editorial utility Bento. After the first result, a compact paper tab bar turns the one-off scanner into a calm personal evidence workspace.
- Constraints: mobile capture, keyboard access, 44px controls, no diagnosis, no health score, no automatic interpretation of self-entered health measurements, no stored label image, and clear local-storage boundaries.
- Open decisions: authenticated multi-device profiles, encrypted health-data sync, clinical governance for future interpretations, data export, and account-level retention controls.
