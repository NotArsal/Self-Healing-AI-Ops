# ADR 0014 — MTTD was never measured, so the figure is withdrawn rather than restated

**Date:** 2026-10-19
**Status:** Accepted
**Changes:** `loop.py` stamps `detection.concluded_at`; `harness/report.py`
computes MTTD from it and renames the old quantity `first_verdict_s`.
**Supersedes the claim in:** `REPORT_DRAFT.md` §4.1 (MTTD 48.5s, "missed"),
and the earlier conclusion that the `PRD.md` §10 target was the thing at fault
**Related:** [ADR 0013](0013-f07-llm-diagnosis-was-bought-by-a-promql-window.md)

## Context

The overnight bench reported an MTTD median of **48.5s** against the `PRD.md`
§10 target of **< 30s**. The first draft of `REPORT_DRAFT.md` §4.1 reported
that as a missed target and argued the target itself was wrong: detection is
bounded below by each detector's evaluation window, so a sub-30s median is
arithmetically unreachable.

The argument was reasonable and it was wrong. It was written without checking
what `mttd_s` actually measures.

## What `mttd_s` actually measured

`harness/report.py` set the clock at injection and read it **after
`wait_terminal` returned**. `wait_terminal`'s terminal set is
`{NO_FAULT, AWAITING_APPROVAL, RESOLVED, ESCALATED}`. So the figure spanned,
in order:

1. the F01/F06 traffic warm-up,
2. the pre-detection fast set (`loop.py`, `pre_fast = fast.run(...)`),
3. detection,
4. the **entire LLM diagnosis**,
5. the `permit()` gate.

Four of those five are not detection. The warm-up alone has a median of
**48.6s for F01 and 51.6s for F06** — recorded separately in the very same
artifact, and each larger than the whole 30s target it was being measured
against.

The other end of the interval is no better. `detected_at` is stamped at the
top of `run_once`, **before** detection runs, so it is an incident-open
timestamp. Between an injection stamp held by the harness and an incident-open
stamp held by the loop, **the instant detection concluded was never written
down by anything.**

## Decision

**Withdraw the MTTD figure. Do not restate the target.**

Reporting 48.5s as a missed target would be a second error on top of the
first: it treats a number that measures detect-plus-diagnose-plus-gate as
though it measures detection, and then adjusts the *target* to accommodate it.
That is fitting the acceptance criterion to an instrument nobody had read.

`REPORT_DRAFT.md` §4.1 now records MTTD as **"withdrawn — never measured"**
with no result, and reports 48.5s under its true name, *first verdict*, with
no target attached.

Instrumentation, not arithmetic:

- `loop.py` stamps `inc.detection["concluded_at"]` the moment `det.run_all`
  returns. Pinned by
  `test_detection_stamps_the_instant_it_concluded`, verified failing without
  the change.
- `harness/report.py` computes `mttd_s` from that stamp, and keeps the old
  quantity as `first_verdict_s`. If the stamp is absent — an image built
  before today — MTTD is reported as **missing**, never silently backfilled
  from `first_verdict_s`. That substitution is what produced the wrong number
  in the first place.

## What is still open, and deliberately not decided here

Whether **< 30s is the right target** is now an open question that cannot be
answered until a bench runs on the new stamp. The windows that bound it, for
whoever does that work:

| class | detector signal | window |
|---|---|---|
| F01 | `rate(llm_requests[2m])` error ratio, behind `min_requests ≥ 3.0` | 2m |
| F06 | `rate(empty_context[1m])`, `rate(kept_chunks[1m])` | 1m |
| F07 | prompt file hash vs. baseline | **no PromQL** |
| F08 | live settings vs. baseline snapshot | **no PromQL** |

Prometheus scrapes at 15s. Two classes wait on a rate window and two read no
metric at all, so a single cross-class MTTD target is questionable on its own
terms — but that is an argument to make *with* a measurement, not instead of
one.

## Why this keeps happening

Fourth in four days: the missing trailing newline
([ADR 0011](0011-the-sandbox-and-apply-patch-are-restored.md)), the unset
context window (`RESEARCH_NOTES.md` §4a), the PromQL frame window
([ADR 0013](0013-f07-llm-diagnosis-was-bought-by-a-promql-window.md)), and now
a metric that measured four phases and was named after one.

ADR 0013 stated the rule as *a measurement is a finding about the instrument
until proven otherwise*. This case sharpens it, because here the instrument
was not subtly miscalibrated — it was measuring a different quantity, and the
name on the variable was the only thing asserting otherwise:

> **A metric's name is a claim, and it is the claim least likely to have been
> tested.**

The practical form: for every figure in the report, find the line of code that
stops the clock, and check that the event it stops on is the event in the
metric's name.
