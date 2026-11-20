# ADR 0032 — Automatic checks, off by default

**Date:** 2026-11-19
**Status:** Accepted by the owner 2026-11-19 (chose a setting plus a console switch, every 5 minutes) and implemented the same day.
Tests: `tests/test_auto_check.py` (10; removing the approval guard fails one), `tests/safety.test.tsx` (2).
**Related:** [ADR 0028](0028-a-restart-leaves-no-decision-hanging-and-never-loosens-the-mode.md), [ADR 0030](0030-the-incident-lifecycle-is-one-table.md)

## Context

Kavach checked the target only when someone clicked Run loop or a script
called `POST /v1/loop/run`. Detection, diagnosis and repair were automatic
once a run started, but starting it was not, which was the first gap anyone
noticed in the review.

## Decision

`KAVACH_AUTO_CHECK` (default `false`) and `KAVACH_AUTO_CHECK_EVERY_S`
(default 300, minimum 60) set whether the API starts a loop run on its own,
and how often. `GET /v1/auto-check` reports the state, and `PUT /v1/auto-check`
switches it for the life of the process. Every switch is audited
(`auto_check_change`) and logged. A restart returns to the setting, never to
what the console last chose: an unattended run starts only when the durable
configuration, or a person who is present, says so.

A background task ticks every 5 seconds and starts a run when one is due. It
**skips** while a run is in flight, and **while any plan waits for approval**.
Without that rule, each check would re-find the parked fault, park a duplicate
incident and spend a slot of the hourly limit (5 per hour), and after five the
limit would refuse the operator's own Approve. A skipped or refused check is
recorded as the last result and shown on the console. A tick that raises is
logged, and the next tick still runs.

An automatic run is an ordinary run: the same gate, mode, limit and audit.
Its timeline says "automatic check started a loop run", and its log line has
`started_by=automatic check`. A healthy check costs nothing against the
hourly limit, which is spent only once a fault is found (`loop.py`,
`safety.permit`). Each check does put load on the target: 3 test questions
per check, so 36 an hour at the default interval.

## What it changes

- **In APPROVAL mode** (the default), an automatic check can only find a fault
  and park a plan for a person. Nothing is written without an approval.
- **In AUTONOMOUS mode**, a LOW-risk repair it finds runs with nobody present.
  That is what AUTONOMOUS already means, and it is the first time Kavach can
  heal with nobody in the loop at all. The console says so beside the switch.

## Limits

- The hourly limit is still kept in memory (a known gap), so a restart resets
  it. Automatic checks do not make that worse, because they never run while
  a plan is parked, but persisting the count remains open.
- No notification leaves the console when a check finds something (`PRD.md`
  lists a webhook as P2).
