# ADR 0027 — ASCII art is allowed in the console, in two narrow forms

**Date:** 2026-11-12
**Status:** Accepted by the owner 2026-11-12. **Partly implemented** the same
day, in `apps/console` (tests: `tests/ascii.test.tsx`):

| §7.12 item | State |
|---|---|
| Empty state, "No incidents" | Built. Still frame of `icosahedron` (commit `b324cb0`), `components/ascii/` with the licence beside it |
| Empty state, "No active incident" | Not built. It is in `app/page.tsx`, which had another author's uncommitted edits at the time |
| Rail brand mark | Built as the text initial "K": no ASCII mark is legible at 40x40. Removes the §2.4 gradient violation |
| Boot and connecting screen | Not built. No such screen exists, and adding one is a new screen, not a piece |
| Incident durations | Built. A `Duration` column in the history table, bar beside the number, scale stated under the table. No end time shows "—", not "open": `resolved_at` is set only on RESOLVED, so APPROVED, NO_FAULT and ESCALATED rows have none either, and the status pill says which |
| Verification probes | Built as a budget bar: total time against `budget_s`, numbers beside it, "over budget" in words |
| Loop stages | Not built. The Loop Ring and the timeline already show every stage in words; the piece added nothing (see "Known costs") |

## Context

`DESIGN_SYSTEM.md` allowed no decorative art. Its direction is a calm
instrument in which the Loop Ring is the only gradient and the only motion that
is not a response to a user action, and monospace is for machine strings only.

The owner asked to use the animated ASCII library at
`https://www.ascii-magic.com/ascii` in the console. What was checked first:

- **Licence.** The `ascii-magic-art` repository states MIT, including commercial
  use. Two photo-based pieces, `ocean-sunset` and `starry-ridge`, keep the
  Unsplash licence. The LICENSE file itself was not read, only the README and
  the site FAQ.
- **Maturity.** 8 commits, one maintainer, no releases, 424 stars. A copied
  file cannot be pinned to a release, so a piece is copied, not depended on.
- **The stock pieces carry demo data.** Opened in a browser, *Circuit Breaker
  States* shows `payments-svc` and *Canary Rollout Gates* shows
  `canary v4.7.0 vs stable v4.6.0`. Shown in this console they would display
  services and releases Kavach never had.
- **Run-time loading breaks the offline demo.** The web embed loads a script
  from `ascii-magic.com`, and the terminal player is fetched by `npx`.
- **A piece is a small function from time to a frame of text**, with a `Grid`
  helper. A piece of our own can therefore draw real values.

## Decision

`DESIGN_SYSTEM.md` §7.12 permits ASCII art in two forms and nowhere else.

**A. Decorative, still frames,** in exactly three places: the empty states, the
rail brand mark, and the boot and connecting screen. One frame, one ink
(`--k-text-muted`), `aria-hidden`, technical or structural subjects, never a
mascot.

**B. Data-bound,** drawn from real API values by our own piece functions. Real
values only, the number always printed beside the drawing, unknown and
unimplemented states kept visible as pending, redrawn on data change with no
animation. The initial set is loop stages, incident durations and verification
probes, each checked against `lib/api/generated/schema.d.ts` (`EventOut`,
`IncidentSummary`, `VerificationOut`).

Pieces are **copied into the repo** with the licence text and source URL. They
are never loaded from `ascii-magic.com` or fetched by `npx` at run time.

## Options put to the owner

| Question | Chosen | Not chosen |
|---|---|---|
| Where | Empty states, rail mark, boot screen | Loading-only; anywhere decorative |
| Motion | Still frames only | Animate when idle; animate freely |
| Source | Copy into the repo | Load from ascii-magic.com at run time |
| Real data | A separate rule beside the still frames | Real data only; still frames only |

"Anywhere decorative" and "animate freely" were put as options and not chosen.
They would have removed the rule that the Loop Ring is the only motion.

## What this does not change

- §2.4: one gradient. The brand mark is flat ink.
- §9: the Loop Ring remains the only motion that is not a user action.
- §11: no sparkles, wands or magic vocabulary; that list is extended, not
  relaxed.
- The target's frontend. `DESIGN_SYSTEM.md` §0 still governs `apps/console/`
  and nothing else.

## Known costs and open points

- **The loop-stage piece overlaps the Loop Ring.** The ring already shows the
  seven stages. The piece is justified only if it adds something the ring does
  not, such as the stage name in words or the per-stage outcome. If it does not,
  it should not be built.
- **ASCII is coarser than the SVG sparkline §7.11 specifies.** A bar rounds,
  which is why the number is required beside it.
- **The rail brand mark must be legible in a 40×40 target.** If it is not, the
  rail keeps a text initial.
- **The rail logo was a gradient square**
  (`apps/console/components/ui/Rail.tsx`), which broke §2.4. It is now the flat
  text initial, and a test asserts the rail never uses the loop gradient.
- **The decorative frame needs its own size token**, `.k-ascii-art` (8/8): the
  smallest type token would make it 324px tall. Recorded in §7.12 A.
- **The running `kavach-console` container does not have this change.** It is a
  built image; it shows the change after `make up` rebuilds it.
- **`DESIGN_SYSTEM.md` §10.1 is out of date.** It lists the approval dialog and
  the mode switch as not built, but `ApprovalPanel.tsx` and `ModeSwitch.tsx`
  exist. Not corrected here, because it is outside this decision.
- **The SLO-window probe is still unimplemented**, so a verification piece
  shows it as pending (§7.8).
