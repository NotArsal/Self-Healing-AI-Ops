# ADR 0020 — The incident routes read the store, and the bench scores two answers

**Date:** 2026-10-20
**Status:** Accepted
**Changes:** `loop.Incident.from_dict`; `LoopRunner.history()` and `.find()`;
`GET /v1/incidents`, `GET /v1/incidents/{id}` and `GET /v1/llm-calls` read
through the store; `harness/report.py` records `llm_action` and
`escalation_reason` and reports **class accuracy** and **action accuracy**
separately; `postmortem` prints UTF-8.
**Closes:** `RESEARCH_NOTES.md` §7.2, and §10's second gap
**Related:** [ADR 0014](0014-mttd-was-never-measured-so-the-figure-is-withdrawn.md),
[ADR 0019](0019-mttd-is-measured-and-the-target-stays-but-per-class.md)

## Context

Two findings from the 2026-10-20 bench, both about reading rather than doing.

**Incidents were persisted and never read back.** All of them were in
Postgres with full RCA payloads, and `IncidentStore.get()`/`.recent()` both
existed — but `GET /v1/incidents` returned `runner.incidents()`, the in-process
ring. So an API restart emptied the console's history and `make postmortem`
printed *"no incidents recorded yet"* with the data sitting in the database.
Run B's thirty-seven diagnoses had to be dumped to an artifact by hand
(`harness/dump_diagnoses.py`) so a finding this repository now reports would
survive a `make down`.

**The bench scored one of the model's two answers.** A diagnosis carries a
`fault_class` *and* a `candidate_repair`. `report.py` recorded only the class,
as `llm_class`, and every accuracy figure in the report came from that field —
while `validate.py` has always checked both, as `deterministic_agreement` and
`repair_permitted`.

## Decision

### Read through the store, and never write through it

`Incident.from_dict` inverts `to_dict`, which is what the store persists, so
the API's existing mappers serve a restored incident unchanged — no second
reconstruction layer on the read path, which is why §7.2 left this open.

Three properties, each tested:

- **Memory wins a collision.** `_remember` saves best-effort, so a database
  that blinked mid-incident holds the older copy. Preferring the stored row
  would show a stale status for an incident still running.
- **An unreachable store degrades to the old behaviour**, never to an error.
  A database that is down must not cost a read, as it must not stop a heal.
- **A restored incident cannot be approved.** `approve()` and `reject()` gate
  on `_awaiting`, which lives in memory and is never repopulated. This is the
  safety property of the change and it is the same reasoning as `approve()`
  re-detecting rather than replaying: *a plan parked before a restart was
  derived from a world that has since moved.*

**Alerts still read memory**, deliberately. Every alert rule asks *why will
the next repair be refused* — an escalation streak, an open breaker, blast
radius spent. Those are claims about now. Evaluated over a restored history
they would fire on three escalations from last week, and an operator who
learns to ignore the panel is worse off than one with an empty panel.

### Score the class and the action separately

`report.py` now records `llm_action` from `rca.diagnosis.candidate_repair` and
the validator's `escalation_reason` verbatim, and prints the joint table. The
action is scored against the **injected** class, not against the class the
model named: scoring it against its own claim would measure internal
coherence and mark a self-consistent wrong answer correct.

`permitted_repair()` is imported from `rca.validate` rather than re-typed. A
copied lookup that drifted is how the accuracy column came to read the
deterministic verdict once already.

## What it found immediately

Replaying run B's 37 diagnoses through the new scoring:

| | action right | action wrong |
|---|---|---|
| **class right** | 31 | **1** |
| **class wrong** | **2** | 3 |

Both off-diagonal cells are populated, and the second one was not predicted.

- **`INC-210032`** — class right, repair forbidden. Detection F06, diagnosis
  F06 at 0.95, agreement rule satisfied, and `rollback_prompt` proposed for a
  retrieval collapse. **The old scoring counted it in the 17/20 as correct,
  and it healed nothing.**
- **`INC-230239`, `INC-010248`** — class wrong, repair right. On injected F07
  the model named F06 and still proposed `rollback_prompt`, the correct F07
  repair.

So **action accuracy (33/37) is higher than class accuracy (32/37)**. The
repair the model reached for was right more often than the label it wrote.
These are not one measurement with noise in it; the class is the weaker of
the two, and it is the one that was being reported.

## What this cost to find

**`make postmortem` crashed on Windows** after rendering 1.5KB of a report
nobody saw: `UnicodeEncodeError: 'charmap' codec can't encode '→'`. The
Markdown was correct and `--out` always wrote it fine; the default console
encoding was the problem, and the demo's closing beat runs without `--out`.
It now reconfigures stdout to UTF-8 and substitutes rather than raises — a
postmortem with an arrow turned into `?` is still a postmortem, a traceback
is not. Found only because fixing the store made the renderer get far enough
to fail.

**A mutation check caught a hole in the safety test.** The first version of
`test_a_restored_incident_cannot_be_approved` asserted on `awaiting()` without
calling `history()` first, so a deliberately introduced mutant that pushed
restored `AWAITING_APPROVAL` incidents straight into `_awaiting` **passed it**
— the mutated line never ran. Both mutants are caught now.

> **A test that does not execute the line it is protecting is documentation
> with an assert in it.** The cheapest way to find out is to break the code on
> purpose and check the test notices.

## Limits, stated

- `history()` is capped at `HISTORY_MAX` (50), so the console shows the 50
  most recent incidents and not the full table. Pagination is not built.
- The joint table above is over **37 diagnoses**, which counts both draws of
  each approved incident. The bench's own `n` is 20 first draws. Two
  denominators for two questions, named wherever either is quoted.
- Action accuracy has **no target** in `PRD.md` §10. It is reported without
  one rather than being given one after the fact.
