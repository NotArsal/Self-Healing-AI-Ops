# PRD.md — Kavach

> **Autonomous AI Operations Platform**
> VIT · CSE-AI (E) · Group 14 · Engineering Research & Innovation · AY 2026-27

**Companion documents:** `CONTRACT.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `AGENTS.md`, `DESIGN_SYSTEM.md`.

---

## 1. Product overview

**One line:** Kavach is an autonomous AI operations engine that takes a structured incident scenario, works out why it happened, plans a bounded repair, safely applies that repair in a controlled simulation, verifies the result, and unwinds when necessary.

### The key scope decision

**Kavach is standalone in v1.**

It does **not**:

- connect to another AI application,
- inject faults into another application,
- restart another application's containers,
- modify another application's files/configuration,
- mount a Docker socket,
- perform production self-healing.

Developers create the failure scenarios themselves. Kavach reasons over those scenarios and demonstrates its self-healing loop against simulated state.

The future product can attach a runtime adapter to a real application, but that is a separate phase.

---

## 2. Problem

AI applications can fail at many layers: model provider, retrieval, prompts, configuration, cache, connection pools and runtime resources.

The operational challenge is not only detecting failure. A useful system must also:

1. distinguish possible causes,
2. support its diagnosis with evidence,
3. select a repair appropriate to the fault,
4. restrict what it is allowed to do,
5. preserve a deterministic undo path,
6. verify multiple objectives after the repair.

A successful repair is not automatically a correct diagnosis. A system that restores availability while silently degrading output quality can make the application worse.

---

## 3. Thesis

Kavach focuses on four ideas:

1. **Evidence-grounded RCA** — diagnoses cite stored evidence.
2. **Safety as a separate gate** — confidence does not grant permission.
3. **Transactional recovery** — every simulated mutation has a pre-state witness and inverse.
4. **Multi-objective verification** — health, quality, latency and cost are compared as deltas.

The standalone MVP is intentionally designed to prove these ideas before introducing real-system integration complexity.

---

## 4. Goals

- **G1** Close the incident loop end-to-end in simulation.
- **G2** Make every decision inspectable: evidence, confidence, action, inverse, risk and verification.
- **G3** Make unsafe actions impossible through a deterministic deny-by-default gate.
- **G4** Prove rollback correctness through forced verification failures.
- **G5** Demonstrate multiple fault classes through manually created scenario replays.
- **G6** Produce measurable research results for RCA, repair success, false healing and undo.

### 4.1 Non-goals

Not a general AIOps platform. Not a Kubernetes operator. Not a production automation system. Not a target-application testing harness. Not a fault-injection framework. Not multi-tenant. Not predictive forecasting. Not claiming autonomous handling of unknown real-world failures.

---

## 5. Locked scope

| Decision | v1 | Future |
|---|---|---|
| Operating environment | Standalone simulated application state | Runtime adapters for real applications |
| Incident creation | Manual/synthetic scenarios | Live telemetry-driven incidents |
| Fault injection | **None** | Optional external test tooling outside Kavach |
| Execution | Simulated state only | Real runtime adapters |
| Autonomy | LOW-risk simulated actions may auto-execute | Real-system autonomy after separate safety validation |
| Verification | Health + objectives + golden evaluation | Runtime probes + observation windows |
| Fault catalogue | 9 classes, declarative | Application-authored catalogues |
| Debt | `F01` first, general mechanism | All mitigating repairs |
| Laya | Shadow evaluation later | Possible decision support after calibration |
| Knowledge base | Incident memory/retrieval | Larger cross-application corpus |

### 5.1 Explicit integration boundary

A real application adapter must not appear in the MVP simply because the architecture can support one.

The adapter boundary is documentation/design only until the standalone Kavach loop is complete and tested.

---

## 6. Operating model

Kavach operates on a scenario object.

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

state:
  model_primary: unavailable
  model_backup: healthy

objectives:
  availability: 0.45
  quality: 0.84
```

The developer may create this scenario through the API, UI or YAML file.

Kavach must never create the failure itself.

---

## 7. Fault catalogue

Nine classes are retained as **scenario definitions**. Each definition contains detection signals, evidence requirements, repair, inverse, verification probes, risk tier and outcome.

| ID | Fault | Detection signal | Simulated repair | Risk | Outcome |
|---|---|---|---|---|---|
| `F01` | Provider outage | Error ratio > threshold | Switch to backup model | LOW | MITIGATED + debt |
| `F02` | Provider latency degradation | p95 latency > SLO × 2 | Switch provider + enable cache | LOW | MITIGATED + debt |
| `F03` | Crash-loop / OOM | Restart/exit signal | Restart service + raise memory | LOW | RESOLVED |
| `F04` | Cache poisoning | Quality drop with healthy retrieval | Flush cache | LOW | RESOLVED |
| `F05` | Connection pool exhaustion | Connection errors + saturated pool | Reset pool / restart dependent | LOW | RESOLVED |
| `F06` | Retrieval collapse | Similarity below floor / empty context | Rebuild index from snapshot | MEDIUM | RESOLVED |
| `F07` | Prompt regression | Golden-set score drop | Roll back prompt | MEDIUM | RESOLVED |
| `F08` | Config regression | Config change + objective breach | Roll back config | MEDIUM | RESOLVED |
| `F09` | Token/cost blowout | Tokens > 3× baseline | Roll back prompt / clamp tokens | MEDIUM | RESOLVED |

`F06`–`F09` remain the stronger research-oriented scenarios.

### 7.1 Catalogue is data, not code

Adding `F10` should require no new Python branch in detection, RCA, safety or execution.

---

## 8. Core features

| ID | Feature | Priority |
|---|---|---|
| `F-SCN` | Manual scenario creation and replay | P0 |
| `F-CON` | Scenario contract parsing and validation | P0 |
| `F-EVID` | Evidence model with stable IDs | P0 |
| `F-EVAL` | Golden-set runner + scorers | P0 |
| `F-DET` | Objective breach + anomaly detection | P0 |
| `F-RCA` | Evidence-grounded RCA with confidence | P0 |
| `F-SAFE` | Deterministic safety gate | P0 |
| `F-TNR` | Writer lock, undo stack, witness, no-regression | P0 |
| `F-HEAL` | Simulated executor with mandatory inverse | P0 |
| `F-VER` | Multi-objective verification with deltas | P0 |
| `F-AUD` | Append-only hash-chained audit | P0 |
| `F-UI` | Live operations console | P0 |
| `F-MODE` | Simulation / Approval / Autonomous modes | P0 |
| `F-CAT` | Declarative catalogue interpreter | P1 |
| `F-DEBT` | Remediation debt | P1 |
| `F-MEM` | Incident knowledge base | P1 |
| `F-UNK` | Unknown-failure hypothesis flow | P1 |
| `F-LAYA` | Laya shadow decision engine | P2 |
| `F-BENCH` | Scenario evaluation benchmark runner | P1 |

### 8.1 Multi-objective verification

Verification returns a delta vector:

```python
VerificationResult(
    passed=True,
    outcome=MITIGATED,
    deltas={
        "availability": +0.99,
        "quality": -0.12,
        "latency": -0.30,
        "cost": +0.60,
    },
    tolerance_consumed={"quality": 0.80},
)
```

A repair that restores availability while reducing quality by 12% within tolerance is `MITIGATED`, not `RESOLVED`.

---

## 9. Laya

Laya is optional and later.

The deterministic rule engine remains the authority.

When evaluated:

- use `choice`, not `noul`, for gate-style decisions;
- gate on calibrated `confidence`, not `act_probability`;
- temperature-calibrate probabilities;
- use `choice` for LOW/MEDIUM/HIGH risk;
- keep Laya shadow-only until validated.

The purpose is to produce a research comparison, not to make the safety system dependent on an experimental decision model.

---

## 10. User flows

### 10.1 Manual scenario creation

Developer selects or submits `F01` scenario → Kavach validates the scenario → creates incident → begins the loop.

### 10.2 Autonomous LOW-risk simulated heal

`F01` scenario → Detected → Evidence → Diagnosed `provider_outage` → Plan `switch_model` → Safety Gate `ALLOW_AUTO` → Simulated execution → Verify → `MITIGATED` → debt created → audit.

### 10.3 Medium-risk approval

Scenario → RCA → plan → safety gate → `REQUIRE_APPROVAL` → console shows diagnosis, evidence, diff, inverse and risk rationale → human approves → simulated execute → verify.

### 10.4 Unknown failure

No catalogue match → collect wider evidence → rank hypotheses → propose candidates → return `ESCALATED`. In the MVP, unknown failures are not autonomously executed.

### 10.5 Verification failure → unwind

Verification fails → immediately unwind undo stack → verify restoration → `ESCALATED` if successful, `UNRECOVERABLE` if not.

### 10.6 Debt repayment

`MITIGATED` → debt recorded → simulated trigger fires → repayment proposal passes the same gate → execute → verify → debt cleared and incident becomes `RESOLVED`.

---

## 11. Requirements

### 11.1 Scenario and evidence

- `R-01` Validate every scenario before execution.
- `R-02` Every evidence item has a stable ID.
- `R-03` Scenario objectives include at least availability and quality for full verification.
- `R-04` Scenario state is isolated from any external application.

### 11.2 Detection and diagnosis

- `R-05` Detect objective breaches from scenario signals.
- `R-06` RCA emits fault class, confidence, evidence IDs and rejected alternatives.
- `R-07` RCA can return `INSUFFICIENT_EVIDENCE`.
- `R-08` No action is proposed below the configured confidence threshold.

### 11.3 TNR

- `R-09` Writer exclusivity.
- `R-10` Stack-based faithful undo.
- `R-11` No-regression check.
- `R-12` Inverses are deterministic data, never model-generated.

### 11.4 Safety gate

- `R-13` The gate can refuse.
- `R-14` Allow-list is explicit and deny-by-default.
- `R-15` Action without a working inverse cannot auto-execute.
- `R-16` Blast radius and circuit breaker stop repeated unsafe behaviour.
- `R-17` Idempotency key on every action.
- `R-18` The autonomous path can mutate only simulated state.

### 11.5 Verification and debt

- `R-19` Verification checks health, objectives and golden evaluation when available.
- `R-20` Verification returns a delta per objective.
- `R-21` Tolerance breach triggers unwind.
- `R-22` Every `MITIGATED` outcome creates debt.
- `R-23` Debt repayment uses the same safety gate.

### 11.6 Audit

- `R-24` Record incident, diagnosis, confidence, action, inverse, risk, timestamps, verification deltas and outcome.
- `R-25` Audit is append-only.
- `R-26` Audit records are hash-chained.

### 11.7 UX

- `R-27` Mode visible on every screen.
- `R-28` Live incident state without manual refresh.
- `R-29` Every diagnosis claim links to evidence.
- `R-30` Verification shows deltas, not a single pass/fail badge.
- `R-31` The UI clearly labels simulated execution.

### 11.8 Performance targets

Detection < 30s · RCA < 45s p95 locally · simulated LOW execution < 2s · full loop < 3 min · console first paint < 1.5s · live updates < 500ms.

---

## 12. Success metrics

The evaluation set consists of **manually authored scenarios**. Kavach never injects the faults.

Recommended initial evaluation:

```text
9 fault classes × 5 scenario replays = 45 runs
```

| Metric | Target |
|---|---|
| Scenario detection rate | ≥ 95% |
| Fault localisation accuracy | ≥ 80% |
| RCA accuracy | ≥ 75% |
| LOW-risk simulated auto-heal rate | ≥ 70% |
| **False-healing rate** | **≤ 5%** |
| Undo correctness | 100% |
| Mean time to detection | < 30s |
| Mean time to simulated recovery | < 3 min |
| Audit completeness | 100% |
| Simulation side-effect isolation | 100% |

### 12.1 Conditional metrics

Report:

- P(heal succeeds | diagnosis correct)
- P(heal succeeds | diagnosis wrong)
- P(diagnosis correct | heal succeeds)

This separates true reasoning from lucky symptom matching.

### 12.2 Baselines

- Rule-based diagnosis vs. LLM RCA on identical scenario replays.
- Undo enabled vs. undo ablated.
- Deterministic rule engine vs. Laya shadow.
- Human-resolved scenario replay as a timing baseline.

---

## 13. Out of scope for v1

**Explicitly excluded:**

- connecting to a real AI application;
- fault injection into another application;
- production self-healing;
- Docker socket control;
- Kubernetes;
- cloud deploy integrations;
- canary traffic splitting;
- multi-tenancy, RBAC, SSO;
- CI/CD integration;
- predictive failure forecasting;
- reinforcement learning for healing;
- multi-agent distributed incident management;
- external application onboarding / Proof #2;
- fine-tuned Laya in the live safety path;
- actions that delete data, drop databases, scale to zero or run migrations.

Real application integration is a future phase and requires a separate safety review.

---

## 14. Known risks

| Risk | Mitigation |
|---|---|
| **Confabulated RCA** | Evidence citations, `INSUFFICIENT_EVIDENCE`, calibrated confidence, closed fault vocabulary |
| **Simulation-to-real gap** | Explicit future runtime boundary; do not claim production autonomy from simulation alone |
| **Verification theatre** | Multi-objective probes and deltas |
| **Scope creep into external integration** | §13 is binding |
| **Catalogue refactor overruns** | Keep the simulator and closed loop working first |
| **Laya over-trust** | Shadow-only, deterministic safety gate remains authoritative |
| **Four people, one semester** | Prioritise one complete loop over breadth |
