# ARCHITECTURE.md — Kavach

> How it is built. Read `PRD.md` and `CONTRACT.md` first.

---

## 1. System overview

Kavach is a **standalone autonomous AI operations control plane**. In the MVP, it does not connect to or modify another AI application.

Instead, Kavach operates against a **controlled simulated application state**. A developer supplies an incident scenario containing signals, evidence, baseline state and the fault context needed for the scenario. Kavach runs the same decision loop it will eventually use for a real adapter, but every mutation stops at the simulator.

The important separation is:

**scenario input → graph decides → safety gate permits → simulated executor acts → verifier checks**

```text
                      MANUAL SCENARIO
                 signals · logs · metrics
                          │
                          ▼
                  ┌──────────────┐
                  │  DETECTION   │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │   EVIDENCE   │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │     RCA      │
                  │ class +      │
                  │ confidence + │
                  │ citations    │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │     PLAN     │
                  │ action +     │
                  │ inverse +    │
                  │ pre-state    │
                  └──────┬───────┘
                         ▼
              ╔════════════════════╗
              ║    SAFETY GATE     ║
              ║  deny by default   ║
              ╚═══════╦══════╦═════╝
                      ║      ║
                   ALLOW    DENY
                      │      └──────────────► ESCALATE
                      ▼
             ┌─────────────────────┐
             │ SIMULATED EXECUTOR  │
             │ safe state mutation │
             └──────────┬──────────┘
                        ▼
             ┌─────────────────────┐
             │     VERIFY          │
             │ health · objectives │
             │ golden evaluation   │
             └───────┬────────┬────┘
                 PASS│        │FAIL
                     │        ▼
                     │   ┌──────────────┐
                     │   │ UNWIND STACK │
                     │   └──────┬───────┘
                     │          ▼
                     │    ESCALATED /
                     │    UNRECOVERABLE
                     ▼
              RESOLVED / MITIGATED
                     │
                     ▼
                   AUDIT
                     │
                     ▼
               LEARNING / KB
```

### 1.1 Properties that must not be broken

1. **The gate can refuse.** Scoring and permission are different operations.
2. **The graph does not have side effects.** Only the executor changes simulated state.
3. **Verification failure unwinds first.** Analysis happens only after the state is safe.
4. **The knowledge base feeds future evidence collection.**
5. **No component in the MVP can reach an external AI application's runtime.**

### 1.2 Component responsibilities

| Component | Owns | Does not own |
|---|---|---|
| Scenario API | Manual/synthetic incident input | Diagnosis |
| Scenario store | Reusable scenario definitions and state | Decisions |
| Detection | Objective breaches and anomaly signals from scenario state | RCA |
| Evidence | Structured evidence collection and storage | Decisions |
| Catalogue | Declarative fault definitions | Execution |
| Graph | Incident state machine | Direct mutation |
| Decision engine | Candidate diagnosis/ranking | Permission |
| Safety gate | Allow-list, tier, confidence, blast radius, breaker, mode | Choosing repair |
| TNR | Writer lock, undo stack, pre-state witness, no-regression | Choosing repair |
| Simulated executor | **Only state mutation in the MVP** | Deciding whether to act |
| Verification | Probes, deltas, outcome classification | Repairing |
| Debt | Tracking and repayment proposal | Privileged execution |
| Audit | Append-only event record | Editing history |
| Knowledge base | Similar incident retrieval | Authorising actions |

The key separation remains:

**the graph decides, the gate permits, the executor acts.**

---

## 2. Tech stack

### 2.1 Chosen

| Layer | Choice | Why |
|---|---|---|
| Control plane | Python 3.12 | Agent ecosystem and team familiarity |
| API | FastAPI + Uvicorn | Async and typed API surface |
| Orchestration | **LangGraph** | Cyclic incident state machine with durable checkpoints |
| LLM | Ollama + local instruct model | Local, offline-friendly RCA and structured classification |
| Decision model | **Laya**, later and shadow-only | Optional independent decision evaluation |
| Database | PostgreSQL 16 + pgvector + TimescaleDB | Incidents, vectors and time-series data in one store |
| Cache/events | Redis 7 | Pub/sub, idempotency and short-lived control state |
| Frontend | Next.js 15 + TypeScript + Tailwind v4 + shadcn/ui | Console |
| Charts | Recharts | Lightweight quantitative views |
| Validation | Pydantic v2 | Typed boundaries |
| Python tooling | uv, ruff, mypy --strict, pytest | Quality |
| JS tooling | pnpm, eslint, prettier, vitest, playwright | Quality |

Prometheus and OpenTelemetry may be used for **Kavach's own observability**. They are not required as an external application's telemetry path in the standalone MVP.

### 2.2 Explicitly rejected for the MVP

| Rejected | Why |
|---|---|
| MongoDB | No need for a separate document database |
| LangChain / CrewAI beside LangGraph | One orchestration framework is enough |
| PyTorch / TensorFlow | Not required for the MVP detection methods |
| Toxiproxy / custom fault injector | Kavach must not inject failures into external applications |
| Docker SDK / Docker socket control | Real runtime control is future work |
| Kubernetes | Future runtime adapter |
| Cloud deploy integrations | Outside standalone MVP |

---

## 3. Project structure

```text
kavach/
├── apps/
│   ├── control-plane/
│   │   └── kavach/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── api/
│   │       │   ├── routes/       # scenarios, incidents, actions, audit, debt
│   │       │   └── schemas/
│   │       ├── scenarios/         # manual/synthetic scenario input and replay
│   │       ├── catalogue/         # declarative fault definitions
│   │       ├── evidence/          # evidence model + collection
│   │       ├── detection/         # objectives + anomaly detection
│   │       ├── evaluation/        # golden set + scorers
│   │       ├── graph/             # LangGraph state machine
│   │       ├── safety/            # deterministic permission gate
│   │       ├── tnr/               # lock, undo stack, witness, severity
│   │       ├── decision/           # rule engine + optional Laya shadow
│   │       ├── simulation/         # simulated application state + executor
│   │       ├── verification/       # probes + deltas + outcomes
│   │       ├── debt/               # remediation debt
│   │       ├── knowledge/          # embeddings + retrieval
│   │       ├── audit/              # append-only hash chain
│   │       ├── llm/                # client + prompts
│   │       ├── db/                 # models + migrations
│   │       └── telemetry/          # Kavach's own telemetry
│   └── console/
│       ├── app/
│       ├── components/
│       └── lib/
├── scenarios/
│   ├── F01-provider-outage.yaml
│   ├── F02-provider-latency.yaml
│   ├── F03-crash-loop.yaml
│   ├── F04-cache-poisoning.yaml
│   ├── F05-pool-exhaustion.yaml
│   ├── F06-retrieval-collapse.yaml
│   ├── F07-prompt-regression.yaml
│   ├── F08-config-regression.yaml
│   └── F09-token-blowout.yaml
├── infra/                         # Kavach infrastructure only
├── docs/decisions/                # ADRs
├── CONTRACT.md
├── PRD.md
├── ARCHITECTURE.md
├── AGENTS.md
├── DESIGN_SYSTEM.md
├── ROADMAP.md
└── Makefile
```

There is intentionally **no `targets/` directory and no `harness/` injector directory** in the MVP.

---

## 4. Data flow

### 4.1 Scenario input

A developer creates a scenario manually through the console or API.

```yaml
id: scenario-f01-demo
fault_class: F01
signals:
  gen_ai_error_ratio: 0.35
  provider_latency_ms: 4200
evidence:
  - kind: log
    source: model_primary
    payload:
      status: 503
  - kind: metric
    source: gen_ai_error_ratio
    payload:
      value: 0.35
state:
  model_primary: unavailable
  model_backup: healthy
  cache: healthy
objectives:
  availability: 0.45
  quality: 0.84
```

The scenario is a **test/input artifact**, not a failure injector.

### 4.2 Incident loop

The scenario runner creates an incident. Detection evaluates the supplied signals and objectives. The graph then performs:

```text
detect
→ collect_evidence
→ diagnose
→ plan
→ risk_gate
→ execute_simulated
→ verify
→ unwind / observe
→ outcome
→ audit
```

The catalogue interpreter maps a signal and diagnosed class to the action, inverse and verification probes. The graph does not contain one branch per fault class.

### 4.3 Live console

The graph publishes state transitions to Redis pub/sub. The WebSocket hub sends those events to the console.

The console shows the same sequence the engine executes and never implies that a simulated mutation affected an external system.

---

## 5. Database

PostgreSQL is the system of record.

```sql
-- Scenarios
scenarios(id, name, fault_class, definition JSONB, created_at, updated_at)
scenario_runs(id, scenario_id, started_at, finished_at, status)

-- Objectives / baselines
objectives(id, run_id, dimension, value, threshold, weight)
baselines(id, run_id, captured_at, state JSONB, metrics JSONB, eval_scores JSONB)

-- Incidents
incidents(id, run_id, status, fault_class, detected_at,
          resolved_at, mttd_s, mttr_s, outcome,
          severity_at_detect, severity_at_close)
evidence(id, incident_id, kind, source_ref, payload JSONB, collected_at)
diagnoses(id, incident_id, fault_class, confidence,
          evidence_ids TEXT[], rejected_alternatives JSONB,
          model, prompt_version, created_at)

-- Safety / simulated actions
risk_decisions(id, incident_id, action_name, risk_tier,
               verdict, reasons JSONB, decided_by,
               typed_decision_frame JSONB)
actions(id, incident_id, seq, name, params JSONB,
        inverse_name, inverse_params JSONB,
        pre_state_witness JSONB, idempotency_key UNIQUE,
        status, started_at, finished_at, error)
undo_stack(id, incident_id, seq, action_id, applied, applied_at)

-- Verification
verifications(id, incident_id, action_id, ran_at, outcome,
               probe_results JSONB, deltas JSONB, tolerance_consumed JSONB)

-- Debt
debt(id, incident_id, created_at, reason, repayment_action,
     repayment_params JSONB, trigger JSONB, max_age_s,
     status, repaid_at, repaid_incident_id)

-- Audit
audit_log(id, incident_id, ts, actor, event, payload JSONB,
          prev_hash, hash)

-- Knowledge
incident_memory(id, incident_id, summary, embedding vector(768),
                fault_class, repair_action, outcome, deltas JSONB)
```

Redis stores:

```text
kavach:lock
kavach:idem:{key}
kavach:cb:{fault}
kavach:blast
kavach:events
```

---

## 6. TNR — the recoverability guarantee

TNR remains central, but it operates on simulated state in the MVP.

| Property | Implementation |
|---|---|
| Writer exclusivity | One per-incident/per-simulation writer lock prevents execute and unwind from interleaving |
| Faithful undo | Per-incident undo stack containing `(action, inverse, pre_state_witness)` |
| No regression | Weighted severity sampled before and after actions |

A pre-state witness is the captured prior simulated value. The inverse is deterministic data; it is never generated by asking an LLM what it changed.

### TNR invariants

1. An action without an inverse cannot be registered.
2. The inverse is recorded **before** the action executes.
3. Unwind runs in reverse order.
4. Verification failure triggers unwind immediately.
5. No analysis or learning step may happen between failure and unwind.
6. The same lock protects both execution and unwind.

The implementation should preserve the same guarantee that a future real adapter will need, without requiring real external writes today.

---

## 7. The safety gate

One public entry point:

```python
def permit(action: Action, incident: Incident, state: SimulationState) -> Verdict:
    ...
```

`Verdict` is:

```text
ALLOW_AUTO
REQUIRE_APPROVAL
DENY
```

`REQUIRE_SANDBOX` is deferred because the MVP has no real runtime or production environment to sandbox.

Evaluation order:

1. **Allow-list** — action not explicitly allowed → `DENY`.
2. **Inverse** — missing/unusable inverse → `DENY`.
3. **Confidence** — below threshold → `REQUIRE_APPROVAL`.
4. **Risk tier** — deterministic catalogue value.
5. **Blast radius** — too many actions in one run → `DENY`.
6. **Circuit breaker** — repeated same-fault healing → `DENY`.
7. **Mode**:
   - `SIMULATION` → produce a dry-run plan only.
   - `APPROVAL` → wait for human approval before simulated execution.
   - `AUTONOMOUS` → execute LOW-risk actions against **simulated state only**; MEDIUM requires approval; HIGH is denied/escalated.

Every gate decision is written to `risk_decisions`.

### 7.1 Risk tiers

| Action | Tier | Reason |
|---|---|---|
| `switch_model` | LOW | Configuration-only in simulation |
| `restart_service` | LOW | Reversible simulated state change |
| `flush_cache` | LOW | Rebuildable simulated state |
| `retry_request` | LOW | Idempotent simulated action |
| `raise_memory_limit` | LOW | Bounded additive change |
| `rollback_prompt` | MEDIUM | Behaviour-changing state |
| `rollback_config` | MEDIUM | Behaviour-changing state |
| `rebuild_index` | MEDIUM | Retrieval state change |
| anything else | HIGH | Default-deny |

---

## 8. Verification

The MVP does not use production observation windows or canary rollout.

Verification is deterministic over the simulated state:

```python
VerificationResult(
    passed=True,
    outcome=MITIGATED,
    probes={
        "health": PASS,
        "objectives": PASS,
        "golden_eval": DEGRADED,
    },
    deltas={
        "availability": +0.99,
        "quality": -0.12,
        "latency": -0.30,
        "cost": +0.60,
    },
    tolerance_consumed={"quality": 0.80},
)
```

Outcome classification:

- All objectives satisfied and no tolerance consumed → `RESOLVED`
- Availability restored but another objective degraded within tolerance → `MITIGATED`
- Degradation exceeds tolerance → verification failure → unwind
- Unwind succeeds → `ESCALATED`
- Unwind fails → `UNRECOVERABLE`

---

## 9. Remediation debt

A `MITIGATED` outcome creates a debt record even in simulation because the concept is part of Kavach's decision model.

- Record the repayment action.
- Record a machine-evaluable trigger.
- Route repayment through the same safety gate.
- Verify repayment.
- Clear debt on successful repayment.
- Escalate overdue debt.

For `F01`, the simulation can model:

```text
primary unhealthy
→ switch to backup
→ availability restored, quality slightly degraded
→ MITIGATED + debt
→ simulated primary becomes healthy
→ repayment proposal
→ switch back
→ verify
→ RESOLVED
```

---

## 10. Declarative catalogue

Built-in definitions live in `catalogue/builtin/*.yaml` or the equivalent scenario catalogue.

```yaml
id: F01
name: provider_outage

detect:
  signal: gen_ai_error_ratio
  condition: above
  threshold: 0.20
  window_s: 60

evidence:
  - provider_errors
  - provider_state
  - similar_incidents

repair:
  action: switch_model
  params:
    from: model_primary
    to: model_backup
  inverse:
    action: switch_model
    params:
      from: model_backup
      to: model_primary

verify:
  - health
  - objectives
  - golden_eval

risk: LOW
outcome_on_success: MITIGATED

debt:
  repayment_action: switch_model
  trigger:
    condition: primary_healthy_for_s
    value: 600
  max_age_s: 86400
```

Adding `F10` should require no change to the graph, safety engine, simulator or console.

---

## 11. Runtime boundary

The MVP has one runtime:

```text
SimulationRuntime
```

Its interface is intentionally shaped so that a future adapter can fit behind the same seam:

```python
class RuntimeAdapter(Protocol):
    def read_state(...) -> RuntimeState: ...
    def apply(...) -> ApplyResult: ...
    def restore(...) -> RestoreResult: ...
```

The current implementation is:

```text
SimulationRuntime
```

A future implementation may eventually be:

```text
DockerRuntimeAdapter
KubernetesRuntimeAdapter
CloudRuntimeAdapter
```

Those are **future integrations only**. They are not implemented or mounted into the MVP.

---

## 12. Deployment

```bash
make up
make dev-api
make dev-console

make scenario NAME=F01
make demo
make bench
```

The deployment contains only Kavach infrastructure and simulation state. There is no target application and no Docker socket mount.

---

## 13. Scalability notes

These are design seams, not MVP work:

- Multiple simulations can run concurrently with incident-level locking.
- PostgreSQL and Redis already provide the persistence and event primitives needed for more workers.
- pgvector can scale the incident knowledge base before a separate vector store becomes necessary.
- RCA runs once per incident, not per request.
- A future runtime adapter can reuse the graph, safety gate, TNR and verification interfaces.

---

## 14. Observing Kavach itself

Kavach should observe its own:

- API health
- graph latency
- RCA latency
- simulation execution time
- verification failures
- queue/event lag
- audit integrity

This is separate from observing an external AI application and is safe to build now.
