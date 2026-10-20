# DESIGN_SYSTEM.md — Kavach Console

> Visual rules for `apps/console/`. Every screen an AI agent generates **for the
> Kavach console** must obey this file, so the console reads as one instrument
> rather than a folder of pages.

---

## 0. Jurisdiction — what this document governs

**This document governs `apps/console/` and nothing else.**

| In scope | Out of scope |
|---|---|
| `apps/console/` — the Kavach operations console, Next.js 15 / Tailwind v4 / shadcn/ui | **The system under management's frontend.** `Simple_RAG-Pipeline`, the first reference workload, ships its own Next.js 14 / Tailwind 3 / lucide-react chat UI (`PRD.md` §5.1). It is an independent application with its own conventions |

**The console is a Kavach surface, not a RAG surface.** It renders incidents, evidence, diagnoses, actions and verification — the generic vocabulary of `ARCHITECTURE.md` §1.3. Where it currently shows workload-specific rows (`threshold`, `corpus`, a "grounded" case result), that is the first adapter's vocabulary leaking into a generic view, and it is recorded as debt in §1.4. Do not add more of it: a second workload must not require a second console.

Do not restyle, retokenise, or "bring into line" the target's UI. It is not a Kavach surface, it is the application Kavach is watching, and changing it is outside the eleven permitted target additions (`PRD.md` §5.2). `AGENTS.md` § Target boundary rule 11 says the same thing from the other direction.

One consequence worth stating because it looks like an inconsistency otherwise: the console is Next.js **15** with Tailwind **v4**, while the target is Next.js **14** with Tailwind **3**. That is two separate applications on two separate version tracks, not a migration anyone forgot to finish.

`docs/DESIGN-cursor.md` is **visual reference material only** and carries no authority. Where it disagrees with this file, this file wins.

---

## 1. Visual identity: Midnight Operations

**What this product is:** an instrument panel for a machine that is allowed to change your production system without asking. The person looking at it is deciding whether to trust it.

**The emotional job is therefore not "sleek AI product." It is trust under uncertainty.** Every design decision below serves one of three questions the user is silently asking:

1. What is happening right now?
2. How sure is the system, and on what evidence?
3. What is it about to do to me, and can it be undone?

**Direction — Midnight Operations:**
- **Surfaces:** Deep charcoal and deep-slate surfaces (`#070a11`, `#0f1724`, `#162032`) instead of flat black or generic gray backgrounds.
- **Accents:** Cyan (`#22d3ee`) and teal (`#14b8a6`) accents for primary actions, selected navigation, active telemetry, and interactive focus.
- **Secondary Accent:** Indigo (`#7c7cf5`) as a restrained secondary accent in the Loop Ring gradient and diagnostic reasoning.
- **Typography:** Refined typography with clear hierarchy, consistent spacing, subtle borders, and carefully controlled depth (GeistSans display and body, JetBrains Mono for machine tokens and tabular numbers).
- **Telemetry & Charts:** High-quality metrics with readable axes, useful tooltips, clear time ranges, and restrained grid lines.
- **Semantic Operational Colors:** Green for verified healthy states (`#3dd68c`), amber for warnings, degraded performance, and mitigated debt (`#f59e0b`), and red for genuine failures and escalations (`#f43f5e`).
- **Depth & Restrained Glow:** Subtle depth and controlled glow (`box-shadow: 0 0 16px -2px rgba(34, 211, 238, 0.2)`) only around selected active or highlighted elements. Avoid excessive neon, glowing borders everywhere, or a gaming-style appearance.

**The signature element:** the **Loop Ring**. A single cyan→indigo gradient ring (`linear-gradient(135deg, #22d3ee 0%, #7c7cf5 100%)`) that sits on the active incident and advances through the seven loop stages. It is the primary gradient in the product and its rotation is the only non-user-triggered motion.

### 1.1 Rules that follow from the direction

- **Colour is data.** Hue means risk tier or incident state, and nothing else. There is no "brand accent" applied to arbitrary elements.
- **Density over whitespace.** This is an operator's screen. A reviewer should be able to see an entire incident — evidence, diagnosis, plan, risk, verification — without scrolling.
- **Monospace is functional, not stylistic.** It is used only for machine-generated strings: trace IDs, container names, log lines, metric values, diffs, action names. Never for labels or headings. A monospace label would be costume; a monospace trace ID is legibility.
- **No decorative cards.** A bordered surface means "this is a discrete object with its own state." If the content has no state, it does not get a border.

---

## 2. Colour tokens

Dark is the primary theme and must be correct first. Light theme is a secondary obligation, not a design driver.

### 2.1 Base palette

```css
:root,
:root[data-theme="dark"] {
  /* Ground — deep charcoal/slate, not flat black or neutral grey. */
  --k-bg:            #070a11;   /* page floor */
  --k-surface:       #0f1724;   /* panels, cards */
  --k-surface-raised:#162032;   /* popovers, modals, active/hovered rows */
  --k-surface-sunken:#05080e;   /* log streams, code, diffs, inset panes */

  /* Structure */
  --k-border:        #223249;   /* quiet default border */
  --k-border-strong: #354c6d;   /* focused / active object, input borders */
  --k-border-subtle: #172335;   /* internal rules inside a panel */

  /* Type */
  --k-text:          #f0f4fc;   /* crisp primary text */
  --k-text-muted:    #94a7c1;   /* secondary labels, metadata */
  --k-text-faint:    #627794;   /* timestamps, disabled, placeholder */
  --k-text-inverse:  #070a11;   /* on filled signal surfaces */

  /* Focus & active glow */
  --k-glow-subtle:   0 0 16px -2px rgba(34, 211, 238, 0.2);
}
```

### 2.2 Signal palette — risk

Risk is the user's primary anxiety. It gets the clearest, most separable hues.

```css
  --k-risk-low:      #3dd68c;   /* auto-executable · verified healthy */
  --k-risk-low-bg:   #09261a;
  --k-risk-med:      #f59e0b;   /* sandbox / approval · degraded / warning */
  --k-risk-med-bg:   #291b07;
  --k-risk-high:     #f43f5e;   /* human only · breach / failure */
  --k-risk-high-bg:  #2c0e14;
  --k-risk-denied:   #8fa3bf;   /* blocked by allow-list or breaker */
  --k-risk-denied-bg:#162032;
```

### 2.3 Signal palette — incident state

Deliberately a different hue family from risk, so a user never confuses "this is dangerous" with "this is in progress."

```css
  --k-state-detected:  #38bdf8;  /* breach raised */
  --k-state-collecting:#38bdf8;
  --k-state-diagnosing:#9b8cfa;  /* the LLM is reasoning */
  --k-state-awaiting:  #f59e0b;  /* blocked on a human */
  --k-state-healing:   #22d3ee;  /* executing */
  --k-state-verifying: #7c7cf5;  /* probing */
  --k-state-resolved:  #3dd68c;
  --k-state-rolledback:#f58a47;  /* distinct from both resolved and escalated */
  --k-state-escalated: #f43f5e;
```

### 2.4 The one gradient

```css
  --k-loop-gradient: linear-gradient(135deg, #22D3EE 0%, #7C7CF5 100%);
```

Permitted uses, exhaustively: the Loop Ring stroke, the primary action button fill, and the 2px top border of the active incident panel. Nowhere else. Not on text, not on card backgrounds, not on the logo.

### 2.5 Confidence

Confidence is **never** encoded as a hue — a red "low confidence" would collide with high risk. It is a 5-segment bar in `--k-text-muted`, filled in `--k-text`, with the numeric value always shown beside it.

```css
  --k-confidence-track: #223249;
  --k-confidence-fill:  #f0f4fc;
```

### 2.6 Light theme

Same token names, remapped. Do not invent new tokens for light.

```css
:root[data-theme="light"] {
  --k-bg: #f8fafc;  --k-surface: #ffffff;  --k-surface-raised: #f1f5f9;
  --k-surface-sunken: #e2e8f0;
  --k-border: #cbd5e1;  --k-border-strong: #94a3b8;  --k-border-subtle: #e2e8f0;
  --k-text: #0f172a;  --k-text-muted: #475569;  --k-text-faint: #64748b;
  --k-text-inverse: #ffffff;
  --k-risk-low: #059669;  --k-risk-low-bg: #ecfdf5;
  --k-risk-med: #d97706;  --k-risk-med-bg: #fffbeb;
  --k-risk-high: #e11d48; --k-risk-high-bg: #fff1f2;
  --k-risk-denied: #64748b; --k-risk-denied-bg: #f1f5f9;
  --k-state-detected: #0284c7;  --k-state-collecting: #0284c7;
  --k-state-diagnosing: #6366f1; --k-state-awaiting: #d97706;
  --k-state-healing: #0891b2;   --k-state-verifying: #4f46e5;
  --k-state-resolved: #059669;  --k-state-rolledback: #ea580c;
  --k-state-escalated: #e11d48;
  --k-confidence-track: #e2e8f0; --k-confidence-fill: #0f172a;
  --k-glow-subtle: 0 0 16px -2px rgba(14, 116, 144, 0.15);
}
```

---

## 3. Typography

**Geist Sans** for the interface, **JetBrains Mono** for machine strings. Two families, clearly distinct in form and in role, so the distinction carries information.

Geist is chosen over the reflexive Inter because its slightly narrower, more geometric forms hold up in dense tabular layouts and it pairs cleanly with a mono at the same optical size — which matters here, because sans and mono sit side by side on nearly every row.

```css
  --k-font-sans: "Geist", ui-sans-serif, system-ui, sans-serif;
  --k-font-mono: "JetBrains Mono", ui-monospace, "SF Mono", monospace;
```

### 3.1 Scale

| Token | Size / line-height | Weight | Use |
|---|---|---|---|
| `--k-text-display` | 32 / 38 | 600 | Page title, one per screen |
| `--k-text-h1` | 24 / 32 | 600 | Section heading |
| `--k-text-h2` | 18 / 26 | 600 | Panel heading |
| `--k-text-h3` | 15 / 22 | 600 | Sub-panel, card title |
| `--k-text-body` | 14 / 22 | 400 | Default |
| `--k-text-sm` | 13 / 20 | 400 | Secondary, metadata |
| `--k-text-xs` | 12 / 18 | 500 | Badges, chips, table headers |
| `--k-mono-body` | 13 / 20 | 400 | Log lines, diffs, evidence payloads |
| `--k-mono-sm` | 12 / 18 | 400 | Trace IDs, container names, inline values |
| `--k-mono-metric` | 20 / 26 | 500 | Metric readouts, MTTD/MTTR values |

### 3.2 Typographic rules

- Measure: body prose capped at 72ch. Evidence and log panes are exempt and scroll horizontally.
- **Sentence case everywhere.** No ALL-CAPS labels, including table headers and badges. Use weight and `--k-text-muted` for de-emphasis instead.
- **No accented single words.** Do not colour or bold one word inside a heading for emphasis.
- Numbers in tables and metric readouts use `font-variant-numeric: tabular-nums`. A metric that jitters its own column width is a defect.
- Do not add a label above content that already explains itself. "Diagnosis" above a diagnosis is noise; the content's position in the loop already says what it is.

---

## 4. Spacing

4px base. Use the scale; nothing between the steps.

```css
  --k-space-1: 4px;    --k-space-2: 8px;    --k-space-3: 12px;
  --k-space-4: 16px;   --k-space-5: 24px;   --k-space-6: 32px;
  --k-space-7: 48px;   --k-space-8: 64px;
```

**Conventions:** 12px inside a chip or badge · 16px inside a card · 24px between cards · 32px between sections · 48px page gutter on desktop, 16px on mobile.

---

## 5. Radius, borders, elevation

```css
  --k-radius-sm:  4px;   /* badges, chips, inputs */
  --k-radius-md:  8px;   /* buttons, cards */
  --k-radius-lg:  12px;  /* panels, modals */
  --k-radius-full: 9999px; /* status pills, the Loop Ring */
```

**Radius encodes hierarchy.** Do not apply one radius to everything — that uniformity is exactly what makes a generated interface read as generated. Small interactive atoms get `sm`, containers get `md`, top-level surfaces get `lg`.

**Elevation on dark is carried by surface value and border, not by shadow.** Shadows barely read on `#0A0E16` and look like smudge.

| Level | Treatment |
|---|---|
| 0 — flat | `--k-surface`, no border |
| 1 — object | `--k-surface` + 1px `--k-border` |
| 2 — active object | `--k-surface` + 1px `--k-border-strong` |
| 3 — overlay | `--k-surface-raised` + 1px `--k-border-strong` + `0 16px 48px rgba(0,0,0,.6)` |

Overlays are the only place a shadow appears.

---

## 6. Layout

Three zones. The proportions are fixed because the operator's eye path is fixed: *where → what → why*.

```
┌────┬──────────────────────────────────┬─────────────────────────┐
│    │  Incident stream                 │  Inspector              │
│ 64 │  ────────────────────────────    │  ─────────────────────  │
│ px │  ◐ F01 primary endpoint outage   │  Evidence   (12)        │
│    │    backend · healing · 00:46     │   ▸ span 3f2a…  err 503 │
│ r  │  ────────────────────────────    │   ▸ logs backend · 14   │
│ a  │  ✓ F07 prompt regression         │   ▸ cfg rerank 0.35→0.9 │
│ i  │    backend · resolved · 2m14s    │                         │
│ l  │  ────────────────────────────    │  Diagnosis              │
│    │  ⚠ F06 retrieval collapse        │   retrieval_collapse    │
│ ◆  │    backend · awaiting approval   │   confidence 0.91       │
│    │                                  │                         │
│    │                                  │  Plan                   │
│    │                                  │   rollback_config [Med] │
│    │                                  │   undo: rerank → 0.35   │
│    │                                  │                         │
│    │                                  │  Verification           │
│    │                                  │   ✓ health ✓ slo ○ fast │
└────┴──────────────────────────────────┴─────────────────────────┘
  rail        flexible, min 480px            380px fixed
```

The inspector above shows the selected `F06` incident — MEDIUM risk, hence *awaiting approval*. Service names (`backend`) and action names (`rollback_config`, `switch_llm_endpoint`) are the real ones from `PRD.md` §6 and `ARCHITECTURE.md` §6.2; the third verification probe is labelled **fast**, not *eval*, because the live loop runs fast verification and never the full evaluator (`FR-07` vs `FR-07a`).

- **Left rail (64px):** projects and navigation, icons only, tooltip on hover. The mode indicator (`SIMULATION` / `APPROVAL` / `AUTONOMOUS`) lives at the bottom of the rail and is visible on every screen — this satisfies `UX-01` and it must never scroll away.
- **Centre:** the incident stream, newest first, live. Rows are full-width and left-aligned. Left alignment, not centred, because the eye scans a vertical column of status glyphs.
- **Right inspector (380px fixed):** the selected incident's detail, in loop order: evidence → diagnosis → plan → risk → verification → audit. The order never changes, because the operator learns the position.

### 6.1 Breakpoints

```css
  --k-bp-sm: 640px;   --k-bp-md: 1024px;   --k-bp-lg: 1280px;   --k-bp-xl: 1600px;
```

- `< 640`: single column, inspector becomes a full-screen sheet. Rail becomes a bottom bar.
- `640–1024`: rail + stream, inspector as an overlay drawer.
- `1024–1280`: all three, inspector narrows to 320px.
- `≥ 1280`: the layout above.
- `≥ 1600`: stream and inspector both grow; the rail does not.

**Projector constraint (`UX-06`):** the layout must stay legible at 1280×720. Test the demo screens at that size specifically — a review room projector is the real target device.

---

## 7. Components

### 7.1 Loop Ring

The product's signature element. A circular progress ring, `--k-radius-full`, 3px stroke in `--k-loop-gradient`, with seven tick positions: collect · diagnose · plan · gate · execute · verify · learn.

- Advances to a stage only when that stage genuinely starts. It never animates ahead of real state.
- A slow, continuous rotation of the gradient *only* while a stage is in flight. Still when idle.
- Sizes: 20px inline in a stream row, 96px in the inspector header.
- On `prefers-reduced-motion`, the rotation stops; stage advancement still renders as discrete steps.
- **This is the only non-user-triggered motion in the product.**

### 7.2 Risk badge

`--k-radius-sm`, 12px horizontal padding, `--k-text-xs`, text in the tier colour on the tier's `-bg`, 1px border in the tier colour at 30% alpha. **Always carries an icon** — shield (low), shield-alert (medium), shield-x (high), ban (denied). Sentence case: "Low", not "LOW".

### 7.3 Incident row

Height 64px. Grid: `[20px ring] [1fr title+meta] [auto state pill] [auto duration]`.
Title is the fault class ID and name in sans; the service name and timestamps in `--k-mono-sm`, `--k-text-faint`. Hovered row lifts to `--k-surface-raised`; selected row gets `--k-border-strong` and a 2px left bar in its state colour.

### 7.4 Evidence item

Collapsed: a one-line summary with a kind icon and a mono source reference.
Expanded: the payload in `--k-surface-sunken` with `--k-mono-body`, horizontally scrollable, never wrapped.
**Every evidence item carries a stable `evidence_id` shown in mono.** Diagnosis citations link to these IDs — that link is the whole trust mechanism, so it must be visible, not implied.

### 7.5 Diagnosis card

Fault class as `--k-text-h3`. Confidence bar plus numeric value immediately beside it. Beneath, the cited evidence IDs as clickable mono chips. Beneath that, a collapsed "Ruled out" list showing rejected alternatives and the reason each was rejected.

An `INSUFFICIENT_EVIDENCE` result is **not** an error state. It renders in `--k-text-muted` with a neutral icon and the text "Not enough evidence to diagnose." Styling it as a failure would train the user to distrust the system's honesty, which is the one behaviour we most want to encourage.

### 7.6 Action plan

Action name in mono. Params as a key/value grid. The inverse action shown directly beneath, prefixed `undo:`, in `--k-text-muted` mono. The inverse is never hidden behind a disclosure — the user's question is "can this be undone", and the answer must be on screen.

### 7.7 Approval dialog

Overlay, elevation 3, max-width 640px. Order is fixed: diagnosis → proposed diff → sandbox verification result → risk rationale → inverse action → controls.
**The approve button is disabled until the diff region has been scrolled to its end.** Approving unread is the failure mode this product exists to prevent.
Reject requires a reason; the reason feeds the knowledge base.

### 7.8 Verification strip

Three probes in a row: health · SLO window · fast quality. Each is a pill with an icon — pending (hollow circle), passed (check), failed (cross). All three must be visibly present even before they run, so a missing probe is obvious.

The third probe is labelled **fast quality**, not "eval". The live loop runs fast verification — 3 deterministic cases (`FR-07`) — and never the full research evaluator (`FR-07a`), which cannot fit the `PF-04` budget. Labelling it "eval" would imply the console is showing a 40-case run that it is not.

### 7.9 Mode switch

A segmented control, three options. The active segment is filled; `AUTONOMOUS` is the only one that uses `--k-loop-gradient` as its fill. Switching *into* `AUTONOMOUS` opens a confirmation listing exactly which actions become auto-executable for this project. Switching out is immediate and needs no confirmation.

### 7.10 Audit entry

A dense table row, mono throughout. Columns: timestamp · actor · event · risk · verdict · outcome.
The hash-chain link renders as a small chain icon; a broken chain renders in `--k-risk-high` with the text "Chain broken". There is no edit control anywhere on this view — the absence is the point.

### 7.11 Metric readout

`--k-mono-metric` value, `--k-text-xs` muted label beneath, optional 48px sparkline. Used for MTTD, MTTR, auto-resolution rate. No card border — these are readings, not objects.

---

## 8. States

Every interactive element defines all of these. A component is not done until they exist.

| State | Treatment |
|---|---|
| Default | Elevation per §5 |
| Hover | Surface steps up one level. 120ms ease-out. No scale, no shadow bloom |
| Focus | 2px `--k-border-strong` ring, 2px offset. **Never removed.** Visible on dark and light |
| Active | Surface steps up; 1px inset border in the element's own signal colour |
| Disabled | 40% opacity, `cursor: not-allowed`, and a `title` explaining *why* it is disabled |
| Loading | Skeleton blocks in `--k-surface-raised`. Never a spinner for content; spinners only inside buttons |
| Empty | An invitation, not an apology. "No incidents. Kavach is watching 5 services." plus the primary next action |
| Error | What failed, in plain language, and the command or control that fixes it. No apology, no vague "something went wrong" |

### 8.1 Writing in the interface

- Active voice. A button says what happens: "Approve repair", not "Submit".
- The same verb all the way through a flow. "Approve repair" → toast "Repair approved" → audit event "approved".
- Name things as the user understands them. "Backup model", not "fallback provider adapter".
- Errors never apologise and are never vague. "Preflight failed: no health endpoint for `pgvector`. Add one under `services.pgvector.health` in kavach.yaml."
- Empty states are directions. "No projects yet. Point Kavach at a compose file to start."

---

## 9. Motion

Sparing and deliberate. Motion that answers a user action is welcome; motion that decorates is not.

```css
  --k-dur-fast: 120ms;   /* hover, focus */
  --k-dur-base: 200ms;   /* expand, collapse, drawer */
  --k-dur-slow: 400ms;   /* loop stage advance */
  --k-ease: cubic-bezier(.2,0,.2,1);
```

Permitted: hover/focus transitions, disclosure expand/collapse, drawer and overlay entry, the Loop Ring stage advance, and a single state-colour crossfade when an incident changes state.

**Forbidden:** fade-and-slide-up entrances on page sections or lists, staggered reveals, any looping animation other than the Loop Ring, parallax, animated gradients on backgrounds.

All motion respects `prefers-reduced-motion: reduce` — transitions drop to 0ms, the ring stops rotating, state changes still render.

---

## 10. Accessibility

Non-negotiable. The console is read on a projector by people who did not build it.

- **Contrast:** `--k-text` on `--k-surface` ≥ 7:1. `--k-text-muted` ≥ 4.5:1. Every signal colour on its paired `-bg` ≥ 4.5:1. Verify after any token change; do not assume.
- **Never colour alone.** Every risk tier, incident state and probe result carries an icon and a text label. A reviewer with deuteranopia must be able to distinguish LOW from HIGH, and a projector will wash out your greens regardless.
- **Keyboard:** every action reachable by keyboard. Focus order follows the loop order in the inspector. Approval dialogs trap focus and return it on close. `Esc` closes any overlay.
- **Semantics:** real `<button>`, real `<table>` for the audit log, real headings in order. The incident stream is a `<ul>` of `<li>`, not a div soup.
- **Live regions:** incident state changes announce via `aria-live="polite"`. A new HIGH-risk approval request uses `aria-live="assertive"`.
- **Targets:** 40×40px minimum for anything clickable, 44×44 on touch.
- **Zoom:** usable at 200% without horizontal page scroll. Evidence panes may scroll internally.

---

## 10.1 Implemented in P4, and where it knowingly differs

The console implements §2–§6 as written: tokens as CSS variables and TS
constants, both themes with dark primary, the type scale, the 4px spacing
scale, radius-encodes-hierarchy, surface-and-border elevation, and the three
zones. §7 components exist except where the thing they describe does not.

| § | Difference | Why |
|---|---|---|
| 7.9 Mode switch | Built as an **indicator, not a segmented control** | There is nothing to switch to. `permit()` does not exist, the loop reads no mode, and a control that appeared to change a safety posture while changing nothing would be worse than none. It states in words that the mode is configuration rather than an enforced gate. The control arrives with the thing it controls, in P6 |
| 7.7 Approval dialog | Not built | There is no approval flow to drive it (P6) |
| 7.10 Audit entry | The history table reads **incidents**, not an audit log | No hash-chained log exists yet (P6). The table is deliberately not called an audit view |
| 7.11 Metric readout | Not built | MTTD/MTTR are not persisted across incidents, so there is nothing to read |
| 7.8 Verification strip | Three probes render; **the SLO-window probe is permanently pending** | Only two of the three `FR-07` probes are implemented. Hiding the third would make a two-probe verification look complete |
| 6 Layout | A **fourth** zone: health sits between the rail and the stream | The P4 brief puts system health in the left zone. The fixed widths were re-derived so the row still fits 1280px — the first attempt overflowed by 8px, which a test now guards |
| 6 Breakpoints | Below 1024 the inspector **stacks below** rather than becoming an overlay drawer | Every zone stays reachable; nothing hides behind a control that does not exist yet |

Fonts are self-hosted from npm (`geist`, `@fontsource/jetbrains-mono`) rather
than fetched from a font CDN, because the demo has to work offline and a
build-time webfont fetch is a network dependency in the build.

---

## 11. Anti-patterns

Specific things not to generate in this product. These are the tells.

- A hero section with a big gradient number and supporting stats. This is a console; there is no hero.
- Identical rounded cards with the same radius and the same soft grey shadow repeated down the page.
- ALL-CAPS tracked-out eyebrow labels above headings.
- Metadata strings joined with middle dots (`A · B · C`) used as decoration. Used as a compact service/time separator in a row is fine; used as a styling flourish is not.
- `→` appended to button and link text.
- A second gradient anywhere.
- Glassmorphism, blur backdrops, glow effects on cards.
- Emoji as status icons. Use the icon set.
- Numbered markers (`01 / 02 / 03`) on anything that is not genuinely a sequence. The loop stages *are* a sequence and may be numbered. A feature list is not.
- A monospace face on labels, headings or body copy.
- Toasts for events the user can already see on screen.
- Sparkles, wands, or any visual vocabulary that frames the AI as magic. This product's entire argument is that its reasoning is inspectable.
