# ADR 0031 — The target's log in the console, without its users' words

**Date:** 2026-11-17
**Status:** Accepted by the owner 2026-11-17 (asked for directly) and implemented the same day.
Tests: `tests/test_target_logs.py` (3; removing the user-content filter fails 2),
`tests/pages.test.tsx` (1).
**Related:** [ADR 0029](0029-one-page-per-question-history-logs-metrics-traces.md)

## Context

The Logs page showed only Kavach's own log. To see the target app's log, an
operator had to open a terminal and run `docker logs rag_backend`. Kavach
already reads that log, but only during a run and only as RCA evidence:
10 signal lines at most.

The raw log holds users' words. `main: Received chat question: '…'` and
`Generated Queries for expansion: […]` carry each question verbatim, and
`AGENTS.md` rule 12 forbids exposing them.

## Decision

A new read-only route, `GET /v1/target-logs?limit=` (1–1000, default 300),
returns the target's recent lines newest first. It goes through the same
adapter (`executor/adapters/docker.container_logs`) and the same
`USER_CONTENT` filter as the RCA evidence, so there is one privacy rule, not
two. It also drops noise: metrics scrapes, health probes, Kavach's own config
polling, embedding progress bars and blank lines. Every other line is kept,
because an operator reading a log wants context, not just signals.

The Logs page shows the result as a third section, and lines that look like
errors are shown in red. If Docker cannot be reached, the list is empty and
the page says so; this is not an error.

## Limits

- The filter is a list of known patterns. A new log line that quotes a user
  would pass until the pattern list is extended. The test fixture uses the
  real line shapes from the live log on 2026-11-17.
- The target's container name is the evidence code's default (`rag_backend`),
  not read from the manifest, the same as the RCA evidence.
