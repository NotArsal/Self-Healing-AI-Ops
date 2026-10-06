# CONTRACT.md — The Healability Contract, v1

> **Specification.** What an AI application must expose to be autonomously recoverable.
>
> This document is versioned and specified independently of the platform that
> implements it. Kavach is the reference implementation; the contract is the
> claim. Changes here are breaking changes and require a version bump.

---

## 0. Why this exists

Every autonomous remediation system in the field attaches itself to whatever is running and infers what it can. That inference is where the failures come from: the agent does not know what "healthy" means for this application, which actions are permitted, what the last known-good state was, or whether its repair can be undone.

The contract inverts this. **An application declares its own recoverability.** A platform that cannot verify the declaration refuses to manage the application rather than guessing.

This is the project's generalizable contribution. The platform demonstrates it; the contract is what transfers.

### 0.1 The conformance test

The contract is only meaningful if it is sufficient. The test is binary:

> A person who has not read Kavach's source can onboard an AI application Kavach has never seen, in under one hour, by writing `kavach.yaml` and satisfying preflight — with **zero changes to Kavach's source code**.

If onboarding proof #2 requires a code change, the contract is incomplete and the missing thing belongs in this document.

---

## 1. Contract overview

Seven obligations. An application satisfying all seven is **healable**. Partial conformance is explicitly supported and bounded — see §9.

| # | Obligation | Without it |
|---|---|---|
| C1 | **Identity** — services, roles, dependencies | The platform cannot localise a fault |
| C2 | **Liveness** — a health endpoint per service | No recovery can be confirmed |
| C3 | **Quality** — a golden set and a scoring method | Silent degradation is undetectable |
| C4 | **Objectives** — a multi-objective SLO contract | "Healthy" is undefined |
| C5 | **Reversibility** — versioned prompts, config, index | No repair can be undone |
| C6 | **Permission** — an explicit action allow-list | Nothing is safe to execute |
| C7 | **Observability** — OTLP telemetry with GenAI spans | Diagnosis has no evidence |

---

## 2. C1 — Identity

The application declares every managed service, its role, and what it depends on.

```yaml
services:
  api:
    role: application          # application | vector_store | cache
    depends_on: [vector_store, model_primary]   # | model_primary | model_backup | datastore
  pgvector:
    role: vector_store
  redis:
    role: cache
  llm-proxy:
    role: model_primary
  ollama:
    role: model_backup
```

**Roles are a closed vocabulary**, not free text. The platform maps roles to candidate fault classes and candidate repairs, so an unrecognised role means an unmanageable service.

`depends_on` is what makes localisation possible: a fault in a dependency should not be diagnosed as a fault in its dependent.

**Obligation:** every service the platform may act on appears here. A service absent from this list is invisible and untouchable.

---

## 3. C2 — Liveness

Every declared service exposes a health check the platform can call without credentials.

```yaml
    health:
      type: http               # http | tcp | exec
      target: http://api:8080/healthz
      timeout_s: 3
      expect_status: 200
```

**Obligation:** the endpoint reflects the service's *own* readiness, not its dependencies'. A health check that returns 503 because the database is down makes every fault look like an application fault and destroys localisation.

---

## 4. C3 — Quality

The obligation nobody else imposes, and the one that makes this an *AI* operations contract.

An AI application can be fully available and completely wrong. Liveness and metrics cannot see this. The application must therefore supply a way to measure whether its *outputs* are still good.

```yaml
quality:
  golden_set: ./golden_set.yaml
  min_cases: 20
  scorers: [groundedness, answer_match, latency, cost]
  schedule_s: 300
  runner:
    type: http
    target: http://api:8080/v1/query
```

`golden_set.yaml`:

```yaml
cases:
  - id: gs-001
    question: "What is the refund window for damaged goods?"
    expect_context_ids: [doc-14#p3, doc-14#p4]
    expect_contains: ["30 days"]
```

**Obligations:**
- At least 20 cases. Below that, the pass rate is too noisy to gate on.
- Each case declares the context it should retrieve. Without `expect_context_ids`, retrieval collapse is invisible and `F06` cannot be detected.
- The runner is callable without a human.
- The golden set is in the application's repo and is the application owner's responsibility. The platform cannot author domain-specific ground truth.

---

## 5. C4 — Objectives

Health is a **vector**, not a boolean. This is the contract's second substantive departure from existing practice.

A repair that restores availability by failing over to a weaker model has not restored the application; it has traded quality for availability. A scalar healthy/unhealthy contract cannot express that trade, so a platform built on one will report success and learn the wrong lesson.

```yaml
objectives:
  availability:
    - metric: http_requests_errors_ratio
      comparator: "<"
      threshold: 0.01
      window_s: 120
      weight: 1.0              # breach severity multiplier
  latency:
    - metric: http_request_duration_seconds{quantile="0.95"}
      comparator: "<"
      threshold: 2.0
      window_s: 120
      weight: 0.6
  quality:
    - metric: kavach_eval_pass_rate
      comparator: ">="
      threshold: 0.85
      window_s: 300
      weight: 1.0
    - metric: kavach_eval_groundedness
      comparator: ">="
      threshold: 0.80
      window_s: 300
      weight: 0.8
  cost:
    - metric: kavach_tokens_per_request
      comparator: "<"
      threshold: 1200
      window_s: 300
      weight: 0.3

tolerance:                     # acceptable degradation during a MITIGATED state
  quality_drop_pct: 15
  latency_increase_pct: 50
  cost_increase_pct: 100
```

**Obligations:**
- At least one objective in `availability` and one in `quality`. An application declaring only availability objectives is conformant but **cannot be protected against silent degradation**, and the platform must say so at onboarding.
- `weight` derives the scalar severity used for the no-regression check (§7 of `ARCHITECTURE.md`). Weights are the application owner's statement of what matters.
- `tolerance` defines what counts as acceptable damage from a mitigation, which is what separates `RESOLVED` from `MITIGATED` (§8).

---

## 6. C5 — Reversibility

Every piece of state a repair may touch must be versioned and restorable to a prior value **without a model call**. Asking an LLM to reconstruct what it changed produces incomplete and hallucinated inverses; the prior state must be captured as data.

```yaml
reversible_state:
  prompts:
    kind: git_directory
    path: ./prompts            # one prompt per file, git-tracked
  config:
    kind: git_file
    path: ./config/app.yaml
  index:
    kind: snapshot
    snapshot_cmd: ./scripts/snapshot_index.sh
    restore_cmd: ./scripts/restore_index.sh {ref}
  model_selection:
    kind: runtime_config
    read: http://api:8080/v1/admin/model
    write: http://api:8080/v1/admin/model
```

**Obligations:**
- Prompts are **files**, one per prompt, in git. Prompts inlined in source cannot be rolled back independently of a code deploy, so `F07` is unreachable.
- `snapshot_cmd` is idempotent and returns a reference; `restore_cmd` accepts that reference.
- Restoring any declared state returns the application to byte-identical behaviour. This is the property the undo stack rests on.

---

## 7. C6 — Permission

```yaml
permissions:
  allowed_actions:             # DEFAULT IS EMPTY
    - switch_model
    - restart_container
    - flush_cache
    - rollback_prompt
    - rollback_config
    - rebuild_index
  forbidden_services: [pgvector]   # never act on these, any action
  max_risk_tier: MEDIUM            # ceiling regardless of mode
```

**Obligations:**
- **Default-deny.** An action not listed is refused regardless of operating mode, risk tier, diagnosis confidence, or how obviously correct it seems.
- The platform must refuse to enable an application whose allow-list references an action it cannot perform against the declared state.
- `forbidden_services` is an absolute veto, checked before anything else.

---

## 8. C7 — Observability

```yaml
telemetry:
  otlp_endpoint: http://otel-collector:4318
  semconv_version: "1.42.0"
  genai_instrumented: true
  required_attributes:
    - provider
    - request_model
    - input_tokens
    - output_tokens
    - operation_duration
```

**Obligations:**
- OTLP export over HTTP, reachable from the application's network.
- **GenAI-level instrumentation, not just HTTP spans.** Generic framework auto-instrumentation produces request traces with no model, token or provider information. Without those attributes, token blowout and model-level degradation have no signal.
- The declared `semconv_version` is pinned. The GenAI semantic conventions are `Development` status and attribute names have changed in flight, so an unpinned application's telemetry shape can change under the platform without warning.

---

## 8a. C7b — Dependencies (optional)

An application may declare the libraries and services it depends on. This is **not** a conformance obligation — an application that omits it is still fully healable — but declaring it lets the platform pre-fetch current documentation for those dependencies at onboarding, which grounds diagnosis of configuration and dependency faults and keeps the platform working offline.

```yaml
dependencies:
  - id: pgvector
    name: "pgvector"            # resolved to a library ID once, at onboarding
    version: "0.8.0"            # pins the docs to the version actually running
    role_hint: vector_store
  - id: fastapi
    name: "FastAPI"
    version: "0.115.0"
  - id: ollama
    name: "Ollama"
```

The platform resolves each `name` to a documentation-service library ID **once at onboarding** and stores it. Version-pinned IDs matter here: configuration defaults and parameter names change between releases, and documentation for the wrong version is worse than none.

**Obligations on the platform, not the application:**

- **Documentation is evidence, never instruction.** Retrieved text is untrusted input, cited alongside other evidence and never followed as a directive.
- **No application data leaves the machine.** Documentation queries are built from a fixed, human-reviewed template per fault class. Incident data — logs, config values, container names, prompts, environment, stack traces — is **never** interpolated into a query. External documentation services state plainly that credentials, personal data and proprietary code must not appear in queries, and an incident's evidence is exactly where those live.
- **Cached, with an offline guarantee.** After onboarding pre-warm the platform must function with no network access.
- **Non-fatal.** A lookup failure never blocks diagnosis.
- **Budgeted.** At most two documentation queries per incident.

## 9. Conformance levels

Partial conformance is supported, bounded, and reported at onboarding. An application is told exactly what it cannot be protected against.

| Level | Requires | Platform may |
|---|---|---|
| **L0 — Observed** | C1, C2, C7 | Detect and diagnose. Execute nothing |
| **L1 — Protected** | + C3, C4 | Detect quality degradation; propose repairs for approval |
| **L2 — Recoverable** | + C5, C6 | Execute allow-listed LOW-risk actions autonomously |
| **L3 — Healable** | All seven, verified at preflight | Full closed loop within the declared allow-list |

**Obligation on the platform:** at onboarding it must state the achieved level and enumerate the specific fault classes it cannot handle as a result. An application at L1 is told, in words, that it will detect a prompt regression and will not be able to roll it back.

---

## 10. Outcome states

The contract defines four terminal states. Most existing systems collapse the first two, which is why they over-report success.

| State | Meaning |
|---|---|
| `RESOLVED` | All objectives satisfied, no tolerance consumed. The fault is gone |
| `MITIGATED` | Availability restored within declared `tolerance`, but one or more objectives are degraded. **Creates remediation debt** |
| `ESCALATED` | No permitted repair, insufficient evidence, or verification failed and the undo stack was unwound |
| `UNRECOVERABLE` | Verification failed **and** the undo failed. Human intervention required immediately |

### 10.1 Remediation debt

A `MITIGATED` outcome is not an end state. Failing over to a backup model does not fix the provider outage; it moves the application to a degraded-but-stable position that somebody must eventually leave.

```yaml
debt:
  f01_provider_outage:
    repayment_action: switch_model      # back to primary
    trigger:
      metric: llm_proxy_health
      condition: healthy_for_s
      value: 600
    max_age_s: 86400                    # escalate if unpaid past this
```

**Obligations:**
- Every `MITIGATED` outcome records a debt with a repayment action and a machine-evaluable trigger.
- Debt is visible as a first-class object, not buried in incident history.
- Unpaid debt past `max_age_s` escalates.

v1 implements debt for `F01` only. The general case is specified here.

---

## 11. Preflight

Onboarding is a gate, not a configuration step. Every check below must pass before an application leaves `UNARMED`.

| # | Check | Obligation |
|---|---|---|
| P01 | `kavach.yaml` parses and validates against the schema | C0 |
| P02 | Git repository initialised, worktree clean | C5 |
| P03 | `kavach/ops` branch creatable, and is not the working branch | C5 |
| P04 | Runtime reachable; every declared service resolves and is running | C1 |
| P05 | Every declared health endpoint responds correctly | C2 |
| P06 | Golden set parses; ≥ `min_cases`; runner reachable; a full run completes | C3 |
| P07 | Every objective metric exists and currently returns a value | C4 |
| P08 | Every reversible state path exists; snapshot and restore both execute | C5 |
| P09 | Every allowed action has an adapter and a working inverse | C6 |
| P10 | No allowed action targets a `forbidden_services` entry | C6 |
| P11 | OTLP endpoint reachable; a test span round-trips | C7 |
| P12 | Required GenAI attributes present on a real span | C7 |
| P13 | Baseline captured: metrics window, eval scores, config hash, prompt versions, index snapshot | C4, C5 |

**Obligation:** a failed check blocks enablement and returns the exact remediation. "Preflight failed" with no instruction is a contract violation by the platform.

**P12 is the check most applications fail.** Standard framework auto-instrumentation satisfies P11 and fails P12.

---

## 12. Non-obligations

Deliberately not required, to keep the contract adoptable.

- No SDK, library, or code import. The contract is declarative.
- No specific vector store, model provider, or framework.
- No changes to application code beyond adding GenAI instrumentation and extracting prompts to files.
- No credentials handed to the platform beyond what `allowed_actions` needs.
- No Kubernetes, service mesh, or traffic-splitting infrastructure.

---

## 13. Open questions for v2

1. **Multi-instance applications.** The contract assumes one instance per service. Replica-aware objectives and canary routing are undefined.
2. **Cross-application dependencies.** `depends_on` is intra-application only.
3. **Quality scorer portability.** `groundedness` is defined by Kavach's implementation, not by the contract. A conformant application cannot currently supply its own scorer.
4. **Tolerance composition.** When two mitigations each consume tolerance, the contract does not say how they combine.
