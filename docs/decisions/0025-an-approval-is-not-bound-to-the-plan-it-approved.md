# ADR 0025 — An approval is not bound to the plan it approved

**Date:** 2026-11-12
**Status:** Accepted and implemented 2026-11-12 — option 3; a changed plan
parks again for a fresh approval. Unit-tested; not yet exercised live.

## Context

In `APPROVAL` mode a MEDIUM repair parks at `AWAITING_APPROVAL`. The operator
reads the plan (fault class, action, diff, inverse — `UX-05`) and approves.
`runner.approve()` then **re-runs the loop from scratch** with
`approved_from=<incident>`: it re-detects and re-prepares, because the world may
have moved since the dialog opened. That reason is sound and this ADR keeps it.

Two problems come from how the approval travels, and they share one root.

**1. A correct approved plan can be thrown away (measured).** The re-run calls
the LLM again. In the 2026-11-11 qwen2.5:7b bench, F07 rep 5 (INC-142743) was
diagnosed correctly, approved, and then the second RCA call named a different
class. The validator rejected the disagreement, as it should, and nothing was
repaired. It is the one miss in P(heal | diagnosis correct) = 15/16
(`ROADMAP.md`, "An approval does not carry the diagnosis").

It is not a one-off. `harness/compare_benches.py` finds the same signature
twice in the 2026-11-02 bench (`bench-20261102-night.json`, F07 reps 2 and 5):
the first diagnosis is F07, which is correct, and the escalation reads
"LLM says F06, deterministic detection says F07". That bench predates the
`incident_id` field, so the link to an approved re-run is inferred from the
signature, not read from the audit log. **Three times in 45 runs, all F07.**

**2. An approval can execute a plan nobody approved (by code reading, not yet
observed).** The parked record stores `baseline_value`, `policy`, `use_rca` and
a timestamp (`api/runner.py:518`). It does **not** store the fault class, the
action or the diff the operator saw. The approval reaches `permit()` as an
incident id string (`loop.py:496`), and `_route()` treats any non-empty string
as approval (`safety/engine.py`, `if approved: return ... ALLOW_AUTO`). So if the
re-run reaches a *different* plan, it executes under the old approval.

Concrete case: the operator approves `rollback_config` for F06. Before they
click, F06 clears and F01 starts. The re-run detects F01, plans
`switch_llm_endpoint`, and runs it, approved by a click on an F06 dialog.

What still bounds this: steps 1–10 of `permit()` run again, so the action must
be allow-listed, not denied, owned by the project, and have an inverse, and the
breaker and blast radius still apply. For the reference workload the
allow-list is `rollback_config`, `switch_llm_endpoint` and `rollback_prompt`
(`Target_RAG-App/kavach.yaml`), each with a recorded inverse. **For this
project it is a wrong action, not an unsafe one. But it breaks the one promise
`APPROVAL` mode makes: a human saw *this* change before it ran.**

It is worse for any project that allow-lists `apply_patch`. An approval moves a
HIGH action to the sandbox (`_route`), and `loop.py` promotes a patch whose
sandbox has passed. So a mismatched approval could put a generated patch into
production that no human was ever shown. The loop cannot plan `apply_patch`
today: it is the permitted repair for no class, and the model may not name it
(`rca/schema.py`, `NOT_MODEL_PROPOSABLE`). So this path is not reachable
through `approve()` now. A binding closes it before something makes it
reachable.

The root of both problems: **the approval authorises "something", not "this
plan".**

## Options

**1. Leave it.** Problem 1 costs heals whenever the model is unstable, and
problem 2 stays open. Free.

**2. Bind the approval to the plan; re-diagnose as today.** Store the approved
`(fault_class, service, action, requested settings)` in the parked record. If
the re-run reaches the same plan, execute. If it reaches anything else, do not
execute: park again as a new plan with the reason "the plan changed since you
approved it". This closes problem 2 but leaves problem 1, because the second
LLM call can still disagree.

**3. Bind the approval to the plan; re-check deterministically, not with the
LLM.** Same binding as option 2. On approval, re-run *detection* (deterministic,
no LLM) and re-prepare (fresh pre-state, fresh inverse). If the detector still
names the approved class and the plan builds to the approved action and
settings, execute. Otherwise park again. The LLM diagnosis the human read is
carried over, not regenerated.

- **Why this is safe.** The validator only accepts an LLM class that matches
  the detector (`deterministic_agreement`). If the detector still names the
  same class, the approved diagnosis still agrees with it. The "world moved"
  check is the deterministic detector's job, and it still runs.
- **What it gives up.** The cited evidence is not re-validated against the
  fresh evidence frame. The human already read that evidence and approved it.
- **What it changes.** `approve()` currently re-derives the plan "the way it
  was derived" (`use_rca`), after a live F01 approval was lost the other way
  round: RCA was forced onto a deterministic plan. Option 3 follows the same
  lesson from the other side: the approval re-checks the *world*, not the
  *model*.

## Recommendation

**Option 3.** It is the only option that fixes both problems. It keeps the
re-detection that the original design was right to insist on, and it makes the
approval mean what the console tells the operator it means. Option 2 is the
minimum if you want to keep the second LLM call.

Either binding option needs tests that fail today:
- an approved re-run that reaches a different action must not execute;
- an approved re-run whose detector still agrees must execute without a second
  RCA call (option 3 only);
- the audit record keeps `approved_from` and gains the bound plan.

## What the Groq bench did and did not tell us

The 2026-11-11 Groq bench (gpt-oss-120b, `bench-20261111-groq.json`) healed
25/25, with no run diagnosed correctly and left unhealed: the stronger model
overturned no approved diagnosis. So problem 1 is rare with this model, not
impossible: one model change brings it back. **Problem 2 does not depend on the
model at all.** It depends only on the world changing between park and click,
and no bench measures that because the bench approves immediately.

## Decision

The owner chose **option 3** on 2026-11-12. When the re-checked plan differs
from the approved one, Kavach **parks it again** as a new plan with the reason
"the plan changed since you approved it", so it does not escalate. The tests
listed under "Recommendation" are written first and must fail before the change.

## How it was built

- `loop.ApprovedPlan` is what the operator saw: fault class, service, action,
  requested settings, and the diagnosis. `runner.start()` stores it in the
  parked record, and `approve()` passes it to the re-run and writes it on the
  `approved` audit row.
- If the detector still names the approved class on the approved service, the
  re-run carries the approved diagnosis over and the LLM is not called.
  Otherwise it diagnoses afresh, because there is a new plan for a human to
  read.
- At the gate, `ApprovedPlan.mismatch()` compares the rebuilt plan with the
  approved one. On any difference the approval does not reach `permit()`, and
  the `permit` audit row records `approval_mismatch`.
- "Re-park" is implemented as "judged as unapproved". In APPROVAL and
  SIMULATION mode that parks it. In AUTONOMOUS mode a LOW plan would run, which
  is what that mode does for any fresh incident; the old approval grants it
  nothing.
- Tests: `test_f06_loop.py` (a different fault, different settings, a plan
  that still holds with the LLM never called) and `test_p5b.py` (the plan is
  parked, and handed over on approval). With the binding removed, the two
  mismatch tests fail.

## Follow-up 2026-11-12: what the approved incident shows

The approved incident used to keep AWAITING_APPROVAL forever, because the fix
runs as a new incident and nothing updated the old one. The console reads
`awaiting_approval` from that status, so it kept offering an Approve that could
only return 409. The owner chose a new status:

- `approve()` sets the old incident to `APPROVED`, with "the fix runs as
  INC-…" in `outcome`. The reverse link is the `approved_from` field on the
  re-run's `permit` audit row.
- If the re-run cannot start, the plan is parked again and an
  `approval_not_run` audit row records why. Before, the plan was removed first
  and lost.
- `reject()` checks the reason before it removes the plan. A reason of three
  spaces passed the API's length rule and lost the plan.

Not changed: incidents stored before this fix keep AWAITING_APPROVAL, and after
an API restart a parked incident still shows Approve although the plan is gone
from memory (`runner.py`, `_awaiting`). Both settled by ADR 0028 (2026-11-13): stored rows are
corrected from the audit log at startup, and Approve needs the plan in memory. Fleet metrics count `APPROVED` in the
total only, not as resolved, escalated or awaiting.
