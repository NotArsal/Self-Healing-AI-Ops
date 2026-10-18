# ADR 0010 — `empty_context_ratio` moves to a 60-second window, in the manifest and the detector together

**Date:** 2026-10-18
**Status:** Accepted
**Changes:** `kavach.yaml` `slo.empty_context_ratio.window_s` 600 → 60 and its expression's `[10m]` → `[1m]`; `detection/retrieval_collapse.py` and `rca/evidence.py` to match
**Required by:** `PRD.md` §12, which records this window class of problem three times; `AGENTS.md`, which makes the manifest the safety contract

## Context

`ADR`-less work earlier the same day shortened `kept_chunks_mean` from
`[10m]` to `[1m]`. That needed no decision record because `kept_chunks` has
no SLO in the manifest — its only appearance there is as a denominator inside
another expression — so no declared contract governed its window.

`empty_context_ratio` is different. It is a declared SLO with
`window_s: 600`, and the detector's query mirrored it. Shortening the
detector alone would have put the implementation and the contract out of
step, which is the failure this project has already been bitten by in
another form: a fix applied in one call path and measured in another.

F06 claims when **`kept_chunks` is low OR `empty_context_ratio` is high**.
Once `kept_chunks` was shortened, `empty_context_ratio` became the sole
remaining contaminator — and it was enough on its own.

## The measurement

Five candidate windows, live, against the real stack
(`harness/window_sweep_f06.py`, artifact
`harness/reports/window-sweep-empty-context.json`):

| window | detects fault | **forgets it** |
|---|---|---|
| 30s | 18.6s | 19.3s |
| **1m** | 37.7s | **59.1s** |
| 2m | 56.6s | 99.4s |
| 5m | 76.0s | 255.5s |
| 10m (was) | 131.9s | **494.1s** |

**At 600s this signal takes over eight minutes to forget a fault.** For that
entire time, the next fault of any class is diagnosed ambiguously: F06 claims
from the stale ratio alongside whichever detector is actually correct,
`run_all()` refuses to choose, and the loop escalates without acting. That is
the system behaving correctly on bad inputs, and it was observed three times
consecutively on `F07` and `F08` before the cause was understood — each one
looking like a broken fault class when both had passed their own live gate
the same day.

## Decision

`empty_context_ratio` is read over **60 seconds**, in the manifest and in
both copies of the query, changed together in one commit.

**60s rather than 30s**, matching `kept_chunks_mean`, for sample headroom and
because this signal is the more fragile of the two: it is a proportion
against a 0.20 ceiling, so a single empty context in a window holding three
requests reads 0.33. A shorter window makes one transient blip louder.

## What this does not fix

**It shortens the collision window from roughly eight minutes to roughly
one. It does not make a spurious F06 claim impossible.** A blip inside that
minute can still coincide with another fault failing the fast set, and the
same ambiguity results. Eliminating it would mean requiring **both**
grounding signals instead of either, which makes F06 strictly harder to
detect and is a separate decision with its own re-verification cost. It is
not taken here.

The remaining risk is bounded by a guard that already exists: no detector
claims while the fast set passes, so a stale ratio alone cannot drive a
repair. It only matters when something else is already breaking the fast set.

## Consequences

**`similarity_p50` is unchanged at `[10m]`** and its `window_s: 600` stands.
It must stay *healthy* during an F06 — that is what separates a bad rerank
filter from broken embeddings — so a long window on it is correct rather than
merely tolerable.

**A test now enforces agreement rather than a literal.** The previous test
pinned `similarity_p50` and `empty_context_ratio` at `[10m]`, and failed for
doing its job the moment this change was made. Pinning a number means every
legitimate change edits the test, which is not a check.
`test_the_detector_windows_match_the_manifest_they_mirror` instead reads
`kavach.yaml` and asserts the detector's window equals the declared
`window_s` for every mirrored signal — so the pair cannot drift in *either*
direction, and a future shortening of one alone fails loudly. It also asserts
`kept_chunks` still has no SLO, since the day it gains one its window stops
being detector-local.

**Verified after the change:** `make check` green (321 pytest, 79 vitest),
and `harness/p5_gate_live.py` re-run end to end — F06 detected on round 1 and
the full vertical PROVEN. A spec change that broke detection would be worse
than the contamination it fixes, so this was measured rather than assumed.

**This is the fourth occurrence of one root cause** and worth naming as a
pattern for the report: a windowed metric read over a window shorter than its
own contents. It has appeared as a fixed sleep that was too short, as F01's
error ratio carrying residue at `[5m]`, as one fault's harness poisoning
another's window, and now here. The general lesson is that any rate window in
this system is also a *memory*, and a measurement taken inside it measures
the past as much as the present.
