---
name: Food Label Health Agent
description: A bright health-log dashboard for evidence-led food label analysis
colors:
  paper-canvas: "#F4F6F5"
  paper-surface: "#FFFFFF"
  editorial-navy: "#202727"
  editorial-navy-deep: "#101817"
  action-teal: "#138A7C"
  action-teal-hover: "#0D6E64"
  action-lime: "#B7E95B"
  supporting-cyan: "#A9DFE5"
  muted-ink: "#788583"
  muted-small: "#64716F"
  muted-compact: "#52615D"
  lime-ink: "#3F6500"
  caution: "#8A4B08"
  avoid: "#A9362B"
  compatible: "#14714B"
typography:
  display:
    fontFamily: "Avenir Next, SF Pro Display, PingFang SC, sans-serif"
    fontSize: "clamp(2.85rem, 5vw, 5.6rem)"
    fontWeight: 800
    lineHeight: 0.94
    letterSpacing: "-0.04em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, sans-serif"
    fontSize: "1rem"
    fontWeight: 450
    lineHeight: 1.55
  evidence:
    fontFamily: "SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.68rem"
    fontWeight: 700
    lineHeight: 1.4
rounded:
  control: "12px"
  field: "14px"
  review: "20px"
  proof: "28px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  section: "72px"
components:
  button-primary:
    backgroundColor: "{colors.action-lime}"
    textColor: "{colors.editorial-navy-deep}"
    rounded: "{rounded.pill}"
    padding: "13px 20px"
  input:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.editorial-navy}"
    rounded: "{rounded.field}"
    padding: "13px 14px"
---

# Design System: Food Label Health Agent

## Creative North Star

**The Personal Health Log** turns a photographed package into a calm, tangible evidence workspace. The visual language takes the user's references as a direction: pale cool canvas, white rounded cards, acid-lime primary actions, soft cyan/coral/lilac data accents, and compact mobile-health dashboard patterns. It does not copy their assets, brand, or wellness claims.

The first viewport contains exactly one promise and one task. The generated unbranded pouch demonstrates which surface to photograph; it has no readable claims and never acts as evidence. After OCR succeeds, the editorial introduction exits and the uploaded label becomes the visual focus beside its correction fields.

## Principles

- **Function inside the Bento.** Every visible card performs upload, review, status, or recovery work.
- **Progressive disclosure.** OCR correction appears only after fields exist; downstream Agent routing stays out of the consumer UI.
- **Evidence before interpretation.** Uploaded imagery and confirmed text lead. Decoration cannot imply a health result.
- **Plain-language safety.** Risk states combine words and symbols, never color alone; no absolute health score or medical clearance.
- **Evidence tiers stay visible.** Official page transcription and dual-reviewed physical-package evidence are distinct states. A link or page capture is never styled or worded as a verified back-label photo.

## Visual language

### Color

- `#F4F6F5` is the pale health-log canvas.
- `#FFFFFF` is the elevated work surface.
- `#202727` and `#101817` carry headings and high-contrast copy.
- `#B7E95B` is the primary action and active navigation accent.
- `#138A7C` carries focus and evidence links.
- `#64716F` is the accessible small-copy tone on surfaces; `#52615D` is reserved for the smallest persistent header/footer copy.
- `#3F6500` is accessible lime-family ink for eyebrow text; bright lime remains a surface or action color, never small text on white.
- Semantic caution, conflict, and compatibility colors appear only beside explicit state text.

### Typography

Product UI uses a rounded, platform-native sans stack with heavier display weights and tighter tracking. OCR confidence and evidence metadata use the monospace stack.

### Layout

Desktop begins as an asymmetric two-column hero: the consumer promise owns roughly 36% and the live upload workbench owns 64%. The upload card combines the example package and the action in one surface. When OCR completes, the introduction is hidden and the workspace becomes a 7/5 image-to-correction split. Returning users with a valid saved profile bypass onboarding and land on label scanning with their active constraints visible. Users without a valid saved profile always see onboarding after reload, even if anonymous scan history exists. They may explicitly choose the guest quick-scan path, which states that no personal allergen or health filtering will occur.

Below 900px the hero stacks in reading order. Below 640px, the package and upload action stack inside the card and the primary button spans the available width. Every interactive target is at least 44px.

### Depth and shape

White work surfaces use restrained layered shadows. Cards use 18–28px radii; buttons and inputs use 12–14px radii. Pills remain limited to transient state. Dashboard colors identify record categories, never health quality.

## Components

### Hero action

The left-side primary button and the right-side upload card open the same file input. This is one action with two affordances, not competing workflow choices.

### Upload workbench

The empty state shows an unbranded package reference, supported file types, the demonstration status, and the privacy default. Drag-over changes tone and lift. Once a file is selected, the package reference disappears and the real image fills the proof surface.

### OCR review

Review fields stay hidden until analysis succeeds. Confidence remains visible, low-confidence fields say `需确认`, and selecting a field activates its matching image annotation. Confirmation is the only primary action in this state.

### Alternative evidence state

Every alternative card states whether the physical ingredient and nutrition panels have completed independent dual review. `fully_verified` is reserved for an exact SKU/specification with immutable physical-package evidence. Records backed only by official-page text use the partial-evidence treatment and say that the physical package still needs checking. Legacy image links are labeled as source images and never as sufficient packaging proof.

### Personal dashboard deck

The dashboard's signature interaction is a four-card layered deck. One card is actionable at a time; the next cards peek from underneath to communicate sequence. Previous and next controls sit directly against the card's left and right edges, while an explicit “第 n 张，共 4 张” label explains position. Users can also use keyboard arrows or a horizontal touch gesture. It never auto-advances, and reduced-motion preferences remove the transition.

### Record composition

Record composition uses one horizontal stacked bar with directly labeled counts. Empty data is expressed as an empty state, not as a zero-valued ring or a health score. The chart's accessible label repeats the same count information in plain language.

### Historical result detail

Every saved recognition summary is a keyboard-accessible destination. Its detail view shows only the structured fields that were actually retained on the device: time, outcome, category, selected profile, compact nutrition facts, health focus, and—when available—the original decision summary and evidence location. Older records degrade to an explicit basic-summary state; the interface never reconstructs deleted images or invents missing evidence.

## Guardrails

- Do not expose LangGraph nodes, RAG routes, MCP calls, or roadmap stages to consumers.
- Do not create equal cards for explanatory filler.
- Do not use the generated package as a real product, recommendation, or OCR result.
- Do not label a food simply safe, healthy, or unhealthy.
- Do not rely on hover for essential information.
- Do not merge this visual experiment into `main` without explicit approval.
