# ADR 0028 — A restart leaves no decision hanging, and never loosens the mode

**Date:** 2026-11-13
**Status:** Accepted by the owner 2026-11-13 ("restart bugs, server too"),
implemented the same night. Unit-tested (`tests/test_restart.py`, 12 tests,
each fix mutation-checked). Exercised once against the real store on the
first restart after it shipped: 117 `AWAITING_APPROVAL` became `APPROVED`
(87 name their re-run, 30 predate `approved_from`), `INC-181546` became
`ESCALATED` with "nothing was written", no approval lapsed, the mode stayed
`APPROVAL`, and the audit chain is intact. The table was dumped before the
restart.

## Context

The API process keeps four things only in memory: the parked plans
(`runner._awaiting`), the run slot, the operator's mode change
(`runner._mode_override`) and the safety engine's counters. The incident rows
are in Postgres. A restart therefore kept the rows and lost what they
referred to, and nothing reconciled the two:

- **117 rows read `AWAITING_APPROVAL`** on 2026-11-13. The console derived
  `awaiting_approval` from the status alone, so each one offered an Approve
  button that could only return 409. The audit log shows that **all 117 had
  in fact been approved**. They predate the `APPROVED` status (ADR 0025
  follow-up), so nothing ever updated them.
- **1 row read `DETECTED`** (`INC-181546`) with no audit row of its own. Its
  result was never saved, so it looked like a run still in progress forever.
- **The mode switch reverted to the manifest on every restart.** In the
  direction that matters, that loosens it: an operator who moved the project
  to `SIMULATION` to stop all writes got `APPROVAL` back, which writes after
  one click, the moment the container restarted.

## Decision

`runner.recover()` runs once at startup, after the store connects
(`main.lifespan`). It never raises.

1. **No stored row can be parked or running at startup**, because both live
   in memory and memory is empty. Every row still in `AWAITING_APPROVAL`,
   `DETECTED` or `HEALING` is settled from the audit log:
   - an `approved` event exists, so the row becomes `APPROVED`, and its
     outcome names the re-run from the `permit` row's `approved_from` where
     that exists (ADR 0025 onward);
   - no `approved` event, so the row becomes `ESCALATED` with "approval
     lapsed", nothing executed, and an `approval_lapsed` audit row. This is
     the same status `reject()` uses for a plan that was not run;
   - `DETECTED` or `HEALING` become `ESCALATED` with a `run_not_finished`
     audit row. `execute_start` is audited before the write, so its absence
     means "nothing was written". If it is present, the outcome says to check
     the target.

   Incident IDs are `INC-HHMMSS` and repeat across days, so an audit row
   counts only if it is not older than the incident it names.
2. **`awaiting_approval` is true only while this process holds the plan.**
   The status alone is not enough. This also covers a store that was down at
   startup, when step 1 could not run.
3. **The mode comes back only if it is stricter than the manifest's.** Order:
   `SIMULATION` < `APPROVAL` < `AUTONOMOUS`. The last `mode_change` in the
   audit log is restored if it is stricter, with a `mode_restored` row.
   Otherwise the manifest applies and a `mode_not_restored` row says why.
   `AUTONOMOUS` is never restored by a restart. A person sets it again or it
   stays off.

## Measured on the real store (2026-11-13)

| status | before | after |
|---|---|---|
| RESOLVED | 124 | 124 |
| AWAITING_APPROVAL | 117 | 0 |
| APPROVED | 0 | 117 |
| ESCALATED | 48 | 49 |
| DETECTED | 1 | 0 |

## Rejected

- **Persist the parked plans** so an approval survives a restart. This is the
  better long-term answer and is not ruled out. Since ADR 0025 the parked
  entry is plain data (`ApprovedPlan`, `use_rca`), so the old reason ("the
  prepared action cannot be pickled") no longer holds. It is a schema change
  and a new way for a stale approval to act, so it gets its own decision.
- **Rewrite the status at read time** instead of in the store. Then the API
  and the database disagree, and `make postmortem` reads the database.
- **A new `LAPSED` status.** `ESCALATED` with a reason already means "Kavach
  did not act, a person must", and `reject()` set the precedent. That costs
  one thing: a lapsed approval counts in the repair-success denominator.

## Not changed

- **The safety engine's counters reset on restart.** The five-starts-an-hour
  blast radius (`safety/limits.py`, an in-memory deque) and the breaker start
  empty, so a restart lets more heals through in that hour than the limit
  says. This follows from the code and was not exercised: on 2026-11-13 the
  bench had used 5 of 5 when the API was rebuilt, and the next live run was
  deliberately held until the real window had room. This is a weakening of
  a safety limit by restart. It is recorded in `PRD.md` §12 and
  not fixed here. The fix is the same pattern (rebuild the window from
  the audit log), but it changes the safety engine, which deserves its own
  review.
- One API process per database is assumed. A second process (`make dev-api`
  against the same Postgres) would settle the first one's parked rows at its
  own startup.
- `HEALING` is set before the gate inside `run_once`, but never leaves it.
  Every path reassigns the status before returning, and the runner stores
  only the result, so no reader sees it. No change.

## Follow-up 2026-11-13: the store can connect late

The owner restarted Docker Desktop and the console showed no incidents and no
timeline. The audit log shows why: `store_init` at 05:44:29 UTC failed with
"the database system is starting up". Docker restarts every container at once
and does not honour `depends_on`, so the API started before Postgres. It tried
once, and served an empty list for the life of the process. Every incident was
still in the database.

- `main.lifespan` now keeps retrying (`connect_when_ready`, every 5s) until
  the store answers, and then runs `settle()`. The mode is still restored at
  startup, because that does not need the database.
- Retries are quiet: the first failure and the success are audited, not each
  attempt.
- Incidents that ran while the store was down are written once it connects.
- Settling skips a parked plan or a run that belongs to this process. That
  was guaranteed only at startup, and a late connection breaks it.

The empty timeline is a separate cause: events lived only in the API's memory.
Owner decision the same day: persist them (see the events table).
