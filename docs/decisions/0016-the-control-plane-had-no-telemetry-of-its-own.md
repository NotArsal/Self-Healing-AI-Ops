# ADR 0016 — The control plane had no telemetry of its own

**Date:** 2026-10-19
**Status:** Accepted
**Changes:** new `kavach/telemetry.py`; `/metrics` on the API;
`kavach-api` scrape job enabled; collector traces exported to a new Jaeger;
new Grafana with a provisioned dashboard; `otlp_endpoint` now defaults to
empty.
**Supersedes the claim in:** `synopsis-original.md` *"Monitoring: Prometheus,
Grafana, OpenTelemetry"*
**Related:** [ADR 0013](0013-f07-llm-diagnosis-was-bought-by-a-promql-window.md),
[ADR 0014](0014-mttd-was-never-measured-so-the-figure-is-withdrawn.md),
[ADR 0015](0015-context7-is-not-a-runtime-component.md)

## Context

Kavach's thesis is that observability drives healing. Asked where its own
logs, traces and metrics were, the answer turned out to be:

| | claimed | actual, before today |
|---|---|---|
| **Metrics** | Prometheus | Real and load-bearing for the *target*. For Kavach itself: `GET /metrics` returned **404**, and the `kavach-api` scrape job had been commented out in `infra/prometheus.yml` since Phase 0 with the note *"Enabled in P1"*. |
| **Traces** | OpenTelemetry | A **healthy collector receiving nothing**. `opentelemetry-*` was explicitly listed in `pyproject.toml` as *"deliberately absent"*; there were zero instrumentation call sites; the collector's traces pipeline exported to `debug`, which prints each span to stdout and drops it. `Settings.otlp_endpoint` was declared, wired in compose, and **read by no code anywhere**. |
| **Grafana** | Grafana | **Not in the compose file at all.** |
| **Logs** | — | `structlog` is a dependency and is imported in four modules. There are **3 log calls in 11,500 lines** and `structlog.configure()` is never called. |

Nothing in the repository said any of this. Like [ADR 0015](0015-context7-is-not-a-runtime-component.md),
found by reading the synopsis against the implementation rather than by
anything failing.

The audit log is the one piece that was never missing: hash-chained,
append-only, 336 rows verified intact. It remains the durable record of what
Kavach did. What was absent is everything an *operator* would use to see the
control plane working, and everything a reader of the report would use to
check a figure against a running system.

## Decision

**Instrument the control plane, keeping every part of it outside the healing
path.**

### Metrics

Five series, in `telemetry.py`. The set is deliberately **the report's own
figures** rather than a generic RED dashboard, so the live dashboard and the
paper cannot disagree about what was measured:

| series | the figure it is |
|---|---|
| `kavach_incidents_total{fault_class,status,diagnosed_by}` | outcome distribution; the denominator behind "0/20 false heals" |
| `kavach_permit_verdicts_total{verdict,risk_tier}` | every side effect in Kavach passes the gate, so this counts all of them |
| `kavach_detection_seconds` | **MTTD**, from `detection.concluded_at` and nothing else (ADR 0014) |
| `kavach_incident_seconds{status}` | MTTR, split by status because the mean of a resolve and an escalation describes neither |
| `kavach_rca_latency_seconds` | one LLM diagnosis; an approved heal pays it twice, because `approve()` re-diagnoses |

### Traces

One span per run, `kavach.heal`, with each loop stage as an **event** on it —
not a child span per stage. A child span must be opened on `started` and
closed on `ok`/`failed`, which means pairing state carried across a worker
thread and a span that leaks whenever a stage ends in a way nobody
anticipated. Events carry the same timestamps, cannot leak, and Jaeger renders
them as marks on the run's timeline, which is the stage decomposition the demo
wants to show. FastAPI is auto-instrumented for HTTP spans, with `/metrics`
and `/healthz` excluded so a 15s scrape does not bury the heals.

Collector → Jaeger. Jaeger all-in-one keeps spans in memory: restarting it
loses the history, which is the right trade for something that must never be
load-bearing.

### Grafana

Provisioned from files in `infra/grafana/`, not configured through the
browser, so the datasource and the dashboard are in git. A dashboard built by
clicking exists only on the machine it was clicked on, which is not evidence
anybody can reproduce. `allowUiUpdates: false` for the same reason.

The three target panels reuse **the detectors' own PromQL verbatim**. ADR 0013
is why: an evidence frame is an interface, and a graph drawn from a different
window than the detector uses is a graph of a different fault.

## What keeps this out of the healing path

The property that makes the whole change safe to make four days before a
demo:

1. **Every public function in `telemetry.py` swallows.** A registry error, a
   malformed timestamp or an absent collector produces a missing graph, never
   a missed repair. `test_recording_never_raises_whatever_it_is_handed` pins
   it against an object whose every attribute raises.
2. **`loop.py` and `safety/engine.py` are untouched.** The call sites are one
   route in `main.py` and two lines in `api/runner.py`, riding the `publish`
   sink that already existed for the console. Adding a metric never means
   editing the loop.
3. **Grafana and Jaeger are observers, never participants.** Neither holds a
   credential for the target, neither can reach it, and the demo passes with
   both stopped.
4. **Tracing is opt-in.** See below.

## The bug this change found on its way in

`Settings.otlp_endpoint` defaulted to `http://localhost:4318`. Harmless while
nothing read it — but the moment `setup_tracing` did, **every pytest run that
built the app stood up a real OTLP exporter** and began retrying against a
collector that does not exist in CI. Two telemetry tests passed alone and
failed in the full suite, which is what surfaced it.

The default is now **empty, meaning tracing off**; compose opts in explicitly
for the container. A setting whose default turns on a network client is a
setting that was written before anyone intended to read it — the same shape as
the unset context window in `RESEARCH_NOTES.md` §4a.

## What is deliberately still not done

- **No log aggregation.** Three log calls and no `structlog.configure()` is
  the honest state, and a Loki stack would be infrastructure around almost no
  content. The audit log is where Kavach's record of its own actions lives,
  and it is better than application logs for the purpose: tamper-evident.
- **No alerting rules.** Alerts without an on-call rotation are decoration.
- **Kavach does not ingest its own OTLP.** `ingestion/otlp.py` is still
  unbuilt; the collector comment now says so rather than promising "P2".
- **No child spans per stage.** Upgrade path noted in `telemetry.py` if stage
  durations are ever needed programmatically rather than read off a timeline.

## Lesson

ADR 0013: a measurement is a finding about the instrument. ADR 0014: a
metric's name is a claim. This one:

> **A platform that measures something else is the last place anyone thinks to
> look for missing measurement.**

Kavach scraped the target every 15 seconds for three weeks while answering
404 on its own `/metrics`, and nothing in the repository found that strange,
because every document described the monitoring stack in terms of what it
watched rather than what watched it.
