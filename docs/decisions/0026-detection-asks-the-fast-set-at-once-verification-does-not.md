# ADR 0026 — Detection asks the fast set at once; verification does not

**Date:** 2026-11-12
**Status:** Accepted and implemented 2026-11-12. Unit-tested, exercised live
(`p5-gate-live-20261112-adr0026.log`), and measured on F02 (see "Measured").

## Context

`loop.py` runs the 3-case fast set twice per incident: once before detection
(`pre_fast`, shared by every detector) and once after a repair (`post_fast`,
the verification that decides whether the repair worked). `FR-07` said both
run "serially (never concurrently)". No document recorded why.

Under F02 each chat takes ~78s, so the serial pre-check alone is ~234s of
F02's ~473s detection time (`ROADMAP.md`, "Why detection takes 241s").

`harness/fastset_parallel.py` measured both modes against the live target
(`harness/reports/fastset-parallel-20261112.json`):

| | serial | all at once | speed-up |
|---|---|---|---|
| healthy, 10 pairs | 17.7s, 10/10 pass | 11.3s, 10/10 pass | 1.57x |
| F02, 5 pairs | 234s, 0/5 pass | 83s, 0/5 pass | 2.82x |

Same verdict in all 30 runs, and no quality failure in either mode. Under F02,
the serial set fails on health AND on the 120s budget. The parallel set
finishes inside the budget, so it fails on health alone.

## The constraint that shaped the decision

The budget means "the three answers together took under 120s". At once, the
wall time is the slowest case, not the sum, so the same 120s is about 3x
looser. **In verification that is a safety check:** a repair that left every
answer taking ~100s would pass, which is a false heal. `AGENTS.md` forbids
weakening a safety check. In detection the budget is one of three fault signals
(health, budget, quality), and loosening it costs sensitivity, not safety: a
missed detection heals nothing, but it never heals wrongly.

## Options put to the owner

1. Ask all at once everywhere, with a 40s budget for parallel runs. This keeps
   the budget about as strict as before, but the new number needs its own
   false-alarm screening.
2. Ask all at once everywhere, keeping 120s. **Refused**: it loosens the
   verification safety check.
3. Ask all at once for detection only; verification stays serial with 120s.
4. Change nothing.

## Decision

The owner chose **option 3**.

- `fast.run(..., parallel=True)` asks every case on its own thread after the
  health probe. Cases keep the set's order, and pass/fail rules are unchanged.
- `loop.py` uses it for `pre_fast` only. `post_fast` is unchanged.
- `FastVerificationResult.parallel` records which mode ran. The RCA evidence
  item EV-V00 then says "with all cases asked at once", because "took 83s,
  within the 120s budget" read as a serial total would understate an F02
  latency. Serial EV-V00 text is unchanged byte for byte.

## Costs, stated

- **Detection under a slowdown that `/healthz` cannot see** (slowness in the
  app's own code, not the model) now needs each answer to exceed ~120s rather
  than the three together. F02 is unaffected: `/healthz` failed in 5 of 5 F02
  runs in both modes.
- **The evidence the LLM reads changed for every class.** EV-V00's total time
  is lower, and under F02 it reads "within" rather than "OVER" the budget.
  Per-case times (~83s each under F02) are still in EV-V01..03. Measured
  below: gpt-oss-120b still diagnoses F02 5 of 5. Other classes are not
  re-measured with this change.
- **The target's manifest** declares `execution: serial`
  (`Target_RAG-App/kavach.yaml`, validated as `Literal["serial"]`). No code
  reads it. It is left as is and read as describing verification, which stays
  serial. Changing a target file needs its own decision (`PRD.md` §5.2).
- **Load:** detection now sends three concurrent chats to the target. On the
  healthy laptop target each answer slowed from ~6s to ~11s, so the local
  model partly queues them.

## Tests

- `test_f06_loop.py`: parallel gives the serial verdict, in the same order,
  faster; the loop asks at once for detection and one at a time for
  verification. That test fails if verification is made parallel.
- `test_f02_detection.py`: EV-V00 names the parallel mode.

## Measured

F02 only, 5 reps, gpt-oss-120b via Groq, the same model as the bench it is
compared with (`bench-20261112-f02-parallel` against the F02 rows of
`bench-20261111-groq`):

| F02, 5 reps | before | after |
|---|---|---|
| MTTD median (range) | 473.3s (472.7-475.3) | 327.1s (322.5-330.7) |
| of which harness warm-up | ~234s | ~236s |
| of which the loop's own detection | ~239s | ~91s |
| LLM names F02 | 5/5, conf 0.92-0.93 | 5/5, conf 0.92-0.93 |
| repair `switch_llm_endpoint` | 5/5 | 5/5 |
| healed / false heals | 5/5 / 0 | 5/5 / 0 |
| MTTR median | 741.2s | 446.2s |
| target clean after run | 5/5 | 5/5 |

- **The EV-V00 risk did not show.** The changed evidence ("within" rather
  than "OVER" the budget) did not move the diagnosis or its confidence.
- **MTTD is as predicted** (~320s estimated). It still misses the 30s target
  by about 11x. The warm-up is the harness running one serial fast-set round
  so that F02's two-minute p95 crosses its floor (`kavach_baseline.py`,
  `warm_up_f02`). It was not changed, and it is still counted in MTTD.
- **MTTR is not ADR 0026 alone.** The earlier bench predates ADR 0025, and an
  approved heal detects twice: once before it parks and once after approval.
  Both detections got faster. `first_verdict - MTTD` (the LLM call plus the
  gate) is ~5s, so ADR 0025's skipped second call accounts for at most ~5s
  of the ~295s drop. The rest is the second detection.
- n = 5 per arm, one class, one model. Nothing here is a claim about F01, F06,
  F07 or F08 under parallel detection.
