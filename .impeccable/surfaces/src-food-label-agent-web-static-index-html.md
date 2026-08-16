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
- Direction: keep the warm editorial evidence workspace, then let “我的” become a crisp mobile health dashboard. Four asymmetric deep-teal, leaf, seafoam, and forest tiles show real local activity; the shadowless white dock raises only the currently selected destination, with scan remaining in the central position.
- Memorable moment: the first glance feels like a lively personal health app, while the nearby copy makes it unmistakable that color is categorization rather than risk or achievement.
- Constraints: mobile capture, keyboard access, 44px controls, no diagnosis or health score, no interpretation of self-entered measurements, no stored label image, and explicit local-storage boundaries.
- Open decisions: authenticated multi-device profiles, encrypted sync, clinical governance for future interpretations, data export, and account-level retention controls.
