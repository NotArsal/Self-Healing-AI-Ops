# ADR 0021 — The `fault_name` coherence check is not being added, because its unique catch set is the correct answers

**Date:** 2026-11-02
**Status:** Accepted
**Changes:** nothing in code. This records a decision *not* to add a check, and
corrects the framing of the open question it closes.
**Closes:** `REPORT_DRAFT.md` §9 item 7, `RESEARCH_NOTES.md` §10's open
recommendation
**Depends on:** [ADR 0013](0013-f07-llm-diagnosis-was-bought-by-a-promql-window.md)

## Context

Across three runs that record the field, **28 of 28** diagnoses that emitted
class `F06` carried F07's catalogue name, *Prompt version regression*, instead
of *Retrieval collapse*. Every other class was coherent: **49/49** on F01, F07
and F08. The defect is one cell of the mapping with no gradient, and it
survived a full host rebuild between runs C and D.

Nothing in the pipeline compares the two fields. `permit()` routes on the class
code and never reads the name beside it. The obvious response is to add a
coherence check: refuse any diagnosis whose `fault_name` is not the catalogue
name for its `fault_class`.

The cost of that was known and looked like a genuine tradeoff: such a check
refuses *every* F06 diagnosis, taking F06 from 5/5 to 0/5 and run D's
auto-resolution from 80% to 55%, days before a demo. The report recorded it as
an open decision for that reason.

**That framing was wrong**, and re-deriving it from the artifacts is what this
ADR records.

## The measurement

Pooled over all four bench artifacts — `bench-full.json` (run A),
`bench-20261020-mttd.json` (B), `bench-20261020-night.json` (C),
`bench-20261102-night.json` (D): **80 injections, 11 wrong diagnoses, 0
executed, 0 false heals.** All eleven wrong answers emitted `F06`.

Partition the diagnoses that emit F06 by whether they were *right*:

| | what the gate did | would a name check add anything? |
|---|---|---|
| F06 emitted, injection was **F07/F08** (11 rows, pooled) | **refused — 0 of 11 executed** | no: already refused |
| F06 emitted, injection was **F06** (11 rows in C+D) | 9 healed, 2 refused | **yes — it would refuse all 9 correct heals** |

So the check's *unique* catch set — the rows it would refuse that nothing else
refuses — is exactly the set in which the diagnosis was **correct**. The check
is not merely expensive on this data; it is anti-correlated with error.

### Why the existing gates already catch the real errors

In runs C and D, where `escalation_reason` is recorded, all five wrong rows
were refused with *both* reasons firing:

```
repair_permitted: proposed 'rollback_prompt', but F06 may only use 'rollback_config';
deterministic_agreement: LLM says F06, deterministic detection says F07
```

That is the mechanism, and it explains the whole result. The model's mistake is
**not** "F06 with a wrong name attached". It is a coherent *F07* diagnosis with
one corrupted field:

| field | what it says | which class that is |
|---|---|---|
| `fault_name` | *Prompt version regression* | F07 |
| proposed action | `rollback_prompt` | F07 |
| `fault_class` | `F06` | F06 — **the only field that says F06** |

Two of the three fields agree, and they agree on F07. `repair_permitted` and
`deterministic_agreement` both read the **action**, which stays coherent with
the model's actual understanding, so they fire precisely when that
understanding is wrong about the injected fault.

A name check reads a third field that is wrong for *every* F06 diagnosis —
correct and incorrect alike. It therefore carries no signal about correctness.
It is a constant, not a discriminator.

(In runs A and B the six remaining wrong rows show an empty
`escalation_reason` because the field did not exist in that schema yet, not
because they were unrefused — `executed` is `false` on all of them. The
mechanism above is verified on C and D only; the 0-of-11 execution result holds
across all four.)

## Decision

**Do not add the `fault_name` coherence check to the gate.**

It would convert nine correct, verified heals into escalations and refuse zero
additional bad executions. `AGENTS.md` forbids weakening a check to make
something pass; it does not oblige adding one that removes correct behaviour
and adds no safety.

**Keep recording the field.** The measurement is one of the project's three
headline findings and costs nothing to collect.

## What the finding actually says

This is the part worth carrying into the report, and it is stronger than the
check would have been:

> Kavach's safety on this failure mode comes from cross-checking the **proposed
> repair**, not the **stated class**. The class code is the least reliable field
> in the diagnosis — it is the only one that is ever wrong here — and the gate
> that routes on it is backstopped by two independent checks that do not read
> it.

That is a defence-in-depth result obtained by measurement rather than by
design, and it is also a warning: a future fault whose correct repair happens
to be *permitted* for the mis-bound class would defeat `repair_permitted`, and
only `deterministic_agreement` would be left. The architecture is one check
deep in that scenario, not two.

## What was considered and rejected

- **Trust the action over the class** — re-derive `fault_class` from the
  proposed repair when the two disagree. On this data it would be *more*
  accurate than the class field. Rejected for now: it makes the LLM's action
  choice authoritative over a field the deterministic detector also produces,
  which inverts the trust ordering that `deterministic_agreement` exists to
  enforce. That is a design change, not a fix, and it is not being made days
  before a demo.
- **Warn instead of refuse** — log incoherence without gating. Rejected as
  noise: it is 100% of F06 diagnoses, so the warning is a constant.
- **Fix the prompt** so F06 binds to its own name. Not rejected, but out of
  scope here and it would invalidate the cross-run comparison the four runs
  exist to support. If attempted, it is a new measurement series, not a patch.

## Consequences

- F06's reported 5/5 stands, with the caveat the report already carries: by its
  own prose the model understood those incidents as prompt regression, so the
  class accuracy overstates the quality of the understanding behind it.
- §9 item 7 closes. The ladder item about the mechanism being unnamed stays
  open — this ADR explains what the mis-binding *costs*, not what causes it.
- The "one check deep" scenario above is a new entry for the risk register.
