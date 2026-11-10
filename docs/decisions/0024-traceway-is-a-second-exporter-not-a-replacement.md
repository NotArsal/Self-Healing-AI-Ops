# ADR 0024 — Traceway is added as a second OTLP exporter, not as a replacement for Prometheus

**Date:** 2026-11-10
**Status:** Accepted — owner's decision, 2026-11-10. Implementation gated on the host choice below.
**Corrects:** `ARCHITECTURE.md` §2.2 and §9, which reject Traceway as "a hosted telemetry SaaS"
**Related:** `ADR 0016` (Grafana and OpenTelemetry were absent and were added), `ADR 0010` (the window semantics this ADR refuses to disturb)

## Context

`ARCHITECTURE.md` rejects Traceway under the heading **"A hosted telemetry
SaaS"**, with the reason *"Kavach's telemetry path is entirely local, because
the demo must work offline."* That reason is recorded against something
Traceway is not. Traceway is an **MIT-licensed, OpenTelemetry-native,
self-hostable** platform covering logs, traces, metrics, session replay,
exceptions and AI tracing, ingesting OTLP/HTTP directly. Traceway Cloud is one
deployment mode, not the product.

The target already carries it: `frontend/package.json` declares
`@tracewayapp/react` and `@tracewayapp/bundler-plugin`, `frontend/next.config.js`
registers `TracewayDebugIdsWebpackPlugin` for production client builds, and the
target's `README.md` suggests `OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.tracewayapp.com/api/otel`.
That env var is set nowhere in the target's compose or `.env`, so the cloud
export has never fired. **Disabled by omission, which is why it needed no code.**

Two corrections to the reasoning that was used against it, both mine:

- I argued the current stack is "four heavy containers" that Traceway would
  consolidate. Measured: Prometheus 44 MB, Grafana 55 MB, Jaeger 63 MB, the
  collector 190 MB — **about 350 MB combined**. They are not heavy, and
  ClickHouse alone will likely exceed all four.
- I described self-hosting as one container. It is **four**: ClickHouse,
  PostgreSQL, the API and the frontend.

## Decision

**Add Traceway as an additional OTLP/HTTP exporter alongside Jaeger and
Prometheus. Replace nothing.**

The one-block change to `infra/otel-collector-config.yaml`, kept here rather
than applied, because the live collector must not be restarted mid-experiment
and the host is not yet chosen:

```yaml
exporters:
  # ... prometheus, debug, otlp/jaeger stay exactly as they are ...
  otlphttp/traceway:
    # The otlphttp exporter appends /v1/traces, /v1/metrics and /v1/logs
    # itself, so this endpoint must stop at /api/otel - which is exactly
    # Traceway's documented ingest prefix.
    endpoint: ${env:KAVACH_TRACEWAY_ENDPOINT}
    tls:
      insecure: true

service:
  pipelines:
    traces:
      exporters: [otlp/jaeger, otlphttp/traceway, debug]
```

`KAVACH_TRACEWAY_ENDPOINT` is an env var rather than a literal so the same
config serves either host in the next section without an edit.

**Standing it up is their own compose, not ours.** Traceway ships its own
`docker-compose.yml` (ClickHouse, PostgreSQL, API, frontend) — clone
`github.com/tracewayapp/traceway` and `docker compose up -d`. This ADR does
not reproduce their image tags, because inventing a tag for a component we
have not run is how a config lands in git that nobody has ever started.
Dashboard on port 80, which is free on the current host.

## Why Prometheus is not replaced

Prometheus is **not a dashboard in this system; it is in the detection path.**
`detection/retrieval_collapse.py` and the rest evaluate PromQL — the 60-second
`empty_context_ratio` window, the rolling z-scores. Traceway storing metrics
does not hand a detector a PromQL engine. Replacing it means rewriting every
detector and re-validating every threshold, and `ADR 0010` is the record of
how delicate those window semantics are: the manifest's own header documents
three traps hit while writing those expressions, and this project has been
bitten three separate times by a windowed metric read over a window shorter
than its own contents.

There is also an experiment-integrity reason. The closure ablation's
distractor pool is **scraped live from the target's `/metrics`** — it moved
49 → 52 between the 2026-11-09 and 2026-11-10 runs, and
`EXPERIMENT_CLOSURE_ABLATION.md` §19.2 could not attribute a result because of
it. Changing the metric backend changes the experiment's inputs.

## What this buys

- **AI tracing** out of the box, where Kavach hand-rolls LLM spans into
  Postgres. This is the gap `TOOLING_SURVEY.md` was circling with Langfuse,
  Opik and Phoenix.
- **MIT licence**, which removes the Elastic-License-2.0 objection
  `TOOLING_SURVEY.md` raised against Phoenix.
- **Frontend exceptions and session replay**, where Kavach has nothing and
  the target's frontend is entirely unobserved. Worth stating plainly: **no
  fault in the catalogue is a frontend fault**, so this adds observability
  rather than detection capability.

## Host choice, still open

The owner has a second machine — Victus 15L, i5-13400F, RTX 3050 OEM 8 GB,
**16 GB RAM**. Hosting Traceway there and pointing
`KAVACH_TRACEWAY_ENDPOINT` at it over the LAN keeps ClickHouse off the
measurement machine entirely, which is the better arrangement. On 16 GB that
desktop should do **one** job at a time: Traceway, or a second target with its
own Ollama, not both.

Local measurement stays on the laptop regardless — it is the faster machine on
every axis (16c/24t vs 10c/16t, RTX 4060 vs 3050, 31.7 GB vs 16 GB) and §6's
new environment table ties every latency figure to it.

## Constraints that do not move

- Nothing is enabled while a run is in flight; a collector restart drops spans.
- The target's Traceway **cloud** export stays unset. `PL-02` and the
  offline-reviewable property are unchanged by a self-hosted exporter.
- Traces remain diagnostic, not detection-critical (`ARCHITECTURE.md` §9):
  losing spans degrades an RCA explanation and cannot cause a missed incident.
