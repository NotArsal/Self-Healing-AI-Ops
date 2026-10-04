# CONTRACT.md — The Healability Contract, v1

> **Specification.** The contract describes the state, evidence and permissions Kavach needs in order to reason about and safely repair an AI system.
>
> In the standalone MVP, the contract is applied to a **simulated application state**. Real application onboarding is a future integration and is not required to run Kavach.

---

## 0. Why this exists

Autonomous remediation is unsafe when the platform has to guess what "healthy" means, what may be changed, what the previous state was, or whether a repair can be undone.

Kavach therefore makes recoverability explicit.

The current MVP uses this contract to define **simulation state and incident scenarios**. A future runtime adapter may map the same obligations to a real AI application.

### 0.1 Future integration test

The original external-app onboarding experiment is deliberately deferred.

Future success criterion:

> A person who has not read Kavach's source should be able to connect an unseen AI application by satisfying this contract, without changing Kavach's source.

This is not an MVP acceptance criterion.

---

## 1. Contract overview

The contract keeps seven obligations:

| # | Obligation | Without it |
|---|---|---|
| C1 | **Identity** — services, roles, dependencies | Fault localisation is ambiguous |
| C2 | **Liveness** — health state | Recovery cannot be confirmed |
| C3 | **Quality** — golden set and scoring | Silent degradation is invisible |
| C4 | **Objectives** — multi-objective health | "Healthy" is underspecified |
| C5 | **Reversibility** — versioned/restorable state | Repair cannot be safely undone |
| C6 | **Permission** — explicit allow-list | Safe execution cannot be established |
| C7 | **Evidence / Observability** — structured operational evidence | RCA lacks support |

In the MVP, each obligation can be represented as data inside a scenario rather than through a connection to another application.

---

## 2. C1 — Identity

A scenario declares the logical services involved in the incident.

```yaml
services:
  api:
    role: application
    depends_on: [model_primary, vector_store]
  vector_store:
    role: vector_store
  cache:
    role: cache
  model_primary:
    role: model_primary
  model_backup:
    role: model_backup
```

Roles are a closed vocabulary.

`depends_on` supports fault localisation in the simulation.

---

## 3. C2 — Liveness

The scenario provides a health state for each declared service.

```yaml
health:
  api: healthy
  model_primary: unhealthy
  model_backup: healthy
  vector_store: healthy
  cache: healthy
```

A future runtime adapter may map this to HTTP, TCP or process health checks.

---

## 4. C3 — Quality

The scenario may contain a golden set and its scores.

```yaml
quality:
  golden_set: ./golden_set.yaml
  min_cases: 20
  scorers: [groundedness, answer_match, latency, cost]
```

Golden-set data belongs to the application/domain model, not the LLM.

---

## 5. C4 — Objectives

Health is a **vector**, not a boolean.

```yaml
objectives:
  availability:
    value: 0.45
    threshold: 0.99
    weight: 1.0

  quality:
    value: 0.84
    threshold: 0.85
    weight: 1.0

  latency:
    value: 3.8
    threshold: 2.0
    weight: 0.6

tolerance:
  quality_drop_pct: 15
  latency_increase_pct: 50
  cost_increase_pct: 100
```

Weights define severity. Tolerance defines acceptable degradation for `MITIGATED`.

---

## 6. C5 — Reversibility

Every state that a repair may touch must have a deterministic previous value.

```yaml
reversible_state:
  model_selection:
    value: model_primary
  prompts:
    version: prompt-a91c
  config:
    hash: cfg-1837
  index:
    snapshot_ref: snapshot-042
```

The simulator captures this as the pre-state witness.

Future runtime adapters must provide equivalent restore semantics.

---

## 7. C6 — Permission

```yaml
permissions:
  allowed_actions:             # DEFAULT IS EMPTY
    - switch_model
    - restart_service
    - flush_cache
    - rollback_prompt
    - rollback_config
    - rebuild_index
  max_risk_tier: MEDIUM
```

Obligations:

- **Default-deny.**
- An action not listed is refused.
- The action must exist in the executor registry.
- The action must have a working inverse.
- Future integrations may add `forbidden_services`; the standalone MVP does not need external-service targeting.

---

## 8. C7 — Evidence / Observability

The standalone MVP accepts structured evidence directly in the scenario.

```yaml
evidence:
  - id: ev-001
    kind: metric
    source: gen_ai_error_ratio
    value: 0.35

  - id: ev-002
    kind: log
    source: model_primary
    payload:
      status: 503
      message: "provider unavailable"

  - id: ev-003
    kind: state
    source: model_primary
    payload:
      health: unhealthy
```

A future external telemetry adapter may map OTLP data into the same internal evidence model.

---

## 9. Conformance levels

For the standalone MVP, conformance describes **scenario completeness**, not external application onboarding.

| Level | Requires | Kavach may |
|---|---|---|
| **L0 — Observed** | Identity + evidence + liveness | Detect and diagnose |
| **L1 — Protected** | + quality + objectives | Verify degradation and propose repair |
| **L2 — Recoverable** | + reversibility + permission | Execute allowed LOW-risk repairs in simulation |
| **L3 — Healable** | All seven obligations verified | Run the full simulated closed loop |

A real external application's onboarding will reuse these levels in a future integration phase.

---

## 10. Outcome states

| State | Meaning |
|---|---|
| `RESOLVED` | All objectives satisfied with no tolerance consumed |
| `MITIGATED` | Availability restored while another objective remains degraded within tolerance; debt created |
| `ESCALATED` | No permitted repair, insufficient evidence, or failed verification after successful unwind |
| `UNRECOVERABLE` | Verification failed and unwind also failed |

### 10.1 Remediation debt

```yaml
debt:
  f01_provider_outage:
    repayment_action: switch_model
    trigger:
      condition: primary_healthy_for_s
      value: 600
    max_age_s: 86400
```

Debt is a first-class object even in simulation.

---

## 11. MVP readiness checks

Before a scenario can run:

| # | Check | Obligation |
|---|---|---|
| P01 | Scenario schema validates | C1–C7 |
| P02 | All declared services have logical state | C1 |
| P03 | Health state exists for required services | C2 |
| P04 | Golden set and scores are valid when declared | C3 |
| P05 | Objectives and tolerances are valid | C4 |
| P06 | Every reversible state has a witness/restore definition | C5 |
| P07 | Allowed actions exist and have inverses | C6 |
| P08 | Evidence contains stable IDs and supported kinds | C7 |

A failed check blocks scenario execution and returns the exact remediation.

Real telemetry, external runtime connectivity and production credentials are **not MVP readiness requirements**.

---

## 12. Non-obligations for the standalone MVP

- No SDK or runtime import is required.
- No specific vector store or model provider is required.
- No external AI application connection.
- No fault injection system.
- No Docker socket.
- No Kubernetes or service mesh.
- No production credentials.
- No real-world side effects.

---

## 13. Future questions

1. How should multi-instance real applications represent replica-aware objectives?
2. How should external telemetry adapters preserve evidence lineage?
3. How should application-supplied scorers be standardised?
4. How should cross-application dependencies be represented?
5. What additional safety controls are required before a runtime adapter can leave simulation?
