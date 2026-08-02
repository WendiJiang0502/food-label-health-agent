---
name: Food Label Health Agent
description: A packaging proofing desk for evidence-led food label analysis
colors:
  proof-blue: "#185ADB"
  proof-blue-deep: "#0D3FA3"
  inspection-orange: "#F26B38"
  paper: "#F4F5F1"
  sheet: "#FFFFFF"
  ink: "#17201B"
  muted-ink: "#536159"
  rule: "#CDD4CE"
  caution: "#A85608"
  avoid: "#B42318"
  compatible: "#176B45"
typography:
  display:
    fontFamily: "Avenir Next, Avenir, PingFang SC, sans-serif"
    fontSize: "clamp(2.25rem, 5vw, 4.75rem)"
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Avenir Next, Avenir, PingFang SC, sans-serif"
    fontSize: "clamp(1.5rem, 2.5vw, 2.5rem)"
    fontWeight: 650
    lineHeight: 1.12
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Avenir Next, Avenir, PingFang SC, sans-serif"
    fontSize: "1rem"
    fontWeight: 450
    lineHeight: 1.65
  title:
    fontFamily: "Avenir Next, Avenir, PingFang SC, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 650
    lineHeight: 1.14
  small:
    fontFamily: "Avenir Next, Avenir, PingFang SC, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 450
    lineHeight: 1.5
  measurement:
    fontFamily: "SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.02em"
rounded:
  field: "10px"
  surface: "14px"
  compact: "4px"
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
    backgroundColor: "{colors.proof-blue}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.field}"
    padding: "13px 20px"
  button-primary-hover:
    backgroundColor: "{colors.proof-blue-deep}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.field}"
    padding: "13px 20px"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "13px 14px"
---

# Design System: Food Label Health Agent

## Overview

**Creative North Star: "The Packaging Proofing Desk"**

The interface borrows from packaging prepress and quality-control work: a label is treated as a proof to inspect, annotate, confirm, and release—not as a lifestyle image to score. The visual system is operational and evidence-led, with a large working surface, registration-like markers, compact measurement text, and visible correction states.

The product is often used under bright supermarket light or at a kitchen table, so the default is a cool light canvas with high-contrast ink. Blue owns primary actions and verified structure; orange marks active inspection; risk colors only communicate actual semantic states.

**Key Characteristics:**

- One dominant proofing workspace rather than a dashboard of equal cards.
- Field confidence and source metadata use measurement typography.
- Risk states always combine icon, label, and explanatory text.
- Controls are compact, tactile, and familiar enough for one-handed mobile use.

## Colors

The palette combines cool proofing paper, dense ink, technical blue, and sparingly used inspection orange.

### Primary

- **Proof Blue** (`#185ADB`): primary actions, active workflow state, selected evidence.
- **Deep Proof Blue** (`#0D3FA3`): hover and pressed states.

### Secondary

- **Inspection Orange** (`#F26B38`): crop marks, current annotation, and active review—not decoration.

### Neutral

- **Proofing Paper** (`#F4F5F1`): application canvas.
- **Clean Sheet** (`#FFFFFF`): editable fields and the label work surface.
- **Registration Ink** (`#17201B`): headings and body text.
- **Muted Ink** (`#536159`): secondary explanations and metadata.
- **Rule Gray** (`#CDD4CE`): dividers and field outlines.

### Semantic

- **Caution Amber** (`#A85608`): incomplete or uncertain information.
- **Avoid Red** (`#B42318`): confirmed hard-constraint conflicts.
- **Compatible Green** (`#176B45`): compatible under confirmed information, never an absolute safety guarantee.

**The Semantic Color Rule.** Orange, amber, red, and green appear only when the interface can name the state they encode.

## Typography

**Display Font:** Avenir Next with Avenir and PingFang SC fallbacks

**Body Font:** Avenir Next with system Chinese sans-serif fallbacks

**Measurement Font:** SFMono-Regular with Menlo and Consolas fallbacks

**Character:** The main face is direct and highly legible in Chinese and English. Monospace is reserved for OCR confidence, identifiers, dates, units, and evidence metadata.

### Hierarchy

- **Display** (700, `clamp(2.25rem, 5vw, 4.75rem)`, 0.98): the upload task and no more than one message per viewport.
- **Headline** (650, `clamp(1.5rem, 2.5vw, 2.5rem)`, 1.12): workbench sections and major outcomes.
- **Body** (450, `1rem`, 1.65): explanations with a maximum measure of 70 characters.
- **Measurement** (600, `0.75rem`, 1.4): confidence, version, field type, source, and unit data.

**The Measurement Rule.** Monospace communicates measurement or provenance; it never acts as a generic technical costume.

## Layout

Desktop uses a 12-column workbench: the label proof owns seven columns and the review rail owns five. The first viewport gives most space to the upload and proof, with risk summary occupying a persistent but subordinate rail. Mobile collapses to one column in task order: upload, preview, fields requiring confirmation, then analysis.

The outer canvas uses a maximum width of 1440px and 24–40px gutters. Within the proofing surface, dense field rows use 12–16px gaps; major stages use 40–72px separation. At widths below 760px, primary actions become full-width and all touch targets remain at least 44px high.

## Elevation & Depth

The system is flat by default. Depth comes from tonal separation and one structural shadow under the active proof sheet. Fields use borders without simultaneous shadows.

- **Proof Lift** (`0 18px 48px rgba(23, 32, 27, 0.12)`): only the active label proof or upload sheet.
- **Control Lift** (`0 6px 18px rgba(23, 32, 27, 0.10)`): temporary drag-over or floating mobile action state.

**The Single Lift Rule.** At most one large surface appears physically lifted in a viewport.

## Shapes

The proofing sheet uses 14px corners; editable fields and buttons use 10px; technical tags and crop markers use 4px. Pills are reserved for compact state labels. Borders are one pixel and structural, never paired with an ambient shadow on the same resting component.

## Components

### Buttons

- **Shape:** compact rounded rectangle (`10px`) with a minimum height of 44px.
- **Primary:** Proof Blue on white, 13px × 20px padding.
- **Hover / Focus:** deepens to Proof Blue Deep; focus uses a visible two-part blue-and-white outline.
- **Secondary:** transparent Registration Ink with a Rule Gray border.

### State Tags

- Combine a short state label with an icon or symbol.
- Use semantic color only for actual risk or workflow state.
- Confidence is expressed as text such as `OCR 62% · 需确认`, never color alone.

### Cards / Containers

- Large equal-weight card grids are not part of the system.
- Use one proofing sheet, flat side rails, and divided rows.
- A contained panel must have a task role such as upload, correction, evidence, or risk review.

### Inputs / Fields

- White background, Rule Gray stroke, 10px corners.
- Focus changes the border to Proof Blue and adds an external focus outline.
- Low-confidence fields show the original OCR candidate and a recovery instruction.
- Error and disabled states retain readable labels and do not rely on reduced opacity alone.

### Navigation

Navigation is a quiet horizontal utility bar on desktop and a compact top bar on mobile. The product mark, workflow state, and privacy indicator remain visible; secondary navigation never competes with the upload action.

### Label Proof

The signature component shows the uploaded image, field markers, and a synchronized correction list. Selecting a field highlights both its image region and editable text. In the current milestone, synthetic OCR output is explicitly labeled as demonstration data.

## Do's and Don'ts

### Do:

- **Do** show the label image beside the text the user is confirming.
- **Do** put critical uncertainty before ingredient education or product recommendations.
- **Do** keep source, date, confidence, and rule identity readable but visually secondary.
- **Do** write recovery actions that name exactly what the user should photograph or correct.

### Don't:

- **Don't** assign an absolute health score or imply medical clearance.
- **Don't** use green alone to mean safe.
- **Don't** structure the application as a grid of generic metric cards.
- **Don't** use food illustrations as a substitute for the user's actual label evidence.
