# ARCHITECTURE.md — Kavach

> System architecture for the Autonomous Self-Healing AI Operations Platform.
> Read `PRD.md` first — the locked scope decisions in §5 of that document
> constrain everything here, in particular §5.1 (the target), §5.2 (the
> boundary), §5.3 (sole healing controller) and §5.4 (default mode).

---

## 1. System overview

Kavach is a **general-purpose control plane** that observes and acts on a separate **system under management (SUM)**. The SUM is replaceable by design: it is identified by a manifest, reached through named operations, and never linked into Kavach's process. The two never share a process, a codebase, or a database. The only paths between them are telemetry flowing in and a narrow, allow-listed set of actions flowing out.

**The SUM in this document is `Simple_RAG-Pipeline`, the first reference workload** — a pre-existing RAG application in its own repository (`PRD.md` §5.1). It is the workload Kavach is *validated against*, not the workload Kavach is *for*. Read every concrete RAG name below — `rerank_threshold`, retrieval similarity, corpus — as "what the first adapter supplies", not as a control-plane concept. §1.2 draws the split, §1.3 names the contracts, and §1.4 lists, without softening, the places where the implementation has not yet earned it.

```
┌──────────────────────────────────────────────────────────────────────────┐
│          SYSTEM UNDER MANAGEMENT — Simple_RAG-Pipeline                   │
│          (separate repo, separate compose project)                       │
│                                                                          │
│   frontend ──▶ backend ──┬──▶ db (pgvector)                             │
│   (Next 14)   (FastAPI)  │                                               │
│                          │    ┌─ toxiproxy :A (PRIMARY) ─┐               │
│                          └───▶┤   fault injected here    ├──▶ ollama     │
│                               └─ toxiproxy :B (BACKUP) ──┘      ▲        │
│       │                                      ▲                  │        │
│       └── OTel SDK ──┐          toxiproxy admin API              │        │
└──────────────────────┼───────────────────────┼──────────────────┼────────┘
                       │ OTLP          docker  │  harness         │ direct
                       │               socket  │                  │ (RCA +
                       ▼                       │                  │  eval)
┌──────────────────────┴───────────────────────┴──────────────────┴────────┐
│                          KAVACH CONTROL PLANE                            │
│                                                                          │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────────────┐       │
│  │ Ingestion   │──▶│  Detection   │──▶│   Healing Graph         │       │
│  │ OTLP + Prom │   │  SLO + anom. │   │   (LangGraph)           │       │
│  └─────────────┘   └──────────────┘   │                         │       │
│         │                              │  evidence → rca →      │       │
│  ┌─────────────┐                       │  plan → risk gate →    │       │
│  │ Verifier    │──────────────────────▶│  execute → verify →    │       │
│  │ fast probes │                       │  learn                 │       │
│  └─────────────┘                       └───────┬─────────────────┘      │
│                                                │                         │
│  ┌──────────────────────┐   ┌──────────────────▼──────────────────┐     │
│  │  Safety Engine       │◀──│  Executor (allow-listed adapters)   │     │
│  │  ownership · risk    │   │  docker · git · http · filesystem   │     │
│  │  allow-list · CB     │   └─────────────────────────────────────┘     │
│  │  blast radius · lock │                                               │
│  └──────────────────────┘                                               │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │  PostgreSQL 16 + pgvector  ·  Redis 7  ·  Prometheus         │       │
│  │  telemetry · incidents · audit log · knowledge base          │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                               │                                          │
│                               ▼ WebSocket + REST                         │
│                      ┌─────────────────┐                                │
│                      │  Console (Next) │                                │
│                      └─────────────────┘                                │
└──────────────────────────────────────────────────────────────────────────┘
```

Note two deliberate properties of that diagram:

- **Kavach's own LLM calls go directly to Ollama**, never through Toxiproxy. `F01`/`F02` fault only the target's primary path. Breaking the system under diagnosis must never blind the diagnostician (`PRD.md` §6.3).
- **One Ollama, one Prometheus**, shared. See §2.4.

### 1.1 Component responsibilities

| Component | Owns | Does not own |
|---|---|---|
| **Ingestion** | Receiving OTLP, normalising LLM span attributes, writing telemetry | Deciding anything |
| **Verifier** | The fast-verification probe set; the full research evaluator | Deciding anything |
| **Detection** | Evaluating SLO PromQL expressions and rolling baselines; raising incidents | Diagnosing |
| **Healing graph** | The incident state machine; orchestrating RCA, planning, verification | Executing side effects directly |
| **Safety engine** | Project ownership, risk tier, allow-list, blast radius, circuit breaker, writer lock, mode policy | Choosing the repair |
| **Executor** | The only component with side effects. One adapter per action type | Deciding whether to act |
| **Knowledge base** | Incident embeddings, similarity retrieval, outcome history | Real-time decisions |
| **Decision engine (shadow)** | Laya's independent answer to the same decisions; agreement logging | Anything binding. It never gates (`PRD.md` §7.1) |

The separation that matters: **the graph decides, the safety engine permits, the executor acts.** No component does two of those three.

---

### 1.2 Generic core, workload adapters — and where the seam is real today

Kavach is a **general-purpose self-healing control plane for containerised AI
workloads**. `Simple_RAG-Pipeline` is the **first reference workload**: the
system Kavach is validated against, not the system Kavach is for.

```
                          KAVACH
            general AI self-healing control plane
        detect → evidence → diagnose → validate → decide
                 → execute → verify → resolve
                              │
                   generic contracts (§1.3)
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   RAG workload         agent workload        ML / CV workload
        │                     │                     │
  Simple_RAG-Pipeline      (none yet)            (none yet)
   ← implemented and          ← architectural scope only; no adapter
     validated: F06             exists, and none is claimed
```

**What is actually true today, stated plainly so nobody reads the diagram as a
capability claim:** one workload is onboarded, one fault class is implemented,
and one repair action exists. Everything to the right of `Simple_RAG-Pipeline`
is architecture, not code. Kavach does not support agent or vision workloads;
it is being built so that supporting one means writing an adapter rather than
forking the control plane.

### 1.3 The six contracts

These are the seams a second workload would integrate through. Each row says
what the contract is, and — honestly — whether the implementation has the seam
or merely has the behaviour.

| # | Contract | What is generic | Seam status in code |
|---|---|---|---|
| 1 | **SUM / project** | A manifest declares identity, compose project, services, SLO expressions, allow/deny lists and a control interface. `TargetClient` exposes *named* operations, never an arbitrary path. Preflight is 24 read-only checks | **Mostly real.** `manifest.py` is workload-agnostic except `corpus_fingerprint`, `embedding_model` and the `embed_model` deny rule, which are RAG concepts in a generic validator |
| 2 | **Telemetry / evidence** | `EvidenceFrame` of `(eid, kind, name, value, expected, note)` items with stable citable IDs. Kinds — metric, config, verification, health, log, baseline, service — are workload-neutral | **Frame generic, sources not.** `METRIC_QUERIES` in `rca/evidence.py` hardcodes `ragapp_*` PromQL. A second workload needs its own query set behind the same frame |
| 3 | **Diagnosis** | `fault_class`, `fault_name`, `service`, `confidence`, `evidence_ids`, `reasoning`, `candidate_repair`, `rejected_alternatives` — a closed vocabulary, schema-constrained | **Fully generic.** `rca/schema.py` contains no RAG concept at all. This is the cleanest seam in the system |
| 4 | **Action / executor** | `prepare()` captures a pre-state witness, `execute()`, `invert()`, `verify_applied()`, `verify_restored()`, `unchanged_elsewhere()`, plus an idempotency key. An action without a recorded inverse cannot be constructed | **Pattern generic, no registry.** `config_rollback.py` is one concrete action; the `Action` protocol and registry arrive with the safety engine |
| 5 | **Verification** | A health probe plus N deterministic cases scored locally, inside a declared budget, with no cloud key | **Mostly generic.** `verification/fast.py`'s mechanism is workload-neutral; the `sources_block` check is a RAG grounding assertion and belongs in a workload probe |
| 6 | **Safety / policy** | `permit()` over ownership, deny-list, allow-list, inverse, confidence, risk tier, blast radius, breaker, mode | **Not built.** §6.1–§6.3 describe it; nothing implements it. This is the next phase |

### 1.4 Where the implementation is still RAG-coupled

Recorded as debt, not hidden. None of this is wrong for a one-workload system —
it is wrong for the system the roadmap says Kavach becomes, and it is cheapest
to name now.

| Module | Coupling | Why it matters | Closes in |
|---|---|---|---|
| **`loop.py`** | Imports `detection.retrieval_collapse` and `build_rollback_for_retrieval_collapse` **directly**; `Incident` carries `corpus_before` / `corpus_after`; `_corpus()` queries `ragapp_corpus_chunks` by name; the signature takes `baseline_rerank_threshold` | **The orchestrator is a RAG loop, not a generic lifecycle with a RAG adapter plugged in.** The generic lifecycle currently exists as a docstring, not as a seam | P5 — the detector and action become registry lookups |
| **`api/schemas.py`** | `corpus`, `chunks`, `files` and `rerank_threshold` are first-class fields on the public wire contract | A vision workload would have to misreport or extend the schema. These belong in a per-workload extras map | P5 |
| **`api/routes.py`, `api/runner.py`** | The generic HTTP layer queries `ragapp_corpus_*` and reads `rerank_threshold` from settings | Same reason; the API should ask the adapter, not Prometheus directly | P5 |
| **`rca/evidence.py`** | `METRIC_QUERIES` / `HEALTHY_EXPECTATION` are module-level RAG constants inside the generic collector | The frame is reusable; the query set is not, and nothing separates them | P5 |
| **`rca/validate.py`** | Rule 10 (`corpus_intact`) is a RAG invariant in the generic validator; `PERMITTED_REPAIR` is keyed off the RAG detector's constant | Rules 1–9 are workload-neutral. Rule 10 is a workload precondition and should be supplied by the adapter | P5 |
| **`onboarding/baseline.py`** | Captures `rerank_threshold` and corpus counts as named concepts | Baseline capture is generic; *what* is worth capturing is per workload | P6 |
| **Console** | `SystemHealth` renders "threshold" and "corpus" as fixed rows; the verification strip labels a case "grounded" | The console should render whatever the adapter declares, not a fixed RAG vocabulary | P6 |

**The rule going forward:** a new workload adds an adapter — a detector, an
evidence query set, a repair action with an inverse, and a verification probe —
and changes **nothing** in `rca/schema.py`, `llm/`, `api/events.py`,
`loop.py`'s control flow, or the safety engine. If a change to the core is
needed to support a second workload, the seam is in the wrong place and the
seam is what gets fixed.

---

## 2. Tech stack

### 2.1 Chosen

| Layer | Choice | Rationale |
|---|---|---|
| Control-plane language | **Python 3.12** | Agent ecosystem, OTel SDK maturity, team familiarity |
| API framework | **FastAPI** + Uvicorn | Async, OpenAPI for free, native OTel instrumentation |
| Agent orchestration | **LangGraph** | The incident loop is a cyclic state machine with conditional edges and interrupts. That is precisely what LangGraph models, and its checkpointer gives durable incident state for free |
| LLM (default) | **Ollama**, `qwen2.5:7b-instruct` | The **target's** Ollama instance, reached directly (§2.4). No API key. Acceptable for closed-set classification. May be set to `llama3.2` to reuse the already-loaded model if the 16GB budget is tight. OpenAI-compatible endpoint means swapping to a hosted model is a config change |
| Database | **PostgreSQL 16 + pgvector** | One database. Relational for incidents/audit, pgvector for the knowledge base. **No TimescaleDB in v1** — see §5 |
| Cache / queue | **Redis 7** | Idempotency keys, rate windows, circuit-breaker counters, pub/sub for console updates. *(Control plane only. The target has no cache — `PRD.md` §6.1)* |
| Metrics | **Prometheus** | One instance, in the control plane, scraping both the target and Kavach. The detection layer evaluates PromQL expressions against it (§2.4) |
| Telemetry transport | **OpenTelemetry Collector** | The target exports OTLP to the collector; the collector fans out to Prometheus and to Kavach's OTLP receiver. See §2.3 |
| Decision model (shadow) | **Laya** `laya-typed-decisions`, via `laya-serve` sidecar | Apache-2.0, local, ~33ms, already fine-tuned on agent-trace observability and security-incident workflows. **Shadow-only, never gating.** Priority P1, scheduled P7 (`ROADMAP.md` numbering, canonical as of 2026-10-04). See `PRD.md` §7.1 for the three defects it must be used around |
| Frontend | **Next.js 15 (App Router)**, TypeScript, Tailwind v4, shadcn/ui | `apps/console/` only. See `DESIGN_SYSTEM.md` §0 for jurisdiction |
| Charts | **Recharts** | Composable, fits the token system, no canvas |
| Migrations | **Alembic** | |
| Validation | **Pydantic v2** everywhere, including every LLM structured output | |
| Python tooling | **uv**, **ruff**, **mypy --strict**, **pytest** | |
| JS tooling | **pnpm**, **eslint**, **prettier**, **vitest**, **playwright** | |
| Container control | **docker SDK for Python** | Behind a `RuntimeAdapter` interface; §6.3 ownership checks are mandatory |
| Fault injection | Custom harness + **Toxiproxy** | Two listeners in front of the target's Ollama. Deterministic latency/failure injection at the proxy layer, which is exactly how `F01`/`F02` should be produced (`PRD.md` §6.3) |

### 2.2 Explicitly rejected

Writing these down so nobody re-adds them.

**Scope of this table:** every rejection below applies to **the Kavach control plane**. It does **not** govern the system under management. The target is an independent application with its own dependency choices, and Kavach's job is to observe and operate it, not to re-architect it. Specifically: the target legitimately depends on `sentence-transformers` (and therefore PyTorch) for its `BAAI/bge-reranker-base` reranker, and that is **not** a violation of this table.

| Rejected (in the control plane) | Why |
|---|---|
| **MongoDB** | The synopsis lists Postgres *and* Mongo *and* Redis. Nothing in the data model needs a document store. One less container, one less driver, one less backup story |
| **TimescaleDB** | Was in the earlier draft for two telemetry tables. For one target application on a laptop, plain Postgres with a BRIN index and a delete job is sufficient, and it removes a hard constraint on the Postgres image (§5). Additive later if telemetry volume is ever measured as a problem |
| **LangChain and CrewAI alongside LangGraph** | Three agent frameworks for one agent. LangGraph alone. Use the underlying LLM client directly for single-shot calls |
| **PyTorch and TensorFlow** | Anomaly detection in v1 is statistical (rolling z-score, EWMA, Page-Hinkley for drift) via scipy/numpy. Loading a deep learning framework to compute a z-score is the definition of over-engineering. Laya's own dependencies are isolated in the `laya-serve` sidecar, which is a second reason the control-plane image stays clean of both |
| **Kubernetes** | Out of scope per `PRD.md` §11. The executor's docker adapter sits behind a `RuntimeAdapter` interface so a k8s adapter is additive, not a rewrite. **The target repository contains `k8s/` manifests and a `kubernetes` dependency; Kavach v1 reads neither** (`PRD.md` §5.3) |
| **A second self-healing engine** | The target ships `backend/aiops_agent.py`. In v1 Kavach is the sole writer to the SUM; that agent is neutralised, not integrated (`PRD.md` §5.3). A second writer breaks `FR-15a` outright |
| **A Rust healing executor** | Was in the earlier target architecture. A second language for a component that mostly shells out to the Docker API buys nothing in v1 and costs the team a build toolchain. Revisit only if execution latency becomes a measured problem, which `PF-03` says it will not |
| **Self-hosted Langfuse / Phoenix** | Would add a heavy container to be a trace viewer. Kavach stores the LLM spans it needs in Postgres. If the team wants a trace UI, point the OTel collector at Langfuse *as well* — one extra exporter, zero code |
| **Grafana** | Prometheus is needed as a query engine. Grafana is a second dashboard competing with the console we are building |
| **A hosted telemetry SaaS** | The target currently ships a Traceway provider and bundler plugin, and its README suggests exporting OTLP to `cloud.tracewayapp.com`. Kavach's telemetry path is entirely local (§9), because the demo must work offline. The target's SaaS export is env-gated and left disabled |
| **A custom OTLP implementation** | Use the collector. Kavach does not invent a wire protocol. It *does* normalise attribute **names** at the ingestion boundary, for the reasons in §2.3 — that is a mapping layer, not a protocol |

### 2.3 LLM semantic conventions are not stable — design for that

A widely repeated claim says the ecosystem has "converged on" OpenTelemetry's GenAI conventions as a settled baseline. It has converged on them as the *direction*, but they are not stable and should not be treated as a fixed schema.

As of 2026, **every `gen_ai.*` attribute, span, metric and event carries the status `Development`** — which on OpenTelemetry's own maturity ladder sits *below* Alpha and is defined as "SHOULD NOT be used in production" and "MAY be removed without prior notice." The only Stable attributes on a GenAI span are `error.type`, `server.address` and `server.port`, all inherited from core. On **12 June 2026, in semantic-conventions v1.42.0**, the GenAI, provider-specific and MCP conventions were deprecated in the core repo and moved to a dedicated `semantic-conventions-genai` repository specifically so they could iterate faster than the core stability bar allows. That repository evolves on `main` and has no tagged release. Attributes have already been renamed in flight — `gen_ai.provider.name` replaces the older `gen_ai.system` — and independent comparisons find SDKs disagreeing with each other on several of the most-used attributes while roughly eleven have held steady.

**Three consequences, all binding:**

1. **Pin the convention version** via `OTEL_SEMCONV_STABILITY_OPT_IN` and record which version a span was ingested under. Do not let instrumentation silently change shape under you.
2. **Normalise at the ingestion boundary into Kavach's own internal schema.** Nothing downstream of `ingestion/genai.py` may reference a raw `gen_ai.*` attribute name. A spec rename then costs one mapping file, not a migration across detection, RCA and the console.
3. **Build on the attributes that have held:** operation name, provider, request/response model, token usage, operation duration, finish reason. Treat multimodal content, agent-graph and MCP attributes as volatile.

**A note specific to this target.** Because the target has no OTel instrumentation today (`PRD.md` §5.1), the LLM spans are written by hand as part of §5.2 addition 1 — there is no vendor auto-instrumentation emitting `gen_ai.*` names for us. That makes rule 2 cheap to honour: the target emits Kavach's internal attribute names directly, and `ingestion/genai.py` remains the single mapping point for any future auto-instrumentation that does emit raw `gen_ai.*`.

### 2.4 Shared infrastructure — one Prometheus, one Ollama

`PL-01` is a 16GB laptop. Two Prometheus instances and two Ollama instances (each loading its own model set) do not fit alongside `llama3.2`, `nomic-embed-text`, a CrossEncoder reranker, and an RCA model. Duplicate infrastructure is therefore removed rather than tolerated.

**Prometheus — one instance, owned by the control plane.**

| | |
|---|---|
| Lives in | `infra/docker-compose.yml` |
| Scrapes | the target's `backend:8000/metrics`, the collector's Prometheus exporter, and Kavach's own `/metrics` |
| Why control-plane-owned | Kavach must keep observing the target *while restarting the target's containers*. A Prometheus inside the compose project Kavach is mutating is a Prometheus that can go down exactly when it is needed. This is the "concrete isolation reason" that decides ownership |
| The target's bundled `prometheus` service | Moved behind a compose profile (`profiles: [standalone]`) so `docker compose up` no longer starts it. One additive line; the service definition is preserved for anyone running the target on its own |

**Ollama — one instance, the target's.**

| | |
|---|---|
| Lives in | the target's compose |
| Serves | `llama3.2` (target generation), `nomic-embed-text` (target embeddings), and Kavach's RCA model |
| Kavach reaches it | **directly**, at `http://ollama:11434`, never through Toxiproxy (`PRD.md` §6.3) |
| RCA model | `KAVACH_LLM_MODEL`, default `qwen2.5:7b-instruct`. Set it to `llama3.2` to reuse an already-resident model when memory is tight |

**Networking.** The target's compose creates the network; the control-plane compose joins it as an `external` network, in addition to its own internal network. The control plane can therefore reach `backend`, `ollama` and `toxiproxy` by service name, while the target cannot reach the control plane's Postgres or Redis. Telemetry flows the other way by the target dialling the collector's published address.

---

## 3. Project structure

**This is the target structure.** The repository is a subset of it today; §3.1 reconciles the two and records where the implementation deliberately deviates.

```
kavach/
├── apps/
│   ├── control-plane/              # Python, FastAPI
│   │   ├── kavach/
│   │   │   ├── main.py             # app factory, lifespan, router mounting
│   │   │   ├── config.py           # pydantic-settings, all env in one place
│   │   │   ├── api/                # HTTP layer ONLY — no business logic
│   │   │   │   ├── routes/
│   │   │   │   │   ├── projects.py
│   │   │   │   │   ├── incidents.py
│   │   │   │   │   ├── actions.py      # approve / reject
│   │   │   │   │   ├── audit.py        # read-only, no PUT/DELETE
│   │   │   │   │   ├── telemetry.py    # OTLP receiver
│   │   │   │   │   └── faults.py       # injection control (dev only)
│   │   │   │   ├── schemas/            # pydantic request/response models
│   │   │   │   └── ws.py               # websocket hub
│   │   │   ├── onboarding/
│   │   │   │   ├── manifest.py         # kavach.yaml parsing + validation
│   │   │   │   ├── preflight.py        # the check registry
│   │   │   │   ├── checks/             # one file per check
│   │   │   │   └── baseline.py         # last-known-good capture
│   │   │   ├── ingestion/
│   │   │   │   ├── otlp.py             # OTLP/HTTP receiver
│   │   │   │   ├── genai.py            # LLM attribute normalisation (§2.3)
│   │   │   │   └── prometheus.py       # PromQL expression evaluation
│   │   │   ├── verification/
│   │   │   │   ├── probes.py           # health, slo_window, fast_quality
│   │   │   │   ├── verifier.py         # all-three-must-pass
│   │   │   │   └── fast_set.py         # the 3 deterministic check cases, serial
│   │   │   ├── evaluation/             # research evaluator (P7, FR-07a)
│   │   │   │   ├── runner.py
│   │   │   │   └── scorers/            # latency, cost, quality, groundedness
│   │   │   ├── detection/
│   │   │   │   ├── slo.py              # PromQL expression evaluation
│   │   │   │   ├── anomaly.py          # z-score, EWMA, Page-Hinkley
│   │   │   │   └── classifier.py       # signal → candidate fault classes
│   │   │   ├── graph/                  # THE AGENT — LangGraph
│   │   │   │   ├── build.py            # graph assembly
│   │   │   │   ├── state.py            # IncidentState TypedDict
│   │   │   │   └── nodes/
│   │   │   │       ├── collect_evidence.py
│   │   │   │       ├── diagnose.py
│   │   │   │       ├── plan.py
│   │   │   │       ├── risk_gate.py
│   │   │   │       ├── sandbox.py
│   │   │   │       ├── await_approval.py
│   │   │   │       ├── execute.py
│   │   │   │       ├── verify.py
│   │   │   │       ├── rollback.py
│   │   │   │       └── learn.py
│   │   │   ├── safety/
│   │   │   │   ├── engine.py           # the permit() entry point
│   │   │   │   ├── ownership.py        # §6.3 project/service identity checks
│   │   │   │   ├── rules.py            # deterministic risk classifier
│   │   │   │   ├── allowlist.py
│   │   │   │   ├── denylist.py         # EMBED_MODEL and friends (FR-30)
│   │   │   │   ├── blast_radius.py
│   │   │   │   ├── circuit_breaker.py
│   │   │   │   ├── writer_lock.py      # the A-Lock (§6.0)
│   │   │   │   └── decision_log.py     # emits Laya-format typed decisions
│   │   │   ├── decision/
│   │   │   │   ├── base.py             # DecisionEngine protocol
│   │   │   │   ├── rule_engine.py      # v1 authority
│   │   │   │   └── laya.py             # P1 priority, P7 phase, shadow-only
│   │   │   ├── executor/
│   │   │   │   ├── registry.py         # action name → adapter
│   │   │   │   ├── base.py             # Action, InverseAction protocols
│   │   │   │   ├── undo_stack.py       # per-incident, reverse unwind (§6.0)
│   │   │   │   └── adapters/
│   │   │   │       ├── docker.py       # restart, memory limit. ONLY docker SDK importer
│   │   │   │       ├── git.py          # kavach/ops branch, commit, revert
│   │   │   │       ├── http.py         # the target's config interface (§7.2)
│   │   │   │       └── filesystem.py   # prompt/config file rollback
│   │   │   ├── knowledge/
│   │   │   │   ├── embed.py
│   │   │   │   ├── retrieve.py         # pgvector similarity
│   │   │   │   └── store.py
│   │   │   ├── audit/
│   │   │   │   └── log.py              # append-only, hash-chained writer
│   │   │   ├── llm/
│   │   │   │   ├── client.py           # OpenAI-compatible, direct to Ollama
│   │   │   │   └── prompts/            # versioned prompt files
│   │   │   ├── db/
│   │   │   │   ├── models.py           # SQLAlchemy
│   │   │   │   ├── session.py
│   │   │   │   └── migrations/
│   │   │   └── telemetry/              # Kavach observing ITSELF
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   └── console/                        # Next.js 15 — DESIGN_SYSTEM.md applies HERE only
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx                # fleet overview
│       │   ├── projects/[id]/
│       │   │   ├── page.tsx            # project health
│       │   │   ├── onboarding/page.tsx # preflight checklist
│       │   │   └── settings/page.tsx   # mode, allow-list, SLO
│       │   ├── incidents/
│       │   │   ├── page.tsx            # stream
│       │   │   └── [id]/page.tsx       # the live loop view
│       │   └── audit/page.tsx
│       ├── components/
│       │   ├── ui/                     # shadcn primitives
│       │   ├── incident/               # timeline, evidence, diagnosis card
│       │   ├── safety/                 # risk badge, mode switch, approval
│       │   └── charts/
│       ├── lib/
│       │   ├── api.ts                  # typed client, generated from OpenAPI
│       │   ├── ws.ts                   # websocket hook
│       │   └── tokens.ts               # design tokens as TS constants
│       └── package.json
│
├── targets/
│   └── simple-rag.yaml                 # A POINTER, not a copy of the app.
│                                       # path, base_branch, service map,
│                                       # compose project name. The target
│                                       # itself lives in its own repo at
│                                       # D:\Vit\Academics Sem-5\EDI\Target_RAG-App
│
├── harness/
│   ├── inject.py                       # CLI: F01 F02 F05 F06 F07 F08 F09
│   ├── faults/                         # one module per fault class
│   ├── scenarios/                      # scripted demo sequences
│   └── report.py                       # metrics table for the report
│
├── infra/
│   ├── docker-compose.yml              # the control plane
│   ├── otel-collector-config.yaml
│   └── prometheus.yml                  # the ONE Prometheus (§2.4)
│
├── docs/
│   ├── PRD.md
│   ├── AGENTS.md
│   ├── ARCHITECTURE.md
│   ├── DESIGN_SYSTEM.md
│   ├── ROADMAP.md
│   ├── synopsis-original.md            # archived, superseded, reference only
│   ├── DESIGN-cursor.md                # visual reference only
│   ├── decisions/                      # ADRs — one per scope change
│   └── runbook.md
│
└── Makefile
```

**`targets/simple-rag.yaml` is configuration, not code.** There is no `targets/demo-rag/` and no copy of the application in this repository. Kavach points at the target by path; the target is developed, versioned and run independently.

---

### 3.1 What exists today (P0–P3), and where it deviates from the tree above

**The tree above is the target structure, not the current one.** As of
2026-10-04 the implemented slice is `F06` only — detect, diagnose, repair,
verify — and it is smaller than the tree in several places and differently
shaped in a few. This subsection is the reconciliation, so the specification and
the repository agree instead of quietly disagreeing.

```
apps/control-plane/kavach/
├── main.py                        # FastAPI app: /healthz + the console router
├── config.py                      # pydantic-settings
├── api/                           # ◀ the console surface (P4), not api/routes/
│   ├── routes.py                   # 6 read routes + POST /v1/loop/run + WS /v1/ws
│   ├── schemas.py                  # typed response models; the codegen contract
│   ├── events.py                   # in-process event bus (§4.3), no Redis yet
│   └── runner.py                   # single-flight loop execution + in-memory history
├── openapi.py                      # writes the OpenAPI doc without a running server
├── target.py                       # ◀ DEVIATION — the only HTTP client to the target
├── loop.py                         # ◀ DEVIATION — hand-rolled orchestrator, not graph/
├── onboarding/
│   ├── manifest.py                # kavach.yaml parsing + validation
│   ├── preflight.py               # the check registry (read-only checks)
│   └── baseline.py                # last-known-good capture
├── detection/
│   └── retrieval_collapse.py      # ◀ F06 only; no slo.py, anomaly.py, classifier.py
├── verification/
│   ├── fast.py                    # ◀ health + the 3 quality cases; no SLO-window probe
│   └── fast_set.yaml              # the 3 cases as data, not fast_set.py
├── rca/                           # ◀ DEVIATION — P3's RCA layer, not graph/nodes/
│   ├── evidence.py                # evidence collection and normalisation
│   ├── schema.py                  # the Diagnosis contract (Pydantic)
│   ├── validate.py                # the deterministic validation gate
│   └── engine.py                  # orchestration; never raises
├── llm/
│   ├── client.py                  # Ollama, schema-constrained, direct (not proxied)
│   └── prompts/diagnose.txt       # versioned prompt file
└── executor/
    └── config_rollback.py         # ◀ one concrete action; no registry/, no adapters/

harness/
├── faults/{base,f06_retrieval_collapse}.py
├── stability_f06.py               # the 20-cycle deterministic harness
└── rca_f06_live.py                # live RCA + the P2-vs-P3 comparison
```

**Not present at all:** `ingestion/`, `graph/`, `safety/`, `decision/`,
`knowledge/`, `audit/`, `db/`, `telemetry/`, `evaluation/`,
`executor/adapters/`, `harness/inject.py`, `harness/scenarios/`,
`harness/report.py`. Each is scheduled — see `ROADMAP.md` P5–P7.

**`api/` is flatter than the tree above**, which specifies `api/routes/` with a
file per resource plus `api/schemas/` and `api/ws.py`. Seven routes over one
project do not need seven files, and the WebSocket is nine lines on the same
router. It splits per resource when a second project or an approval flow
arrives. The console's own tree matches the plan: `app/`, `components/ui|incident|safety/`,
`lib/` with the generated client under `lib/api/generated/`.

#### The four deviations, and why

**1. `loop.py` instead of `graph/`.** The closed loop is a hand-rolled
`run_once()`, not a LangGraph graph. `graph/` stays reserved for the LangGraph
implementation; putting a hand-rolled orchestrator inside it would misrepresent
what it is. A graph buys persistence, approval interrupts and resumable state —
all of which arrive together in P6, and none of which the F06 slice has yet.
`loop.py` is deleted or reduced to a thin caller when `graph/` lands; it is not
a parallel implementation to maintain.

**2. `target.py` at the package root.** Every HTTP call to the target goes
through this one module, which is why it is not under `executor/adapters/http.py`
— it is read by detection, verification, baseline capture, evidence collection
and the executor alike, so filing it under the executor would invert the
dependency. It deliberately exposes **no generic `request()` method, no
caller-supplied path and no command string** (`FR-27`); the write path is a
single `apply_settings()` call that the target itself validates and refuses
wholesale if any key is denied, unknown or out of range.

**3. `rca/` instead of `graph/nodes/collect_evidence.py` + `diagnose.py`.**
Same reason as (1): there are no graph nodes to be a node of. The split inside
`rca/` is evidence → schema → validation → engine, which maps onto the two
planned nodes plus the validation gate the tree never named as a file.

**4. `executor/config_rollback.py` instead of `registry.py` + `adapters/`.**
One action, one concrete class. A registry mapping one name to one adapter, and
an `Action` protocol with one implementation, would be an interface with one
implementation. The *guarantee* the registry was there to enforce — no action
without an inverse — is enforced directly instead: `prepare()` refuses to build
a rollback when no known-good baseline was captured, so an action with nothing
to invert to cannot be constructed. The registry arrives with the second action,
in P5/P6.

**Also deviating, more mildly:** `verification/fast.py` replaces the planned
`probes.py` + `verifier.py` + `fast_set.py` trio, and implements **two** of the
three `FR-07` probes — health and the 3 deterministic quality cases. The 120s
SLO-window probe is **not implemented**, so "all three must pass" is currently
"both implemented probes must pass". That is a known gap, scheduled in P6, and
it is the one place where the current verification is weaker than `FR-07`
describes.

**Not a deviation:** `detection/retrieval_collapse.py` is narrow because only
one fault class is implemented, not because the design changed. `slo.py`,
`anomaly.py` and `classifier.py` are still the intended shape.

---

## 4. Data flow

### 4.1 Observation path

```
target backend
  ├─ prometheus_client ──▶ /metrics ◀── scraped directly by Prometheus
  │                                      (metrics path: ONE hop)
  └─ OTel SDK emits spans (Kavach internal attribute schema, §2.3)
     └─ OTLP/HTTP ──▶ OTel Collector
                        └─ otlphttp ──▶ Kavach /v1/traces   (P4, not built)
                                          └─ normalise ──▶ telemetry_spans
```

**Metrics do not go through the collector. Traces do.** An earlier draft routed both over OTLP, and that is wrong for metrics specifically: detection reads these metrics, so putting a collector in the path adds a failure mode where the collector dying leaves detection silently blind — monitoring that fails quietly is the worst way for it to fail. Scraping `/metrics` directly has one hop and one failure mode, and that path was already proven working before any application metric existed.

Traces are diagnostic rather than detection-critical. Losing a batch of spans degrades an RCA explanation; it does not cause a missed incident. The extra hop is acceptable there, and the collector remains the fan-out point for traces — adding Langfuse later means one exporter block and no code change.

**Metrics the target must expose** for the catalogue to be detectable. Those marked *existing* are already there; the rest arrive with §5.2 addition 1.

| Metric | Source | Serves |
|---|---|---|
| `http_request_duration_seconds_bucket{handler,method,status}` | *existing* (`prometheus-fastapi-instrumentator`) | SLO latency |
| `http_requests_total{handler,method,status}` | *existing* | SLO error ratio |
| `ragapp_llm_requests_total{outcome,endpoint,model}` | new | `F01` |
| `ragapp_llm_duration_seconds_bucket{operation}` | new | `F02` |
| `ragapp_llm_tokens_total{kind}` | new (from Ollama's `usage`) | `F09` |
| `ragapp_retrieval_top_similarity_bucket` | new | `F06` |
| `ragapp_retrieval_empty_context_total` | new | `F06` |
| `ragapp_db_pool_in_use` / `ragapp_db_pool_max` | new | `F05` |
| `kavach_fast_eval_pass_rate{project}` | Kavach's own verifier | `F06`, `F07` |

`F03` and `F08` are detected from the Docker API and the config hash respectively, not from Prometheus.

### 4.2 Incident path

```
Detection tick (every 15s)
  ├─ evaluate each SLO PromQL expression against Prometheus
  ├─ evaluate rolling baselines for anomaly
  └─ breach? ──▶ create incident(status=DETECTED) ──▶ start graph run
                                                       │
     ┌─────────────────────────────────────────────────┘
     ▼
  collect_evidence   (parallel: spans, logs, container states, recent git diffs,
                      config snapshot, verification history, similar past
                      incidents from pgvector)
     ▼
  diagnose           LLM → structured Pydantic output:
                     {fault_class ∈ {F01,F02,F03,F05,F06,F07,F08,F09}
                                     | UNKNOWN | INSUFFICIENT_EVIDENCE,
                      confidence: float, evidence_ids: [str],
                      rejected_alternatives: [{class, reason}]}
     ▼
  confidence < threshold OR INSUFFICIENT_EVIDENCE ──▶ escalate
  fault_class == UNKNOWN ──────────────────────────▶ unknown flow (PRD §8.4)
                                                      never auto-executes
     ▼
  plan               fault_class → repair action + inverse action (from catalogue)
     ▼
  risk_gate          safety_engine.permit(action, project, incident)
     │                 → ownership, allow-list, deny-list, inverse,
     │                   confidence, risk tier, blast radius, breaker, mode
     │
     ├─ DENY ─────────────────────────────────▶ escalate
     ├─ mode=SIMULATION ──────────────────────▶ plan + dry-run diff, STOP
     ├─ LOW   + mode=AUTONOMOUS ──────────────▶ execute
     ├─ MEDIUM ──▶ sandbox ──▶ await_approval ─▶ execute
     └─ HIGH ─────────────────▶ await_approval ─▶ execute
     ▼
  execute            acquire writer lock → push (action, inverse, pre_state)
                     onto undo stack → executor.run(action) with idem key
     │
     ├─ severity metric INCREASED after the action (FR-15c)
     │        └──▶ unwind undo stack IMMEDIATELY, do not wait for verify
     ▼
  verify             FAST verification (FR-07):
                     probe 1: health endpoints
                     probe 2: SLO expressions satisfied over a 120s window
                     probe 3: 3 deterministic quality checks (serial)
     │
     ├─ all pass ──▶ learn ──▶ resolved, new baseline captured, lock released
     └─ any fail ──▶ unwind undo stack in reverse ──▶ verify unwind against
                     pre-state witnesses ──▶ escalate
```

The severity early-abort edge is drawn explicitly because it is the mechanism `FR-15c` and the whole TNR claim rest on, and it was absent from the previous draft's diagram.

**What runs today (P2/P3, `F06` only).** The path above is the design. The implemented loop is:

```
harness invokes run_once()
  ─▶ deterministic detection (similarity healthy + grounding lost +
                              fast set failing NOW)
  ─▶ RCA: evidence ─▶ LLM ─▶ the ten-rule gate (§6.4)   [optional stage]
  ─▶ prepare: capture pre-state, derive the inverse
  ─▶ execute rollback_config
  ─▶ verify: health + the 3 quality cases
  ─▶ RESOLVED, or ESCALATED
```

There is no 15s detection tick, no `permit()`, no risk gate, no mode routing, no sandbox, no approval interrupt and no `learn` step. **The severity early-abort edge is not implemented either** — the F06 slice reaches verification and escalates on failure, which is the correct outcome but not the fast one `FR-15c` requires. Scheduled in P6. Without the mode plumbing, the loop cannot act unattended: it only runs when a harness calls it.

`RESOLVED` requires **all** of: verification passed, the repair proved applied, nothing outside the repair's scope changed, and the corpus fingerprint unchanged across the whole incident. Anything else escalates. A loop that reports success on a failed verification is a false-healing machine, which is the worst outcome in the design.

### 4.3 Live console path

The console reads state over HTTP and watches an in-flight loop over a
WebSocket.

```
browser ──HTTP──▶ GET  /v1/system        composed dependency health, identity,
                                          mode, corpus, live threshold
                  GET  /v1/preflight     the existing read-only check registry
                  GET  /v1/incidents     history, newest first
                  GET  /v1/incidents/:id one incident in full
                  GET  /v1/events        the replay buffer
                  POST /v1/loop/run      ONE pass of the existing loop
        ──WS────▶ /v1/ws                 every loop stage, as it happens
```

**Events, not polling, for the thing that moves.** `loop.run_once` takes an
optional `on_event(stage, status, message)` sink. The runner hands it a
closure that publishes to `kavach/api/events.py`, which fans out to each
connected WebSocket. The sink is observation-only: nothing in the loop reads a
return value, no branch depends on it, every call goes through `_notify` which
swallows exceptions, and `None` — the default — leaves the P2/P3 loop
byte-identical. A console that has gone away cannot take an in-flight repair
with it.

The health zone is the exception and polls at 5s. Those are independent cheap
probes with no event source behind them, and inventing a change-detection tick
to feed a socket would be more moving parts for a readout.

**One process, so no Redis.** This section previously specified Redis pub/sub,
and that is the right answer the moment a second control-plane replica exists.
There is one. Everything that would change is behind `publish` and `subscribe`
in `kavach/api/events.py`. Two bounded limits keep a wedged browser harmless:
a 256-event queue per subscriber, dropped oldest-first for that subscriber
alone, and a 500-event replay buffer.

**Replay, so a late console is not blind.** A socket receives the buffer before
the live stream, and the client de-duplicates on `seq`. Without that, opening
the console mid-incident would show an empty timeline, and a reconnect would
render every stage twice.

#### What the browser deliberately cannot say

`POST /v1/loop/run` takes no action name, no service, no container, no config
key, no threshold and no command string — only an `rca` toggle. There is no
docker route and no proxy to the target. The console reads state and asks for
one pass of the loop; it cannot bypass detection, bypass RCA validation, reach
the Docker socket, or name anything `permit()` will have to authorise.

Two consequences recorded on the wire rather than left to the client:
`RcaOut.confidence_is_calibrated` is always `false`, and
`SystemOut.mode_is_enforced` is always `false`. A second client cannot read the
confidence as a probability, or the mode as a gate, by mistake.

#### No timer, and that is load-bearing

**Nothing invokes the loop on a schedule.** A background detection tick that
healed unattended would need the mode check, and `permit()` does not exist
until P6 (`docs/decisions/0006`, amendment 2026-10-04). So a run happens
because an operator asked for one, from the console or a harness, and the
runner allows one at a time — the narrow stand-in for the A-Lock, since two
concurrent runs would each capture a pre-state and the second inverse would
point at the first run's faulty value.

**This constraint must not be removed before the safety engine lands.** It is
currently the only thing standing between the control plane and unattended
writes.

---

## 5. Database & storage

Single PostgreSQL 16 instance with pgvector. **No TimescaleDB in v1** — see §2.2. Telemetry retention is a scheduled delete, and the two high-volume tables carry a BRIN index on `ts`. If telemetry volume is ever *measured* as a problem, converting these two tables to hypertables is additive and requires no change to any query that goes through `ingestion/`.

```sql
-- Projects and their contract
projects(id, name, root_path, compose_file, compose_project, base_branch,
         mode, status, created_at)
--       ^^^^^^^^^^^^^^ compose_project is the ownership key (§6.3)
--                      base_branch is 'modernize-stack' for this target

slo_contracts(id, project_id, name, expression, comparator, threshold, window_s)
--                                  ^^^^^^^^^^ a PromQL EXPRESSION, not a
--                                  metric name. See §7 and FR-09a.

allowed_actions(id, project_id, action_name, max_risk_tier)
baselines(id, project_id, captured_at, config_hash, prompt_version,
          metrics_json, fast_eval_scores_json, rerank_threshold, is_current)

-- Telemetry (plain tables, BRIN on ts, 7-day retention via a delete job)
-- Column names are KAVACH's internal schema, deliberately decoupled from the
-- gen_ai.* spec (see §2.3). provider was gen_ai.system, is now
-- gen_ai.provider.name, and may change again; semconv_version records which
-- convention revision the row was normalised from.
telemetry_spans(ts, project_id, trace_id, span_id, parent_span_id, name,
                duration_ms, status, provider, endpoint, request_model,
                response_model, input_tokens, output_tokens, finish_reason,
                semconv_version, attributes JSONB)
telemetry_logs(ts, project_id, service, severity, body, attributes JSONB)

-- Verification and evaluation
verification_runs(id, project_id, incident_id NULL, kind, started_at,
                  pass_rate, mean_latency_ms, detail JSONB)
--                               kind ∈ {FAST, FULL}  — FR-07 vs FR-07a
verification_cases(id, run_id, question, answer, checks JSONB, passed)

-- Incidents
incidents(id, project_id, status, fault_class, service, detected_at,
          resolved_at, mttd_s, mttr_s, outcome)
evidence(id, incident_id, kind, source_ref, payload JSONB, collected_at)
diagnoses(id, incident_id, fault_class, confidence, evidence_ids TEXT[],
          rejected_alternatives JSONB, model, prompt_version, created_at)
hypotheses(id, incident_id, rank, description, confidence, tested, outcome)

-- Safety and execution
risk_decisions(id, incident_id, action_name, risk_tier, verdict, reasons JSONB,
               decided_by, typed_decision_frame JSONB,
               shadow_engine, shadow_verdict, shadow_agreed)
--             ^^^^^^^^^^^^^ Laya's independent answer. Recorded, never binding.
actions(id, incident_id, name, params JSONB, inverse_name, inverse_params JSONB,
        pre_state_witness JSONB, undo_stack_position,
        idempotency_key UNIQUE, status, started_at, finished_at, error)
verifications(id, incident_id, action_id, probe, passed, detail JSONB, ran_at)

-- Append-only. No UPDATE, no DELETE. Enforced by a trigger, not convention.
audit_log(id, project_id, incident_id, ts, actor, event, payload JSONB,
          prev_hash, hash)

-- Learning
incident_memory(id, incident_id, summary, embedding vector(768),
                fault_class, repair_action, worked BOOLEAN)
```

**On `audit_log`:** each row carries the hash of the previous row, forming a chain. A reviewer can verify no record was altered. This is cheap to implement and it is exactly the kind of property a panel will ask about.

**On `risk_decisions`:** `decided_by` is always the deterministic rule engine in v1. `shadow_*` records Laya's independent answer and whether it agreed. The `typed_decision_frame` column is the training corpus for a future fine-tune and costs nothing to populate now (`PRD.md` §7.1).

**Redis keyspaces:**
`kavach:idem:{key}` (idempotency, 24h TTL) · `kavach:cb:{project}:{service}:{fault}` (circuit breaker counters) · `kavach:blast:{project}` (rate windows) · `kavach:events` (pub/sub)

Redis is **not started yet**, and was not in Phase 0. Every one of those four keyspaces belongs to a check that does not exist yet — console pub/sub arrives in P4, persisted idempotency keys in P6 (`FR-16`, `FR-17`, `FR-18`, §4.3), and a container nothing connects to is a container whose health tells you nothing.

---

## 6. The safety engine

> **Implementation status, 2026-10-04: §6.1–§6.3 are not built.** There is no
> `safety/` package. The `F06` slice (P2/P3) ships one action that is
> project-scoped and deny-list-safe by construction, which is not the same
> thing as a gate. §6.4 is the part that *is* implemented, and it is a
> narrower thing: it validates a diagnosis, not an action. `permit()` is
> scheduled in `ROADMAP.md` P6 and must land before any second repair action
> or any unattended invocation of the loop.

The single most important component. Its guarantee is **Transactional No-Regression (TNR)**, taken from STRATUS (NeurIPS'25, arXiv:2506.02009). Kavach implements the same three properties against Docker rather than Kubernetes.

### 6.0 TNR — the recoverability guarantee

| Property | Implementation in Kavach |
|---|---|
| **Writer exclusivity (A-Lock)** | A per-project advisory lock in Postgres. The executor acquires it before any mutation and the rollback path acquires the same lock. Execution and rollback can never interleave, and two incidents on one project serialise. Acquired in exactly one place: `safety/writer_lock.py`. The target exposes no competing writer (`PRD.md` §5.3) |
| **Faithful undo** | A per-incident **undo stack**, not a single inverse. Every state-mutating action pushes `(action, inverse, pre_state_witness)` before executing. Abort pops and applies in reverse order. A `pre_state_witness` is the captured prior value — container spec, config hash, prompt blob SHA, previous `RERANK_THRESHOLD`, previous LLM endpoint — so the inverse is deterministic and never asks a model to reconstruct it |
| **No regression** | A scalar severity metric derived from the SLO contract, sampled before and after each action. If severity increases, the stack unwinds immediately rather than waiting for the full verification window (§4.2) |

The ablation in the STRATUS paper is the reason this is non-negotiable: on AIOpsLab's 13 mitigation problems, naive retry without undo scores 23.1% against 69.2% with TNR. The undo mechanism is worth roughly 3× on mitigation success — more than any model choice in this stack.

**Implemented today:** the faithful-undo property, per action rather than per
incident. `executor/config_rollback.py` captures the pre-state witness in
`prepare()` and refuses to construct a rollback when no known-good baseline
was captured, so an action with nothing to invert to cannot exist. **Not
implemented:** the A-Lock (no `safety/writer_lock.py`, and nothing yet runs
two incidents concurrently), the undo stack as a structure, and the
no-regression early abort. All three are P6, and the stack matters from the
second action onward.

Two design notes that follow directly:

- **`executor/base.py` must make an action without an inverse unrepresentable**, enforced at registration time. An abstract `inverse()` with no implementation should fail to register, not fail at 3 a.m.
- **The inverse is deterministic data, never a model call.** This is the same conclusion `EvoUndo` reaches: asking an LLM to undo its own action hallucinates or produces incomplete inverses. Capture the pre-state witness; do not re-derive it.

### 6.1 The permit gate

It has one public entry point:

```python
def permit(action: Action, project: Project, incident: Incident) -> Verdict
```

`Verdict` is `ALLOW_AUTO | REQUIRE_SANDBOX | REQUIRE_APPROVAL | DENY`, always with a list of reasons.

Evaluation order — **every check must pass; the first failure short-circuits to DENY or escalation.** None of these ten steps is implemented yet; see the note at the head of §6.


1. **Project ownership.** Does the action's target resolve to a container belonging to this project's compose project and to a declared service? No → `DENY`. See §6.3. This check runs first because it is the one that prevents Kavach touching something it was never onboarded against.
2. **Deny-list.** Is this a forbidden mutation — data deletion, database drop, scale-to-zero, migration, or an `EMBED_MODEL` change (`FR-30`)? Yes → `DENY`, unconditionally, in every mode.
3. **Allow-list.** Is `action.name` in `allowed_actions` for this project? Not listed → `DENY`. The default allow-list is empty and code must not add defaults.
4. **Inverse exists.** Does the action declare a working inverse? No → `REQUIRE_APPROVAL` at best, never auto.
5. **Unknown-failure gate.** Is the driving diagnosis `UNKNOWN`? Yes → never auto, never sandbox-and-execute; route to the unknown flow (`FR-29`, `PRD.md` §8.4).
6. **Confidence.** Is the driving diagnosis above the project threshold? No → `REQUIRE_APPROVAL`. *Implemented today in the RCA gate instead (§6.4, rule 4), because `permit()` does not exist; it moves here when it does. Note the current semantics are stricter than this step: a below-threshold diagnosis is rejected outright rather than routed to approval, since there is no approval path yet.*
7. **Risk tier.** From the deterministic rule table (§6.2), keyed on `(action_name, target_kind, reversibility, data_touching)`.
8. **Blast radius.** ≤ 3 actions this incident, ≤ 5 incidents this hour → else `DENY` and halt automation.
9. **Circuit breaker.** `(service, fault_class)` healed ≤ 3 times in 30 min → else `DENY` and halt automation for that pair.
10. **Mode policy.** `SIMULATION` → never execute, always produce a plan and a dry-run diff. `APPROVAL` → everything to a human. `AUTONOMOUS` → LOW auto, MEDIUM to sandbox-then-approval, HIGH to human (`PRD.md` §5.4).

Every call writes a `risk_decisions` row including a `typed_decision_frame` — the compressed, Laya-shaped version of the decision (`which repair`, `what risk`, `execute automatically?`). When the Laya shadow engine is running (P7), its independent answer and the agreement flag land in the same row. **The shadow answer is never read by this function.**

### 6.2 Risk tier table (v1, deterministic)

Five actions. Everything else is HIGH by default-deny posture.

| Action | Tier | Reasoning | Inverse |
|---|---|---|---|
| `switch_llm_endpoint` | LOW | Config-only, instantly reversible, no data touched | Restore the previous endpoint from the witness |
| `restart_container` | LOW | Reversible by definition; no persistent state in the affected services | Container was running; restore prior state |
| `raise_memory_limit` | LOW | Additive, one step, capped | Restore the previous limit from the container spec witness |
| `rollback_prompt` | MEDIUM | Changes application behaviour; reversible via git | Restore the prompt blob SHA from the witness |
| `rollback_config` | MEDIUM | Changes application behaviour; reversible via git + the config interface | Restore the previous config values from the witness |
| anything else | HIGH | Default-deny posture | — |

**Removed from the previous draft**, with reasons recorded in `PRD.md` §6.2: `flush_cache` (no cache exists; `F04` retired), `rebuild_index` (no vector index and no snapshot mechanism), `scale_replicas_up` (the target binds host port `8000:8000`; a replica cannot start), `retry_request` (no hook in the target's request path). `switch_model` is renamed `switch_llm_endpoint` because it switches an endpoint, not a provider (`PRD.md` §6.3).

### 6.3 Docker safety — project ownership

The docker socket mount is the most dangerous privilege in this system. An action that names a container is an action that could name *any* container on the host, including the control plane's own Postgres. Ownership verification is therefore a precondition, not a courtesy.

**Every Docker mutation follows this sequence, in this order, with no step skippable:**

```
1. verify project identity      container label com.docker.compose.project
                                == projects.compose_project
2. verify service identity      container label com.docker.compose.service
                                ∈ the services declared in kavach.yaml
3. verify action allow-listed   action_name ∈ allowed_actions (and not deny-listed)
4. verify compose membership    the container is in the approved compose project's
                                current container set, re-resolved now, not cached
5. verify inverse exists        action.inverse() is registered and constructible
6. record pre-state witness     container spec / config / blob SHA, as data
7. acquire writer lock          the per-project A-Lock (§6.0)
8. execute                      the adapter, with an idempotency key
9. verify                       fast verification (FR-07)
10. rollback when required      unwind the undo stack in reverse (§6.0)
```

Steps 1, 2 and 4 are new in this revision and implement `FR-26`. They are enforced in `safety/ownership.py` and called from `permit()` step 1, **not** inside the docker adapter — the adapter must never be the only thing standing between a typo and a wrong container.

Two supporting rules:

- **`executor/adapters/docker.py` is the only module in the repository that imports the docker SDK.** Enforced by a lint rule, not by convention.
- **No arbitrary execution, ever** (`FR-27`). There is no `exec` adapter, no shell adapter, no "run this command" parameter on any action. Every action is a named, registered adapter with a typed Pydantic parameter model. If a repair cannot be expressed as one, it is not in the catalogue.

---

### 6.4 The RCA validation gate — implemented in P3, `F06` only

`permit()` above is the full safety engine and does not exist yet (`ROADMAP.md`
P6). What **does** exist is the gate between the LLM and the executor, in
`kavach/rca/`. It is a separate, narrower thing and the distinction matters: the
RCA gate decides whether a *diagnosis* may drive the one implemented repair.
`permit()` decides whether an *action* may run at all. When `permit()` lands,
the RCA gate stays — a diagnosis still has to be validated before it becomes a
proposal — and the confidence check migrates into `permit()`'s step ordering
(`FR-12`), where the specification always put it.

#### The pipeline

```
evidence normalisation ─▶ LLM (schema-constrained) ─▶ Pydantic validation
  ─▶ deterministic validation gate ─▶ the existing rollback_config action
  ─▶ the existing fast verification
```

#### The LLM executes nothing

The model may name a fault class, a service, a confidence, cited evidence IDs
and **one candidate repair from a closed vocabulary**. It has no path to the
executor, no free-text field that anything downstream reads as an instruction,
and no way to name an action with no implementation or no inverse. `reasoning`
exists for a human to audit; nothing branches on it.

RCA never widens what can run. Deterministic detection must still find the
fault, the repair is still the same single action with the same recorded
inverse, and verification is unchanged. RCA adds a gate and an explanation.

**A rejected diagnosis escalates.** It does not fall back to the deterministic
plan — a gate whose refusal can be ignored is decorative.

#### Schema-constrained output, not text parsing

`kavach/llm/client.py` sends Ollama's `format` field a **JSON Schema generated
from the Pydantic model** (`rca/schema.py`), so the constraint the decoder
enforces and the constraint validation enforces cannot drift apart. Output is
validated again on receipt, because a constrained decoder is a strong guarantee
and not a proof. Temperature 0 and a fixed seed: a diagnosis that changes
between identical inputs is not a diagnosis.

The schema offers the **full** catalogue — the eight classes plus `UNKNOWN` and
`INSUFFICIENT_EVIDENCE`, and no `F04` — even though only `F06` is implemented. A
model given one option always picks it, which would make both the diagnosis and
the gate meaningless.

`evidence_ids` is **required with a minimum of two**. It was optional at first,
and a real `llama3.2` run cited IDs inside the prose `reasoning` field while
leaving the array empty, twice, with every other field correct. A constrained
decoder is free to skip an optional field and prompting does not reliably fix
that; the requirement belongs in the grammar.

The client also **asserts it is not pointed at Toxiproxy** (`PRD.md` §6.3).
Kavach's own model path must survive a fault injected into the target's.

#### Evidence normalisation

`kavach/rca/evidence.py` builds a frame of ~33 items, each with a stable citable
ID, an observed value and **the healthy expectation** — never a verdict, so the
model is not asked to ratify a conclusion Kavach already reached.

| IDs | Kind |
|---|---|
| `EV-M01`–`EV-M09` | Metrics: retrieval similarity, kept chunks, empty-context ratio, corpus size, LLM error ratio and latency, DB pool, chat errors |
| `EV-S01` / `EV-S02` | Service identity, and the declared service set |
| `EV-C01`–`EV-C08` | Live config values, config hash, prompt file hashes |
| `EV-B01` | The captured known-good `rerank_threshold` |
| `EV-V00`–`EV-V03` | Fast-set overall result, plus one item per case |
| `EV-H01` | Health |
| `EV-L01`… | Recent backend log lines |

Two deliberate exclusions. **User content is filtered out of the log lines**
(`FR-28`): token counts are telemetry, question text is not. And Kavach's own
interpretation is excluded, for the reason above.

A missing signal is rendered as `None` and the prompt states that **no data is
not zero and not healthy**. Silently treating an absent series as `0` is how a
blind detector reports health.

#### The ten rules, all fail-closed

Evaluated in `kavach/rca/validate.py`, a pure function — nothing in it calls a
model, so the same diagnosis against the same evidence always produces the same
verdict.

| # | Rule | Rejects when |
|---|---|---|
| 1 | `schema_valid` | output missing, unparseable, or failing Pydantic |
| 2 | `actionable_claim` | `UNKNOWN` / `INSUFFICIENT_EVIDENCE` — honest non-answers, never executed (`FR-11`, `FR-29`) |
| 3 | `fault_class_supported` | the class has no implementation in this slice |
| 4 | `confidence_threshold` | below the manifest's `confidence_threshold` (`FR-12`) |
| 5 | `citations_resolve` | a cited ID resolves to nothing, or fewer than two cited (`FR-10`) |
| 6 | `service_declared` | the service is not one the manifest declares |
| 7 | `repair_permitted` | the proposed repair is not the permitted one for that class |
| 8 | `deterministic_agreement` | **the deterministic detector disagrees** on class or service, or did not detect at all |
| 9 | `baseline_available` | no captured known-good value to roll back *to* |
| 10 | `corpus_intact` | corpus size unknown or zero — then a config rollback is the wrong repair |

**Any rule that cannot be evaluated rejects.** There is no path where
uncertainty permits action. The engine never raises either: a transport failure
or a timeout is a rejection, not an exception thrown inside the healing path.

#### Rule 8 is the one that matters

**The deterministic detector remains authoritative on whether the conditions
for a fault actually hold.** The LLM's contribution is a cited, explained
diagnosis — not permission to act. If the model claims `F06` while independent
deterministic evidence says otherwise, the claim is rejected.

That is the whole defence against the failure mode this project is about:
SREGym found mitigation succeeds **22–62% of the time even when the diagnosis is
wrong**, because agents pattern-match a symptom to a fix that happens to work. A
confident wrong diagnosis passed straight to a repair is exactly how that
happens. Requiring agreement with independent evidence means a
plausible-but-wrong diagnosis cannot drive a write.

A corollary worth stating: because detection gates RCA, **a healthy system
never reaches the model**. There is no token cost, and no opportunity for a
model to invent an incident.

#### Confidence is not calibrated

**`confidence` is a raw model output, not a calibrated probability.** No
reliability diagram has been produced, no ECE has been measured, and nothing has
been fitted against observed correctness. Observed behaviour is a flat `0.90`
across repetitions, and `1.0` on an earlier run.

So `0.90` must **not** be described, in the console or the report, as "90%
likely to be correct". The manifest's `confidence_threshold` is therefore a
**floor that blocks obviously unconfident output**, not a probabilistic decision
boundary — and the gate's actual strength comes from rule 8, which does not read
the confidence number at all.

Calibration is future work. The Laya temperature refit (`ROADMAP.md` P7, §2.1)
is where ECE gets measured before and after, and that is the first point at
which a confidence number may be reported as a probability.

#### Current scope

`SUPPORTED_FAULT_CLASSES` is `{F06}` and `PERMITTED_REPAIR` is
`{F06: rollback_config}`. Every other catalogue class is a legitimate thing for
the model to **say** and an illegitimate thing to act on, so a correct
non-`F06` diagnosis is accepted as output and rejected as authority. Both
constants widen one fault class at a time, in P5, each with its own rejection
tests.

---

## 7. The onboarding manifest

`kavach.yaml` lives in the target project's repo and is the contract. Values below are the real ones for `Simple_RAG-Pipeline`.

```yaml
apiVersion: kavach/v1

project:
  name: simple-rag
  compose_file: ./docker-compose.yml
  compose_project: target_rag-app      # the ownership key, §6.3
  git:
    base_branch: modernize-stack       # NOT main — this is where the code lives
    ops_branch: kavach/ops
    push: false                        # Kavach never pushes. Not configurable to true.

services:
  backend:
    health: http://backend:8000/healthz
    role: application
  db:
    health: tcp://db:5432
    role: vector_store
  ollama:
    health: http://ollama:11434/api/tags
    role: model_server
  frontend:
    health: http://frontend:3000/
    role: ui
  toxiproxy:
    health: http://toxiproxy:8474/version
    role: fault_injection

llm_paths:                             # PRD §6.3 — one Ollama, two paths
  primary: http://toxiproxy:21434      # faulted by F01/F02
  backup:  http://toxiproxy:21435      # never faulted
  control_plane: http://ollama:11434   # Kavach's own calls, direct

# SLO contracts are PromQL EXPRESSIONS, evaluated by the detection engine.
# These are the metrics the target actually exposes (§4.1). No invented
# metric names, no fake `quantile` labels on a histogram.
slo:
  - name: chat_latency_p95
    expression: |
      histogram_quantile(0.95,
        sum by (le) (rate(http_request_duration_seconds_bucket{handler="/v1/chat"}[2m])))
    comparator: "<"
    threshold: 2.0
    window_s: 120

  - name: chat_error_ratio
    expression: |
      sum(rate(http_requests_total{handler="/v1/chat",status=~"5.."}[2m]))
        / clamp_min(sum(rate(http_requests_total{handler="/v1/chat"}[2m])), 1e-9)
    comparator: "<"
    threshold: 0.01
    window_s: 120

  - name: llm_error_ratio                      # F01
    expression: |
      sum(rate(ragapp_llm_requests_total{outcome="error"}[1m]))
        / clamp_min(sum(rate(ragapp_llm_requests_total[1m])), 1e-9)
    comparator: "<"
    threshold: 0.20
    window_s: 60

  - name: retrieval_similarity_p50             # F06
    expression: |
      histogram_quantile(0.50,
        sum by (le) (rate(ragapp_retrieval_top_similarity_bucket[5m])))
    comparator: ">="
    threshold: 0.45
    window_s: 300

  - name: tokens_per_request                   # F09
    expression: |
      sum(rate(ragapp_llm_tokens_total[5m]))
        / clamp_min(sum(rate(ragapp_llm_requests_total[5m])), 1e-9)
    comparator: "<"
    threshold: 1200
    window_s: 300

  - name: fast_eval_pass_rate                  # F06, F07 — emitted by Kavach
    expression: kavach_fast_eval_pass_rate{project="simple-rag"}
    comparator: ">="
    threshold: 0.85
    window_s: 300

verification:
  fast:                                # FR-07 — the live recovery probe
    # The case set lives in KAVACH, not here (PRD §13): it must be
    # deterministic, local, and independent of the target's RAGAS harness.
    # This key names it; it is not a path inside the target repo.
    set: kavach/verification/fast_set.yaml   # EXACTLY 3, run serially
    max_duration_s: 120                # serial, never concurrent
  full:                                # FR-07a — research only, never in the loop
    runner: evaluation/evaluate.py     # the target's 40-case RAGAS harness
    schedule_s: 0                      # 0 = on demand only

versioned_paths:
  prompts: ./prompts                   # PRD §5.2 addition 6
  config: ./kavach/config.yaml

allowed_actions:        # default is EMPTY. Nothing here, nothing executes.
  - switch_llm_endpoint
  - restart_container
  - raise_memory_limit
  - rollback_prompt
  - rollback_config

denied_mutations:       # FR-30. Not overridable by allowed_actions.
  - embed_model_change
  - data_delete
  - database_drop
  - scale_to_zero
  - migration

mode: SIMULATION        # SIMULATION | APPROVAL | AUTONOMOUS
                        # Omitting this key means SIMULATION. PRD §5.4.
confidence_threshold: 0.75
```

### 7.1 What Kavach adds to the target

The complete, closed list is `PRD.md` §5.2. Restated here as the interfaces the architecture depends on:

| Addition | Interface it creates |
|---|---|
| OTel SDK + instrumentation | The spans and metrics in §4.1 |
| `GET /healthz` | Verification probe 1; preflight health check. Checks Postgres and Ollama, not just liveness |
| Config interface | §7.2 below |
| Token usage capture | `ragapp_llm_tokens_total` |
| `prompts/*.txt`, loaded per request | `rollback_prompt` without a container rebuild |
| `CHAOS_ENABLED`, default `false` | Removes 10–150ms of random noise from every latency baseline |
| Toxiproxy, two listeners | `F01`/`F02` injection, scoped to the primary path |
| Compose healthchecks | Preflight; `F03` detection |

### 7.2 The target's config interface

The narrowest possible control surface. One module in the target, no reasoning, no orchestration — it reads and writes a whitelist of runtime values.

```
GET  /v1/admin/config   → current values + config_hash   (pre-state witness)
PUT  /v1/admin/config   → set whitelisted keys
```

| Key | Serves | Settable |
|---|---|---|
| `llm_base_url` | `switch_llm_endpoint` (`F01`, `F02`) | yes |
| `llm_model` | `rollback_config` (`F08`) | yes |
| `rerank_threshold` | `rollback_config` (`F06`) | yes |
| `max_tokens` | `F09` clamp | yes |
| `chaos_enabled` | injection control | yes |
| **`embed_model`** | — | **NO. Permanently denied** (`FR-30`) |
| `db_*` | — | **NO** |

Authentication is a shared token in `KAVACH_ADMIN_TOKEN`. The route is unauthenticated-by-default-impossible: absent the token, it returns 401 and changes nothing.

**`embed_model` is the important exclusion.** The target's `backend/db.py` infers vector dimension from the embed-model name and runs `DROP TABLE document_chunks CASCADE` on mismatch. An `EMBED_MODEL` change therefore destroys the corpus. It is denied at the config interface *and* on Kavach's deny-list (§6.1 step 2) — two independent barriers, because one typo should not be able to delete the data the whole application exists to serve.

---

## 8. Fault injection harness

Lives outside the control plane so it can never leak into production code paths.

```
make inject FAULT=F01              # single injection against the onboarded target
make scenario NAME=demo-full       # scripted sequence for the review
make bench                         # 7 × 5 reps = 35, emits the metrics table
```

**Seven injectors for eight classes.** There is no `F04` (`PRD.md` §6.1), and `F03`'s injector is deferred (`PRD.md` §6.4).

| ID | Injector mechanism | Revert |
|---|---|---|
| `F01` | Toxiproxy `down` toxic on **listener A only** | Remove the toxic |
| `F02` | Toxiproxy `latency` toxic on **listener A only** | Remove the toxic |
| `F03` | **Deferred — no injector in v1** (`PRD.md` §6.4) | — |
| `F05` | Open and hold 10 Postgres connections, exhausting `SimpleConnectionPool(1, 10)` | Close the holder connections |
| `F06` | Raise `rerank_threshold` via the config interface (§7.2) | Restore the prior threshold |
| `F07` | Commit a degraded prompt to `prompts/answer.txt` on an incident branch | `git checkout` the prior blob |
| `F08` | Set `llm_model` to a nonexistent model via the config interface | Restore the prior value |
| `F09` | Commit a prompt that triples output length | `git checkout` the prior blob |

Each injector exposes `inject()`, `revert()` and `is_active()`, and `revert()` runs in the test teardown regardless of outcome so a failed run never leaves the stack broken.

**`F06` is the first vertical slice** (`ROADMAP.md` P2, with the LLM RCA layer in P3) because it works against the target as it stands, with no new infrastructure, and it produces the silent HTTP-200-with-no-useful-answer failure that `PRD.md` §2 is built on. Its repair is a config rollback, not an index rebuild; the target has no vector index, and inventing one would be building a feature in order to have something to fix. Index snapshot and rebuild are recorded as future scope (`PRD.md` §6.2).

**`F03` is deferred, and the reason is a design constraint, not laziness.** The target's compose sets `restart: always` on `backend`, so Docker restarts a killed container within seconds and wins the race against a 15s detection tick. Removing `restart: always` would make `F03` injectable by *weakening the target's existing resilience to manufacture a failure* — which is forbidden. The honest version is a memory limit low enough that the process OOMs again on every boot, producing a genuine crash-loop Docker cannot resolve; that is empirical work and is not scheduled. See `PRD.md` §6.4. **Do not write a placeholder `F03` injector.**

---

## 9. External services

| Service | Required? | Fallback |
|---|---|---|
| Ollama (local, the target's) | Yes, default | Any OpenAI-compatible endpoint via `KAVACH_LLM_BASE_URL` |
| Hosted LLM API | No | — |
| Docker daemon | Yes | None. Hard dependency |
| Git | Yes, for the target repo | None. Preflight blocks without it |
| Hosted telemetry SaaS | **No** | The target's Traceway export stays env-gated and disabled |
| Cloud embedding API | **No** | `PL-02`. The target's RAGAS evaluator needs `GEMINI_API_KEY` and is therefore not in any v1 path; the research evaluator must offer a local scoring option |

No third-party SaaS. No network egress required. This is deliberate: it makes the demo work on conference wifi and it keeps the project reviewable offline.

---

## 10. Deployment

Two compose projects, two networks, bridged where telemetry, the docker socket, and the shared Ollama cross.

```bash
make target-up   # the SUM: Simple_RAG-Pipeline, from its own repo
make up          # control plane: api, console, postgres+pgvector,
                 #                prometheus, otel-collector
                 # NOTE: no Ollama here, and no second Prometheus (§2.4).
                 # Redis joins this list in P4 — see §5.
make onboard     # preflight + baseline capture against the target
make demo        # scripted injection sequence
```

**`make up` is the one API.** It builds and publishes the control-plane API on
`API_PORT` (8080). `make dev-api` is a hot-reload copy of the *same* app and
runs on `DEV_API_PORT` (8081) — deliberately not 8080, because Docker Desktop on
Windows does not exclusively reserve a published port: a local uvicorn binds
8080 alongside the container without any error and silently shadows it for
`127.0.0.1` traffic while `localhost` still resolves to the container. Two
different builds answering one port, no warning. A separate port makes the
distinction visible instead.

**Compose is invoked with `--env-file .env`, and that flag is load-bearing.**
Compose reads `.env` from the *compose file's* directory, so the repo-root
`.env` was inert and every `${VAR}` silently fell back to its default — which
looked correct only because every variable had one. `make setup` creates `.env`
from `.env.example`, and never overwrites an existing one.

**The container cannot derive the repository root.** The package sits at
`/app/kavach` with no repository above it, so compose sets `KAVACH_KAVACH_ROOT=/app`
and mounts `harness/baselines` read-only. The target is reached through
`host.docker.internal`, because `localhost` inside the control-plane container
is the control plane.

The control plane mounts the docker socket read-write — this is the executor's only route to the target, and it is the single most dangerous privilege in the system. It is why project ownership (§6.3) and the deny-list run before the allow-list in `permit()`, and why `SIMULATION` is the default mode for every project (`PRD.md` §5.4).

**Platform note (`PL-03`).** The demo machine is Windows 11 with Docker Desktop. Docker socket semantics, `host.docker.internal` resolution, and the target's unconditional `deploy.resources.reservations.devices` nvidia block all behave differently there than on Linux. Phase 0 validates the socket mount and container control on the actual demo machine; this is not deferred to the phase that first needs it.

---

## 11. Scalability notes

Not needed for v1, recorded so the design does not foreclose it.

- **Multiple projects:** the graph is per-incident and stateless between runs; LangGraph's Postgres checkpointer already supports concurrent runs. Scaling means more workers, not more code. The writer lock is per-project, so projects never block each other.
- **Kubernetes:** `RuntimeAdapter` is the seam. A `K8sAdapter` implements the same `restart`, `get_state`, `set_limit` methods against the API server, and `safety/ownership.py` gains a namespace/label check alongside the compose-project check. No change to the graph, safety engine or console. This is **out of scope for v1** (`PRD.md` §11), and the target's existing `k8s/` manifests are not a head start on it — they are unused.
- **Telemetry volume:** plain Postgres with BRIN on `ts` and a 7-day delete job. If this is ever *measured* as a bottleneck, TimescaleDB hypertables are a drop-in for the two telemetry tables, then ClickHouse. Not before it is measured (§2.2).
- **LLM throughput:** RCA runs once per incident, not per request. Even a slow local model is fine. If it is not, the structured-output classification task fits a much smaller model.
- **The learning layer:** pgvector with an HNSW index handles hundreds of thousands of incidents on one node. This will never be the limit for this project.

---

## 12. Observing Kavach itself

The control plane is instrumented with the same OTel SDK it consumes from, and exports to the same collector. If the healing platform is the thing that breaks, it should be visible. This also gives the demo a nice property: the console can show Kavach's own health next to the project's.

---

## 13. Git isolation model

**Both repositories use a `kavach/ops` branch, for different reasons.**

| Repo | `main` | `kavach/ops` |
|---|---|---|
| **Target** (`Simple_RAG-Pipeline`) | Never modified. `FR-05` | Every Kavach-authored change to the target. Branched from `modernize-stack` |
| **Kavach** (this repo) | Holds accepted, reviewed work only | Active development lands here first |

The rest of this section is about the target, where the rule is a *safety* property. In Kavach's own repo it is a *review* convention: work is committed to `kavach/ops` and `main` moves only when the work is accepted. An earlier session committed Kavach work straight to `main` because this section described `kavach/ops` as a target-only concept; that is why it is stated explicitly here.

`FR-05` in one diagram. The target is a repository with two remotes, one of which belongs to a teammate, so "never push" is a safety property and not a style preference.

```
origin  → SwarajShedge27/Simple_RAG-Pipeline   ← a teammate's repo. NEVER pushed to.
fork    → NotArsal/Simple_RAG-Pipeline         ← the owner's fork.  NEVER pushed to.

main                      ← NEVER modified, NEVER checked out for a write
  │
  └── modernize-stack     ← the base branch. The working code lives here.
        │                    Kavach reads it. Kavach never commits to it.
        │
        └── kavach/ops    ← created by Kavach, from modernize-stack.
              │              Every Kavach-authored change lands here.
              │
              └── kavach/incident/{incident_id}
                             ← only when an incident needs an isolated
                               sequence of commits. Derived from kavach/ops,
                               never from main or modernize-stack.
```

Rules, enforced in `executor/adapters/git.py` and tested with deny cases:

| Rule | Enforcement |
|---|---|
| Never modify `main` | The adapter refuses any write when `HEAD` resolves to `main` |
| Never modify the user's working branch | Kavach checks out `kavach/ops`; it never commits to whatever branch it found |
| `kavach/ops` branches from `base_branch` (`modernize-stack`) | Created at onboarding, recorded in `projects.base_branch` |
| **Never push to any remote** | No `git push` code path exists. `kavach.yaml`'s `git.push: false` is documentation of a property, not a toggle |
| Never `commit --amend`, never force-push, never rewrite history | The audit trail and the undo stack both depend on commits being append-only |
| Never commit a secret | `.env`-shaped paths are refused; the target's `.gitignore` already excludes `.env*` and no `.env` is tracked |
| Capture pre-state before every mutation | The blob SHA of every file about to change is the `pre_state_witness` (§6.0) |
| Incident branches only when needed | Default is a commit on `kavach/ops`. An incident branch is for multi-commit sequences that may need unwinding as a unit |

**Preflight verifies before enabling:** the repo exists, the worktree is clean, `base_branch` exists, `kavach/ops` can be created from it, and `HEAD` is not `main`.
