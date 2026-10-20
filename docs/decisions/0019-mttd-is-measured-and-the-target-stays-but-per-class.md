# ADR 0019 — MTTD is measured; the target stays, and is reported per class

**Date:** 2026-10-20
**Status:** Accepted
**Changes:** none to code. `REPORT_DRAFT.md` §4.1 replaces "withdrawn — never
measured" with a measurement; `PRD.md` §10's `< 30s` is **left exactly as
written**.
**Answers the open question in:** [ADR 0014](0014-mttd-was-never-measured-so-the-figure-is-withdrawn.md)
**Related:** [ADR 0013](0013-f07-llm-diagnosis-was-bought-by-a-promql-window.md)

## Context

ADR 0014 withdrew the MTTD figure because the harness had timed
injection-to-first-terminal-status and called it detection. It instrumented
`detection.concluded_at`, renamed the old quantity `first_verdict_s`, and left
one question open on purpose:

> Whether **< 30s is the right target** is now an open question that cannot be
> answered until a bench runs on the new stamp.

That bench ran: **4 classes x 5 reps = 20 injections**, 2026-10-19 18:54:55 to
2026-10-20 03:06:15 UTC, unattended, in `APPROVAL` mode, artifact
`harness/reports/bench-20261020-mttd.json`. Nothing was reset, raised or
disabled. Of the 8h 11m wall clock it spent **445 minutes (7.4h) waiting** for
the blast-radius window to slide.

## The measurement

| class | detector reads | MTTD median | min–max | n | vs `< 30s` |
|---|---|---|---|---|---|
| F08 config regression | live settings vs. snapshot, **no PromQL** | **18.5s** | 18.2–19.1 | 5 | met |
| F07 prompt regression | prompt hash vs. baseline, **no PromQL** | **20.1s** | 19.7–20.5 | 5 | met |
| F01 endpoint outage | `rate(llm_requests[2m])` | 60.8s | 36.5–62.0 | 5 | missed |
| F06 retrieval collapse | `rate(empty_context[1m])` | 71.2s | 53.6–74.4 | 5 | missed |
| **all** | | **28.5s** | 18.2–74.4 | 20 | **met** |

The aggregate meets the target. **That is the least informative true
statement available about it**, and the reason this ADR exists.

## Decision

**Leave `< 30s` in `PRD.md` §10 unchanged, and report MTTD per class with the
detector window beside it. Do not claim the aggregate as a system property.**

Three reasons, in the order they matter.

**1. The aggregate is a property of the class mix, not of Kavach.** The twenty
samples are bimodal with nothing in between: two classes land at 18–20s and
two at 54–74s. The 28.5s median sits in the empty gap, one sample either side
of the boundary. Inject F01 and F06 three times each instead of F07 and F08
and the same unchanged system reports a missed target. A number that moves
with the denominator and not with the code is not a result about the code.

**2. The floors are structural and now visible.** F07 and F08 read no metric:
their detectors compare a hash and a snapshot, so their floor is the fast set,
and they come in at **18–20s with a spread of 0.4s and 0.9s** — tight enough
that the figure is clearly a fixed cost, not a distribution. F01 and F06 wait
on a 2m and a 1m `rate()` behind a 15s scrape. F06's median of 71.2s against a
1m window, and F01's 60.8s against a 2m one, are each roughly one window plus
the fast set: the detectors are not slow, they are *waiting*, and ADR 0014's
arithmetic argument was right about the floor even though it was attached to
the wrong number.

**3. Moving the target after seeing the data is how acceptance criteria stop
meaning anything.** `AGENTS.md` forbids weakening an acceptance threshold to
make something pass. It would equally be weakening to *widen* `< 30s` to
`< 90s` now that two classes are known to exceed it, and it would be a
different kind of error to keep `< 30s` and quietly report only the aggregate
that clears it. The target stays; the two classes that miss it are reported as
missing it, with the window that bounds them.

## What the report must therefore not say

- Not **"MTTD 28.5s, target met"** on its own. True and misleading.
- Not **"the target is wrong"**. ADR 0014 made that argument before measuring
  and had to retract it. The target is a reasonable thing to want; two of four
  detectors cannot reach it by construction, which is a statement about those
  two detectors.
- Not **"F01 and F06 detection is slow"**. The detection logic is fast; the
  evidence is not yet available when it runs. Nor the converse — not
  **"shorten the windows"**: that is untested here.
  `window-sweep-f06.json` swept `30s` through `10m`, but it measured
  *recovery* detection and corpus contamination, not fault-detection latency,
  and what it found was that the **long** end is unsafe — at `5m` and `10m`
  the empty-context ratio stays at 0.48–0.54 while the fast set passes 100%,
  which is a window still reporting a fault that is over. It gives no reason
  to rule out `30s` for F06, and no evidence that `30s` would detect. That
  measurement does not exist yet and is not claimed here.

## Lesson

ADR 0013: *a measurement is a finding about the instrument until proven
otherwise.* ADR 0014: *a metric's name is a claim, and it is the claim least
likely to have been tested.* This one is about the denominator rather than the
instrument or the name:

> **An aggregate over classes with structurally different floors reports the
> class mix, not the system. Stating the aggregate without the split is the
> same error as a wrong name — the number is correct and the claim is not.**

The practical form: before reporting a median, plot the samples. If they are
bimodal, the median is describing the gap between two populations, and nothing
is in the gap.
