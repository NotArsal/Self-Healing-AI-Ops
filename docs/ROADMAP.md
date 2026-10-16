# ROADMAP.md — Kavach

> Build order, acceptance criteria, and owner tracks.
> Read with `PRD.md` (what) and `ARCHITECTURE.md` (how). This file is **when** and **in what order**.
>
> **Every phase below expands Kavach's healing capability.** Kavach is a
> general control plane for containerised AI workloads; `Simple_RAG-Pipeline`
> is the first reference workload it is validated against (`PRD.md` §1,
> `ARCHITECTURE.md` §1.2). "Add `F07`" means teaching the platform a fault
> class, implemented through a workload adapter — not building more of a RAG
> system.

---

## Assumptions — correct these before using the schedule

- **Phases P0–P4 are complete.** ~14 working weeks. Adjust every week number if your deadline differs; the *order* holds regardless.
- **Four people**, part-time alongside other coursework.
- The demo is the deliverable (`PRD.md` §5), so every phase ends in something demonstrable.
- **The target application already exists.** `Simple_RAG-Pipeline` is not built here — it is onboarded and instrumented (`PRD.md` §5.1). The old "build `demo-rag`" phase is deleted, not re-pointed.

---

## The two rules

**1. Vertical, not horizontal.** Never build a layer across all fault classes. Build one fault class through every layer, then the next. A horizontal build means nothing works until the final week.

*Honest note on P2/P3:* the `F06` slice runs detect → diagnose → repair → verify, but **not** through the safety engine, the audit log or a persisted graph, because none of those exist yet. It is a working loop, not a complete vertical. P5 closes that gap, and it has to close it before a second repair action lands.

**2. Build what breaks before what fixes.** The fault injector shipped with the first fault, in P2, not in a late phase. You cannot test detection without deterministic failure, measure MTTD without a known injection timestamp, or write a single integration test without an injector.

---

## Phase map

**Numbering, canonical as of 2026-10-04.** An earlier draft of this file split
the `F06` work into "P2 injector" and "P3 dumb loop", and called the LLM RCA
engine "P4". It was built as one phase, so those two are now one: **P2 is the
`F06` deterministic closed loop, P3 is the `F06` LLM RCA layer**, and
everything after shifts down by one. Phases P0–P3 are complete.

Commit messages and decision records written before this date use the old
numbers (they call LLM RCA "P4"). **History is not rewritten** — the mapping is
old P2+P3 → new P2, old P4 → new P3, old P5–P9 → new P4–P8.

```
P0 scaffold  ✅
 └─ P1 onboard + instrument Simple_RAG-Pipeline  ✅
     └─ P2 F06 DETERMINISTIC CLOSED LOOP  ✅ ━━▶ first demoable milestone, reached
         └─ P3 F06 LLM RCA  ✅ ━━▶ the research comparison, recorded
             └─ P4 console  ✅ ━━▶ the loop is now watchable live
                 └─ P5 SAFETY ENGINE ◀━ gate before any second repair action
                     └─ P6 remaining 7 faults ─┬─ P7 git · memory · Laya
                                                          │
                                                          └─ P8 measure, report, demo
```

| Phase | Goal | Weeks | Gate |
|---|---|---|---|
| P0 | Kavach scaffold | 1 | ✅ `make check` green; docker socket proven on the demo machine |
| P1 | Onboard + instrument the target | 2–3 | ✅ Preflight passes against `Simple_RAG-Pipeline` |
| P2 | **`F06` deterministic closed loop** | 3–6 | ✅ **`F06` auto-heals end to end with a working rollback; 20/20 inject→heal→verify cycles** |
| P3 | **`F06` LLM RCA** | 6–8 | ✅ **Schema-validated diagnosis behind a deterministic gate; measured against the P2 baseline** |
| P4 | Console | 6–9 | ✅ **Loop watchable live over WebSocket, no refresh; generated API client in the gate** |
| P5 | **Full safety engine** | 8–10 | ✅ **`permit()` live with a deny case per rule; three modes enforced; approval flow; incidents persisted; action registry** |
| P6 | The remaining seven faults | 10–12 | Each a complete vertical slice, each added as an adapter |
| P7 | Git isolation, knowledge base, Laya shadow | 11–13 | `make bench` emits the metrics table |
| P8 | Measure, report, rehearse | 12–14 | Demo runs clean 3× in a row |

**Resequenced 2026-10-04: the safety engine moved ahead of the remaining
faults.** The previous order was P5 faults, then P6 safety — while P6's own
text said `permit()` "must land before any second repair action or any
unattended invocation". The roadmap contradicted itself, and the earlier order
would have shipped seven new repair actions through a gate that did not exist.

Two reasons the swap is the right correction rather than a cosmetic one:

1. **Safety.** Today exactly one action can run, it is project-scoped and
   deny-list-safe by construction, and the loop only runs when an operator
   asks. Every one of those properties stops being true with a second action.
2. **It is also the generalisation work.** The safety engine is where the
   `Action` protocol, the registry and `permit()` get built — the seams a
   second fault class should be added *through*. Doing faults first would mean
   copying the `F06` pattern seven times and then retrofitting a registry under
   it (`ARCHITECTURE.md` §1.4).

**P2 and P3 did not deliver everything their earlier drafts listed.** The parts
that were deliberately not built — LangGraph, the `permit()` safety engine, the
hash-chained audit log, incident persistence, Redis, the git adapter, the three
operating modes — are listed as deferred in each phase below and are now
scheduled in P4–P6. Nothing was quietly dropped; the F06 slice is a *working*
loop, not a *complete* platform.

---

## P0 — Kavach scaffold ✅ COMPLETE

**Week 1 · Owner: control-plane track**

> **Accepted 2026-10-01.**

**Deliverables**
- `git init` the Kavach repository. It is not one today, and `docs/decisions/` is meaningless without it
- Repo at the structure in `ARCHITECTURE.md` §3 (directories with `.gitkeep`, **no stub code**)
- `Makefile` with every target in `AGENTS.md`, failing loudly where unimplemented
- `infra/docker-compose.yml`: postgres+pgvector, prometheus, otel-collector, api. **No Ollama, no second Prometheus** (`ARCHITECTURE.md` §2.4), and **no Redis** — nothing in Phase 0 uses it, so it arrives with the phase whose checks need it — console pub/sub in P4, persisted idempotency keys in P5
- FastAPI app with `/healthz` only; Next.js app with one page
- `pyproject.toml` (uv, ruff, mypy strict, pytest), `package.json` (pnpm, eslint, prettier, vitest)
- Pre-commit hooks, `.env.example` with placeholders only
- `targets/simple-rag.yaml` — the pointer file (path, base branch, compose project, service map)
- Decision records: `0001-locked-scope.md`, `0002-target-is-external-repo.md`, `0003-sole-healing-controller.md`, `0004-eight-fault-catalogue.md`
- `docs/synopsis-original.md` — the archived synopsis with a header marking it superseded

**Acceptance**
- [x] `make setup` works on a clean machine
- [x] `make up` brings every control-plane container healthy
- [x] `make check` passes (lint + mypy strict + tsc + tests)
- [x] `curl localhost:8080/healthz` returns 200
- [x] **The docker socket mount works on the Windows demo machine, and a container can be listed, inspected and restarted from inside the control-plane container.** This is `PL-03` and it is the one thing that stops the entire project if it fails. Do not defer it to a later phase
- [x] Kavach can reach the target's `ollama` by service name across the joined network

**Kickoff prompt**
> Read PRD.md, ARCHITECTURE.md and AGENTS.md. Build Phase 0 only: repo scaffold, compose files, tooling, Makefile, a FastAPI healthz route and an empty Next.js app. No business logic, no stub classes for future phases. Prove the docker socket works on this machine. Plan first, then stop for approval.

---

## P1 — Onboard and instrument `Simple_RAG-Pipeline` ✅ COMPLETE

**Weeks 2–3 · Owner: target track**

> **Accepted 2026-10-03.** Preflight passes against the live target; the baseline captures and re-captures with no drift. Target commits are on `kavach/ops` only — `main` and `modernize-stack` untouched, nothing pushed.

This replaces the deleted "build `demo-rag`" phase. The application exists; what does not exist is any way to observe or control it. **The complete, closed list of permitted additions is `PRD.md` §5.2 — ten items. Do not add an eleventh without a decision record.**

All work lands on `kavach/ops`, branched from `modernize-stack`. **Never `main`. Never pushed.**

**Deliverables**

*Observation (`PRD.md` §5.2 items 1, 2, 4)*
- OpenTelemetry SDK + `opentelemetry-instrumentation-fastapi` / `-psycopg2` / `-requests` in the target's backend, exporting OTLP to the collector. **The target has none today** — the README's "FastAPI natively supports OpenTelemetry" claim is false
- Manual spans around the two Ollama calls and the pgvector query, emitting Kavach's internal attribute schema (`ARCHITECTURE.md` §2.3)
- The metrics in `ARCHITECTURE.md` §4.1: `ragapp_llm_requests_total`, `ragapp_llm_duration_seconds`, `ragapp_llm_tokens_total`, `ragapp_retrieval_top_similarity`, `ragapp_retrieval_empty_context_total`, `ragapp_db_pool_in_use`
- Read Ollama's `usage` block into the span (two lines in `rag.py`). **Never log prompt bodies or secrets** (`FR-28`)
- `GET /healthz` checking Postgres **and** Ollama, not just liveness

*Control (items 3, 5, 6, 7)*
- The config interface, `ARCHITECTURE.md` §7.2. `embed_model` is **not** settable
- Lower the 1200-second LLM timeout to ~30s (two lines in `rag.py`)
- Move both prompts to `prompts/answer.txt` and `prompts/query_expansion.txt`, loaded at request time so a rollback needs no rebuild. **Mechanical extraction — do not redesign the RAG pipeline**
- `CHAOS_ENABLED` around the existing jitter middleware, **default `false`**

*Reliability (item 10, `docs/decisions/0005`)*
- **Release Postgres connections in `finally` blocks** in `store_chunks` and `retrieve_relevant_chunks`. Minimal: wrap acquire/release in `try/finally`. **No database-layer redesign, no schema change, no pooling-strategy change.** Without this, every failed injection leaks a pooled connection and the "20 cycles leave the stack identical" criterion is untestable (`PRD.md` §5.2)

*Infrastructure (items 8, 9)*
- Toxiproxy in the target compose with **two listeners** to the one Ollama (`PRD.md` §6.3)
- Healthchecks on `backend`, `frontend`, `ollama`
- The target's bundled `prometheus` service moved behind `profiles: [standalone]` (`ARCHITECTURE.md` §2.4)
- `kavach.yaml` — the full manifest from `ARCHITECTURE.md` §7

*Neutralisation (`PRD.md` §5.3)*
- `POST /v1/webhook/alert` **removed from the running application.** `backend/aiops_agent.py` stays on disk, unimported and unreachable
- Verified: no code path can reach `delete_namespaced_pod`
- The target's `ADR-001` / `ADR-002` are **not modified**

*Control plane*
- `onboarding/` — manifest parsing, the preflight check registry, baseline capture
- `verification/fast_set.yaml` — **exactly 3** deterministic cases, run serially inside 120s, scored locally with **no cloud API key** (`PL-02`). Cases are chosen by measurement against the live clean baseline (`FR-07c`) and must be retrieval-dependent (`FR-07d`)

> **Resolved 2026-10-03** — `apps/control-plane/kavach/verification/fast_set.yaml`.
>
> The target's 40-case `evaluation_dataset.csv` could **not** be used: it asks generic ML-textbook questions while the loaded corpus is two unpublished VIT student papers on unrelated subjects. Screened all 40 against the live clean system — 35 refused outright, best stability was **2 of 3 runs**, and the cases that did pass were **not grounded**, so they would report healthy with retrieval destroyed (`FR-07d`).
>
> The 3 cases were instead built from the corpus that is actually loaded, targeting specific numeric facts. Result: **15/15** executions across 5 serial set-runs, set total **18.1s** mean against a 120s budget. Retrieval-dependence was confirmed by a control run putting the same questions to `llama3.2` with no context — every keyword absent. The 40-case dataset stays as the offline research evaluator (`FR-07a`), untouched.

**Acceptance**
- [x] `make target-up` → the app answers a question correctly from the corpus
- [x] Spans reach the collector carrying model, **token counts** and duration
- [x] Every one of the six new metrics is scrapeable and non-zero under load
- [x] `GET /healthz` returns 503 when Postgres is stopped, and 503 when Ollama is unreachable
- [x] `PUT /v1/admin/config` changes `rerank_threshold` and the next query reflects it, with **no container restart**
- [x] `PUT /v1/admin/config` with `embed_model` is rejected, and the `document_chunks` table is intact
- [x] Rewriting `prompts/answer.txt` changes the next answer with no rebuild
- [x] `CHAOS_ENABLED=false` → p95 latency variance measurably drops
- [x] `POST /v1/webhook/alert` returns 404
- [x] Both Toxiproxy listeners proxy to Ollama; a toxic on A leaves B working
- [x] `make onboard` → preflight passes; baseline captured (metrics, fast-eval scores, config hash, prompt SHA, `rerank_threshold`)
- [x] Every SLO expression in `kavach.yaml` parses and evaluates against the live Prometheus
- [x] Fast verification completes in **under 120s** with zero network egress, and its quality probe is keyword-presence + non-refusal only — **no model-scored metric** (`FR-07b`)
- [x] **Connection-leak fix proven:** force 15 consecutive `/v1/chat` failures, then confirm the pool still serves requests and `ragapp_db_pool_in_use` returns to its idle value
- [x] `git log kavach/ops` shows the work; `main` and `modernize-stack` are untouched; nothing was pushed

**Cut line:** the fast-verification set is 3–5 cases. That is the ceiling, not a target. The 40-case RAGAS evaluator is P7 research work and is **never** in the live loop.

---

## P2 — `F06`: the deterministic closed loop ⭐ ✅ COMPLETE

**Weeks 3–6 · Owner: target track + control-plane track**

> **Completed 2026-10-03.** Previously two phases ("P2 injector", "P3 dumb
> loop"); built as one and recorded as one. Commits for this phase are
> `231f22f`, `11f24b0`, `97034f8`.

**`F06` retrieval collapse is the first fault**, reversing the earliest draft's
`F01`-first order. Three reasons:

1. It works against the target **as it already is** — `rerank_threshold` is live config. No new provider, no second model, no new infrastructure.
2. It produces the **silent HTTP 200 with "I don't know based on the provided documents"** failure. Detection cannot come from HTTP error rate; it must come from retrieval similarity and fast-verification pass rate. That forces the quality-driven detection path to be real now instead of deferred, and that path is the project's actual contribution (`PRD.md` §2.1).
3. It is a **novelty fault** (`PRD.md` §2.2). The cheapest faults to build, `F03` and `F05`, are the infrastructure-level ones that prior art already covers.

`F01` is *not* first because its repair needs the two-listener Toxiproxy design
and a configurable endpoint, both of which settled in P1. `F03` is not first —
or scheduled at all — because the target sets `restart: always` on `backend`,
so **Docker heals it before Kavach can**, and the only way to change that would
be to weaken the target's own resilience. Its injector is deferred
(`PRD.md` §6.4).

### The loop, exactly as built

```
detect ─▶ known-fault lookup ─▶ prepare (capture pre-state + inverse)
       ─▶ execute ─▶ verify ─▶ RESOLVED, or ESCALATED
```

No LLM, no LangGraph, no decision model, no allow-list engine, no sandbox. The
plan step is a literal dict, `{F06: rollback_config}`. That is deliberate: it
closes the loop cheaply, and it is the **non-LLM baseline** P3 has to beat.

**Delivered**

- `harness/faults/base.py` — the `inject()` / `revert()` / `is_active()` protocol, and a context manager that reverts in `__exit__` so a test raising mid-fault still restores the target
- `harness/faults/f06_retrieval_collapse.py` — raises `rerank_threshold` to `0.999` through the target's config interface and records the prior value as the inverse
- `harness/stability_f06.py` — the 20-cycle stability harness, per-line flushed so a long run is observable while it runs
- `kavach/target.py` — the **only** module that speaks HTTP to the target. No generic `request()`, no caller-supplied path, no command string (`FR-27`)
- `kavach/verification/fast.py` + `kavach/verification/fast_set.yaml` — health probe plus the 3 deterministic quality cases, serial, scored on keyword presence + non-refusal + a `**Sources:**` block. **Shared by baseline capture and the loop**, so a baseline and a verification can never drift apart
- `kavach/detection/retrieval_collapse.py` — deterministic detection. Fires only when raw similarity is **healthy** AND grounding is lost AND the fast set is failing **now**. The similarity condition is what separates a bad rerank filter from broken embeddings or a damaged corpus; the "failing now" condition exists because a stale grounding window once outvoted a just-passed fast set and the loop "healed" a working system
- `kavach/executor/config_rollback.py` — `prepare()` / `execute()` / `invert()` / `verify_applied()` / `verify_restored()` / `unchanged_elsewhere()`, with an idempotency key. Refuses to run with no captured baseline: a rollback to a guessed value is not a rollback
- `kavach/loop.py` — the orchestrator. `RESOLVED` requires fast verification passing **and** the repair proved applied **and** scope respected **and** the corpus fingerprint unchanged. Anything else escalates

**The one rule this phase exists to enforce:** an incident is `RESOLVED` only if
verification passed *and* the corpus fingerprint is unchanged. A loop that
reports success on a failed verification is a false-healing machine, which is
the single worst outcome in the whole design.

**Acceptance — met**

- [x] `F06` injection → raw retrieval similarity holds, kept chunks go to zero, empty-context rate rises
- [x] The app returns HTTP **200** with a non-answer — the failure is silent, which is the point
- [x] `revert()` restores retrieval
- [x] **20 consecutive inject → verify-failure → rollback → verify-recovery cycles, 20/20**, leaving the stack identical to the start state
- [x] A test that raises mid-fault still reverts
- [x] `ragapp_retrieval_top_similarity` and the fast-set pass rate both visibly move
- [x] Injection timestamp recorded, so MTTD is measurable
- [x] Detected and healed end to end with no human involved
- [x] `rollback_config` executes, fast verification passes, the incident resolves
- [x] Forced-failure behaviour: with verification failing the incident escalates rather than reporting success
- [x] The corpus is unchanged across the whole incident, fingerprinted before detection and after verification
- [x] An action with no recorded inverse cannot run — `prepare()` refuses without a baseline
- [x] `main` untouched, nothing pushed

**SLO rebase.** The manifest's SLO expressions were re-derived against the live
system in this phase. The error-ratio SLOs were unevaluable as written:
`sum(rate(counter))` returns an **empty series** when the counter has never
incremented, so they could not be evaluated precisely when the system was
healthy — fixed with `or vector(0)`. A separate trap: the target's default
histogram buckets topped out at 1s against 6.5s requests, so
`histogram_quantile` returned `1` regardless of reality. Buckets are now
0.25s–120s.

**Deliberately not built here — now scheduled in P4–P7**

| Not built | Why | Now in |
|---|---|---|
| `graph/` — LangGraph with `PostgresSaver` | A hand-rolled `run_once()` proved the mechanism; a graph with no persistence and no approval interrupt buys nothing yet | P5 |
| `safety/` — the `permit()` gate, risk tiers, blast radius, breaker, writer lock as its own module | The one implemented action is project-scoped and deny-list-safe by construction. A gate with one caller and one action is an interface with one implementation | **P5** |
| The three operating modes, `SIMULATION` as default | There is no mode plumbing to default: the loop is invoked explicitly by a harness, never on a timer, so it cannot act unattended | P5 |
| `audit/` — the append-only hash-chained log | Nothing persists yet | P5 |
| Incident persistence, MTTD/MTTR in the database | `Incident` is an in-memory dataclass; runs are recorded as JSON artifacts under `harness/reports/` | P4 |
| `ingestion/` — an OTLP receiver inside Kavach | Metrics go **direct** to `/metrics` and are scraped by Prometheus (`ARCHITECTURE.md` §4.1); only traces use OTLP, and nothing in the loop reads a trace yet | P4 |
| `detection/slo.py` on a 15s tick | PromQL instant queries exist and are used; there is no scheduler, because the harness drives every run | P4 |
| Redis | Still nothing connects to it. It arrives with console pub/sub (P4) and persisted idempotency keys (P5) | P4 / P5 |
| The git adapter | `rollback_config` writes through the target's HTTP config interface, not a file, so `FR-05` has not been triggered yet | P7 |
| `harness/inject.py` CLI and `make inject FAULT=F06` | The injector is used as a Python context manager by the harnesses; a CLI wrapper had no second caller | P6, with the second fault |
| The 120s SLO-window verification probe | Fast verification is the health probe plus the 3 quality cases. The SLO-window probe is the second of the three `FR-07` probes and is **still missing** | P5 |

**This is the project's de-risking milestone and it is banked.** One fault, zero
intelligence — but it detects a silent failure, repairs it, proves the repair,
and refuses to claim success otherwise.

**P2 is also the non-LLM baseline.** Its numbers are in the P3 comparison below
and cannot be recovered later.
---

## P3 — `F06` LLM RCA ✅ COMPLETE

**Weeks 6–8 · Owner: control-plane track**

> **Completed 2026-10-04.** Commit `3e12689`. This phase was called "P4" in the
> earlier draft of this file and in that commit message; see the numbering note
> under **Phase map**.

An evidence-grounded LLM diagnosis stage in front of the **existing** P2 repair.
The P2 loop is untouched and remains both the reference baseline and the
fallback.

```
evidence normalisation ─▶ LLM (schema-constrained) ─▶ Pydantic validation
  ─▶ deterministic validation gate ─▶ existing rollback_config
  ─▶ existing fast verification
```

**The LLM executes nothing.** It may name a fault class, a service, a
confidence, cited evidence IDs and one candidate repair from a closed
vocabulary. It cannot reach the executor. RCA never widens what can run:
deterministic detection must still find the fault, the repair is still the same
single action with the same recorded inverse, and verification is unchanged.
RCA adds a gate and an explanation.

**A rejected diagnosis escalates.** It does not silently fall back to the
deterministic plan — that would make the gate decorative.

**Delivered**

- `kavach/llm/client.py` — the Ollama client. Structured output via Ollama's `format` field, taking a JSON Schema **generated from the Pydantic model** so the decoder constraint and the validation constraint cannot drift apart. Temperature 0, fixed seed: a diagnosis that changes between identical inputs is not a diagnosis. It asserts it is **not** pointed at Toxiproxy (`PRD.md` §6.3) — Kavach's own model path must survive a fault injected into the target's
- `kavach/llm/prompts/diagnose.txt` — the versioned prompt: the catalogue, the similarity discriminator, the rules, and a required-output-shape example
- `kavach/rca/schema.py` — the diagnosis contract. `extra="forbid"`, the **eight** catalogue classes plus `UNKNOWN` and `INSUFFICIENT_EVIDENCE` (no `F04`), and `evidence_ids` **required with a minimum of two**
- `kavach/rca/evidence.py` — evidence normalisation into ~33 citable items
- `kavach/rca/validate.py` — the deterministic gate, ten fail-closed rules
- `kavach/rca/engine.py` — orchestration. Returns a result carrying `approved` / `approved_action` / `rejection_reasons`, and **never raises**: a transport failure or a timeout is a rejection, not a crash in the healing path
- `kavach/loop.py` — an **optional** `rca` stage. Absent, the loop is exactly the P2 loop
- `harness/rca_f06_live.py` — the live run and the P2-vs-P3 comparison

**Evidence supplied to the model.** Each item carries a stable ID, an observed
value and the healthy expectation — never a verdict, so the model is not asked
to agree with a conclusion Kavach already reached.

| IDs | What |
|---|---|
| `EV-M01`–`EV-M09` | Retrieval similarity, kept chunks, empty-context ratio, corpus size, LLM error ratio and latency, pool, chat errors |
| `EV-S01` / `EV-S02` | **Service identity** and the declared service set |
| `EV-C01`–`EV-C08` | Live config, config hash, prompt file hashes |
| `EV-B01` | The captured known-good `rerank_threshold` |
| `EV-V00`–`EV-V03` | Fast-set overall plus per-case results |
| `EV-H01` | Health |
| `EV-L01`… | Recent backend log lines |

**Two deliberate exclusions:** user content is filtered out of the log lines
(`FR-28` — token counts are telemetry, question text is not), and so is Kavach's
own interpretation.

**The ten validation rules, all fail-closed.** Schema valid → honest
non-answers respected and never executed → fault class implemented →
confidence at or above the manifest's threshold → every cited ID resolves to a
real collected item, at least two → service is manifest-declared → repair is
the permitted one for the class → **the deterministic detector agrees on class
and service** → a known-good baseline exists → the corpus is intact. Any rule
that cannot be evaluated rejects.

**The agreement rule is the important one.** SREGym found mitigation succeeds
22–62% of the time *even when the diagnosis is wrong*, because agents
pattern-match a symptom to a fix that happens to work. Requiring the model to
agree with independent deterministic evidence means a plausible-but-wrong
diagnosis cannot drive a write.

**Scope:** `SUPPORTED_FAULT_CLASSES` is `{F06}`. Every other catalogue class is
a legitimate thing for the model to *say* and an illegitimate thing to act on,
so a correct non-`F06` diagnosis is accepted as output and rejected as
authority. The full catalogue is offered in the schema on purpose: a model
given one option always picks it, which would make the diagnosis meaningless
and the gate untestable.

**Acceptance — met**

- [x] Diagnosis names `F06` with a confidence and at least two cited evidence IDs
- [x] Every cited `evidence_id` resolves to a real collected item — fabricated and duplicate citations are both rejection-tested
- [x] `INSUFFICIENT_EVIDENCE` is a first-class return value and proposes nothing
- [x] Below-threshold confidence escalates instead of executing
- [x] An `UNKNOWN` diagnosis escalates and executes nothing (`FR-29`)
- [x] Confidence-threshold gating reads `confidence_threshold` from `kavach.yaml` — it was declared and ignored before this phase
- [x] Kavach's LLM client points **directly** at Ollama, bypassing Toxiproxy, and asserts it
- [x] **Comparison recorded:** P2 deterministic mapping vs P3 LLM RCA on the same injection
- [x] RCA completes well under the 45s `PF-02` budget — 1.7 / 1.9 / 2.2s over three reps
- [x] Unit tests run with **zero network calls**; recorded responses only
- [ ] **With `F01` injected, RCA still completes** — not testable until `F01` has an injector (P6). The client-side assertion that Kavach bypasses Toxiproxy is in place; the end-to-end proof is not

**Live result** — real `llama3.2` on the host Ollama, real `F06` injection:

| | |
|---|---|
| Healthy system | `NO_FAULT`, and **RCA not consulted at all** — deterministic detection gates it, so a healthy system costs no tokens |
| Injected `F06` | 3/3 reps approved; `F06` / `retrieval_collapse` / `backend` every time |
| Validation | all ten checks pass |
| Corpus | 30 chunks / 2 files, unchanged |
| Final fast set | PASS, 100% |

**P2 vs P3 on the same fault, full closed loop:**

| Mode | Status | Diagnosis correct | RCA | Loop |
|---|---|---|---|---|
| P2 deterministic | `RESOLVED` | yes | 0.0s | 55.3s |
| P3 LLM RCA | `RESOLVED` | yes | 2.5s | 56.8s |

**The honest finding: on this one fault class the deterministic detector is not
beaten.** Both reach the same correct repair; RCA costs ~2.5s and adds cited,
auditable reasoning. That is why P2 stays the baseline and the fallback. The
comparison only becomes interesting across several fault classes, where a dict
lookup cannot discriminate — which is P6's job, and the real test of this
phase's claim.

### Known limitation — confidence is not calibrated

**`confidence` is a raw model output, not a calibrated probability.** The model
returns `0.90` flatly across repetitions, and an earlier run returned `1.0`. No
reliability diagram has been produced, no ECE has been measured, and nothing
has been fitted against observed correctness.

So **do not describe `0.90` as "90% likely to be correct"** in the report, in
slides, or in the console. It is the number the model emitted.

The threshold in `kavach.yaml` is therefore a **floor that blocks obviously
unconfident output**, not a probabilistic decision boundary. The gate's actual
strength comes from the deterministic agreement rule, which does not depend on
the confidence number at all.

Calibration is future work: the Laya temperature refit in P7 is where ECE gets
measured before and after, and that is the first point at which a confidence
number may be reported as a probability.

**Two real bugs the live run found, both in Kavach's own code**

1. **The evidence frame never named the services**, so `llama3.2` invented `service="RAG"`. Validation caught it, but the gap was in the frame. Fixed by adding `EV-S01` / `EV-S02`.
2. **`evidence_ids` was optional.** The model cited IDs inside the prose `reasoning` field while leaving the array empty — every other field correct, twice running. A constrained decoder is free to skip an optional field and prompting did not fix it. Made required with a minimum of two, moving the requirement into the grammar; the validator keeps the same rule as a second barrier.

**This phase produces a research result**, not just a feature: a measured
comparison between symptom-matching and evidence-grounded diagnosis on an
identical fault.
---

## P4 — The console ✅ COMPLETE

**Weeks 6–9 · Owner: console track**

> **Completed 2026-10-04.** The console reads and visualises the existing
> P2/P3 loop. The loop's own behaviour is unchanged: the only edit to
> `loop.py` is an optional `on_event` callback that defaults to `None`.

**`DESIGN_SYSTEM.md` governs `apps/console/` and nothing else** — the target's
Next.js 14 frontend is out of its jurisdiction (`DESIGN_SYSTEM.md` §0).

### What shipped

*Backend — the minimum needed to expose existing state (`kavach/api/`)*
- `events.py` — in-process event bus with a bounded replay buffer, published from the loop's worker thread via `call_soon_threadsafe`
- `schemas.py` — typed response models, so `make gen-client` produces types that break `tsc` rather than a useless `Record<string, never>`
- `routes.py` — `GET /v1/system`, `/v1/preflight`, `/v1/incidents`, `/v1/incidents/{id}`, `/v1/events`, `WS /v1/ws`, and `POST /v1/loop/run`
- `runner.py` — single-flight loop execution, in-memory incident history, and the baseline read from the newest capture on disk
- `openapi.py` — writes the OpenAPI document without a running server, so codegen works in CI

*Console (`apps/console/`)*
- Design tokens as CSS variables **and** TS constants, both themes, dark primary
- Three-zone layout: rail · health · incident + timeline · inspector
- Loop Ring, incident row, evidence item, diagnosis card, action plan, verification strip, risk badge, mode indicator, history table
- Live incident updates over WebSocket; the health zone polls on a 5s interval
- Onboarding/preflight screen over the existing check registry
- `make gen-client` wired as the **first** prerequisite of `make check`

### Three decisions worth recording

**1. No Redis.** `ARCHITECTURE.md` §4.3 names Redis pub/sub, and it is right the
moment there is a second control-plane process. There is one. Redis would add a
container and a failure mode to move messages between two objects in the same
interpreter. Everything that would change is behind `publish` and `subscribe`
in `kavach/api/events.py`; **add it when a second replica exists**, not before.

**2. No background detection tick, so no unattended healing.** A timer that
detected and healed on its own would need the mode gate, and `permit()` does
not exist until P6 (`docs/decisions/0006`, amendment). The loop therefore runs
when an operator asks it to, from the console or a harness. **This is the
constraint that keeps the missing safety engine honest, and it must not be
removed before P6 lands.**

**3. In-memory incident history.** `Incident` is a dataclass and there is no
database, so restarting the control plane empties the history. The harness
still writes JSON artifacts under `harness/reports/`. Persistence moves to P6
with the graph's `PostgresSaver`, which is the thing that actually needs it.

### What the console deliberately cannot do

There is no route that accepts an action name, a service, a container, a config
key, a threshold or a command string. `POST /v1/loop/run` is parameterless
apart from an `rca` toggle. The browser can read state and ask for one pass of
the existing loop — it cannot bypass detection, bypass RCA validation, reach
Docker, or name anything a future `permit()` would have to authorise.

**Acceptance — met**

- [x] Inject `F06` and watch the whole loop live without refreshing
- [x] Every diagnosis citation is clickable and opens the matching evidence item in place, never an external page
- [x] Mode indicator visible on every screen without scrolling. It renders as an **indicator, not a switch**, and states in words that the mode is configuration rather than an enforced gate — a segmented control that appeared to change a safety posture while changing nothing would be worse than none
- [x] Legible at 1280×720 — one viewport-height grid with internal scroll regions
- [x] Keyboard-only navigation works; focus is never removed
- [x] No colour-only state indicators: every state, risk tier and probe result carries an icon and a word, asserted by test
- [x] Both themes render; dark is primary and default
- [x] **A backend type change breaks the frontend build** — proven by renaming one field, regenerating, and watching `tsc` fail in both a component and the fixtures
- [x] `make gen-client` works and runs first inside `make check`

**Not built, and why**

| Not built | Why | Now in |
|---|---|---|
| Redis pub/sub | One process; see decision 1 | P6, with a second replica |
| Incident persistence in Postgres | No database yet; in-memory was the scoped choice | P6 |
| The mode **switch** (§7.9 segmented control) | Nothing to switch: no `permit()`, and the loop reads no mode | P6 |
| Approval dialog (§7.7) | There is no approval flow to drive it | P6 |
| Audit table over a hash chain (§7.10) | The history table reads incidents; there is no audit log yet | P6 |
| Metric readout with MTTD/MTTR (§7.11) | Not persisted, so there is nothing to read across incidents | P6 |
| `/v1/traces` OTLP receiver | Nothing in the loop reads a trace | P6 |

---

## P5 — The full safety engine ✅ COMPLETE

**Weeks 8–10 · Owner: control-plane track**

> **Moved ahead of the fault classes on 2026-10-04**, because it used to sit
> after them and contradicted its own entry condition.
>
> **Completed 2026-10-16.** Commits `39903e8` (the gate and its deny cases) and
> `a616385` (wiring, persistence, approval, mode switch). The entry condition
> for P6 is now satisfied: a second repair action may be added.
>
> **Delivered beyond the original list:** the action registry, which is the
> seam a new fault class plugs into, and the approval flow with its
> scroll-to-end control. **Not delivered, with reasons:** LangGraph (what it
> would buy is delivered by persisting the incident and re-preparing on
> resume; replacing a validated `run_once()` with a graph framework is a
> rewrite with no behaviour change), `F-UNK`'s hypothesis flow (the table
> exists; the flow does not), and the 120s SLO-window probe. Those three move
> to P6.

> **Correction to the earlier draft**, which assumed ownership, the deny-list
> and the allow-list were already real from the first loop. They are not.
> **No `safety/` package exists.** P2 shipped one action that is project-scoped
> and deny-list-safe by construction, which is not the same as a gate. This
> phase builds `permit()` from nothing, and it must land before any second
> repair action or any unattended invocation — which is why it now comes
> first.

This phase also picks up what P2 deferred: LangGraph with `PostgresSaver`, the
undo stack as its own module, the hash-chained audit log, the three operating
modes with `SIMULATION` as the default, and the 120s SLO-window verification
probe — the one `FR-07` probe still missing.

**Deliverables**
- `safety/` — the package itself, and the full ten-step `permit()` entry point
- `graph/` — LangGraph with `PostgresSaver`, replacing `loop.py`'s hand-rolled orchestration (`ARCHITECTURE.md` §3.1)
- `executor/undo_stack.py` and `safety/writer_lock.py` as modules, replacing the per-action `invert()` the F06 slice carries
- `audit/log.py` — the append-only hash-chained writer
- The three operating modes, with `SIMULATION` as the default
- The second `FR-07` verification probe: SLO expressions satisfied over a 120s window
- Deterministic risk-tier table (`ARCHITECTURE.md` §6.2) — five actions, everything else HIGH
- Blast radius: ≤3 actions/incident, ≤5 incidents/hour
- Circuit breaker: ≤3 heals per `(service, fault_class)` per 30 min
- Idempotency keys
- The full ten-step `permit()` order (`ARCHITECTURE.md` §6.1)
- `APPROVAL` mode via LangGraph `interrupt()` + `Command` resume; full `AUTONOMOUS` tier routing
- `risk_decisions` rows including the Laya-format `typed_decision_frame`
- `F-UNK` — the unknown-failure flow, which **always** reaches human escalation (`PRD.md` §8.4)
- Sandbox (`F-SBX`, priority P1 — see cut line)

**Acceptance** — reviewed against the suite and a live run on 2026-10-16.

- [x] **Every rule has a passing deny-case test** — this is the phase's real deliverable. `tests/test_safety.py`, 52 tests
- [x] A gated mode produces a full plan and writes nothing — **verified live, not just in a test:** with `mode: APPROVAL` and a real `F06` injected, the loop reached `AWAITING_APPROVAL` carrying the prepared `rollback_config`, its inverse and its pre-state witness, and the target's live `rerank_threshold` was still the faulty `0.999` afterwards. *The docker-state half of this box is vacuous rather than passed: no registered action touches a container, so there is no container state to diff. It becomes meaningful in P6, when `restart_container` lands*
- [x] An action not on the allow-list is denied regardless of mode or risk tier
- [x] An `embed_model` change is denied even if someone adds it to the allow-list — the deny-list wins, and is also checked against the action's *parameters* so a permitted action cannot smuggle one through
- [x] A container outside the compose project is denied even with a matching service name
- [x] Circuit breaker: the 4th heal of the same `(service, fault_class)` inside 30 min escalates instead of healing. *Unit-level; not yet driven by four live injections*
- [x] Blast radius halts automation at the limit
- [x] Approval flow: proposal → park → human approves → re-prepare → **execute**. Verified live: the audit chain records `permit → approved → permit → execute_start → execute_done`. **Not via a LangGraph `interrupt()`/`Command` resume** — there is no graph; approval re-detects and re-prepares, because what a human approves is the decision, not a frozen payload
- [ ] **Graph state survives a control-plane restart mid-interrupt.** Split out of the line above because it does not hold. The incident is persisted, but the parked approval lives in `LoopRunner._awaiting` in memory, so a restart loses it and the operator re-runs. Carried to P6 with the rest of the graph question
- [x] Duplicate idempotency key is a no-op
- [ ] An `UNKNOWN` failure runs the full hypothesis flow and **always** ends at human escalation, never execution. The `hypotheses` table exists; the flow does not. Carried to P6
- [x] No route, parameter or adapter accepts an arbitrary command string (`FR-27`) — grep confirms

**Artifacts**
- `harness/p5_gate_live.py` — the live gate run, driving the HTTP API end to end: inject a real `F06`, assert the loop parks and writes nothing, approve, assert it executed against the captured pre-state. Writes `harness/reports/p5-gate-live.json`. Deliberately does **not** require `RESOLVED`; see `PRD.md` §12 and the script's own docstring
- `harness/stability_f06.py`, `harness/rca_f06_live.py` — unchanged from P2/P3

**What the live run cost, and why it was worth more than the tests.** Four defects survived the whole of P5 development and every one of them needed a real container and a real target to surface:

1. **`/v1/mode`, `/v1/loop/run` and the approve route all failed inside the container**, because the target's `kavach.yaml` — which *is* the safety policy — was read from a host Windows path that is not mounted. The same bug class as P4's `parents[4]` IndexError: a path that only ever resolved on a host checkout. Fixed by mounting the one file read-only and pointing `KAVACH_TARGET_PATH` at the mount
2. **`/v1/system` reported `mode: SIMULATION, mode_is_enforced: false`** on a project whose manifest says `APPROVAL`, because it still returned the global default. The console showed the one field an operator must be able to trust, wrong
3. **An approval could never execute anything.** Approval was implemented as a one-run flip to `AUTONOMOUS`, and `AUTONOMOUS` routes a MEDIUM action to a sandbox that does not exist until P7 — so approving a real repair parked it a second time. An approval is now evidence on the request, satisfying the mode and confidence gates and nothing else
4. **`audit.append("execute_start", incident_id=…, action=…, **action.to_dict())` raised `TypeError`** on duplicate keywords, because the action record already carries both keys. It had never run: no verdict had ever been `ALLOW_AUTO`, so the entire execute-and-audit path was dead code

Defects 3 and 4 are the instructive pair. Both sat behind a gate that nothing had yet opened, so a suite that only ever exercised refusals could not see them — and P5's suite is, by design, mostly refusals.

**Cut line, revised 2026-10-15: the sandbox is no longer the first thing to cut.** It was, on the reasoning that the approval path works without it. That stopped being true when `apply_patch` was accepted (`ARCHITECTURE.md` §6.2.1): a generated patch must be tried somewhere survivable before a human is asked to approve it, and the sandbox is that somewhere. **If the sandbox is cut, `apply_patch` is cut with it** — they are one decision now, not two. Cut `F02` and `F05` first instead.

The sandbox remains the most likely thing to overrun — ports, volumes and stateful services make it harder than it reads. That is a scheduling risk to plan around, not a licence to drop it and keep the generated repair.

---

## P6 — The remaining seven fault classes

**Weeks 10–12 · Owner: target track leads, control-plane supports**

> **Entry condition: P5 has landed.** Every fault here adds a repair action,
> and a repair action without `permit()` is the thing P5 exists to prevent.
>
> **Each fault is an adapter, not a fork.** A new class supplies a detector, an
> evidence query set, a repair action with its inverse, and a verification
> probe — and changes nothing in `rca/schema.py`, `llm/`, or the safety engine.
> If the core has to change, the seam was in the wrong place
> (`ARCHITECTURE.md` §1.3–§1.4). The first fault added after P5 is the real
> test of whether those seams exist.

`F06` shipped in P2. Seven remain. One complete vertical slice each: injector → detection signal → RCA path → repair action + inverse → verification probe → integration test. **Never start the next until the previous passes.**

**Each new fault also needs the `harness/inject.py` CLI that P2 skipped** — a second caller finally justifies it.

| Order | Fault | Note |
|---|---|---|
| 1 | `F01` primary LLM endpoint outage | Toxiproxy from P1; gives the LOW-risk autonomous demo path of `PRD.md` §8.2 |
| 2 | `F08` config regression | Reuses the config interface already built for `F06` |
| 3 | **`F07` prompt regression** | **Needs the git adapter extended to prompt blobs.** Prompts were externalised in P1, so this is the git work, not the extraction |
| 4 | **`F09` token blowout** | Reuses `F07`'s machinery; token capture landed in P1 |
| 5 | `F02` latency degradation | Toxiproxy already in place. **Confirm the ~30s timeout from P1 holds** — at 1200s this is a hang, not a fault |
| 6 | `F05` pool exhaustion | Watch for the target's pre-existing connection leak confounding results (`PRD.md` §12) |
| — | ~~`F03` crash-loop / OOM~~ | **Deferred, not scheduled.** `restart: always` means Docker heals it first, and removing that would weaken the target's resilience to manufacture a fault. See `PRD.md` §6.4 |

**There is no `F04`** — the target has no cache (`PRD.md` §6.1). Do not add Redis to the target to create one.

**`F03` is not in this phase.** If a deterministic, honest crash-loop injector is found (a memory limit that OOMs on every boot, proven over 20 cycles), it can be added as an eighth slice. **Do not write a placeholder injector to make the catalogue look complete** — `AGENTS.md` forbids it, and a fake injector corrupts every number derived from it.

**Acceptance per fault**
- [ ] Injector is deterministic, reverts cleanly, 20 cycles stable
- [ ] Detection fires within 30s
- [ ] Diagnosis names the right class in ≥8 of 10 runs
- [ ] Repair executes; the inverse restores prior state exactly, verified against the pre-state witness
- [ ] All three fast verification probes pass
- [ ] Integration test green in CI
- [ ] Forced-verification-failure test green
- [ ] Ownership and deny-list checks still pass for this fault's action

**Cut line — this is the one that matters.** `F06`–`F09` carry your novelty claim (`PRD.md` §2.2), and `F06` is already banked from P2. If time runs out, **cut `F02` and `F05` — never `F07` or `F09`.** Five faults including all four novel ones beats eight faults where the novel ones are half-finished.

---

## P7 — Git isolation, knowledge base, Laya shadow

**Weeks 11–13 · Owner: evaluation track**

**Deliverables**

*Git isolation, completed*
- The full model in `ARCHITECTURE.md` §13: incident branches derived from `kavach/ops`, pre-state blob witnesses, the complete deny-case suite
- Deny-case tests for: write while `HEAD` is `main`, any `push`, `commit --amend`, force-push, committing a `.env`-shaped path

*Generated repair (`F-CODE`, `apply_patch`)*
- `executor/adapters/git.py` extended to apply a unified diff against a known blob SHA on an incident branch, with `git revert` as the recorded inverse
- The six constraints of `ARCHITECTURE.md` §6.2.1, each as a deterministic check with its own deny-case test
- A diff-budget setting in `kavach.yaml`, and the `versioned_paths` allow-list enforced on path **and** content
- **Entry condition: P5 and P6 have both landed.** The action is HIGH-risk and sandbox-mandatory, so it cannot exist before `permit()` and the sandbox do. Building it earlier is the failure mode to refuse

*Knowledge base*
- `knowledge/` — incident embedding, pgvector similarity retrieval, wired into evidence collection

*Laya shadow (`F-DEC`, priority P1, phase P7)*
- `laya-serve` sidecar in the control-plane compose
- `decision/laya.py` implementing `DecisionEngine`, **shadow-only, never gating**
- Decision-frame compressor fitting the ~768-token state budget
- Temperature refit on collected decisions. **This is also where RCA confidence stops being an uncalibrated model output** — ECE measured before and after, and the first point at which a confidence number may be reported as a probability (see the P3 limitation)
- `shadow_engine` / `shadow_verdict` / `shadow_agreed` populated on every `risk_decisions` row

*Research evaluator (`F-EVAL-FULL`, `FR-07a`)*
- A clean evaluation interface, adapted from the target's RAGAS harness rather than adopted. It must: not require `GEMINI_API_KEY` for its default path (`PL-02`), not monkeypatch `PydanticOutputParser`, and use the same model the backend uses
- `harness/report.py` → `make bench`: **7 injectable faults × 5 reps = 35 injections**, metrics table including the `PRD.md` §10.1 conditionals and the stated denominator

**Acceptance**
- [ ] Laya answers every decision in shadow; agreement/disagreement rate logged
- [ ] **Laya's output is never read by `permit()`** — grep to confirm
- [ ] **No `noul` questions anywhere** — all booleans are two-option `choice` with neutral keys
- [ ] **Nothing gates on `act_probability`** — grep to confirm
- [ ] Temperature refit done; ECE recorded before and after
- [ ] Decision frames never exceed the state budget; overflow raises rather than truncating
- [ ] Similar past incidents appear in evidence collection
- [ ] The research evaluator runs with **no cloud API key** and no monkeypatch, and its scores are reproducible across two runs
- [ ] `make bench` emits a complete metrics table unattended, with **35** injections and the denominator printed
- [ ] Every git deny case has a passing test
- [ ] **`apply_patch` is denied in `AUTONOMOUS` with a LOW-risk allow-listed candidate present** — the tier is fixed by the action, not computed
- [ ] A patch touching a path outside `versioned_paths` is denied on path, before its content is read
- [ ] A patch whose diff exceeds the budget is denied
- [ ] A patch against a stale blob SHA escalates rather than overwriting
- [ ] A patch reaching a deny-listed target is refused in every mode, on content as well as path
- [ ] No sandbox result → no proposal

---

## P8 — Measure, write, rehearse

**Weeks 12–14 · Owner: everyone**

The phase most teams skip and most reviewers notice.

**Deliverables**
- **Human baseline run** — all 35 injections in `SIMULATION` mode, resolved manually by a teammate, timed. ~2 hours of work and it is what makes MTTR mean anything
- **Undo ablation run** — the catalogue with the undo stack disabled. Reproducing the shape of STRATUS's result on your own system is your strongest research contribution
- Full `make bench` with conditional metrics
- **Localization reported honestly** — with the denominator and the per-service confusion matrix (`PRD.md` §10.2)
- `make scenario NAME=demo-full` — a scripted sequence: one autonomous heal, one approval heal, one rollback, one unknown-failure escalation
- Report, slides, demo rehearsal

**Acceptance**
- [ ] Human baseline MTTR recorded per fault class
- [ ] Undo ablation numbers recorded
- [ ] P(heal | correct diagnosis) and P(heal | wrong diagnosis) both reported
- [ ] P2 vs. P3 and rule-engine vs. Laya comparisons written up — the P2-vs-P3 numbers for `F06` are already recorded; extend them across every fault class
- [ ] The eight-fault catalogue and `F04`'s retirement are stated in the report, with the reason
- [ ] The target's Kubernetes files are explained as *not* a Kavach capability (`PRD.md` §5.3)
- [ ] **Demo script runs clean three times consecutively on the demo machine**
- [ ] Offline rehearsal — no network, local model only, no `GEMINI_API_KEY` present
- [ ] A failure path is in the demo. Showing a rollback that works is more persuasive than four successes

---

## Owner tracks

| Track | Phases | Owns |
|---|---|---|
| **Control plane** | P0, P2, P3, P5 | `graph/`, **`safety/`, `executor/`, `verification/`** |
| **Target + faults** | P1, P2, P6 | The target's instrumentation, `harness/faults/` — and the workload adapters a new fault class needs |
| **Console** | P4 | `apps/console/` |
| **Evaluation** | P7, P8 | `evaluation/`, `harness/report.py`, all baselines |

**`safety/` and `executor/` have one author.** Those two directories carry the recoverability guarantee; split ownership is how an inverse quietly stops being recorded.

**The target track has a second responsibility:** every change to `Simple_RAG-Pipeline` stays inside the ten permitted additions (`PRD.md` §5.2), lands on `kavach/ops`, and is never pushed. That track owns the boundary, not just the code.

---

## Working with Claude Code

- **One phase per session.** Never hand it the whole roadmap.
- **Always plan-then-stop.** Review the plan before any code.
- **`make check` green before you accept anything.**
- Read the "Problems I noticed but did not fix" section of every summary. That is where the real information is.
- **Keep the synopsis out of context.** It contradicts `PRD.md` on scope — Kubernetes, nine layers, multi-cloud, MongoDB — and both in context means Claude Code averages them.
- **Keep the target's `ADR-002` out of context too**, for the same reason: it declares Kubernetes mandatory for self-healing, which is the opposite of Kavach's scope.

Three failure modes to watch for: building adjacent phases because they appear in the PRD; quietly weakening a safety check to make a test pass; and widening the ten permitted target additions. `AGENTS.md` forbids all three. Check anyway.

---

## Checkpoints

| When | Question | If no |
|---|---|---|
| End of week 1 | Does the docker socket work from inside a container on the demo machine? | ✅ **Passed** |
| End of week 3 | Does `F06` inject and revert deterministically, 20×, with the metrics moving? | ✅ **Passed** — 20/20 |
| End of week 6 | Does one fault auto-heal end to end with a working rollback? | ✅ **Passed** — `F06`, with the LLM RCA layer on top |
| End of week 7 | Does a second workload type look like an adapter, or a fork? | Fix the seam before P6 multiplies the coupling (`ARCHITECTURE.md` §1.4) |
| End of week 8 | **Has the safety engine started?** | **Stop.** Nothing that adds a repair action may begin until `permit()` exists (P5) |
| End of week 10 | Are `F07` and `F09` started? | Drop `F02` and `F05` now, not later |
| End of week 11 | Does `make bench` run unattended? | Cut the Laya shadow, protect P8 |
| End of week 12 | Has the human baseline been run? | Do it this week. It is 2 hours and it is load-bearing |

---

## What success looks like

A reviewer sees a fault injected into a **real, pre-existing RAG application that was never designed to be healed**. They watch the application return HTTP 200 with a useless answer while every liveness probe stays green — and they watch Kavach notice anyway. The system diagnoses it with cited evidence and a stated confidence, a risk decision is made and recorded, a repair executes under a writer lock with its inverse already captured, and verification confirms it. Then a *second* fault where verification fails and the system unwinds itself cleanly.

Alongside that: a table showing LLM RCA beating symptom-matching, and undo beating no-undo, on the same injections — and an honest note that `F04` was dropped because the target has no cache, rather than a cache added to make the number nine.

That is a stronger project than nine fault classes half-working.
