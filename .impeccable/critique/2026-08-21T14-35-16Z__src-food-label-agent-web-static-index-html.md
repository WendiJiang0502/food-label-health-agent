---
target: src/food_label_agent/web/static/index.html
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 4
timestamp: 2026-08-21T14-35-16Z
slug: src-food-label-agent-web-static-index-html
---
# Food Label Agent UI Critique

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | OCR/privacy states are clear; first-use and return state is not. |
| 2 | Match System / Real World | 3 | Mostly plain language; “Agent” and composition graphics add abstraction. |
| 3 | User Control and Freedom | 2 | Returning users do not land in a continuity-oriented console. |
| 4 | Consistency and Standards | 2 | Evidence workspace and health dashboard feel like adjacent products. |
| 5 | Error Prevention | 3 | Validation, consent, and destructive confirmations are solid. |
| 6 | Recognition Rather Than Recall | 3 | Constraints stay visible, but long summaries can become unreadable. |
| 7 | Flexibility and Efficiency | 2 | Repeat users must follow a scan-oriented route again. |
| 8 | Aesthetic and Minimalist Design | 2 | First-use choices and dashboard statistics are too dense. |
| 9 | Error Recovery | 3 | Local recovery is good; interrupted/stale workflow recovery is less clear. |
| 10 | Help and Documentation | 2 | Strong boundaries, limited task help for photography and uncertain results. |
| **Total** | | **25/40** | **Acceptable; significant improvements needed** |

## Design Specificity Verdict

The scan and evidence flow is meaningfully specific to 食鉴: explicit privacy, OCR confirmation, personal constraints, official-source framing, and refusal to manufacture a health score all support trust. The dashboard is less specific and reads like a generic wellness tracker. Its concentric rings imply progress or scoring even while the copy denies that interpretation. The strongest direction is to keep the health-log warmth but make every dashboard object express food-label continuity: what was checked, what remains uncertain, and what the user can do next.

The deterministic scan confirmed a 375px clipped overflow, an unsafe 391–404px health-chart breakpoint, undersized touch targets, weak primary-button focus, asymmetric additive-card padding, and the absence of a true layered/sliding overview. Detector output was advisory-only in retained results and centered on design-system font-size, color, and radius drift in `styles.css`; many of those are probable false positives caused by the stale design sidecar and palette mismatch.

No reliable user-visible overlay was created because the available browser evaluation surface was read-only. Browser geometry, computed styles, source rules, screenshots, and four viewport checks were used instead.

## Overall Impression

The product has a strong evidence-first backbone, but the return experience and dashboard do not yet reward repeated use. The single biggest opportunity is to turn “我的” into a true continuity console: a restrained, accessible layered card deck whose content is specific to food-label decisions rather than generic wellness metrics.

## What's Working

- Evidence provenance and privacy boundaries are unusually explicit and trustworthy.
- Profile → focus preview → scan → confirmation → evidence is a defensible product-specific workflow.
- Semantic fieldsets, focus-visible states, live announcements, reduced-motion handling, and large primary controls provide a good accessibility base.

## Priority Issues

### [P1] Returning-user routing breaks continuity

First-use completion and permission to persist sensitive profile details are coupled. Returning users are not reliably taken to a continuity-oriented console. Add a separate non-sensitive onboarding-complete flag: new users see onboarding, saved-profile users land on “我的,” and users without a stored profile get a lightweight console with a clear profile setup action.

Suggested command: `$impeccable onboard`

### [P1] Mobile content is clipped at 375px

The page measured 554px wide in a 375px viewport. `.privacy-note { white-space: nowrap; }` is the confirmed source and `overflow-x: clip` only hides the failure. Allow wrapping or constrain the note, then recheck intermediate widths.

Suggested command: `$impeccable adapt`

### [P1] Summary cards lack reliable containment

The profile promise and scan profile summary visually read as cards but do not consistently provide full inset spacing or resilient long-text behavior. Use an explicit `minmax(0,1fr) auto` header grid, stacked detail rows, 20–24px inset spacing, and `overflow-wrap:anywhere`; keep the edit action at least 44px.

Suggested command: `$impeccable layout`

### [P1] Health composition uses the wrong visual model

Concentric rings overlap at intermediate mobile widths and imply health progress. Replace them with a directly labeled stacked bar or simple count list. Keep the total outside the graphic and support empty, one-category, and four-category states at 320px.

Suggested command: `$impeccable clarify`

### [P2] Result and overview cards need authored rhythm and motion

Additive items have vertical spacing but no sufficient horizontal inset. Give each item 16–20px padding and clear content zones. Replace the four flat “今日概览” cards with one active card plus two or three offset cards, drag/swipe, keyboard controls, a position indicator, 240–320ms user-triggered motion, no autoplay, and an instant reduced-motion state.

Suggested commands: `$impeccable layout`, then `$impeccable animate`

## Persona Red Flags

**Distracted mobile shopper:** Sees more than seventeen choices before the scan task, then may revisit and still miss a continuity dashboard. The 375px clipping and large headings further delay action.

**Keyboard, screen-reader, or low-vision user:** Existing semantics are strong, but the planned card deck must expose explicit previous/next controls, position announcements, and reduced-motion behavior. The current ring and tiny legend are hard to interpret.

**Consumer managing a serious allergen:** Long avoidance summaries can collide or hide the exact constraint they need to verify. The primary result must repeat the matched ingredient and evidence location before additives, nutrition, or alternatives.

## Minor Observations

- Tablet header privacy copy competes with the brand and OCR badge.
- “食品标签解释 Agent” is implementation language; “食品标签解释” is clearer.
- The current promise that repeat visits will “先确认” conflicts with the requested direct console landing.
- The primary submit focus outline is white on white and should use the product focus color.
- “修改” is only 32px wide at 375px and needs a larger hit area.
- The reference's layered-card metaphor is useful; its ratings and generic wellness symbolism should not be copied.

## Questions to Consider

- Should the layered deck primarily navigate destinations, or summarize the latest food-label decisions? The latter is more specific to 食鉴.
- Should users who decline profile storage still get a non-sensitive onboarding-completed flag so they are not forced through onboarding again?
- What should the first active card show after a serious allergen match: the latest result, unresolved evidence, or the next recommended action?
