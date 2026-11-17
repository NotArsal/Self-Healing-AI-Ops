# ADR 0030 — The incident lifecycle is one table

**Date:** 2026-11-17
**Status:** Accepted by the owner 2026-11-17 and implemented the same day.
Tests: `tests/test_lifecycle.py` (17), each guard mutation-checked.
**Related:** [ADR 0025](0025-an-approval-is-not-bound-to-the-plan-it-approved.md),
[ADR 0028](0028-a-restart-leaves-no-decision-hanging-and-never-loosens-the-mode.md)

## Context

An incident's status was set in 19 places: 13 in `loop.run_once`, 3 in the
runner (approve, reject, the worker's crash handler), and 3 in ADR 0028's
startup settle, which writes database rows directly. Nothing said which
moves were legal, so an APPROVED incident could have been set back to
ESCALATED by any of them. Two of this month's bugs lived in that gap: the
approved incident that read AWAITING_APPROVAL forever (ADR 0025 follow-up)
and the 117 rows left parked by a restart (ADR 0028).

## Decision

`loop.MOVES` lists the legal moves, and `loop.transition(inc, to)` is the only
way to change a status. It raises `IllegalTransitionError` and leaves the
incident as it was. The settle checks `loop.legal()` before writing a row.

| from | to |
|---|---|
| DETECTED | NO_FAULT, ESCALATED, HEALING |
| HEALING | AWAITING_APPROVAL, RESOLVED, ESCALATED |
| AWAITING_APPROVAL | APPROVED, ESCALATED |
| NO_FAULT, RESOLVED, ESCALATED, APPROVED | nothing: final |

A test scans `kavach/` and fails on any status assignment outside
`transition()`. The two serialisation lines in `Incident` are marked
`# lifecycle-ok` with the reason.

An illegal move is a bug, so it raises. Inside a run, the runner's crash
handler turns that into ESCALATED, which acts on nothing: the safe direction.

## Not changed

- **The Approve button still also needs the plan in this process's memory**
  (`incident_out(parked=…)`, ADR 0028). The table removes the cause, but
  dropping that guard would weaken a safety check, which `AGENTS.md` forbids.
- **DETECTED still doubles as "run in progress".** The runner stores it before
  detection has found anything. A separate RUNNING status would change what
  `harness/report.py` waits on, so it is a follow-up, not part of this change.
