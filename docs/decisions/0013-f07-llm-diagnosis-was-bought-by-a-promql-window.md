# ADR 0013 — F07's 10/10 LLM diagnosis was bought by a PromQL window, and it is not being bought back

**Date:** 2026-10-19
**Status:** Accepted
**Changes:** nothing in code. This records a measurement and refuses a revert.
**Supersedes the claim in:** `ROADMAP.md` P6 F07 acceptance, `REPORT_DRAFT.md` §4.3
**Depends on:** [ADR 0010](0010-empty-context-window-is-a-spec-change.md)

## Context

The overnight `make bench` run (4 classes × 5 reps, 2026-10-18/19) healed
F07 **zero times out of five**. Three reps the model diagnosed F06; two it
diagnosed F07 and then flipped to F06 on the post-approval re-run. Every one
escalated with nothing written.

This contradicted the recorded P6 acceptance result of **10/10** for
`qwen2.5:7b-instruct` on F07, measured 2026-10-17.

## The measurement

`harness/rca_f07_live.py`, same model, same baseline file
(`baseline-simple-rag-20261017T163257+0000.json`), same ten repetitions, one
variable changed per run.

| run | frame window | `num_ctx` | result | artifact |
|---|---|---|---|---|
| 2026-10-17 | `[10m]` | 4096 | **10/10 F07** | `p6-f07-rca-qwen.json` |
| 2026-10-19 | `[1m]` | 8192 | **0/10** — all F06 | `p6-f07-rca-qwen-ctx8192.json` |
| 2026-10-19 | `[1m]` | 4096 | **0/10** — all F06 | `p6-f07-rca-qwen-ctx4096-ab.json` |
| 2026-10-19 | `[10m]` | 8192 | **10/10 F07** | `p6-f07-rca-qwen-frame10m-ab.json` |

The context window is exonerated: `[1m]` fails at both 4096 and 8192. The
frame window is causal — reverting only the two `METRIC_QUERIES` ranges in
`rca/evidence.py` restores 10/10, validator approval 10/10, and the correct
repair named 10/10.

ADR 0010 and the undocumented `kept_chunks` change before it moved those
ranges from `[10m]` to `[1m]` so that **the evidence frame and the detector
read the same signal** — a correctness fix with a test pinning it
(`test_the_frame_and_the_detector_read_kept_chunks_identically`). Nobody
re-measured F07 afterwards, because F07's accuracy had no visible dependency
on a retrieval metric.

## What the model actually does when it fails

It is not confused about the fault. At `[1m]` it returns:

> `fault_class: "F06"`, `fault_name: "Prompt version regression"`

F07 *is* "Prompt version regression". The model reads `EV-C08` — the line
saying `answer.txt` differs from its baseline — in **10 of 10** failing runs,
names the fault correctly in prose, and emits the wrong class code. Its
stated reason is that `EV-M02` (`4.0`) and `EV-M03` (`0.0`) look healthy,
which it treats as evidence *for* F06 while describing F06 as a rerank filter
discarding chunks it has just observed are not being discarded.

At `[10m]` the same metrics read `2.6471` and the model writes "This rules
out F06." The shorter window makes retrieval look *more* healthy, and a
cleaner retrieval signal pushes a 7B model toward the retrieval class rather
than away from it. That is not a reasoning chain; it is a 7B model
pattern-matching on the most recently salient numbers.

## Decision

**Keep `[1m]`. Do not revert for the sake of the number.**

Reverting would buy a 10/10 by putting the frame and the detector back out of
step — showing the model a different value from the one the deterministic
verdict rests on, which is the exact failure ADR 0010 and two tests exist to
prevent. Trading a verified invariant for a better-looking accuracy figure is
the "weaken the measurement to make something pass" move that `AGENTS.md`
forbids outright. The number is the result.

The consequences are accepted as follows:

- **F07's LLM path is reported as 0/10.** `ROADMAP.md`'s "≥ 8 of 10" P6
  acceptance for F07 is **FAILED**, not quietly re-scoped.
- **F07's deterministic path is unaffected and still works.** The bench
  detected F07 5/5 at a 39.4s median, and F07 resolves deterministically
  (`INC-191014`, 2026-10-19, `rollback_prompt`, verified). The repair does
  not need the model; the deterministic path heals it.
- **The cross-check absorbed the whole failure.** Five bench injections, five
  escalations, nothing written, target clean. The system's response to a
  model that cannot tell F07 from F06 was to refuse to act, which is what it
  is for.

## What this costs the report, stated plainly

`REPORT_DRAFT.md` §4.3's table is re-labelled. Ten repetitions against one
frozen frame measure **decoder determinism**, not accuracy — and this ADR
shows they are not even stable against an unrelated, correct change to a
PromQL range. Any figure of that shape is a property of the frame it was
taken on.

This is the **third** time in three days that a published measurement has
turned out to describe the instrument: the missing trailing newline
([ADR 0011](0011-the-sandbox-and-apply-patch-are-restored.md)), the unset
context window (`RESEARCH_NOTES.md` §4a), and now this. The pattern is worth
more than any individual number, and it belongs in the conclusion:

> **A measurement is a finding about the instrument until proven otherwise.**

The specific, generalisable version: **an evidence frame is an interface.**
Changing a PromQL range inside it is an API change to every consumer of that
frame, including a model whose behaviour nobody re-tests. Frame changes need
the same re-measurement discipline as prompt changes.

## Not done, and why

An obvious repair is available — when the deterministic detector is
unambiguous, do not re-derive the diagnosis through the model on the approved
path. That would heal F07 end to end. It is not taken here because it changes
what an operator's approval means, which is the operator's decision and not
an overnight one. Recorded in `RESEARCH_NOTES.md` §6.
