# ADR 0018 — The six observability views, and the two that are links

**Date:** 2026-10-19
**Status:** Accepted
**Changes:** `telemetry.py` gains a log ring buffer and `configure_logging`;
new `api/alerts.py`; three read-only routes (`/v1/logs`, `/v1/llm-calls`,
`/v1/alerts`); new console route `/observability`; `otlp_endpoint`'s sibling
`log_level` now does something.
**Related:** [ADR 0016](0016-the-control-plane-had-no-telemetry-of-its-own.md),
[ADR 0017](0017-the-console-was-the-one-thing-make-up-did-not-start.md)

## Context

ADR 0016 gave Kavach metrics and traces, in Grafana and Jaeger. The request
that followed was for the six things a commercial APM shows in one place —
traces, logs, exceptions, service health, alerts, AI-call visibility — in the
console rather than across three tools.

Auditing the six against what existed:

| | state before |
|---|---|
| Service health | **done** — `SystemHealth.tsx`, 8/8 dependencies |
| AI-call visibility | **data complete, no view** — `RcaResult` already recorded model, latency, tokens, diagnosis, validation |
| Traces | **existed in Jaeger**, unreachable from the console |
| Exceptions | **captured, unsurfaced** — `escalation_reason`, `rca.error` |
| Logs | **genuinely absent** — 4 log calls, `structlog.configure()` never called |
| Alerts | **absent** |

So four of six were a display problem over data already held.

## Decision

**Build four, link two, and say which is which.**

### Built

**AI calls.** The view with research value rather than decoration. Every
diagnosis with the deterministic validator's verdict beside it — because
`REPORT_DRAFT.md`'s central result is that the model was wrong three times and
the system acted on it zero times, and that relationship had no home in the
product. A confident diagnosis shown as *refused* is the architecture working.
`raw_response` stays out, per `schemas.py`: raw generations do not belong in a
screenshot.

**Alerts, as rules over Kavach's own state.** Every rule reads a limit
`permit()` itself enforces or an invariant the system claims — breaker open,
blast radius spent, dependency down, audit chain broken, escalation streak,
LLM unreliable. A rule firing on a number no gate consults would be telling an
operator about something nobody acts on. **Displayed, never delivered:** an
alert exists to interrupt someone not looking, and this project has no on-call
rotation. Every alert carries an `action`, because an alert without one is a
notification and notifications get ignored.

**Logs, as a bounded ring buffer.** Loki for four log statements would be a
storage cluster around an empty table. A deque the console reads gives the
same answer with no new container. Credential-shaped keys are redacted **on
the way in**, so a secret is not hidden from the endpoint — it never reaches
the buffer.

**Exceptions** are the same buffer filtered by level. One endpoint, two views,
because an exception here *is* an error log line. Deliberately distinct from
an escalated incident, which is Kavach declining to act and is not a fault.

### Linked, not rebuilt

**Traces** deep-link to Jaeger, per incident, via the `kavach.incident_id`
span attribute. **Metric history** links to Grafana. A worse copy of a trace
viewer inside the console would be a second thing to maintain and a second
thing to be wrong.

## Why a separate route

`/` answers *"what is happening to this incident, and do I approve it"*.
`/observability` answers *"how is the control plane itself behaving"*. Putting
fleet-wide noise beside the approval dialog would crowd the one screen where a
distracted operator is expensive.

## What this cost to find

**`log_level` was dead.** Declared in `config.py`, set by compose, read by
nothing, because `structlog.configure()` was never called. Identical to
`otlp_endpoint` before ADR 0016 — the second dead setting in two days, both
found only when something finally tried to read them.

**The control plane had no non-failure log line.** All four statements are
error paths, so a healthy system logged nothing and a working buffer was
indistinguishable from a broken one. One startup line now records version,
mode, level and whether tracing came up.

**The console image build needed the network to choose a pnpm version.**
`corepack enable` with no `packageManager` field resolves *latest* over the
network on every build. It timed out, failing a build for a reason unrelated
to the code. `package.json` now pins `pnpm@12.4.1`.

## Limits, stated

- **The AI-calls view is memory-scoped.** `runner.incidents()` reads the
  in-process ring, not Postgres, so a restart empties it. That is the open
  question in `RESEARCH_NOTES.md` §7.2 — wiring `GET /v1/incidents` to the
  store — and this view inherits it rather than working around it.
- **The log buffer is per-process and lost on restart.** The durable record of
  what Kavach *did* is the hash-chained audit trail, which is better than
  application logs for the purpose because its integrity is checkable.
- **No alert is delivered anywhere.** By decision, above.

## Lesson

ADR 0016 found a platform that measured everything except itself. This one
found the next layer:

> **Data captured and never displayed is indistinguishable from data never
> captured — and it is the version that looks fine in code review.**

Every field in the AI-calls view had been recorded, incident after incident,
since P4. The measurement was not missing. The way to look at it was.
