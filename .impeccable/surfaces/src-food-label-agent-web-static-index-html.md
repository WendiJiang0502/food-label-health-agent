---
version: 1
slug: "src-food-label-agent-web-static-index-html"
primary_target: "src/food_label_agent/web/static/index.html"
related_targets: ["src/food_label_agent/web/static/styles.css","src/food_label_agent/web/static/app.js"]
---

# Personal profile, label confirmation, history, and health dashboard workspace

- Mode: Operate; audience is consumers checking packaged food at purchase time or at home and returning to review prior decisions.
- Primary job: declare allergens and plain-language health concerns, confirm a label, receive a traceable result, then revisit privacy-preserving scan summaries and self-entered health activity.
- Sequence: personal profile → analysis-focus preview → upload and OCR correction → deterministic result and alternatives → persistent history, central scan action, and user destinations.
- Required truth: scan history stores structured summaries but never uploaded images; health records require explicit on-device consent, compare only the same metric, and never label a change as better or worse.
- Critical states: empty and populated dashboard, week/month/year periods, new profile, saved profile, upload, OCR correction, all result outcomes, consent, invalid/future health entry, single and repeated metric entries, and clear-history confirmation.
- Direction: keep the evidence workflow, then let “我的” become one coherent flat clinical organizer: warm ivory fields, black-gray type, fine taupe outlines, pastel pink actions, and muted yellow, blue, pink, and sage category bands.
- Memorable moment: a compact pastel selector travels across a light outlined dock, rising through a canvas-colored border cutout around the current icon while its label remains untouched and fully legible.
- Constraints: mobile capture, keyboard access, 44px controls, no diagnosis or health score, no interpretation of self-entered measurements, no stored label image, and explicit local-storage boundaries.
- Open decisions: authenticated multi-device profiles, encrypted sync, clinical governance for future interpretations, data export, and account-level retention controls.
