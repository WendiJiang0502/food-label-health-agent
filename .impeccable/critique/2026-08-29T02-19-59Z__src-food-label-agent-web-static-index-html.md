---
target: src/food_label_agent/web/static/index.html
total_score: 27
max_score: 40
na_heuristics: 0
p0_count: 1
p1_count: 4
timestamp: 2026-08-29T02-19-59Z
slug: src-food-label-agent-web-static-index-html
---
Method: dual-agent (A: /root/ux_critique · B: /root/ui_audit)

# Impeccable design critique — 食品标签解释与替代品 Agent

Target: `src/food_label_agent/web/static/index.html`

## Overall design

The interface is visibly custom and evidence-led rather than a generic health dashboard, but two product identities compete: a fast label-checking tool and a longitudinal health tracker. The scan workspace is the strongest state; onboarding and the returning-user dashboard delay it. Design health is **27/40 (Acceptable)**, but the privacy fail-open state is a launch blocker.

## Nielsen design health

| Heuristic | Score | Finding |
|---|---:|---|
| Visibility of system status | 3 | OCR and workflow state are clear in the happy path; dependency/processing-location failure is hidden. |
| Match with the real world | 3 | Consumer language is mostly good; evidence terminology still costs attention. |
| User control and freedom | 2 | First use cannot skip the profile; several state changes have no undo. |
| Consistency and standards | 3 | Controls are coherent, with some misleading disabled/empty-state styling. |
| Error prevention | 3 | Confirmation and deterministic constraints are strong; empty returning-profile state is not prevented. |
| Recognition over recall | 3 | Profile and evidence summaries help; layered card/deck states add interpretation cost. |
| Flexibility and efficiency | 2 | Core flow is rigid and returning users are routed away from the high-frequency scan task. |
| Aesthetic and minimalist design | 3 | Visually polished, but onboarding and the result tail are overloaded. |
| Error recognition and recovery | 3 | Local errors are actionable; cross-session profile loss is not explained. |
| Help and documentation | 2 | Boundaries are documented, but long inline explanations become part of the burden. |

Total: **27/40**. N/A heuristics: **0**.

## Cognitive load and emotional journey

Four of eight cognitive-load checks fail: chunking, one-thing-at-a-time, minimal choices, and progressive disclosure. First use exposes 9 allergen options, a custom field, 8 health concerns, another custom field, storage consent, and a CTA before the user experiences a scan. On mobile the form is about 1,564 px tall. The emotional high point is the scan workspace; the low points are the questionnaire wall and the empty “我的档案” state after a non-persisted profile expires.

## Priority findings

### [P0] Processing-location and privacy copy fails open

`loadHealthStatus()` silently catches `/api/health` failure while the static page continues to claim demo OCR and that images are not saved. If the real backend processing path differs, upload remains enabled under an unverified promise. A failed status check must disable upload or display “处理位置无法确认，请重试”; it must never retain an optimistic default.

### [P1] Non-persisted profiles become an unsafe empty returning state

Submitting onboarding writes the completion flag even if the profile is not saved. After refresh, the app enters “我的档案的健康主页” with no allergens or health concerns and still permits scanning. Separate onboarding completion, active session profile, persisted profile, and history. If no valid profile exists, say so and require confirmation before personalized evaluation.

### [P1] First use delays the core value with a decision wall

The 9+8 visible choices, custom inputs, consent, and second confirmation step come before the first scan. Make “先扫描” the default, or split setup into three progressive steps with a clear skip path and visible progress.

### [P1] Keyboard skip navigation points to hidden content

The global skip link targets `#workspace`, which is hidden during onboarding and the dashboard. Browser testing showed no useful focus or scroll change. The skip target must follow the active view and land on a focusable current heading or `<main>`.

### [P1] Small text fails WCAG AA contrast

Measured examples include 3.03:1 brand-small text, 2.82:1 eyebrow text, 3.53:1 footer disclosure, 4.13:1 inactive period controls, and 4.07:1 destructive-history text. Increase contrast and/or size to meet 4.5:1 for normal text.

## Additional findings

- [P2] Mobile hides the top privacy/data-flow disclosure at <=640 px even though mobile capture is the primary scenario.
- [P2] The 1.43 MB decorative pouch PNG loads even when its view is hidden; use AVIF/WebP, responsive sources, and lazy/conditional loading.
- [P2] Returning users default to the health dashboard rather than the high-frequency scan task.
- [P2] Result pages can expose portion guidance, nutrition, reasons, additives, claims, folded evidence, and alternatives at once. Fix the first viewport to conclusion, immediate action, label location, and first official source.
- [P2] Desktop inherits a floating mobile-style dock; use stable desktop navigation and keep the floating dock for mobile.

## Persona checks

- Jordan, first-time user: sees a health questionnaire rather than proof that the product can understand a label.
- Casey, distracted mobile user: must scroll multiple screens before scanning and may return to an empty profile after interruption.
- Sam, keyboard or low-vision user: benefits from headings, fieldsets, focus styles, live regions, inert deck cards, and reduced-motion support, but encounters a broken skip link and multiple contrast failures.

## What works

- Trust boundaries are unusually explicit across image handling, OCR demo status, structured history, and non-diagnostic health records.
- The scan state has the clearest hierarchy and lowest anxiety in the product.
- The evidence chain—label fact, user constraint, evidence location, official basis—is the correct information model.
- Mobile layouts at 390 px and 320 px have no horizontal overflow; visible touch targets are generally at least 44 px.
- Empty-submit errors use an alert, move focus, and visibly outline the invalid proxy control.
- The health deck supports arrows, inert non-current cards, and reduced motion without autoplay.

## Run notes

- Mode: Operate. Target slug: `src-food-label-agent-web-static-index-html`.
- Ignore list: `.impeccable/critique/ignore.md` absent.
- Independence: Assessment A completed before Assessment B findings entered synthesis; neither assessor read the other output.
- CLI detector: exit 0, JSON `[]`, no false positives. The detector covers markup patterns only.
- Browser verification: desktop 1280/1440, mobile 390, narrow 320; console empty; inspected keyboard, error, onboarding, scan, and dashboard states.
- Overlay: mutation preflight failed because the browser evaluation surface was read-only, so no live overlay was injected and no human overlay findings are claimed.
- Cleanup: temporary servers stopped, tabs closed, viewport reset; no product files changed.

## Targeted questions

1. Should first use optimize for immediate proof (“先扫一次”) or complete personalization before any scan?
2. Is “我的” a secondary history space or the default returning-user homepage?
3. When processing-location status cannot be verified, should the product block upload entirely or allow an explicit user-confirmed degraded mode?
