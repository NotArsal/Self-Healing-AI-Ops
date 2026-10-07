# ARCHITECTURE.md — Kavach

> How it is built. Read `PRD.md` §5 (locked scope) and `CONTRACT.md` first.

---

## 1. System overview

Kavach is a **control plane** acting on a separate **target** — an onboarded AI application. They never share a process, a network namespace, or a database. Two paths connect them: telemetry in, allow-listed actions out.

```
         ONBOARDING  (a precondition, not a loop phase)
         preflight P01–P13 → conformance level → baseline → ARMED
                                 │
┌────────────────────────────────┼─────────────────────────────────┐
│  TARGET: one onboarded compose application                       │
│  api · vector store · cache · model primary · model backup       │
└────────────────┬───────────────────────────────▲─────────────────┘
       OTLP/Prom │                               │ allow-listed actions
                 ▼                               │ (writer lock held)
          ┌──────────────┐                       │
          │  DETECTION   │ objective breach · anomaly · eval drop
          └──────┬───────┘                       │
                 ▼                               │
          ┌──────────────┐                       │
          │   EVIDENCE   │ spans·logs·state·git·evals·similar past
          └──────┬───────┘                       │
                 ▼                               │
          ┌──────────────┐                       │
          │     RCA      │ class + confidence + CITED evidence      │
          │              │ may return INSUFFICIENT_EVIDENCE         │
          └──────┬───────┘                       │
                 ▼                               │
          ┌──────────────┐                       │
          │     PLAN     │ action + INVERSE + pre-state witness     │
          └──────┬───────┘                       │
                 ▼                               │
     ╔═══════════════════════╗                   │
     ║   SAFETY GATE         ║ allow-list FIRST, deny by default    │
     ║   CAN SAY NO          ║ inverse? confidence? blast? breaker? │
     ╚═══╦═══════╦═══════════╝                   │
         ║       ║        ╚═══ DENY ──────────► ESCALATE
    LOW  ║  MED  ║  HIGH                         │
         ║       ║         ╚═► HUMAN APPROVAL ═╗ │
         ║       ╚═► SANDBOX ═► APPROVAL ══════╣ │
         ╚═══════════════════════════════════════╣
                                                 ▼
                                      ┌─────────────────────┐
                                      │  EXECUTE            │
                                      │  push inverse onto  │
                                      │  undo stack FIRST   │
                                      └──────────┬──────────┘
                                                 ▼
                                      ┌─────────────────────┐
                                      │  VERIFY — 3 probes  │
                                      │  health             │
                                      │  objectives         │
                                      │  GOLDEN-SET EVAL ◀──┼── the AI part
                                      │  → DELTA PER        │
                                      │    OBJECTIVE        │
                                      └─────┬──────────┬────┘
                                       PASS │          │ FAIL
                                            │          ▼
                                            │   ┌──────────────┐
                                            │   │ UNWIND STACK │ first,
                                            │   │ verify undo  │ before
                                            │   └──────┬───────┘ analysis
                                            │          ▼
                                            │   ESCALATED or
                                            │   UNRECOVERABLE
                                            ▼          │
                             ┌──────────────────────┐  │
                             │ RESOLVED             │  │
                             │   or                 │  │
                             │ MITIGATED + DEBT ────┼──┼──► debt checker
                             └──────────┬───────────┘  │     (repays later)
                                        ▼              ▼
                             ┌─────────────────────────────┐
                             │ AUDIT — append-only,        │
                             │ hash-chained                │
                             └──────────┬──────────────────┘
                                        ▼
                             ┌─────────────────────────────┐
                             │ LEARN — successes AND       │
                             │ failures                    │
                             └──────────┬──────────────────┘
                                        ▼
                             KNOWLEDGE BASE ──┐
                                        ▲     │
                                        └─────┘
                                  back into EVIDENCE
```

### 1.1 Four properties of this flow that are easy to get wrong

1. **The gate can refuse.** Scoring and permission are different operations. A ranking function that produces confidence and risk can never say *no*; the allow-list, blast radius and circuit breaker are a separate deny-by-default gate that runs regardless of how good the score is.
2. **Risk routes; the sandbox is not on the critical path.** A crash-looping container should not wait for a stack clone. Routing by tier is also what makes the sandbox cuttable without killing the loop.
3. **Verification failure unwinds before it analyses.** Analysis is what you do once the system is safe, never instead of making it safe.
4. **The knowledge base feeds evidence collection.** A knowledge base that only writes is a log.

### 1.2 Component responsibilities

| Component | Owns | Does not own |
|---|---|---|
| Ingestion | OTLP receipt, GenAI normalisation, telemetry writes | Any decision |
| Eval runner | Golden set, four scorers | Any decision |
| Detection | Objectives vs. live signal; raising incidents | Diagnosing |
| Catalogue | Interpreting declarative fault definitions | Executing |
| Graph | The incident state machine | Direct side effects |
| Safety gate | Permission: allow-list, tier, blast radius, breaker, mode | Choosing the repair |
| TNR | Writer lock, undo stack, no-regression | Choosing anything |
| Executor | **The only component with side effects** | Deciding whether to act |
| Verification | Probes, delta vector, outcome classification | Acting on the result |
| Debt | Tracking, trigger evaluation, repayment proposal | Executing repayment |

The separation that matters: **the graph decides, the gate permits, the executor acts.** No component does two.

---

## 2. Tech stack

### 2.1 Chosen

| Layer | Choice | Why |
|---|---|---|
| Control plane | Python 3.12 | Agent ecosystem, OTel maturity, team familiarity |
| API | FastAPI + Uvicorn | Async, OpenAPI for free, native OTel |
| Orchestration | **LangGraph** | The loop is a cyclic state machine with conditional edges and interrupts. `PostgresSaver` gives durable incident state; `interrupt()`/`Command` give the approval pause for free |
| LLM (default) | Ollama, `qwen2.5:7b-instruct` | Local, no key, adequate for closed-set classification over nine classes |
| Decision model (shadow) | **Laya** `laya-typed-decisions` via `laya-serve` sidecar | Apache-2.0, local, ~33ms, already fine-tuned on agent-trace observability and security incidents. Shadow only — see `PRD.md` §8.2 for its three defects |
| Database | PostgreSQL 16 + pgvector + TimescaleDB | One database: relational for incidents, hypertables for telemetry, vectors for the knowledge base |
| Cache/queue | Redis 7 | Cache, rate limits, idempotency, pub/sub for the console |
| Metrics | Prometheus | Scrapes target and control plane; detection queries it with PromQL |
| Telemetry | OpenTelemetry Collector | Fan-out point. See §2.3 — the GenAI conventions are **not** stable |
| Frontend | Next.js 15, TypeScript, Tailwind v4, shadcn/ui | See `DESIGN_SYSTEM.md` |
| Charts | Recharts | Composable, token-friendly, no canvas |
| Validation | Pydantic v2 everywhere, including LLM outputs | |
| Python tooling | uv, ruff, mypy --strict, pytest | |
| JS tooling | pnpm, eslint, prettier, vitest, playwright | |
| Runtime control | docker SDK for Python | |
| Fault injection | Custom harness + Toxiproxy | Deterministic network latency and failure for `F01`/`F02` |
| Documentation evidence | **Context7**, cached in Postgres | Current library docs for config-shaped faults. Optional, non-fatal, off the LOW-risk path — see §4.4 |

### 2.2 Explicitly rejected

| Rejected | Why |
|---|---|
| **MongoDB** | Nothing in the data model needs a document store. One less container, driver and backup story |
| **LangChain / CrewAI beside LangGraph** | Three agent frameworks for one agent. LangGraph alone; call the LLM client directly for single-shot work |
| **PyTorch and TensorFlow** | v1 anomaly detection is rolling z-score, EWMA and Page-Hinkley via numpy/scipy. Two deep-learning frameworks to compute a z-score is the definition of over-engineering. Separately, `transformers` probes for TF at import and its abseil runtime deadlocks `laya.load()` |
| **Kubernetes** | Out of scope. The `RuntimeAdapter` interface is the seam; a k8s adapter is additive |
| **Canary traffic splitting** | Needs replicas and a router that compose does not provide. v1 ships staged verification instead (§8). Returns with the k8s adapter |
| **A Rust executor** | A second language and toolchain for a component that mostly calls the Docker API. Revisit only if execution latency is measured as a problem, which `PRD.md` §10.8 says it will not be |
| **Self-hosted Langfuse / Phoenix** | A heavy container to be a trace viewer. If one is wanted, add an exporter to the collector — one config block, zero code |
| ~~**Grafana**~~ | **Reversed, scoped.** Included in the observability profile purely as the viewer for Loki and Tempo, which have no UI of their own. It is a *linked-to* tool, never a second operations dashboard — the console remains the only place incidents are managed |
| ~~**Loki and Tempo**~~ | **Reversed — now included, scoped.** See §2.4. Rejected as a *query layer*; accepted as a *human-facing view* behind an optional compose profile |
| **Loki/Tempo as Kavach's query layer** | Detection and evidence collection read Postgres. Moving them to LogQL/TraceQL rewrites ingestion and evidence collection, and makes the healing loop depend on two more services being healthy. Postgres remains the source of truth for everything Kavach reasons over |
| **GitHub PR-based remediation** | Kavach commits to a dedicated `kavach/ops` branch. A PR flow is a different product with a different approval model; adding it would mean two remediation paths with different guarantees |
| **Autonomous code repair** | Writing code fixes into the target is a different risk class from restarting a container or rolling back a prompt — there is no deterministic inverse for a code change, so TNR cannot cover it. Every published system that attempts it stops at opening a PR for human review. Out of scope |

### 2.4 Loki, Tempo and Grafana — the observability profile

**Why they are here.** Not for Kavach to query. For a human to click.

A diagnosis cites `evidence_id`s, and the console shows the payload. With Tempo present, an evidence row also carries a deep link, so a reviewer goes from "diagnosis: provider outage, confidence 0.91" straight into the trace showing the 503 responses. That turns evidence citation from a claim into something checkable, which is the whole trust argument of the product.

**How they are wired.** Three extra exporters on the collector that already exists. Kavach's ingestion, detection, evidence collection and RCA are unchanged.

```
target → OTel SDK → OTel Collector
                       ├─ prometheusremotewrite → Prometheus   (detection queries this)
                       ├─ otlphttp              → Kavach       (RCA queries this)
                       ├─ loki                  → Loki         (human view)
                       └─ otlp                  → Tempo        (human view)
                                                     ↑
                                                  Grafana — viewer only
```

**Four rules:**

1. **Postgres stays the source of truth.** Nothing in the healing loop may query LogQL or TraceQL. If detection starts reading Loki, the loop now depends on Loki being healthy, and that is the risk this scoping exists to avoid.
2. **Optional compose profile.** `make up` runs lean; `make up PROFILE=observability` adds all three. Loki ~250MB, Tempo ~400MB, Grafana ~150MB on top of Ollama 7B at ~5–6GB — workable on a 16GB machine, not comfortable. If the demo machine struggles, drop the profile and nothing breaks.
3. **Grafana is a viewer, not a dashboard.** Loki and Tempo have no UI of their own, which is the only reason Grafana is here. Incidents are managed in the console and nowhere else. Do not build operational views in Grafana.
4. **Degrade silently.** With the profile off, trace deep links are simply absent from evidence rows. No error, no empty panel.

```python
# evidence rows carry an optional viewer link; None when the profile is off
tempo_link: str | None  # f"{grafana_base}/explore?...traceID={trace_id}"
```

### 2.3 The GenAI semantic conventions are not stable

A widely repeated claim says the ecosystem has converged on OpenTelemetry's GenAI conventions as a settled baseline. It converged on them as a *direction*. They are not stable.

Every `gen_ai.*` attribute, span, metric and event carries status **`Development`** — below Alpha on OpenTelemetry's own ladder, defined as "SHOULD NOT be used in production" and "MAY be removed without prior notice." The only Stable attributes on a GenAI span are `error.type`, `server.address` and `server.port`, inherited from core. On **12 June 2026, in semantic-conventions v1.42.0**, the GenAI, provider-specific and MCP conventions were deprecated in the core repo and moved to a dedicated `semantic-conventions-genai` repository to iterate faster than the core stability bar allows. That repo evolves on `main` with no tagged release. Attributes have already been renamed in flight — `gen_ai.provider.name` replaced `gen_ai.system` — and SDKs disagree with each other on several of the most-used attributes, while roughly eleven have held steady.

**Three binding consequences:**

1. **Pin the version** via `OTEL_SEMCONV_STABILITY_OPT_IN` and record it per row. `CONTRACT.md` §8 makes the application declare it.
2. **Normalise at the ingestion boundary.** Nothing downstream of `ingestion/genai.py` references a raw `gen_ai.*` name. A spec rename then costs one mapping file instead of a migration across detection, RCA and the console.
3. **Build on what held:** operation name, provider, request/response model, token usage, duration, finish reason. Treat multimodal, agent-graph and MCP attributes as volatile.

---

## 3. Project structure

```
kavach/
├── apps/
│   ├── control-plane/
│   │   └── kavach/
│   │       ├── main.py  config.py
│   │       ├── api/            # HTTP only — no business logic
│   │       │   ├── routes/     # projects incidents actions audit debt telemetry faults
│   │       │   ├── schemas/    ws.py
│   │       ├── contract/       # CONTRACT.md made executable
│   │       │   ├── schema.py   # kavach.yaml pydantic models
│   │       │   ├── validate.py
│   │       │   └── conformance.py   # L0–L3 determination
│   │       ├── onboarding/
│   │       │   ├── preflight.py     # check registry
│   │       │   ├── checks/          # one file per P01–P13
│   │       │   └── baseline.py
│   │       ├── catalogue/      # THE DECLARATIVE INTERPRETER
│   │       │   ├── schema.py   # fault definition models
│   │       │   ├── loader.py   # built-in + application-supplied
│   │       │   ├── matcher.py  # signal → candidate classes
│   │       │   └── builtin/    # f01..f09.yaml
│   │       ├── ingestion/      # otlp.py genai.py prometheus.py
│   │       ├── evaluation/     # runner.py golden_set.py scorers/
│   │       ├── detection/      # objectives.py anomaly.py
│   │       ├── graph/
│   │       │   ├── build.py  state.py
│   │       │   └── nodes/      # collect_evidence diagnose plan risk_gate
│   │       │                   # sandbox await_approval execute verify
│   │       │                   # unwind observe learn
│   │       ├── safety/
│   │       │   ├── gate.py          # permit() — the deny authority
│   │       │   ├── rules.py allowlist.py blast_radius.py circuit_breaker.py
│   │       │   └── decision_log.py  # Laya-format typed decisions
│   │       ├── tnr/                 # THE RECOVERABILITY GUARANTEE
│   │       │   ├── lock.py          # writer exclusivity
│   │       │   ├── undo_stack.py
│   │       │   ├── witness.py       # pre-state capture
│   │       │   └── severity.py      # weighted scalar, no-regression
│   │       ├── decision/       # base.py rule_engine.py laya.py
│   │       ├── executor/
│   │       │   ├── registry.py base.py
│   │       │   └── adapters/   # docker git redis http filesystem
│   │       ├── verification/   # probes.py verifier.py deltas.py
│   │       ├── debt/           # ledger.py triggers.py checker.py
│   │       ├── knowledge/      # embed.py retrieve.py store.py
│   │       ├── audit/          # log.py (append-only, hash chain)
│   │       ├── llm/            # client.py prompts/
│   │       ├── db/             # models.py session.py migrations/
│   │       └── telemetry/      # Kavach observing ITSELF
│   └── console/                # Next.js 15 — see DESIGN_SYSTEM.md
│       ├── app/                # fleet · projects · incidents · debt · audit
│       ├── components/         # ui/ incident/ safety/ debt/ charts/
│       └── lib/                # api.ts (generated) ws.ts tokens.ts
├── targets/
│   ├── ragpipe/                # PROOF #1 — forked, AIOps half stripped
│   └── proof2/                 # PROOF #2 — the conformance experiment
├── harness/                    # inject.py faults/ scenarios/ report.py
├── infra/                      # compose, otel-collector, prometheus
├── docs/decisions/             # ADRs
├── CONTRACT.md PRD.md ARCHITECTURE.md AGENTS.md DESIGN_SYSTEM.md ROADMAP.md
└── Makefile
```

---

## 4. Data flow

### 4.1 Observation

```
target service → OTel SDK (gen_ai.* spans, pinned semconv)
   → OTLP/gRPC → OTel Collector
        ├─ prometheusremotewrite → Prometheus
        └─ otlphttp → Kavach /v1/traces → normalise → telemetry_spans
```

The collector is the fan-out point. Adding Langfuse later is one exporter block.

### 4.2 Incident

Detection ticks every 15s, evaluating the objective contract against Prometheus and the rolling baselines. A breach creates an incident and starts a graph run, which follows §1 exactly.

The `plan` node resolves a repair through the **catalogue interpreter**, not through Python branching. The matcher maps the breaching signal plus the diagnosed class to a fault definition; the definition names the action, params, inverse and verification probes.

### 4.4 Documentation evidence (Context7)

`collect_evidence` may add a `library_docs` evidence kind for configuration-shaped faults (`F05`, `F08`, `F09`) and for `UNKNOWN` investigation. Never for `F01`–`F04`, `F06` or `F07`.

Two phases, deliberately split.

**At onboarding (preflight P14), once per dependency:**

```
for dep in contract.dependencies:
    resolve-library-id(dep.name, dep.role_hint)
      → pick by reputation + snippet count + version match
      → store "/org/project/version" in dependency_refs
    for each DOC_QUERIES template applicable to dep's role:
        query-docs(libraryId, template) → docs_cache
```

**At incident time, query only:**

```
collect_evidence
  └─ needs_docs(fault_class)?   # F05, F08, F09, UNKNOWN only
       ├─ no  → skip entirely
       └─ yes → docs/cache.py lookup, key = (library_id, DOC_QUERIES[fault_class])
                  ├─ hit  → evidence row, ZERO network
                  └─ miss → query-docs, 5s timeout, max 2 per incident
                             ├─ ok   → cache, evidence row
                             └─ fail → log, continue. NOT fatal
```

`resolve-library-id` never runs during an incident. The API caps calls at 3 per tool per question, so spending that budget at onboarding keeps it off the hot path entirely.

**Module:** `kavach/docs/` — `client.py`, `cache.py` (Postgres, TTL), `prewarm.py`, **`queries.py`**.

### 4.4.1 `queries.py` — the only place a query string may exist

```python
# Fixed, human-reviewed, one per fault class. NO f-strings. NO interpolation.
DOC_QUERIES: dict[str, str] = {
    "F05": "connection pool size configuration and defaults",
    "F08": "configuration file schema and valid values",
    "F09": "maximum output token parameter and limits",
}
```

A query is a single concept, as the API requires, and is a module-level constant. **Nothing from an incident is ever interpolated into it.**

This is a data-exfiltration boundary, not a style preference. Documentation services state that credentials, personal data and proprietary code must not be sent — and incident evidence (logs, config values, prompts, environment, stack traces) is exactly where those live. A query built with an f-string over evidence ships the user's secrets to a third party.

**Enforce it in CI:** a test asserts that no string reaching `client.query_docs` originates outside `DOC_QUERIES`.

**Five invariants:**

1. **No application data leaves the machine.** Template queries only.
2. **Untrusted data in.** Retrieved documentation enters the RCA prompt in a delimited evidence block, cited like any other evidence, never as instruction.
3. **Offline guarantee.** Pre-warm at onboarding; `PRD.md` §10.9 requires the default path to work with no network.
4. **Non-fatal.** Timeout, error or empty result degrade silently.
5. **Off the critical path, and budgeted.** No LOW-risk repair waits on a network call; at most 2 queries per incident.

```sql
dependency_refs(id, project_id, dep_id, name, version, library_id,
                resolved_at, reputation, snippet_count)
docs_cache(id, library_id, query_key, content, fetched_at, ttl_s, source_url)
```

### 4.3 Live console

The graph publishes every state transition to Redis pub/sub; the WebSocket hub fans out. The console never polls for incident state.

---

## 5. Database

One PostgreSQL instance. TimescaleDB hypertables for telemetry, pgvector for the knowledge base.

```sql
-- Contract and onboarding
projects(id, name, root_path, compose_file, mode, status,
         conformance_level, contract_version, created_at)
objectives(id, project_id, dimension, metric, comparator, threshold,
           window_s, weight)
tolerances(id, project_id, dimension, max_degradation_pct)
allowed_actions(id, project_id, action_name, max_risk_tier)
forbidden_services(id, project_id, service)
baselines(id, project_id, captured_at, config_hash, prompt_versions JSONB,
          metrics JSONB, eval_scores JSONB, index_snapshot_ref, is_current)
preflight_runs(id, project_id, ran_at, check_id, passed, detail JSONB)

-- Telemetry (hypertables, 7-day retention)
-- Column names are KAVACH's internal schema, deliberately decoupled from
-- gen_ai.* (see §2.3). provider was gen_ai.system, is now gen_ai.provider.name.
telemetry_spans(ts, project_id, trace_id, span_id, parent_span_id, name,
                duration_ms, status, provider, request_model, response_model,
                input_tokens, output_tokens, finish_reason,
                semconv_version, attributes JSONB)
telemetry_logs(ts, project_id, service, severity, body, attributes JSONB)

-- Evaluation
eval_runs(id, project_id, started_at, trigger, pass_rate, groundedness,
          mean_latency_ms, mean_cost, incident_id NULL)
eval_cases(id, run_id, case_id, question, answer, retrieved_ids, scores JSONB)

-- Incidents
incidents(id, project_id, status, fault_class, service, detected_at,
          resolved_at, mttd_s, mttr_s, outcome, severity_at_detect,
          severity_at_close)
evidence(id, incident_id, kind, source_ref, payload JSONB, collected_at)
diagnoses(id, incident_id, fault_class, confidence, evidence_ids TEXT[],
          rejected_alternatives JSONB, model, prompt_version, created_at)
hypotheses(id, incident_id, rank, description, confidence, tested, outcome)

-- Safety and execution
risk_decisions(id, incident_id, action_name, risk_tier, verdict, reasons JSONB,
               decided_by, typed_decision_frame JSONB)   -- Laya corpus
actions(id, incident_id, seq, name, params JSONB, inverse_name,
        inverse_params JSONB, pre_state_witness JSONB,
        idempotency_key UNIQUE, status, started_at, finished_at, error)
undo_stack(id, incident_id, seq, action_id, applied, applied_at)

-- Verification — deltas, not booleans
verifications(id, incident_id, action_id, ran_at, outcome,
              probe_results JSONB, deltas JSONB, tolerance_consumed JSONB)

-- Remediation debt
debt(id, project_id, incident_id, created_at, reason, repayment_action,
     repayment_params JSONB, trigger JSONB, max_age_s,
     status, repaid_at, repaid_incident_id)

-- Append-only. Enforced by trigger, not convention.
audit_log(id, project_id, incident_id, ts, actor, event, payload JSONB,
          prev_hash, hash)

-- Learning
incident_memory(id, incident_id, summary, embedding vector(768),
                fault_class, repair_action, outcome, deltas JSONB)
```

Each `audit_log` row carries the previous row's hash, so alteration is detectable. Cheap to implement and exactly what a panel asks about.

**Redis:** `kavach:lock:{project}` (writer exclusivity) · `kavach:idem:{key}` · `kavach:cb:{project}:{service}:{fault}` · `kavach:blast:{project}` · `kavach:events`.

---

## 6. TNR — the recoverability guarantee

From STRATUS (NeurIPS'25), implemented against Docker rather than Kubernetes.

| Property | Implementation |
|---|---|
| **Writer exclusivity** | A per-project advisory lock in Postgres, acquired by the executor *and* the unwind path. Execution and unwind cannot interleave; two incidents on one project serialise |
| **Faithful undo** | A per-incident **undo stack**. Each mutating action pushes `(action, inverse, pre_state_witness)` before executing; abort pops and applies in reverse. A witness is the captured prior value — container spec, config hash, prompt blob SHA, index snapshot ref — so the inverse is deterministic and never reconstructed by a model |
| **No regression** | A weighted severity scalar from `objectives[].weight`, sampled before and after each action. Increase → unwind immediately rather than waiting for the window |

STRATUS's ablation on AIOpsLab's 13 mitigation problems: naive retry without undo 23.1%, with TNR 69.2%. The undo mechanism is worth roughly 3× on mitigation success — more than any model choice in this stack.

Two consequences:

- **`executor/base.py` must make an action without an inverse unrepresentable**, enforced at registration. An abstract `inverse()` with no implementation should fail at import, not at 3 a.m.
- **Inverses are data, never model calls.** The same conclusion `EvoUndo` reaches: asking an LLM to undo its own action hallucinates or produces incomplete inverses.

---

## 7. The safety gate

One public entry point:

```python
def permit(action: Action, project: Project, incident: Incident) -> Verdict
```

`Verdict` is `ALLOW_AUTO | REQUIRE_SANDBOX | REQUIRE_APPROVAL | DENY`, always with reasons. **Scoring is not permission.** The decision engine ranks candidates; this gate decides whether any of them may run.

Evaluation order, first failure short-circuits:

1. **Forbidden services.** Target in `forbidden_services` → `DENY`. Absolute veto, checked first.
2. **Allow-list.** Action not in `allowed_actions` → `DENY`. Unbypassable by mode, tier or confidence.
3. **Inverse exists** and is executable → else never auto.
4. **Confidence** above the project threshold → else `REQUIRE_APPROVAL`.
5. **Risk tier** from the deterministic table (§7.1).
6. **Blast radius.** ≤3 actions/incident, ≤5 incidents/hour → else `DENY` and halt.
7. **Circuit breaker.** ≤3 heals per `(service, fault_class)` per 30 min → else `DENY` and halt.
8. **Mode policy.** `SIMULATION` plans only. `APPROVAL` routes everything to a human. `AUTONOMOUS` auto-executes LOW, sandboxes MEDIUM, escalates HIGH.

Every call writes a `risk_decisions` row including a `typed_decision_frame` — the compressed Laya-shaped version. That column is the fine-tuning corpus and costs nothing to populate now.

### 7.1 Risk tiers (deterministic, v1)

| Action | Tier | Reasoning |
|---|---|---|
| `switch_model` | LOW | Config-only, instantly reversible, no data touched |
| `restart_container` | LOW | Reversible by definition; no persistent state in these services |
| `flush_cache` | LOW | Cache is rebuildable by definition |
| `retry_request` | LOW | Idempotent at the app layer |
| `scale_replicas_up` | LOW | Additive only. Scaling *down* is not in the catalogue |
| `raise_memory_limit` | LOW | Additive, one step, capped |
| `rollback_prompt` | MEDIUM | Changes behaviour; reversible via git |
| `rollback_config` | MEDIUM | Changes behaviour; reversible via git |
| `rebuild_index` | MEDIUM | Touches the retrieval store; reversible via snapshot |
| anything else | HIGH | Default-deny posture |

---

## 8. Staged verification

Canary is deferred (`PRD.md` §5.1). v1 stages the rollout instead:

```
MEDIUM risk:   sandbox → verify in sandbox → approval → production → observe
LOW risk:      production → observe
```

**The sandbox** clones the compose project under a distinct project name on an isolated network, applies the repair, and runs the probes there. Stateful services are seeded from the current snapshot. This is the component most likely to overrun — ports, volumes and state make it harder than it reads — which is why it is P1 and why the approval path works without it.

**The observation window** is 120s post-execution during which objectives continue to be sampled. An incident does not close until the window passes. A regression inside the window triggers unwind exactly as a failed probe would. This is the cheap part of what canary would have given us.

### 8.1 Verification returns deltas

```python
VerificationResult(
    passed=True, outcome=MITIGATED,
    probes={"health": PASS, "objectives": PASS, "golden_eval": DEGRADED},
    deltas={"availability": +0.99, "quality": -0.12,
            "latency": -0.30, "cost": +0.60},
    tolerance_consumed={"quality": 0.80},
)
```

Outcome classification:

- All objectives satisfied, no tolerance consumed → `RESOLVED`
- Availability restored, other objectives degraded **within** tolerance → `MITIGATED`, create debt
- Degradation **exceeds** tolerance → verification failure → unwind
- Unwind succeeded → `ESCALATED`; unwind failed → `UNRECOVERABLE`, alert loudly

---

## 9. The debt ledger

A `MITIGATED` outcome is a position, not a destination. v1 implements this for `F01`; the general form is in `CONTRACT.md` §10.1.

- On `MITIGATED`, write a `debt` row with a repayment action and a machine-evaluable trigger.
- A background checker evaluates open triggers every 60s.
- A fired trigger proposes the repayment action through **the same safety gate** — repayment is not privileged.
- Repayment executes, verifies, and on success clears the debt and moves the original incident to `RESOLVED`.
- Debt older than `max_age_s` escalates.

---

## 10. The declarative catalogue

Built-in definitions live in `catalogue/builtin/*.yaml`; applications may ship their own beside `kavach.yaml`. The interpreter is what makes this a platform.

```yaml
id: F01
name: provider_outage
applies_to_roles: [model_primary]
detect:
  signal: gen_ai_error_ratio
  condition: above
  threshold: 0.20
  window_s: 60
evidence: [spans:gen_ai, logs:model_primary, container_state, similar_incidents]
repair:
  action: switch_model
  params: {from: "{role:model_primary}", to: "{role:model_backup}"}
  inverse: {action: switch_model, params: {from: "{role:model_backup}", to: "{role:model_primary}"}}
  requires: [permissions.allowed_actions.switch_model, services.model_backup]
verify: [health, objectives, golden_eval]
risk: LOW
outcome_on_success: MITIGATED
debt:
  repayment_action: switch_model
  trigger: {metric: model_primary_health, condition: healthy_for_s, value: 600}
  max_age_s: 86400
```

**Acceptance for this component:** adding `F10` requires changes to no Python file. If it does, the interpreter is incomplete.

---

## 11. External services

| Service | Required | Fallback |
|---|---|---|
| Ollama (containerised) | Yes | Any OpenAI-compatible endpoint via `KAVACH_LLM_BASE_URL` |
| Docker daemon | Yes | None. Hard dependency |
| Git | Yes, in the target repo | None. Preflight P02 blocks |
| `laya-serve` | No | Rule engine alone |
| **Context7** | **No** | Cache; then no documentation evidence at all |

**One external service, and it is optional.** Context7 is the only outbound dependency in the system, it is cached, and every path degrades cleanly without it. The offline guarantee holds: pre-warm at onboarding, then the demo runs on conference wifi or none.

---

## 12. Deployment

```bash
make up          # control plane
make target-up   # targets/ragpipe
make onboard     # preflight + conformance + baseline
make demo        # scripted injection sequence
```

The control plane mounts the docker socket read-write. **This is the single most dangerous privilege in the system** — it is why the forbidden-services and allow-list checks run first, and why `SIMULATION` is the default for any project not deliberately armed.

---

## 13. Scalability notes

Recorded so the design does not foreclose them; none are v1 work.

- **Multiple projects:** the graph is per-incident; `PostgresSaver` already supports concurrent runs. More workers, not more code.
- **Kubernetes:** `RuntimeAdapter` is the seam. A `K8sAdapter` implements `restart`, `scale`, `get_state` against the API server with no change to the graph, gate or console. **Canary becomes meaningful here**, because replicas exist.
- **Telemetry volume:** hypertables, 7-day retention, continuous aggregates for baselines. ClickHouse is the drop-in if measured as a bottleneck.
- **LLM throughput:** RCA runs once per incident, not per request.
- **Knowledge base:** pgvector with HNSW handles hundreds of thousands of incidents on one node.

## 14. Observing Kavach itself

The control plane exports to the same collector it consumes from. If the healing platform is what breaks, it should be visible — and the console can show Kavach's own health beside the target's.
