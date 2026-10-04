# DESIGN_SYSTEM.md — Kavach Console

> Visual rules for `apps/console/`. Derived from the Cursor design language:
> warm cream canvas, near-black ink, one orange, hairlines instead of shadows,
> display type at weight 400.
>
> **This replaces the earlier dark-first version.** Kavach is light-first now.

---

## 1. Direction

**What this product is:** an instrument panel for a machine that reasons about incidents and applies bounded repairs inside a controlled simulation. The person looking at it is deciding whether to trust the reasoning.

**Why cream and not dark.** The obvious move for a developer tool is a near-black IDE skin. Cursor goes the other way — a warm cream editorial canvas with magazine-weight display type — and that choice suits us better than it suits them. An incident console is read under pressure, often on a projector in a bright room, and often by someone deciding whether to approve a simulated repair. Cream with near-black ink is calmer, prints legibly, and does not make every amber warning glow.

**Three questions every screen must answer:**

1. What is happening right now?
2. How sure is the system, and on what evidence?
3. What is it about to do, and can the change be undone?

**The one bold thing: the loop timeline.** Cursor's signature is a pastel pill timeline marking AI-action stages — Thinking, Grepping, Reading, Editing, Done. Our incident loop is exactly that shape, and it inherits the palette directly. It is the only chromatic element in the product. Everything else is ink on cream with hairlines.

**Rules that follow:**
- **Orange is scarce.** `#f54e00` appears on primary CTAs and the wordmark. Nothing else.
- **Pastels are scoped to the loop timeline.** They mark incident stages. They never indicate risk, health or system action — that is what the semantic colours are for.
- **Hairlines, never shadows.** Depth comes from white-on-cream and 1px rules.
- **Display stays at weight 400.** The whole voice depends on it. Never 700.
- **Monospace is functional.** Trace IDs, container names, log lines, diffs, metric values, action names. Never labels or headings.

---

## 2. Colour

### 2.1 Base

```css
:root {
  /* Canvas — cream, never pure white */
  --k-canvas:          #f7f7f4;   /* page floor */
  --k-canvas-soft:     #fafaf7;   /* inset panes: logs, diffs, evidence */
  --k-surface:         #ffffff;   /* cards */
  --k-surface-strong:  #e6e5e0;   /* badges, inert fills */

  /* Ink */
  --k-ink:             #26251e;   /* primary text, display */
  --k-body:            #5a5852;   /* body copy */
  --k-muted:           #807d72;   /* labels, metadata */
  --k-muted-soft:      #a09c92;   /* timestamps, placeholder, disabled */

  /* Hairlines — this is the depth system */
  --k-hairline-soft:   #efeee8;   /* internal rules inside a card */
  --k-hairline:        #e6e5e0;   /* default card outline, dividers */
  --k-hairline-strong: #cfcdc4;   /* focused / active object, input borders */

  /* Brand — scarce */
  --k-primary:         #f54e00;
  --k-primary-active:  #d04200;
  --k-on-primary:      #ffffff;
}
```

### 2.2 Loop stages — the pastel timeline

Inherited from Cursor's agent timeline. These mark **where an incident is**, never how dangerous anything is.

```css
  --k-stage-detect:    #dfa88f;   /* peach   — breach raised */
  --k-stage-evidence:  #9fc9a2;   /* mint    — collecting */
  --k-stage-diagnose:  #9fbbe0;   /* blue    — the LLM is reasoning */
  --k-stage-execute:   #c0a8dd;   /* lavender— acting */
  --k-stage-verify:    #c0a8dd;   /* lavender, lighter weight */
  --k-stage-done:      #c08532;   /* gold    — closed */
```

Stage pills use `caption-uppercase` type on the pastel fill with `--k-ink` text, except `done` which takes white.

### 2.3 Semantic — risk, health, outcome

Separate family from the pastels, deliberately. A reader must never confuse "this is in progress" with "this is dangerous."

```css
  --k-success:         #1f8a65;   /* LOW risk · passed · resolved */
  --k-success-bg:      #e8f3ee;
  --k-caution:         #c08532;   /* MEDIUM risk · degraded · mitigated */
  --k-caution-bg:      #f7efe2;
  --k-danger:          #cf2d56;   /* HIGH risk · failed · escalated */
  --k-danger-bg:       #fbeaef;
  --k-denied:          #807d72;   /* blocked by allow-list or breaker */
  --k-denied-bg:       #efeee8;
  --k-unrecoverable:   #a3123c;   /* undo itself failed — the loudest state */
```

### 2.4 Outcome states

Four terminal states, and they must look different from each other:

| Outcome | Colour | Note |
|---|---|---|
| `RESOLVED` | `--k-success` | Clean |
| `MITIGATED` | `--k-caution` | **Never green.** Up, and carrying damage |
| `ESCALATED` | `--k-danger` | Unwound, human needed |
| `UNRECOVERABLE` | `--k-unrecoverable` | Undo failed. The only state with its own hue |

### 2.5 Objective deltas

Verification returns a value per objective, not a tick. Sign does not map to good/bad uniformly — cost falling is good, quality falling is not — so the colour comes from the *judgement*, not the sign.

```css
  --k-delta-improved:  #1f8a65;
  --k-delta-neutral:   #807d72;
  --k-delta-degraded:  #c08532;   /* within declared tolerance */
  --k-delta-breached:  #cf2d56;   /* tolerance exceeded */
  --k-tolerance-track: #e6e5e0;
  --k-tolerance-fill:  #c08532;
```

### 2.6 Confidence

Never a hue — a red "low confidence" would collide with high risk. A 5-segment bar in `--k-hairline-strong`, filled `--k-ink`, numeric value always beside it.

### 2.7 Dark theme

Cursor is light-only, so this is our departure and it is **secondary**. Get light right first. Invert by remapping the same token names — never introduce new ones.

```css
:root[data-theme="dark"] {
  --k-canvas: #1b1a16;  --k-canvas-soft: #141310;  --k-surface: #24231d;
  --k-surface-strong: #33312a;
  --k-ink: #f2f1ea;  --k-body: #c4c1b6;  --k-muted: #928e82;  --k-muted-soft: #6b685e;
  --k-hairline-soft: #2b2a23;  --k-hairline: #38362e;  --k-hairline-strong: #504d43;
  /* pastels lift ~12% lightness; semantics lighten to hold 4.5:1 on --k-surface */
}
```

---

## 3. Typography

**Inter** at weight 400 with -1.5% letter-spacing for display and body — the documented open substitute for CursorGothic. **JetBrains Mono** for every machine-generated string.

```css
  --k-font-sans: "Inter", system-ui, "Helvetica Neue", Helvetica, Arial, sans-serif;
  --k-font-mono: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
```

| Token | Size / LH | Weight | Tracking | Use |
|---|---|---|---|---|
| `display-lg` | 36 / 1.2 | 400 | -0.72px | Page title, one per screen |
| `display-md` | 26 / 1.25 | 400 | -0.325px | Section heads |
| `display-sm` | 22 / 1.3 | 400 | -0.11px | Panel heads |
| `title-md` | 18 / 1.4 | 600 | 0 | Card titles |
| `title-sm` | 16 / 1.4 | 600 | 0 | List labels |
| `body-md` | 16 / 1.5 | 400 | 0 | Default |
| `body-sm` | 14 / 1.5 | 400 | 0 | Secondary |
| `caption` | 13 / 1.4 | 400 | 0 | Metadata |
| `caption-uppercase` | 11 / 1.4 | 600 | 0.88px | Stage pills, section labels, table headers |
| `code` | 13 / 1.5 | 400 | 0 | Logs, diffs, evidence — JetBrains Mono |
| `code-sm` | 12 / 1.5 | 400 | 0 | Trace IDs, container names, inline values |
| `metric` | 26 / 1.2 | 400 | -0.325px | MTTD, MTTR, delta percentages |
| `button` | 14 / 1.0 | 500 | 0 | CTA labels |

### 3.1 Rules

- **Display never exceeds weight 400.** This is the single rule the voice depends on.
- **Negative tracking on display only.** Body and mono sit at 0.
- `caption-uppercase` is the *only* uppercase in the product, and only for stage pills, section labels and table headers. Nothing else is tracked-out caps.
- Numbers in tables and metric readouts use `font-variant-numeric: tabular-nums`. A metric that jitters its own column width is a defect.
- Body prose caps at 72ch. Evidence and log panes are exempt and scroll horizontally.
- No display-mega. Cursor's 72px hero belongs to a marketing page; a console has no hero.

---

## 4. Spacing

4px base. Cursor's scale, with one adaptation.

```css
  --k-space-xxs: 4px;   --k-space-xs:  8px;   --k-space-sm: 12px;
  --k-space-base:16px;  --k-space-md: 20px;   --k-space-lg: 24px;
  --k-space-xl: 32px;   --k-space-xxl:48px;   --k-space-section: 80px;
```

**The adaptation.** Cursor's 80px section rhythm is editorial pacing for a marketing site. A console needs density — a reviewer should see an entire incident without scrolling. So: `--k-space-section` applies only to top-level page bands and the onboarding flow. Inside working surfaces use 16–24px, which is what Cursor itself does for cards within a band.

Conventions: 10px×18px inside a button · 16px inside a compact card · 24px inside a panel · 24px between cards · 32px between sections · 48px page gutter on desktop, 16px on mobile.

---

## 5. Shape and depth

```css
  --k-radius-xs:   4px;    /* inline tags */
  --k-radius-sm:   6px;    /* compact rows */
  --k-radius-md:   8px;    /* buttons, inputs */
  --k-radius-lg:  12px;    /* cards, panes */
  --k-radius-pill: 9999px; /* stage pills, badges */
```

Radius encodes hierarchy. Applying one radius everywhere is what makes generated interfaces read as generated.

**Depth is hairline-only. There are no shadows in this product.**

| Level | Treatment |
|---|---|
| Canvas | `--k-canvas` |
| Inset pane | `--k-canvas-soft` — logs, diffs, evidence payloads |
| Card | `--k-surface` + 1px `--k-hairline` |
| Active card | `--k-surface` + 1px `--k-hairline-strong` |
| Overlay | `--k-surface` + 1px `--k-hairline-strong`. **Still no shadow** — separate with a `rgba(38,37,30,.28)` scrim |

---

## 6. Layout

Three zones. Fixed, because the operator's eye path is fixed: *where → what → why*.

```
┌────┬──────────────────────────────────┬─────────────────────────┐
│    │  Incident stream                 │  Inspector              │
│ 64 │  ──────────────────────────────  │  ─────────────────────  │
│ px │  ◐ F01 provider outage           │  Evidence   (12)        │
│    │    api · executing · 00:46       │   ▸ span 3f2a…  err 503 │
│ r  │  ──────────────────────────────  │   ▸ logs api 14 lines   │
│ a  │  ✓ F07 prompt regression         │   ▸ git  prompts@a91c   │
│ i  │    api · resolved · 2m14s        │                         │
│ l  │  ──────────────────────────────  │  Diagnosis              │
│    │  ◆ F01 provider outage           │   provider_outage  0.91 │
│ ◆  │    MITIGATED · owes switch-back  │                         │
│    │                                  │  Plan                   │
│ ●  │                                  │   switch_model   [Low]  │
│    │                                  │   undo: switch_model    │
│ mode                                  │                         │
│ AUTO                                  │  Verification           │
│                                       │   avail +99%            │
│                                       │   quality −12%  ▓▓▓▓░   │
└────┴──────────────────────────────────┴─────────────────────────┘
  rail        flexible, min 480px            380px fixed
```

- **Left rail, 64px.** Projects and nav, icons with hover tooltips. The mode indicator sits at the bottom and is visible on every screen — it must never scroll away.
- **Centre.** Incident stream, newest first, live, left-aligned. Rows are full width.
- **Right inspector, 380px fixed.** Loop order, always: evidence → diagnosis → plan → risk → verification → audit. The order never changes, because the operator learns the positions.

### 6.1 Breakpoints

```css
  --k-bp-sm: 640px;  --k-bp-md: 1024px;  --k-bp-lg: 1280px;  --k-bp-xl: 1600px;
```

`<640` single column, inspector is a full-screen sheet, rail becomes a bottom bar · `640–1024` rail + stream, inspector as a drawer · `1024–1280` all three, inspector 320px · `≥1280` the layout above · `≥1600` stream and inspector grow, rail does not.

**Projector constraint:** legible at 1280×720. Test the demo screens at that size on the actual projector. Cream canvas helps here; a dark console would not have.

---

## 7. Components

### 7.1 Loop timeline (signature)

Cursor's pastel pill timeline, carrying our seven stages: **detect · evidence · diagnose · plan · gate · execute · verify**.

- Horizontal pill row in the inspector header; a single compact pill in a stream row showing the current stage only.
- Pills use `caption-uppercase` on the stage pastel, `--k-radius-pill`, 4px×10px.
- Completed stages fill solid. The current stage fills solid with a slow pulse. Future stages render as a hairline outline on canvas.
- **Advances only when a stage genuinely starts.** It never animates ahead of real state.
- The only non-user-triggered motion in the product. On `prefers-reduced-motion`, the pulse stops; advancement still renders.

### 7.2 Risk badge

`--k-radius-sm`, 10px horizontal padding, `caption-uppercase`, semantic text on the matching `-bg`, 1px border in the semantic colour at 30% alpha. **Always carries an icon** — shield (low), shield-alert (medium), shield-x (high), ban (denied).

### 7.3 Incident row

64px tall. Grid: `[20px stage pill] [1fr title + meta] [auto outcome chip] [auto duration]`. Title in `title-sm`; service and timestamps in `code-sm`, `--k-muted-soft`. Hover lifts to `--k-surface`; selected gets `--k-hairline-strong` plus a 2px left bar in the stage pastel.

### 7.4 Evidence item

Collapsed: one line, kind icon, mono source reference. Expanded: payload in `--k-canvas-soft` with `code`, horizontally scrollable, never wrapped. **Every item shows its stable `evidence_id` in mono** — diagnosis citations link to these, and that link is the entire trust mechanism.

### 7.5 Diagnosis card

Fault class in `title-md`. Confidence bar plus numeric value beside it. Cited evidence IDs as clickable mono chips. A collapsed "Ruled out" list showing rejected alternatives with reasons.

`INSUFFICIENT_EVIDENCE` is **not an error state**. It renders in `--k-muted` with a neutral icon: "Not enough evidence to diagnose." Styling honesty as failure trains users to distrust it.

### 7.6 Action plan

Action name in mono, params as a key/value grid. **The inverse directly beneath, prefixed `undo:`, in `--k-muted` mono, never behind a disclosure.** The user's question is "can this be undone"; the answer belongs on screen.

### 7.7 Verification: probe strip + delta strip

**Probe strip.** Three pills: health · objectives · golden eval. States: pending (hollow), passed (check), **degraded (half-filled)**, failed (cross). All three visible before they run.

`DEGRADED` is distinct from both neighbours and is usually the one telling the truth: it ran, the system works, something got worse. Never collapse it.

**Delta strip.** One row per objective: label, signed percentage in `metric` type, a short bar coloured from the delta scale. Beneath, a tolerance meter showing how much of the declared budget this repair consumed.

A `MITIGATED` result reads "availability +99% · quality −12% · 80% of tolerance used". **Never a green tick.** A reviewer should see the cost of the repair without opening anything.

### 7.8 Debt chip and debt view

A `MITIGATED` incident carries a chip in its row: a `--k-caution` pill reading the repayment condition in plain words — "owes: switch back when primary healthy 10m".

The debt view is a top-level rail destination, not a tab inside incidents — outstanding obligations are something an operator checks, not a detail of a closed incident. Rows show what was mitigated, what is owed, the trigger and its current state, age, and proximity to `max_age_s`. Overdue renders in `--k-danger` with age in mono.

### 7.9 Approval dialog

Overlay, max-width 640px, scrim rather than shadow. Fixed order: diagnosis → proposed simulation diff → verification expectations → risk rationale → inverse → controls.

**The approve button stays disabled until the diff region has been scrolled to its end.** Approving unread is the failure mode this product exists to prevent.

Reject requires a reason; the reason feeds the knowledge base.

### 7.10 Mode switch

Segmented control, three options. Active segment fills; `AUTONOMOUS` is the **only** element besides primary CTAs that may use `--k-primary`. Switching *into* `AUTONOMOUS` opens a confirmation listing exactly which simulated actions become auto-executable. Switching out is immediate.

### 7.11 Scenario readiness checklist

One row per check P01–P13: ID in mono, name, pass/fail icon, and on failure **the exact remediation inline** — "P12 failed: spans carry no model or token attributes. Add GenAI instrumentation — see CONTRACT.md §8."

The achieved scenario conformance level renders as a `badge-pill` with its consequence spelled out beneath in `body-sm`: "Level 1 — Protected. Prompt regressions will be detected but cannot be rolled back automatically." A level with no stated consequence is a badge, not information.

### 7.12 Audit entry

Dense table row, mono throughout: timestamp · actor · event · risk · verdict · outcome. The hash-chain link is a small chain icon; a broken chain renders `--k-danger` reading "Chain broken". **No edit control exists anywhere on this view** — the absence is the point.

### 7.13 Buttons

| Variant | Fill | Text | Border | Size |
|---|---|---|---|---|
| Primary | `--k-primary` | white | none | 40px, 10×18, radius-md |
| Secondary | `--k-surface` | `--k-ink` | 1px `--k-hairline-strong` | 40px, 9×17 |
| Tertiary | transparent | `--k-ink` | none | inline |
| Destructive | `--k-surface` | `--k-danger` | 1px `--k-danger` @30% | 40px |

Primary appears **once per screen at most**. If two things look primary, neither is.

### 7.14 Metric readout

`metric` type value, `caption` muted label beneath, optional 48px sparkline. MTTD, MTTR, auto-resolution rate. No border — these are readings, not objects.

---

## 8. States

Every interactive element defines all of these. A component is not done until they exist.

| State | Treatment |
|---|---|
| Default | Per §5 |
| Hover | Surface steps up one level, or hairline → hairline-strong. 120ms ease-out. No scale, no shadow |
| Focus | 2px `--k-ink` ring at 2px offset. **Never removed** |
| Active | 1px inset border in the element's own semantic colour |
| Disabled | 40% opacity, `cursor: not-allowed`, and a `title` saying *why* |
| Loading | Skeleton blocks in `--k-surface-strong`. Spinners only inside buttons, never for content |
| Empty | An invitation: "No incidents. Create a scenario to begin." plus the next action |
| Error | What failed, in plain language, and the control or command that fixes it |

### 8.1 Writing

- Active voice. Buttons say what happens: "Approve simulated repair", not "Submit".
- Same verb through a whole flow: "Approve simulated repair" → "Simulated repair approved" → audit event `approved`.
- Name things as the user does. "Backup model", not "fallback provider adapter".
- Errors never apologise and are never vague. "Preflight failed: no health endpoint for `pgvector`. Add one under `services.pgvector.health`."
- Empty states are directions, not apologies.

---

## 9. Motion

```css
  --k-dur-fast: 120ms;   /* hover, focus */
  --k-dur-base: 200ms;   /* expand, collapse, drawer */
  --k-dur-slow: 400ms;   /* loop stage advance */
  --k-ease: cubic-bezier(.2, 0, .2, 1);
```

**Permitted:** hover and focus transitions, disclosure expand/collapse, overlay entry, the loop stage advance, and one colour crossfade when an incident changes stage.

**Forbidden:** fade-and-slide-up entrances on sections or lists, staggered reveals, any looping animation other than the current-stage pulse, parallax, animated gradients.

All of it respects `prefers-reduced-motion: reduce` — transitions to 0ms, pulse stops, state changes still render.

---

## 10. Accessibility

- **Contrast:** `--k-ink` on `--k-canvas` is roughly 13:1. `--k-body` ≥ 7:1. `--k-muted` ≥ 4.5:1. **Verify every pastel pill: the stage pastels are light, so they take `--k-ink` text, never white** — except `--k-stage-done`, which is dark enough for white. Re-check after any token change; do not assume.
- **Never colour alone.** Every risk tier, stage, outcome and probe result carries an icon and a text label. A projector will wash out the pastels regardless.
- **Keyboard:** everything reachable. Inspector focus order follows loop order. Dialogs trap focus and return it. `Esc` closes any overlay.
- **Semantics:** real `<button>`, real `<table>` for audit, headings in order, the stream as `<ul>`/`<li>`.
- **Live regions:** stage changes `aria-live="polite"`; a new HIGH-risk approval `aria-live="assertive"`.
- **Targets:** 40×40px minimum, 44×44 on touch.
- **Zoom:** usable at 200% with no horizontal page scroll; evidence panes scroll internally.

---

## 11. Anti-patterns

- **A single green tick for a verification result.** The specific thing this system exists to prevent — it hides the trade the repair made.
- **A green `MITIGATED`.** It is caution-coloured. The point is that a reviewer sees damage at a glance.
- **Pastels used for risk or health.** They mark loop position only. Risk is semantic.
- **A second brand colour.** Orange is the only one.
- **Display type at weight 700.** The voice depends on 400.
- **Drop shadows.** Hairlines and ink-on-cream carry depth.
- A hero section with a big number and supporting stats. This is a console; there is no hero.
- Identical rounded cards at one radius repeated down the page.
- ALL-CAPS eyebrow labels outside `caption-uppercase`'s three sanctioned uses.
- `→` appended to button and link text.
- Emoji as status icons. Use the icon set.
- Numbered markers on anything that is not genuinely a sequence. The loop stages *are* a sequence. A feature list is not.
- Monospace on labels, headings or body copy.
- Toasts for events already visible on screen.
- Sparkles, wands, or any vocabulary framing the AI as magic. The entire argument of this product is that its reasoning is inspectable.
