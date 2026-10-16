# ADR 0007 — The target's health probe reads the runtime endpoint (addition 11)

**Date:** 2026-10-16
**Status:** Accepted
**Required by:** `PRD.md` §5.2, which caps permitted target changes at a closed list and requires a decision record for each addition beyond it.

## Context

`PRD.md` §5.2 listed ten permitted additions to the target. This record adds an eleventh. It was found by Kavach performing a real repair, not by reading the code.

`backend/main.py::_check_ollama()` read the **environment variable**:

```python
base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
```

while `backend/embeddings.py::_api_base()` and the two call sites in
`backend/rag.py` — the paths that actually serve queries — all read the
**runtime setting**:

```python
runtime_config.get("llm_base_url").rstrip("/")
```

`llm_base_url` is in `control_interface.settable`, so anything may change it
through `PUT /v1/admin/config`. The health check was the only caller still
reading the env var, which is fixed at container start. The two values are
identical until something changes the setting, and then they diverge
permanently.

**How it surfaced.** Kavach injected `F01` (primary LLM endpoint outage, by
disabling the `ollama-primary` Toxiproxy listener), diagnosed it, and executed
`switch_llm_endpoint` to fail the application over to the clean `:21435`
backup. Post-repair verification then measured:

```
quality_ok  : true
pass_rate   : 1.0        all three fast-verification cases passed, 19.78s
health_ok   : false      GET /healthz -> HTTP 503
```

Every query was being served correctly through the backup endpoint while
`/healthz` reported 503 about an endpoint the application had stopped using.
Verification requires health **and** quality, so the loop correctly refused to
call it resolved and unwound the repair (1/1 restored, clean).

This matters to Kavach for one specific reason: **`F01` cannot reach
`RESOLVED`.** The autonomous path was otherwise proven — `permit()` returned
`ALLOW_AUTO` for the LOW-risk action under `AUTONOMOUS` and the repair executed
with no human — but the end-to-end heal verdict was unreachable through no
fault of the repair.

It is also a real defect in the target independent of Kavach. A readiness probe
that answers about the wrong endpoint is worse than no probe: it reports a
working service as down, and it would equally report a broken service as **up**
if the env var happened to point somewhere healthy.

## Decision

**Fix it, minimally.** `_check_ollama()` reads
`runtime_config.get("llm_base_url")`, like every other caller.

One line of behaviour change. `runtime_config` seeds `llm_base_url` from
`OLLAMA_BASE_URL` with the same `http://localhost:11434` default, so startup
behaviour is byte-identical and the two only diverge after a deliberate runtime
change — which is exactly when they must.

Explicitly **not** in scope:

- No change to what `/healthz` checks, or to its 503 semantics
- No new dependency, import or abstraction — `main.py` already imports `runtime_config` and already calls it for `chaos_enabled` and `config_hash`
- No change to the database half of the probe
- No touching `backend/aiops_agent.py`, which stays on disk and unimported (`docs/decisions/0003`)
- No change to the corpus, the embedding model, the prompts, or any other setting

### The alternative that was rejected

Declaring a per-fault verification profile in Kavach that treats health as
**advisory** for `F01`, leaving the target untouched.

Rejected because it weakens the one check that would catch a repair which
satisfies the quality probes while leaving the service down. Fast verification
asks three questions and gets three right answers; the health probe is what
notices that the service is nonetheless unwell. Making it optional per fault is
how a false-healthy verdict gets manufactured, which `fast_set.yaml` and
`AGENTS.md` both forbid. Fixing the probe to tell the truth is strictly better
than teaching Kavach to ignore it when it lies.

## Consequences

- **Positive:** `F01` becomes able to reach `RESOLVED`, so the LOW-risk autonomous path in `PRD.md` §8.2 is demonstrable end to end rather than only up to the write.
- **Positive:** a genuine bug fix the target benefits from regardless of Kavach, and it makes `/healthz` agree with what the application actually does.
- **Positive:** the probe did not get weaker. Verified in both directions below.
- **Negative:** the permitted-additions list grows from ten to eleven. The list is a boundary precisely because it is easy to erode; this record exists so the growth is visible rather than ambient. §5.2, `ROADMAP.md` and `ARCHITECTURE.md` have all been updated from "ten" to "eleven".
- **Negative:** this is the first addition made at the control plane's prompting rather than to make a fault injectable. Worth stating plainly: Kavach found a target defect while repairing the target, and the fix was authorised explicitly rather than taken.

## Verification

Measured 2026-10-16 on the live stack, isolating the probe from the loop. The
second row is the point — it reports **503 for a real outage on the endpoint in
use** — and the third is the fix:

| Step | `llm_base_url` | `/healthz` | |
|---|---|---|---|
| baseline | `toxiproxy:21434` | 200 | |
| `ollama-primary` disabled | `toxiproxy:21434` | **503** | still catches a genuine outage |
| failed over to the backup | `toxiproxy:21435` | **200** | follows the runtime endpoint |
| restored | `toxiproxy:21434` | 200 | |

Startup behaviour unchanged: `config_hash` was `de4cfaed14a8bb98` before and
after the rebuild.
