---
name: Food Label Health Agent
description: A calm optical Bento workspace for evidence-led food label analysis
colors:
  optical-blue: "#0071E3"
  optical-blue-deep: "#0058B0"
  optical-blue-soft: "#D9ECFF"
  violet: "#6657E8"
  violet-soft: "#E8E5FF"
  optical-pink-soft: "#F5E9F3"
  optical-magenta: "#B34EA6"
  optical-navy: "#18294A"
  canvas: "#F5F5F7"
  surface: "#FFFFFF"
  ink: "#1D1D1F"
  muted-ink: "#6E6E73"
  line: "rgba(29, 29, 31, 0.12)"
  caution: "#8A4B08"
  avoid: "#B42318"
  compatible: "#147A4B"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Display, PingFang SC, sans-serif"
    fontSize: "clamp(3.25rem, 7.2vw, 6rem)"
    fontWeight: 720
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Display, PingFang SC, sans-serif"
    fontSize: "clamp(2rem, 3vw, 3.35rem)"
    fontWeight: 680
    lineHeight: 1.08
    letterSpacing: "-0.03em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, sans-serif"
    fontSize: "1rem"
    fontWeight: 450
    lineHeight: 1.55
  small:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 450
    lineHeight: 1.5
  measurement:
    fontFamily: "SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.7rem"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "0.04em"
rounded:
  small: "12px"
  control: "14px"
  compact-surface: "16px"
  upload-field: "18px"
  mobile-surface: "20px"
  optical-control: "22px"
  inner-surface: "24px"
  workspace: "28px"
  bento: "32px"
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
    backgroundColor: "{colors.optical-blue}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "13px 20px"
  button-primary-hover:
    backgroundColor: "{colors.optical-blue-deep}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "13px 20px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "13px 14px"
---

# Design System: Food Label Health Agent

## Overview

**Creative North Star: "The Quiet Optical Bento"**

The interface turns food-label evidence into a small set of calm, touchable rooms. It borrows the spacious composition, oversized cropping, optical color fields, and confident system typography of premium device storytelling, while keeping the product operational rather than promotional.

The user often holds a package in bright supermarket or kitchen light. The surface therefore stays cool and light, with dense black type, a single optical blue action color, and soft blue-violet fields reserved for the label-inspection experience. Bento structure expresses workflow ownership: every room has one job and unequal rooms reflect unequal importance.

**Key Characteristics:**

- One dominant label-input room before recognition; correction appears only when it has content.
- Large headlines and quiet explanatory copy establish an immediate reading order.
- Uploaded label imagery becomes the visual hero; decoration never replaces evidence.
- Soft optical color fields carry whole regions, not scattered accents.
- Safety meaning always combines text, symbol, and state.

## Colors

The palette combines Apple-like cool whites and ink with one clear action blue and a restrained optical violet.

### Primary

- **Optical Blue** (`#0071E3`): primary actions, active workflow state, selected OCR evidence.
- **Deep Optical Blue** (`#0058B0`): hover, pressed, and high-contrast link states.

### Secondary

- **Optical Violet** (`#6657E8`): image-analysis fields and branded optical objects, never health-risk meaning.

### Neutral

- **Cool Canvas** (`#F5F5F7`): application background under bright ambient light.
- **Pure Surface** (`#FFFFFF`): correction and editable rooms.
- **System Ink** (`#1D1D1F`): headings, controls, and primary copy.
- **Muted System Ink** (`#6E6E73`): explanations and secondary metadata.
- **Hairline** (`rgba(29, 29, 31, 0.12)`): field boundaries and separators.

### Semantic

- **Caution Brown** (`#8A4B08`): incomplete or uncertain information.
- **Avoid Red** (`#B42318`): confirmed hard-constraint conflicts.
- **Compatible Green** (`#147A4B`): compatible under confirmed information, never absolute safety.

**The Whole-Field Rule.** Blue and violet may fill an entire inspection region; semantic colors appear only when the interface can name the state they encode.

## Typography

**Display Font:** system SF Pro Display with PingFang SC fallback

**Body Font:** system SF Pro Text with PingFang SC fallback

**Measurement Font:** SFMono-Regular with Menlo fallback

**Character:** The typography is direct, large, and consumer-readable. System faces keep Chinese and English balanced and avoid an external font dependency.

### Hierarchy

- **Display** (720, `clamp(3.25rem, 7.2vw, 6rem)`, 0.98): one consumer promise in the opening viewport.
- **Headline** (680, `clamp(2rem, 3vw, 3.35rem)`, 1.08): room purpose and major outcomes.
- **Body** (450, `1rem`, 1.55): explanations with a maximum measure near 70 characters.
- **Measurement** (650, `0.7rem`, 1.4): confidence, dates, units, and evidence provenance only.

**The Plain-Language Rule.** Consumer meaning is large and immediate; technical metadata is present but never visually leads.

## Layout

Before recognition, desktop uses one centered label-input room so the upload action has no competitor. After recognition, the workspace progressively becomes a 12-column composition: the label image owns seven columns and the correction form owns five.

Rooms use 24px gaps and 28px outer radii. Below 1040px the recognized workbench becomes one column in task order. Below 760px, all interactive targets stay at least 44px and surface radii reduce to 22px.

## Elevation & Depth

The system is mostly tonal. The outer Bento rooms do not float; only the active proof sheet is physically lifted over its optical field.

- **Proof Lift** (`0 30px 70px rgba(43, 50, 74, 0.16)`): the uploaded label proof.
- **Control Lift** (`0 10px 28px rgba(29, 29, 31, 0.12)`): drag-over and temporary control elevation.

**The Evidence Lift Rule.** Elevation belongs to the evidence currently being inspected, not every container.

## Shapes

Outer Bento rooms use 32px corners, internal proof surfaces use 24px, and fields and controls use 14px. Pills are reserved for compact state labels. Circles are used for optical objects, step indexes, and concise symbols.

## Components

### Buttons

- **Shape:** compact rounded rectangle (`14px`) with a minimum height of 44px.
- **Primary:** Optical Blue on white with a direct action label.
- **Hover / Focus:** blue deepens and gains offset depth; keyboard focus uses a visible white-and-blue ring.

### State Tags

- State text sits on a low-contrast neutral pill.
- Risk cannot rely on color alone.
- Confidence is written as `OCR 62% · 需确认`.

### Workspace Rooms

- The input room uses one full optical field; the correction room is plain white.
- The correction room is hidden until OCR results exist.
- Generic icon-heading-text card repetition is not part of the system.

### Inputs / Fields

- White background, hairline stroke, and 14px corners.
- Focus changes the border to Optical Blue and adds an external focus field.
- Low-confidence fields preserve OCR candidate text and show a recovery instruction.

### Label Proof

The signature room synchronizes uploaded imagery, OCR markers, and editable fields. Uploaded evidence is the visual hero. Synthetic OCR is always labeled as demonstration data.

## Do's and Don'ts

### Do:

- **Do** let one meaningful image or task dominate each viewport.
- **Do** use unequal Bento rooms to communicate priority.
- **Do** reveal correction controls only after recognition succeeds.
- **Do** show the label beside the exact text being confirmed.
- **Do** keep uncertainty and recovery actions visible before interpretation.
- **Do** reserve full optical color fields for input, inspection, and product identity.

### Don't:

- **Don't** copy Apple product imagery, copywriting, or proprietary assets.
- **Don't** turn every fact into an equal card.
- **Don't** expose roadmap stages, Agent routing, or implementation terminology to consumers.
- **Don't** assign an absolute health score or imply medical clearance.
- **Don't** use gradient text or decorative glass panels.
- **Don't** use green alone to mean safe.
