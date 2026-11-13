# ADR 0029 — One page per question: History, Logs, Metrics, Traces

**Date:** 2026-11-13
**Status:** Accepted by the owner 2026-11-13 and implemented the same day.
**Supersedes, in part:** [ADR 0018](0018-the-six-observability-views.md). Its
six views are kept. The single `/observability` route is split, and Metrics
and Traces are now drawn in the console instead of only linking out.
**Related:** [ADR 0028](0028-a-restart-leaves-no-decision-hanging-and-never-loosens-the-mode.md)
(events are now stored, which is what makes the Traces page possible).

## Context

- The incident history table sat under the incident stream on the operations
  screen, 3654px down a 210px scroll box, and listed the same 50 incidents
  the stream already listed. In practice it could not be reached.
- `/observability` held alerts, service health, AI calls, errors, logs and
  links to Jaeger and Grafana on one long page.
- The owner asked for separate History, Logs, Metrics and Traces pages, drawn
  in the console rather than embedded from Grafana and Jaeger, and for the
  timeline to survive a restart.

## Decision

| Page | What it answers | Reads |
|---|---|---|
| Operations (`/`) | What is happening now, and do I approve it | as before; the stream keeps the newest 8 and links to History |
| History (`/history`) | What happened | `GET /v1/incidents?limit=1000`; each ID opens that incident on `/` via `?incident=` |
| Logs (`/logs`) | What the control plane said | `GET /v1/logs` (errors and the log, moved from `/observability`) |
| Metrics (`/metrics`) | How Kavach is doing overall | `/v1/metrics`, per-class figures derived from `/v1/incidents`, `/v1/alerts`, `/v1/llm-calls`, service health |
| Traces (`/traces`) | Where one run spent its time | a run's stored events (`GET /v1/incidents/{id}/events`), per-stage start and length, and a link to that run in Jaeger |

- `/observability` redirects to `/metrics`.
- The read-only pages re-read on a slow timer (5s to 30s), the same kind of
  readout as the 5s health probe. The operations screen keeps its live feed.
- Per-class and per-stage figures are pure functions over fields the API
  already returns (`lib/stats.ts`, tested). Nothing on these pages is a new
  measurement.
- Stage lengths use the data-bound ASCII bar of DESIGN_SYSTEM.md §7.12 B,
  with the number beside it. The row is added to §7.12's table.

## Not done

- **Jaeger and Grafana stay the source for span trees and history over
  time.** The Traces page shows stages from the stored timeline, not spans.
  A native span viewer would need a Jaeger query proxy, and ADR 0018's
  argument against a second, worse trace viewer still holds for spans.
- **Runs before 2026-11-13 have no stored events**, so their Traces view is
  empty and says so.
- **No audit-log view.** DESIGN_SYSTEM.md §7.10 is still unbuilt.
- **MTTD per class is not shown.** The store keeps detection and resolution
  times, but not the injection time MTTD is measured from. Bench MTTD stays
  in `harness/reports/`.
