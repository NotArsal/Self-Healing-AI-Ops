# ADR 0023 — `F02` is restored, because it is the second confusable pair and shares `F01`'s repair

**Date:** 2026-11-10
**Status:** Accepted — owner's decision, 2026-11-10
**Partially reverses:** `ROADMAP.md`'s week-10 checkpoint, which dropped `F02` and `F05`
**Required by:** `PRD.md` §5, which makes scope binding and requires a decision record for a change to it
**Does not revive:** `F03`, `F05` or `F09` — see "What stays out"

## Context

The implemented catalogue is four classes: `F01`, `F06`, `F07`, `F08`.
`PRD.md` §6 still says *"Seven of the eight have a v1 injector"*, written when
that was true; `harness/report.py` has printed the real denominator with every
table since, precisely because it shrank. `F02` was not closed on evidence
like `F09` — it was dropped on schedule at a checkpoint.

Three things make it the cheapest honest class to add, and I argued against
adding any class before checking them:

1. **The injection mechanism already exists and is already documented.**
   `harness/faults/f01_endpoint_outage.py` says it outright: *"Toxiproxy can
   inject latency, bandwidth limits and partial failures, and `F02` (latency
   degradation) is exactly that."* `F01` disables the listener instead,
   deliberately, so that *"a timeout-shaped toxic would be `F02` wearing
   `F01`'s name"* could not happen. The design for `F02` is a latency toxic
   through the same Toxiproxy admin API `F01` already drives.
2. **The repair already exists and is shared.** `PRD.md` §6 assigns `F02` the
   same `switch_llm_endpoint` as `F01`, which is implemented and measured.
3. **The detection signal reads metrics that already exist** — p95 LLM
   operation duration against `SLO x 2`, off the LLM spans the collector
   already receives.

## The research argument, which is the real reason

`PRD.md` §6 already claims `F07`/`F08` being *"behaviourally identical and
separable only by which artifact drifted"* is **a harder discrimination test
than a fifth easy class would have been**. The 2026-11-09 run makes that the
most interesting property in the project rather than a footnote: the shipped
evidence frame named `F07` as `F06` in 30 of 39 diagnoses **at 0.95
confidence** (`EXPERIMENT_CLOSURE_ABLATION.md` §17.2).

`F01`/`F02` is a second confusable pair with one decisive difference: **the
two classes share a repair action.** That separates two things the current
catalogue cannot:

- With `F07`/`F08`, a wrong class label means a wrong or refused repair. The
  gate's class check is load-bearing, and `REPORT_DRAFT` §6 now quantifies its
  cost — 4 of 5 wrong-class diagnoses proposed the *correct* repair and were
  refused anyway.
- With `F01`/`F02`, a wrong class label still yields the **right action**. So
  it isolates the question the gate's cost raises: when the action is
  identical, does the class check cost anything at all, or does it only cost
  when the classes differ in repair?

No existing class can ask that. That is a sharper reason to add `F02` than
breadth, and it is the reason this ADR exists rather than a checkpoint
reversal note.

## What must be built

| Piece | State |
|---|---|
| injector — latency toxic via the Toxiproxy admin API | new; mechanism exists, `F01` drives the same API |
| detector — p95 LLM operation duration > `SLO x 2` | new; the spans and the metric pipeline exist |
| `DISCRIMINATING` entry for `F02` in `harness/evidence_closure.py` | new, additive; keyed per class, so the four existing entries are untouched and the ablation's control arm is unaffected |
| repair `switch_llm_endpoint` | **exists**, shared with `F01` |
| verification probe, risk tier LOW | defined in `PRD.md` §6 already |
| acceptance criteria in `ROADMAP.md`, tests | new |

**Consequence to state, not hide:** the bench denominator goes from four to
five, and every table that prints it must be regenerated. `report.py` prints
the denominator with every table by design, so this is a re-run rather than an
edit.

## What stays out

- **`F03`** — crash-loop / OOM. `PRD.md` §6.4: no honest way to inject it
  against this target has been found. Nothing has changed.
- **`F09`** — token blowout. **Closed on measurement 2026-10-18** with the
  numbers published: `rerank_threshold` to 0.0 gives 1.20x because the
  retriever fetches a fixed top-k *before* reranking; three verbose prompts
  give 0.87x, 1.17x and 1.01x; `max_tokens` is a ceiling. The honest route is
  `top_k` in the control interface, which is a **twelfth** permitted target
  addition against §5.2's cap of eleven and needs its own ADR. Re-opening it
  on anything less would be the contrived injector this project forbids
  itself.
- **`F05`** — connection pool exhaustion. Feasible: the repair
  (`restart_container`) exists. Left out because the injector is messier and
  it adds no confusable pair, so it buys breadth and nothing else. Revisit
  only after `F02` lands.

## Sequencing

**After** `EXPERIMENT_CLOSURE_ABLATION.md` §17.4's report rewrites and the
cross-provider run. A fifth fault class cannot fix a report whose §4.4a
explains a mechanism its own primary test refuted. This is a scope *addition*
with 31 days to the deck, so it is ordered behind the work that removes a
contradiction rather than ahead of it.
