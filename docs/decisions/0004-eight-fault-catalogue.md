# ADR 0004 — Eight fault classes, seven injectable

**Date:** 2026-10-02
**Status:** Accepted

## Context

The catalogue was nine classes, `F01`–`F09`, designed before the target application was audited. Two do not survive contact with it.

**`F04` cache poisoning / stale cache**, repaired by `flush_cache`. The target has no cache. No Redis, no response cache, no embedding cache. The one cache-shaped object in the codebase, `_cached_ranker` in `rag.py`, is a loaded CrossEncoder handle — it cannot be poisoned, and "flushing" it means reloading a model.

**`F03` container crash-loop / OOM**, repaired by `restart_container`. The target's compose sets `restart: always` on `backend`, so Docker restarts a killed container within seconds — faster than a 15s detection tick.

## Decision

**The catalogue is eight classes. Seven have a v1 injector.**

`F01, F02, F03, F05, F06, F07, F08, F09`

1. **`F04` is retired.** Redis is **not** added to the target to manufacture a fault for it. Building a feature in order to have something to break inverts the premise of the project.
2. **`F03` stays in the catalogue; its injector is deferred.** Its detection signal, repair and risk tier are all defined and its repair is shared with `F05`, so the class is meaningful. But the only honest injector is a memory limit low enough to OOM on every boot — a genuine crash-*loop* that `restart: always` cannot resolve — and finding that limit reliably is empirical work, not a design decision. Removing `restart: always` to make `F03` easy is **forbidden**: it would weaken the target's existing resilience in order to manufacture a failure Kavach can be seen fixing.
3. **IDs are stable identifiers, not indices.** `F04`'s number is never reused and the catalogue is never renumbered. IDs appear in logs, the UI, tests and the metrics table.
4. **No placeholder injectors.** A fault injector that does not really inject its fault silently corrupts every number derived from it, which is worse than an absent one.

Four actions are also removed: `flush_cache` (no cache), `rebuild_index` (no vector index and no snapshot mechanism — `F06` repairs by config rollback instead), `scale_replicas_up` (the target binds host port `8000:8000`, so a replica cannot start), `retry_request` (no hook in the request path). `switch_model` is renamed `switch_llm_endpoint`, because with one Ollama it switches an endpoint, not a provider.

## Consequences

- **Positive:** the catalogue is honest. Every remaining entry is injectable against the real target.
- **Positive:** all four novelty faults (`F06`–`F09`) survive, and `F06` is the first vertical slice.
- **Negative:** the benchmark denominator is **7 × 5 = 35 injections**, not 45. Every reported rate must state its denominator, and if `F03` lands later the earlier numbers are restated rather than silently replaced.
- **Negative:** the two cheapest faults to build (`F03`, `F05`) are the infrastructure-level ones prior art already covers, and one of them is now deferred. The novelty faults need the most target instrumentation. That ordering is inconvenient but it is the real shape of the problem.
- **Acceptable outcome:** if `F03` is never implemented, v1 ships with seven faults and says so. No part of the novelty claim depends on it.
