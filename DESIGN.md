---
name: Sovereign AI Workbench
description: On-premise, governed industrial intelligence. Control-room night outside, calm daylight inside.
colors:
  brand-navy: "#020e21"
  night-surface-0: "#010a18"
  night-surface-1: "#041329"
  night-surface-2: "#081d38"
  night-surface-3: "#0e2a4c"
  night-line: "rgba(128, 176, 232, 0.16)"
  night-line-strong: "rgba(128, 176, 232, 0.34)"
  night-text: "#e8eff8"
  night-text-muted: "#a3b4ca"
  night-text-faint: "#71859f"
  nameplate-white: "#f5f9fe"
  signal-white: "#eef6fb"
  cta-ink: "#031226"
  instrument-cyan: "#35d7e8"
  instrument-cyan-soft: "#8fe3f0"
  night-agent-blue: "#3d8bff"
  night-flow-green: "#2fe0a4"
  night-review-amber: "#f2a93b"
  night-knowledge-violet: "#8b6cff"
  night-danger: "#ef5b5f"
  daylight-field: "#f3f5f8"
  daylight-surface: "#ffffff"
  daylight-surface-2: "#f4f7fb"
  daylight-surface-3: "#e6edf6"
  daylight-line: "rgba(20, 45, 80, 0.14)"
  daylight-line-strong: "rgba(20, 45, 80, 0.3)"
  daylight-ink: "#0b1a2e"
  daylight-ink-muted: "#3f5570"
  daylight-ink-faint: "#5d7089"
  workbench-blue: "#1d63d6"
  workbench-teal: "#096b76"
  verified-green: "#1c7c48"
  review-amber: "#9a5b00"
  error-red: "#b3261e"
  knowledge-violet: "#5a3fd1"
  stale-grey: "#9aa4b2"
  chart-1: "#2563eb"
  chart-2: "#0f8a80"
  chart-3: "#7c3aed"
  chart-4: "#c26a00"
typography:
  display:
    fontFamily: "Archivo, Segoe UI Variable Display, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(3rem, 5.6vw, 5.5rem)"
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: "-0.035em"
    fontVariation: "'wdth' 112"
  headline-brand:
    fontFamily: "Archivo, Segoe UI Variable Display, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(1.9rem, 3.2vw, 2.6rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.025em"
    fontVariation: "'wdth' 108"
  auth-title:
    fontFamily: "Archivo, Segoe UI Variable Display, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(2.5rem, 4.4vw, 4.4rem)"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.035em"
    fontVariation: "'wdth' 110"
  headline:
    fontFamily: "Segoe UI Variable Display, Inter, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(1.9rem, 3.2vw, 2.6rem)"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Segoe UI Variable Display, Inter, Segoe UI, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, Segoe UI Variable Text, Segoe UI, system-ui, Noto Sans, Nirmala UI, Noto Sans Devanagari, Noto Sans Tamil, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: "Inter, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    letterSpacing: "0.08em"
  data:
    fontFamily: "Inter, Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    fontFeature: "'tnum' 1"
  mono:
    fontFamily: "JetBrains Mono, Cascadia Code, Consolas, ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 700
rounded:
  sm: "6px"
  md: "10px"
  lg: "16px"
  xl: "24px"
  pill: "999px"
spacing:
  "1": "0.25rem"
  "2": "0.5rem"
  "3": "0.75rem"
  "4": "1rem"
  "5": "1.5rem"
  "6": "2rem"
  "7": "3rem"
  "8": "4rem"
  "9": "6rem"
components:
  button-landing-primary:
    backgroundColor: "{colors.signal-white}"
    textColor: "{colors.cta-ink}"
    rounded: "{rounded.pill}"
    padding: "0 2rem"
    height: "50px"
  button-landing-primary-hover:
    backgroundColor: "{colors.daylight-surface}"
  button-landing-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.night-text}"
    rounded: "{rounded.pill}"
    padding: "0 2rem"
    height: "50px"
  button-auth-submit:
    backgroundColor: "{colors.signal-white}"
    textColor: "{colors.cta-ink}"
    height: "48px"
    width: "100%"
  button-workbench-primary:
    backgroundColor: "{colors.workbench-blue}"
    textColor: "{colors.daylight-surface}"
    rounded: "{rounded.md}"
    padding: "0 1rem"
    height: "40px"
  button-workbench-default:
    backgroundColor: "{colors.daylight-surface-3}"
    textColor: "{colors.daylight-ink}"
    rounded: "{rounded.md}"
    padding: "0 1rem"
    height: "40px"
  button-danger:
    backgroundColor: "{colors.daylight-surface}"
    textColor: "{colors.error-red}"
    rounded: "{rounded.md}"
    height: "44px"
  input-workbench:
    backgroundColor: "{colors.daylight-surface}"
    textColor: "{colors.daylight-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    height: "42px"
  input-auth:
    backgroundColor: "rgba(1, 8, 20, 0.6)"
    textColor: "{colors.night-text}"
    height: "46px"
  card-workbench:
    backgroundColor: "{colors.daylight-surface}"
    textColor: "{colors.daylight-ink}"
    padding: "1.5rem"
  panel-workbench:
    backgroundColor: "{colors.daylight-surface}"
    rounded: "{rounded.lg}"
    padding: "1.5rem"
  nav-link-active:
    backgroundColor: "color-mix(in srgb, #1d63d6 10%, #ffffff)"
    textColor: "{colors.workbench-blue}"
    rounded: "{rounded.md}"
    padding: "0.5rem 0.75rem"
  chip-status-ok:
    backgroundColor: "color-mix(in srgb, #1c7c48 11%, #ffffff)"
    textColor: "{colors.verified-green}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  chip-status-warn:
    backgroundColor: "color-mix(in srgb, #9a5b00 12%, #ffffff)"
    textColor: "{colors.review-amber}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  chip-status-bad:
    backgroundColor: "color-mix(in srgb, #b3261e 10%, #ffffff)"
    textColor: "{colors.error-red}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  auth-instrument-card:
    backgroundColor: "rgba(4, 13, 28, 0.64)"
    textColor: "{colors.night-text}"
    padding: "clamp(1.5rem, 3.2vw, 2.5rem)"
---

# Design System: Sovereign AI Workbench

## Overview

**Creative North Star: "The Control Room and the Day Shift"**

One product, two registers, split by the login. The public side (landing `/` and authentication `/login`, `/signup`, recovery) is **control-room night**: a brand-navy field, cyan and teal instrument light used as signal rather than decoration, a P&ID-style perspective grid, and Archivo set wide like an equipment nameplate. The approved Sovereign mark forms from particles in raw WebGL, and the approved auth footage runs behind the sign-in form. Everything there argues that the intelligence runs inside the plant.

Past the login, the `/app` workbench is the **day shift**: an off-white field, white work surfaces, navy and slate ink, one restrained blue for action and selection, and state colours that mean one thing each. It is built for long shifts. Density is moderate, motion is short and exponential, and every figure on screen is live or plainly marked empty. The workbench uses no glow, no WebGL, no footage and no display face.

The registers share one token file, the same spacing and radius scales, the same UI sans, and the same semantic roles (agent, human review, knowledge, ok, danger). Only the values flip. Surfaces pick a register with `data-theme`: landing and auth pin `dark`, and the workbench defaults to `light` (operators can switch it to dark).

**Key Characteristics:**
- Two registers split at the login: cinematic dark for Persuade, calm light for Operate.
- Instrument light: cyan marks signal (the spine, active stations, the sovereign boundary, focus), never fills.
- Archivo expanded appears only on landing and auth. The workbench speaks in its UI sans.
- White pill buttons on the night side; blue 10px-radius buttons on the day side.
- Semantic colour is fixed: blue for agent and action, amber for human review, green only for verified or healthy, red only for errors.
- Honest state is a visual element: empty, loading, planned and stale each have a stated form.

## Colors

The palette is a navy night with cyan instrument light on the public side and a cool off-white daylight with a single blue accent in the workbench. Semantic roles carry across both.

### Primary
- **Brand Navy** (`brand-navy`): the landing and auth field, sampled from the approved brand boards so logo crops blend in. In the workbench it survives only as the badge behind the white wordmark in the top bar.
- **Instrument Cyan** (`instrument-cyan`): night-side signal: the scroll spine, P&ID tag bubbles, active workflow stations, the sovereign boundary line, auth input focus and OCR boxes. **Instrument Cyan Soft** (`instrument-cyan-soft`) is its text form: the highlighted phrase of the hero headline and tag-bubble labels.
- **Workbench Blue** (`workbench-blue`): the one day-side accent. It marks primary buttons, the active nav item, the current view in segmented controls, card links, the selected work order, open-work bars, and focus rings.

### Secondary
- **Signal White** (`signal-white`) on **CTA Ink** (`cta-ink`): the night-side primary button. It goes to pure white on hover. It is quiet because it is achromatic, and the cyan stays reserved for signal.
- **Workbench Teal** (`workbench-teal`): day-side secondary accent for inspection-type work orders and plain links. Chosen for AA on every light surface.

### Tertiary (semantic roles, both registers)
- **Review Amber** (`review-amber` day, `night-review-amber` night): human attention. Used for items awaiting review, H3 transcript flags, thresholds, the "planned" badge, corrective work orders, disclaimers and disabled-capability notices.
- **Verified Green** (`verified-green`): verified, healthy or confirmed state only, such as connected signal dots, ok status chips, checked flags and decision acknowledgements. The night side also has **Flow Green** (`night-flow-green`), which appears only at the far end of the workflow progress gradient and in hash codes in the audit chain.
- **Error Red** (`error-red` day, `night-danger` night): errors, invalid fields and reject actions only.
- **Knowledge Violet** (`knowledge-violet`, `night-knowledge-violet`): knowledge and vision evidence, including vision boxes on P&ID figures.
- **Stale Grey** (`stale-grey`): unknown or stale state dots.

### Neutral
- **Night surfaces** (`night-surface-0` to `night-surface-3`): tonal steps above the navy. Landing cards use translucent night-surface-1 (`rgba(4, 19, 41, 0.75–0.9)`) so the grid and particles read through.
- **Night text** (`night-text`, `night-text-muted`, `night-text-faint`): body, supporting copy and captions on the dark side. **Nameplate White** (`nameplate-white`) is used only for Archivo headlines.
- **Daylight Field** (`daylight-field`): the workbench page background. **Daylight Surface** (`daylight-surface`) is the card, panel, nav and top bar surface. `daylight-surface-2` is used for nested wells, hover rows and kanban columns, and `daylight-surface-3` for tracks, segmented-control beds and default buttons.
- **Daylight ink** (`daylight-ink`, `daylight-ink-muted`, `daylight-ink-faint`): navy-slate text. Faint ink is kept at AA on the field.
- **Lines** (`night-line`/`-strong`, `daylight-line`/`-strong`): 1px hairlines are the main structural device in both registers.
- **Chart series** (`chart-1` to `chart-4`): blue, teal, violet and amber, in that order. Night-side equivalents: `#60a5fa`, `#2dd4bf`, `#a78bfa`, `#fbbf24`.

### Named Rules
**The Register Rule.** Landing and auth are always `data-theme="dark"`. The `/app` workbench defaults to light. No public surface goes light, and no workbench surface borrows the cinematic devices (WebGL, footage, glow, Archivo).

**The Signal-Not-Decoration Rule.** Cyan on the night side marks something live, active or bounded: a line, a stroke, a focus ring, a highlighted phrase. It never fills a large area or a button.

**The One-Meaning Rule.** In the workbench, green means verified or healthy, amber means a human must look, and red means error. Workbench Blue marks action and selection and never stands in for status.

## Typography

**Display Font:** Archivo variable (self-hosted, SIL OFL; width axis 62–125%), with Segoe UI Variable Display and system-ui fallbacks.
**Body Font:** Inter, then Segoe UI Variable Text and system-ui, with Nirmala UI and Noto Sans Devanagari/Tamil so Hindi and Tamil render natively offline.
**Label/Mono Font:** JetBrains Mono, then Cascadia Code and Consolas.

**Character:** Archivo, bold and stretched to 108–125%, reads like the stamped nameplate on a pump. The workbench drops it entirely and relies on one neutral UI sans with tabular numerals. Mono marks machine facts: tag bubbles, station indices, hash blocks, OCR labels.

### Hierarchy
- **Display** (Archivo 700, wdth 112, `clamp(3rem, 5.6vw, 5.5rem)`, 0.98): the landing hero headline only. It is split into masked lines, and the key phrase is set in Instrument Cyan Soft.
- **Auth Title** (Archivo 700, wdth 110, `clamp(2.5rem, 4.4vw, 4.4rem)`, 1.02): the story line on each auth route.
- **Headline Brand** (Archivo 700, wdth 108, `clamp(1.9rem, 3.2vw, 2.6rem)`, 1.05, balanced wrap): landing section headings.
- **Ghost wordmark** (Archivo 900, wdth 125, `clamp(7rem, 23vw, 25rem)`, outline-only 1px stroke at 16% opacity): "SOVEREIGN" behind the hero sculpture. It is masked so it never runs behind the copy column.
- **Headline** (UI stack 700, `clamp(1.9rem, 3.2vw, 2.6rem)`, 1.1): workbench page titles.
- **Title** (700, 1.125rem): workbench card and panel titles. Review panes step up to 1.75rem at -0.02em.
- **Body** (400, 1rem, 1.6): running text. Page descriptions are capped at 72ch and landing story copy at 640px.
- **Data** (700, 1.375–1.75rem, tabular numerals): counts and metric values, set beside a plain-language unit ("1 draft awaits human review").
- **Label** (700, 0.75rem, 0.08–0.12em tracking, uppercase): sidebar group names, metric labels, and evidence-type labels (Observation / Hypothesis / Verify). Labels always name the content they sit on.
- **Mono** (700, 11–14px): P&ID tag bubbles, workflow station indices, the sovereign boundary label, hash-chain blocks.

### Named Rules
**The Nameplate Rule.** Archivo is for the night side only, always bold and stretched. The workbench never uses it.

**The Tabular Rule.** Every live number in the workbench uses tabular numerals so values do not jitter on refresh.

## Layout

**Night side.** Story sections are at least 100vh for pinned scenes and 72vh otherwise, with inline padding `clamp(2rem, 8vw, 9rem)` and a 6rem block rhythm. The hero is a left copy column (max `min(42rem, 46vw)`) with the WebGL sculpture on the right, over a copy-side scrim for legibility. Content sections use two-column grids (1fr / 1–1.2fr) with 3rem gaps. A fixed cyan spine runs down the left edge and carries P&ID tag bubbles. At 900px the sculpture moves to the top 38% of the viewport. Below 1024px the grids stack, and below 760px the spine and header nav hide. Auth uses a story column plus a fixed 440px instrument card inside a 1320px frame. On phones the card rises as a bottom sheet over visible footage.

**Day side.** The shell is a 264px sticky sidebar plus a 64px sticky blurred top bar. Main padding is 2rem block and `clamp(1rem, 3vw, 3rem)` inline. The dashboard is a 3-column grid (2 at 1280px, 1 at 760px) with 1.5rem gaps and `span-2` feature cards. It opens with a single signals strip (one sentence of status, divided by hairlines), not a wall of tiles. Work surfaces use a list-plus-inspector split (kanban with a 340px sticky inspector, review desk with a 300px sticky queue), which collapses to one column at 1100–1180px. The sidebar becomes a drawer below 1024px. Wide tables scroll inside their card, never the page. Form inputs cap at 40rem.

Spacing follows the 4px-based `spacing` scale in both registers.

## Elevation & Depth

**Night side.** Depth comes from light, not shadow: radial navy-to-deep-blue gradients, the WebGL grid floor and horizon light, translucent cards over moving particles, and a bottom fade into the navy. Shadows are long, soft and dark (`0 18px 40px -18px rgba(0,0,0,0.7)`, and `0 50px 120px -30px` under the workbench reveal frame). The only glow is on the sovereign core node, the enter mark, and auth input focus. The auth card is the one glass surface (28px blur, 150% saturate over footage, for legibility), with a single inset top highlight.

**Day side.** Surfaces are hairline-bordered and lifted only slightly. Cards rest on `shadow-1` and rise to `shadow-2` on hover. Floating layers (menus, drawer, sticky decision bar) use `shadow-3`, and the command palette uses its own deeper drop over a lightly blurred backdrop.

### Shadow Vocabulary
- **Rest** (`0 1px 2px rgba(15, 35, 65, 0.06)`): cards, panels, signals strip, work-order cards.
- **Lift** (`0 8px 24px rgba(15, 35, 65, 0.08)`): card hover, chart tooltip, open inspector.
- **Float** (`0 18px 48px rgba(15, 35, 65, 0.14)`): menus, mobile nav drawer, sticky decision bar.
- **Selection halo** (`0 0 0 3px` at 18% of the accent): selected work order, healthy signal dot.

### Named Rules
**The Light-Is-Depth Rule.** On the night side, depth comes from light sources and translucency. On the day side it comes from hairlines and three soft shadows. Neither side uses hard offset shadows.

## Shapes

Corners are consistently soft. Controls and inputs use 10px, panels and cards 16px, large figures 24px, and badges, chips, fact pills and the night-side CTAs are fully round. Status dots are circles (7–9px). Structure is drawn with 1px hairlines. Dashed strokes mean something provisional or bounded: planned features, the empty inspector, the sovereign network boundary, OCR boxes, and review hypotheses. Solid strokes mean observed fact.

**The Dashed-Means-Provisional Rule.** A dashed border or stroke signals planned, empty, hypothetical or a boundary. Never use it as decoration.

## Components

### Buttons
- **Shape:** 10px radius in the workbench (`rounded.md`); full pill on landing CTAs; 12px on the full-width auth submit.
- **Night primary:** Signal White on CTA Ink, 50px tall, `0 2rem` padding. Goes to pure white on hover.
- **Night ghost:** transparent with a 22% white border that strengthens to 50% on hover.
- **Workbench primary:** Workbench Blue with white text, 40px tall. On hover it mixes 14% toward the ink colour.
- **Workbench default:** surface-3 bed with a strong hairline. The border turns teal on hover.
- **Danger:** white surface, red text and a 45% red border, with a light red wash on hover. Decision buttons are at least 150×44px.
- **Press:** `scale(0.98)` at 120ms, with no bounce. Focus is always a 3px outline in the register's focus colour, offset 3px.

### Chips
- **Status chip:** pill, 12px bold, a currentColor dot before the text, and a tinted fill (ok green 11%, warn amber 12%, bad red 10% over white).
- **Series chip:** pill toggle with a colour key. When pressed off it drops to 60% opacity and the key becomes an outline.
- **Top-bar pills:** a status dot plus a short fact ("Backend connected", "0 hosted AI calls").

### Cards / Containers
- **Corner Style:** 16px (`rounded.lg`) for panels, route cards and kanban columns.
- **Background:** Daylight Surface on the field. Nested wells use surface-2.
- **Shadow Strategy:** Rest, then Lift on hover (see Elevation).
- **Border:** 1px `daylight-line`.
- **Internal Padding:** 1.5rem for cards and panels, 1rem for nested cards, 2rem for the review pane.

### Inputs / Fields
- **Workbench:** 42px, white, strong hairline, 10px radius. Invalid fields get a red border. Disabled fields drop to 55% opacity.
- **Auth:** 46px, `rgba(1, 8, 20, 0.6)`, cyan-tinted hairline, 12px radius. Focus sets the border to `#5ad8e8` with a 4px cyan halo at 18%.

### Navigation
- **Workbench sidebar:** grouped (Operate / Evidence / Knowledge / Govern / Trust) under uppercase labels. Links are 14px/600 in muted ink with a surface-2 hover. The active link gets a 10% blue wash, blue text and a blue icon.
- **Top bar:** 88% white with a 14px blur; brand wordmark on a navy badge; pill search trigger with a keyboard hint; status pills; language select; theme toggle; user menu.
- **Landing header:** fixed, 78% navy with a 14px blur and a hairline bottom. Text links in muted night text plus a white pill "Sign in". The links hide below 760px.

### Signals Strip (signature, workbench)
A single white bar of 5 hairline-divided cells. Each cell has a state dot, a small label and a bold tabular value, and links to its source. A pending dot breathes at 1.4s.

### Particle Mark and Spine (signature, landing)
Raw-WebGL particles assemble the approved Sovereign mark over a receding P&ID grid floor. They part around the pointer and disperse on scroll. With reduced motion, Save-Data or no WebGL, a still image replaces them. A fixed rail carries pulses of cyan light that stream down as the page scrolls and flare with scroll speed, with circular mono tag bubbles (P&ID instrument-tag form) marking each section.

### Atmosphere and Glass (signature, landing)
One fixed raw-WebGL backdrop runs from the hero to the footer (`atmosphere.js`). It is domain-warped smoke in navy, blue and a cold indigo undertone, softly lit where the cursor is. Cursor movement pushes the smoke in the direction of travel and briefly quickens it; scroll lifts it at a slower rate than the page. No beams or laser lines: they read as overstated and were removed at the owner's request. It renders at half resolution, pauses when the tab is hidden, draws a single still frame under reduced motion, and falls back to the CSS gradient under Save-Data or when WebGL is unavailable. Story panels (`[data-glass]`) are frosted glass over it: 16px backdrop blur, a top-lit sheen, an inset highlight edge and a cyan under-glow. On fine pointers they tilt toward the cursor (8° at most, less for large panels), drift up to 6px after it, and light the face and the edge nearest to it. Section headlines resolve word by word out of a blur.

### Auth Instrument (signature, auth)
The approved footage is graded toward navy, pushed in slowly over 32s, crossfaded between routes, and overlaid with film grain at 7% opacity. On top sits one glass card at 26px radius with a single inset highlight edge. A live-backend pill with a state dot sits in the top bar. Content is visible by default; motion only adds a short rise with a blur-in.

### Motion
Motion is exponential (`cubic-bezier(0.16, 1, 0.3, 1)`) and always starts from visible content. Charts draw their lines in 1.2s and grow bars with a 28ms stagger. Page changes cross-fade only the main pane (140ms out, 320ms in). Everything is gated by `prefers-reduced-motion`.

## Do's and Don'ts

### Do:
- **Do** pick the register by surface: `data-theme="dark"` for landing and auth, the light default for everything under `/app`.
- **Do** keep night-side cyan to lines, strokes, focus and one highlighted phrase. Primary actions there are Signal White pills.
- **Do** use Workbench Blue as the only day-side action and selection colour, and reserve green, amber and red for verified, review and error.
- **Do** set every live workbench number in tabular numerals next to a plain-language unit.
- **Do** give every empty, loading, planned or stale state a visible form: dashed for planned or empty, a breathing dot for pending, grey for stale.
- **Do** use dashed strokes only for provisional, hypothetical or boundary meaning.
- **Do** ship a still fallback for every WebGL or video surface under reduced motion, Save-Data or no WebGL.

### Don't:
- **Don't** bring Archivo, glow, WebGL, footage or navy fields into the `/app` workbench.
- **Don't** fill buttons or large areas with Instrument Cyan.
- **Don't** use green for anything that is not verified or healthy.
- **Don't** use hard offset shadows in either register.
- **Don't** redraw or recolour the approved logos. On light surfaces, place the white wordmark on a Brand Navy badge.
- **Don't** put a small uppercase label above a heading as a kicker. Uppercase labels name the content they sit on (nav groups, metrics, evidence types).
