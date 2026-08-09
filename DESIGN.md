---
name: Food Label Health Agent
description: A warm editorial Bento workbench for evidence-led food label analysis
colors:
  paper-canvas: "#F4F0E8"
  paper-surface: "#FFFDF8"
  editorial-navy: "#26334A"
  editorial-navy-deep: "#172338"
  action-teal: "#0A4650"
  action-teal-hover: "#06343C"
  supporting-periwinkle: "#909ABF"
  muted-ink: "#6E7890"
  muted-small: "#566177"
  caution: "#8A4B08"
  avoid: "#A9362B"
  compatible: "#14714B"
typography:
  display:
    fontFamily: "Iowan Old Style, Songti SC, STSong, Georgia, serif"
    fontSize: "clamp(3.5rem, 5vw, 5.2rem)"
    fontWeight: 600
    lineHeight: 0.93
    letterSpacing: "-0.055em"
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
  control: "8px"
  field: "10px"
  review: "22px"
  proof: "24px"
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
    backgroundColor: "{colors.action-teal}"
    textColor: "{colors.paper-surface}"
    rounded: "{rounded.control}"
    padding: "13px 20px"
  input:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.editorial-navy}"
    rounded: "{rounded.field}"
    padding: "13px 14px"
---

# Design System: Food Label Health Agent

## Creative North Star

**The Editorial Label Desk** turns a photographed package into a calm, tangible evidence workspace. The visual language adapts the user-pinned Nova Benefits Bento reference: warm paper, dark editorial type, asymmetrical functional cards, physical-object photography, and modest offset depth. It does not copy the reference's assets, brand, or benefits-product metaphors.

The first viewport contains exactly one promise and one task. The generated unbranded pouch demonstrates which surface to photograph; it has no readable claims and never acts as evidence. After OCR succeeds, the editorial introduction exits and the uploaded label becomes the visual focus beside its correction fields.

## Principles

- **Function inside the Bento.** Every visible card performs upload, review, status, or recovery work.
- **Progressive disclosure.** OCR correction appears only after fields exist; downstream Agent routing stays out of the consumer UI.
- **Evidence before interpretation.** Uploaded imagery and confirmed text lead. Decoration cannot imply a health result.
- **Plain-language safety.** Risk states combine words and symbols, never color alone; no absolute health score or medical clearance.

## Visual language

### Color

- `#F4F0E8` is the warm paper canvas.
- `#FFFDF8` is the elevated work surface.
- `#26334A` and `#172338` carry editorial headings and high-contrast copy.
- `#0A4650` is reserved for primary actions, focus, and active evidence.
- `#909ABF` supports the introductory promise without becoming a status color.
- `#566177` is the accessible small-copy tone on paper surfaces.
- Semantic caution, conflict, and compatibility colors appear only beside explicit state text.

### Typography

Editorial display text uses Iowan Old Style with Songti SC and Georgia fallbacks. Chinese line breaks are controlled by physical container width rather than `ch` units. Operational copy uses the platform sans-serif stack. OCR confidence and evidence metadata use the monospace stack.

### Layout

Desktop begins as an asymmetric two-column hero: the consumer promise owns roughly 36% and the live upload workbench owns 64%. The upload card combines the example package and the action in one surface. When OCR completes, the introduction is hidden and the workspace becomes a 7/5 image-to-correction split.

Below 900px the hero stacks in reading order. Below 640px, the package and upload action stack inside the card and the primary button spans the available width. Every interactive target is at least 44px.

### Depth and shape

White work surfaces use a restrained offset shadow to evoke printed cards. Primary actions use the same directional offset. Cards use 18–24px radii; buttons and inputs use compact 8–10px radii. Pills remain limited to transient state.

## Components

### Hero action

The left-side primary button and the right-side upload card open the same file input. This is one action with two affordances, not competing workflow choices.

### Upload workbench

The empty state shows an unbranded package reference, supported file types, the demonstration status, and the privacy default. Drag-over changes tone and lift. Once a file is selected, the package reference disappears and the real image fills the proof surface.

### OCR review

Review fields stay hidden until analysis succeeds. Confidence remains visible, low-confidence fields say `需确认`, and selecting a field activates its matching image annotation. Confirmation is the only primary action in this state.

## Guardrails

- Do not expose LangGraph nodes, RAG routes, MCP calls, or roadmap stages to consumers.
- Do not create equal cards for explanatory filler.
- Do not use the generated package as a real product, recommendation, or OCR result.
- Do not label a food simply safe, healthy, or unhealthy.
- Do not rely on hover for essential information.
- Do not merge this visual experiment into `main` without explicit approval.
