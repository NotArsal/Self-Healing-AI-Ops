# ADR 0005 — Postgres connection-leak fix in the target (addition 10)

**Date:** 2026-10-02
**Status:** Accepted
**Required by:** `PRD.md` §5.2, which caps permitted target changes at a closed list and requires a decision record for each addition beyond it.

## Context

`PRD.md` §5.2 listed nine permitted additions to the target. This record adds a tenth.

The target's `rag.py` acquires a pooled Postgres connection and releases it **inline** rather than in a `finally` block:

- `store_chunks` (rag.py:14–38)
- `retrieve_relevant_chunks` (rag.py:103–152)

Any exception raised between `get_connection()` and `release_connection(conn)` leaks the connection permanently. With `SimpleConnectionPool(1, 10)` in `db.py`, ten failed requests exhaust the pool and every subsequent request raises `PoolError`.

This is a pre-existing bug, not something Kavach introduced. It matters to Kavach for two specific reasons:

1. **It makes `F05` unmeasurable.** `F05` *is* pool exhaustion. A pool-exhaustion fault cannot be measured on a system that exhausts its own pool as a side effect of unrelated failures — the injected fault and the ambient fault are indistinguishable.
2. **It makes every repeated injection untrustworthy.** Each failed injection of *any* fault leaks a connection. Run 9 of a 20-cycle stability test is therefore not operating on the same system as run 1, which directly invalidates the `ROADMAP.md` acceptance criterion *"20 consecutive inject/revert cycles leave the stack identical to the start state."* That criterion is load-bearing for every number in the report.

## Decision

**Fix it, minimally.** Wrap each acquire/release pair in `try/finally` so the connection returns to the pool on every path.

Explicitly **not** in scope:

- No redesign of the database layer
- No change to the pooling strategy or pool size
- No schema change
- No context-manager abstraction introduced across the codebase
- No fixing of other latent issues noticed nearby (`except Exception: pass` in `db.py`'s database-creation path is reported, not fixed)

## Consequences

- **Positive:** `F05` becomes measurable, and 20-cycle stability becomes a meaningful criterion.
- **Positive:** it is a genuine bug fix the target benefits from regardless of Kavach.
- **Negative:** the permitted-additions list grows from nine to ten, and every document that cites the count has been updated. The list is a boundary precisely because it is easy to erode; this record exists so the growth is visible rather than ambient.
- **Verification** (`ROADMAP.md` P1): force 15 consecutive `/v1/chat` failures, then confirm the pool still serves requests and `ragapp_db_pool_in_use` returns to its idle value.

## Scope note

This is a **reliability** fix, not a feature or an instrumentation hook. If further target bugs are found, each needs its own record — this one does not establish a general licence to fix things in the target.
