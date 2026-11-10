# ADR 0022 — No heartbeat watchdog; the dirty-target guard already removed the danger

**Date:** 2026-11-10
**Status:** Proposed — needs a decision, see "What I need from you"

## Context

`EXPERIMENT_CLOSURE_ABLATION.md` §15 names an unbuilt heartbeat watchdog as
its **top open item**: "a revert cannot survive a kill". That is literally
true. `one_incident` reverts its fault in a `finally`, and a `finally` does not
run on SIGKILL. Three faults were stranded in two days:

| Date | Cause | Stranded |
|---|---|---|
| 2026-11-08 | host killed the run for memory pressure | F06 (`rerank_threshold=0.999`) |
| 2026-11-08 | a `timeout 180` I put on a verification run | F01 |
| 2026-11-09 | `KMODE_EXCEPTION_NOT_HANDLED` bluescreen | none, by luck — F06's injection is a live config value and the container restart reset it. F07 writes prompt files to disk and would have persisted. |

**§15 was written before the dirty-target guard existed, and was not revisited
after.** The guard, added the same day, runs before the LLM probe and before
the fast set, refuses to start when any of F01/F06/F07/F08 is already active,
injects nothing, and names the remedy (`inject.py revert --all`). So the
failure mode today is a loud refusal costing one command — not a silent run
measuring a contaminated target, which is what made a stranded fault dangerous.

That changes the question from "how do we auto-revert" to "is auto-revert
worth anything now", and §15's priority is stale.

## Options

**1. Separate watchdog process with a lease file.** The runner heartbeats; the
watchdog reverts when the lease goes stale.

- Introduces **a second process that can mutate the system under management**,
  which is the thing **ADR 0003** exists to forbid and `FR-15a` (writer
  exclusivity) prohibits. A watchdog being "part of Kavach" does not fix this:
  the concurrency is the problem, not the ownership.
- A stalled heartbeat reverts a *live* experiment. A single slow LLM call
  during a 2h17m run would be enough with a tight threshold, and a loose
  threshold does nothing a human would not have done sooner.
- Most code, most risk, and it is the option §15 assumed.

**2. Teach the existing guard to self-heal from a lease.** No new process. The
guard already runs before every run and already detects a dirty target. The
runner writes a lease on start and removes it on exit; when the guard finds a
dirty target **and** a stale or absent lease, it reverts and proceeds instead
of refusing.

- ~20 lines, no new process, no second writer.
- But it converts a **refusing** safety check into an **acting** one, which
  `AGENTS.md` puts under "never weaken a safety check". I do not think an
  auto-revert is a weakening — the end state is still a verified-clean target
  and the guard still runs — but two things genuinely get worse: a human loses
  the chance to notice that something crashed, and if the lease is absent
  because a *different* process legitimately owns that fault, the guard
  clobbers a live run. That second case is exactly the concurrency hazard of
  option 1, moved to a different place.

**3. Do nothing. Keep the loud refusal.** Costs one `inject.py revert --all`
after a crash. That is three commands over the two days that produced this ADR.

## Decision (proposed)

**Option 3 now; option 2 only if crashes keep happening.** A watchdog is the
most machinery for the least remaining risk, and it reintroduces the one thing
ADR 0003 was written to prevent. The guard already converted this from a
correctness hazard into an inconvenience, and an inconvenience that costs one
command three times in two days does not justify a concurrent mutator.

I am recording this rather than building it because the only cheap design
(option 2) changes the behaviour of a safety check, and that is not a call to
make unilaterally — least of all overnight.

## What I need from you

Pick one. If option 2, I will also need to know whether a **missing** lease
(not merely stale) may authorise an automatic revert; I would say no, because
a missing lease is indistinguishable from a run started another way, and
refusing in that case keeps the guard's current behaviour as the default.

## Consequences

- §15's "top open item" is superseded by the guard and should say so. Noted
  there rather than rewritten, since §15 is a dated record.
- The stranded-fault risk is not zero: it is one manual command, discovered
  by a refusal rather than by a wrong number. That is the property worth
  keeping, whichever option is chosen.
