# Autonomous Self-Healing AI Operations Platform

## Final Combined Architecture & Implementation Blueprint

> **Status:** Recommended architecture to implement
>
> **Project type:** Web-based Autonomous AI Operations Platform
>
> **Core loop:** Detect → Understand → Experiment → Heal → Verify → Remember → Improve
>
> **Primary implementation approach:** Kubernetes + OpenTelemetry + Prometheus/Loki/Tempo + FastAPI + LangGraph + Rust Healing Executor + PostgreSQL/pgvector + React/Next.js

---

# 1. Executive Summary

The project is a web-based Autonomous AI Operations Platform designed to monitor an AI/RAG application and its Kubernetes infrastructure, detect failures or abnormal behavior, investigate the likely root cause, plan safe recovery actions, execute only policy-approved actions, verify whether the system actually recovered, and retain verified incident knowledge for future incidents.

The platform is **not primarily a chatbot**, and it is not just a collection of restart scripts. The dashboard is the operator interface; the core system is the backend orchestration and controlled infrastructure automation beneath it.

The project combines two environments:

1. **Target AI System (the system being healed)**
   - FastAPI/RAG application
   - Vector database
   - LLM gateway/endpoint
   - Kubernetes deployment

2. **AIOps Platform (the system doing the healing)**
   - Web dashboard
   - FastAPI API gateway
   - Monitoring and incident managers
   - LangGraph orchestration
   - Investigation/RCA/repair planning
   - Risk and safety engine
   - Sandbox/canary validation
   - Rust-based Healing Executor
   - Verification engine
   - PostgreSQL + pgvector incident memory

The supplied research concludes that a complete public dataset containing metrics, logs, traces, AI responses, failures, root causes, recovery actions, and verification results is not available as one static dataset. Therefore, the end-to-end evaluation dataset should be generated through controlled fault injection against the project's own target system, while public benchmarks are used to inform/evaluate individual components.  

---

# 2. Final Product Definition

## What are we building?

> **A Kubernetes-based, web-accessible autonomous AIOps control platform with agentic investigation and RCA, risk-controlled remediation, isolated repair validation, automated verification, rollback/escalation, and persistent incident memory.**

The product should allow an operator to:

- view system health
- inspect services
- inspect logs, metrics and traces
- view active incidents
- see the investigation timeline
- view RCA hypotheses and evidence
- see proposed recovery actions
- see risk and confidence
- approve or reject risky actions
- observe sandbox testing
- observe healing execution
- inspect verification results
- inspect rollback events
- browse historical incidents
- see similar previous incidents
- see learning/self-improvement metrics

An optional AI console/chat interface can query the same underlying agent, but it is not the main product.

---

# 3. Architecture at a Glance

```text
                                  ┌──────────────────────────┐
                                  │        OPERATOR          │
                                  │                          │
                                  │  Web Dashboard           │
                                  │  Optional AI Console     │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │       API GATEWAY        │
                                  │          FastAPI         │
                                  └────────────┬─────────────┘
                                               │
                       ┌───────────────────────┼──────────────────────┐
                       │                       │                      │
                       ▼                       ▼                      ▼
                ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
                │ Monitoring   │       │ Incident     │       │ Configuration│
                │ Manager      │       │ Manager      │       │ Manager      │
                └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
                       │                       │                      │
                       └───────────────────────┼──────────────────────┘
                                               ▼
                                  ┌──────────────────────────┐
                                  │    AI ORCHESTRATOR       │
                                  │        LangGraph         │
                                  ├──────────────────────────┤
                                  │ Investigation Node       │
                                  │ RCA / Hypothesis Node    │
                                  │ Repair Planning Node     │
                                  │ Memory Retrieval Node    │
                                  │ Verification Node        │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │   DECISION / SAFETY      │
                                  │         ENGINE           │
                                  ├──────────────────────────┤
                                  │ Risk                     │
                                  │ Confidence               │
                                  │ Policy                   │
                                  │ Permissions              │
                                  │ Action Allowlist         │
                                  └────────────┬─────────────┘
                                               │
                     ┌─────────────────────────┼─────────────────────────┐
                     │                         │                         │
                     ▼                         ▼                         ▼
                  LOW RISK                MEDIUM RISK                HIGH RISK
                     │                         │                         │
                     │                         ▼                         ▼
                     │                  Sandbox / Shadow            Human Approval
                     │                         │                         │
                     │                         ▼                         │
                     │                      Canary                      │
                     │                         │                         │
                     └─────────────────────────┼─────────────────────────┘
                                               ▼
                                  ┌──────────────────────────┐
                                  │    HEALING EXECUTOR      │
                                  │          RUST             │
                                  │       Axum API            │
                                  │       kube-rs             │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │     KUBERNETES API       │
                                  │   ServiceAccount + RBAC  │
                                  └────────────┬─────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
             restart / scale              rollback                config change
                    │                          │                          │
                    └──────────────────────────┼──────────────────────────┘
                                               ▼
                                  ┌──────────────────────────┐
                                  │     TARGET AI SYSTEM     │
                                  │                          │
                                  │ FastAPI / RAG            │
                                  │ Retriever                │
                                  │ Vector DB / pgvector     │
                                  │ LLM Gateway              │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │      OBSERVABILITY        │
                                  ├──────────────────────────┤
                                  │ OpenTelemetry             │
                                  │ Prometheus                 │
                                  │ Loki                       │
                                  │ Tempo                      │
                                  └────────────┬─────────────┘
                                               │
                                               └──────────► Monitoring Manager

       ┌─────────────────────┐
       │    CHAOS ENGINE     │
       │ CPU / RAM / Network │
       │ DB / Pod / LLM      │
       └──────────┬──────────┘
                  │
                  └────────────────────────► TARGET AI SYSTEM

                                  ┌──────────────────────────┐
                                  │  VERIFICATION ENGINE     │
                                  ├──────────────────────────┤
                                  │ Health checks             │
                                  │ Metrics comparison        │
                                  │ Log/error checks           │
                                  │ Application tests         │
                                  │ Optional RAG quality     │
                                  └────────────┬─────────────┘
                                               │
                                   ┌───────────┴───────────┐
                                   ▼                       ▼
                                SUCCESS                  FAILURE
                                   │                       │
                                   ▼                       ▼
                                 LEARN            ROLLBACK / ESCALATE
                                   │                       │
                                   └───────────┬───────────┘
                                               ▼
                                  ┌──────────────────────────┐
                                  │    KNOWLEDGE / MEMORY    │
                                  │                          │
                                  │ PostgreSQL                │
                                  │ pgvector                  │
                                  │ Incident History          │
                                  │ Repair Knowledge          │
                                  │ Runbooks                  │
                                  └──────────────────────────┘
```

---

# 4. Why the Architecture Is Split This Way

The architecture intentionally separates responsibilities.

| Layer | Responsibility |
|---|---|
| Web Dashboard | Operator visibility and control |
| FastAPI | External API and backend coordination |
| Managers | Monitoring, incidents and configuration abstraction |
| LangGraph | Stateful reasoning and workflow orchestration |
| Safety Engine | Risk/confidence/policy/permission decisions |
| Sandbox | Safe validation of selected repairs |
| Healing Executor | Controlled infrastructure actions |
| Kubernetes RBAC | Technical permission boundary |
| Observability | Metrics, logs and traces |
| Verification | Determines whether recovery actually worked |
| PostgreSQL/pgvector | Incident memory and similarity search |
| Chaos Engine | Controlled experimental failures |

This prevents the LLM from becoming an unrestricted administrator of the infrastructure.

---

# 5. Target AI System: The System Being Healed

For the college project, the target system should be a small RAG application built and controlled by the team.

```text
User
  │
  ▼
FastAPI / RAG API
  │
  ├──────────────► Retriever
  │                    │
  │                    ▼
  │               Vector Database
  │                    │
  │                    ▼
  └──────────────► LLM Gateway
                       │
                       ▼
                    Response
```

The target system should be deployed inside Kubernetes so its services, dependencies and resources can be observed and deliberately stressed.

Recommended components:

- FastAPI
- RAG pipeline
- PostgreSQL + pgvector or another controlled vector store
- LLM API/model endpoint
- health endpoints
- structured logs
- OpenTelemetry instrumentation

The original research recommends deploying a target RAG application consisting of FastAPI, pgvector and an LLM endpoint, applying synthetic user load, collecting baseline telemetry and then injecting faults. 

---

# 6. Kubernetes Environment

The project should run as a set of isolated Kubernetes namespaces.

```text
Kubernetes Cluster
│
├── target-system/
│   ├── rag-api
│   ├── vector-db
│   ├── llm-gateway
│   └── supporting services
│
├── aiops/
│   ├── fastapi
│   ├── langgraph
│   ├── verification
│   └── rust-healing-executor
│
├── observability/
│   ├── opentelemetry-collector
│   ├── prometheus
│   ├── loki
│   └── tempo
│
├── memory/
│   └── postgresql + pgvector
│
├── chaos/
│   └── fault injection jobs/experiments
│
└── sandbox/
    └── temporary validation namespaces
```

Namespaces provide a practical isolation mechanism for the college environment.

The project's first version should target a local Kubernetes environment such as Docker Desktop Kubernetes or another compatible cluster.

---

# 7. Observability Architecture

The system must collect three primary telemetry signals:

```text
                    TARGET SYSTEM
                          │
               OpenTelemetry instrumentation
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Metrics        Logs        Traces
             │            │            │
             ▼            ▼            ▼
       Prometheus        Loki         Tempo
             │            │            │
             └────────────┼────────────┘
                          ▼
                 Monitoring Manager
```

## Metrics

Prometheus collects time-series signals such as:

- CPU utilization
- memory utilization
- request rate
- error rate
- latency
- pod restarts
- service health
- resource pressure
- RAG latency
- LLM latency

## Logs

Loki stores/query application and infrastructure logs such as:

- HTTP 500 errors
- database connection failures
- timeout messages
- OOMKilled events
- rate limit failures
- model errors
- dependency failures

## Traces

OpenTelemetry + Tempo provide distributed request traces.

Example:

```text
Trace ID: 8f2d...

RAG API          25 ms
Retriever        42 ms
Vector DB       1900 ms  <── suspicious
LLM              150 ms
```

## Trace correlation

The system should use a consistent trace identifier to connect:

```text
incident
   │
   ├── metrics context
   ├── logs
   ├── trace spans
   └── AI response evaluation
```

The original research explicitly recommends keeping metrics, logs and traces in specialized stores and linking them using a standardized trace ID rather than flattening everything into one file. 

---

# 8. Monitoring Manager

The Monitoring Manager is a backend abstraction layer.

Its job is to hide observability implementation details from the rest of the platform.

For example:

```text
LangGraph
    │
    └── query_metrics(service="vector-db")
                     │
                     ▼
             Monitoring Manager
                     │
              ┌──────┼───────┐
              ▼      ▼       ▼
         Prometheus  Loki   Tempo
```

The agent should not need to know how Prometheus, Loki or Tempo are deployed.

Example internal functions:

```text
query_metrics()
query_logs()
get_trace()
get_service_health()
get_recent_events()
compare_with_baseline()
```

---

# 9. Failure Detection Layer

The Detection layer answers:

> **Is something abnormal happening?**

It should not initially decide how to fix the problem.

Recommended MVP detection:

```text
Prometheus Alerts
      +
Baseline Deviation
      +
Health Checks
      +
Simple statistical rules
```

Examples:

```text
IF error_rate > 10%
    → incident

IF p95_latency > 3 × baseline
    → incident

IF memory_usage > 90%
    → incident

IF pod health = failed
    → incident
```

ML-based anomaly detection may be added later but should not be a dependency of the MVP.

The supplied research similarly argues that failure detection can use robust statistical methods and Prometheus alerting instead of forcing a custom deep-learning detector into the platform. 

---

# 10. Incident Manager

Once a detection rule fires, the Incident Manager creates the central incident object.

Example:

```json
{
  "incident_id": "INC-0042",
  "timestamp": "2026-09-19T18:20:00Z",
  "affected_service": "vector-db",
  "severity": "HIGH",
  "failure_type": "high_latency",
  "status": "INVESTIGATING",
  "trace_ids": ["8f2d..." ]
}
```

The incident state should move through explicit workflow states.

```text
DETECTED
   ↓
INVESTIGATING
   ↓
RCA_READY
   ↓
REPAIR_PLANNED
   ↓
SAFETY_CHECK
   ↓
SANDBOX_TEST        (when required)
   ↓
APPROVAL            (when required)
   ↓
EXECUTING
   ↓
VERIFYING
   ├──→ RESOLVED
   ├──→ ROLLBACK
   └──→ ESCALATED
```

This stateful workflow is one of the main reasons LangGraph is useful in the system.

---

# 11. AI Orchestrator: LangGraph

LangGraph should be the central workflow engine.

It should manage state rather than simply sending one large prompt to an LLM.

```text
Incident
   ↓
Load Context
   ↓
Investigation
   ↓
RCA / Hypotheses
   ↓
Historical Retrieval
   ↓
Repair Planning
   ↓
Safety Decision
   ↓
Sandbox / Approval
   ↓
Healing
   ↓
Verification
   ↓
Memory
```

## Important implementation decision

Do **not** begin with six independent LLM agents.

Use one LangGraph orchestration workflow with specialized nodes/tools.

Recommended logical nodes:

```text
Investigation Node
        ↓
RCA / Hypothesis Node
        ↓
Memory Retrieval Node
        ↓
Repair Planning Node
        ↓
Safety Decision Node
        ↓
Execution Node
        ↓
Verification Node
        ↓
Learning / Memory Node
```

Later, selected nodes can be split into independent agents if there is a clear benefit.

---

# 12. Investigation Layer

The investigation stage collects evidence before deciding on a repair.

Available tools should include:

```text
query_metrics()
query_logs()
get_trace()
inspect_pod()
inspect_deployment()
inspect_events()
inspect_service()
inspect_dependencies()
retrieve_similar_incidents()
```

Example:

```text
Incident:
RAG API latency increased

Investigation:
├── Metrics → CPU normal
├── Logs → DB timeouts
├── Traces → vector-db span = 1.9 sec
├── Kubernetes → vector-db pod memory = 94%
└── Memory → similar incidents found
```

The agent now has evidence rather than relying only on the initial alert.

---

# 13. RCA / Hypothesis Engine

The RCA stage should not blindly claim certainty.

Instead it should produce hypotheses with evidence and confidence.

Example:

```text
H1:
Vector DB memory pressure
Confidence: 0.86
Evidence: high memory + latency + I/O wait

H2:
Database network degradation
Confidence: 0.42
Evidence: intermittent timeout logs

H3:
Bad deployment
Confidence: 0.18
Evidence: no recent deployment detected
```

This is more defensible than saying:

> "The AI knows the exact cause."

For unknown incidents, the objective is evidence-driven investigation, candidate generation, controlled testing, verification and escalation where appropriate.

---

# 14. Incident Memory and RAG

Historical incidents become operational memory.

```text
Current Incident
      ↓
Create embedding
      ↓
pgvector similarity search
      ↓
Similar verified incidents
      ↓
Retrieve successful/failed actions
      ↓
Provide context to LangGraph
```

Example:

```text
Current:
"GPU allocation failures + 99% GPU memory + high inference latency"

Retrieved:
INC-017
INC-034
INC-083

Previous successful action:
Restart GPU worker
```

The memory system should retain both successes and failed attempts where possible.

Recommended information:

- incident
- symptoms
- telemetry context
- hypotheses
- evidence
- actions attempted
- successful action
- failed actions
- side effects
- confidence
- verification result
- MTTD
- MTTR

This allows learning without continuously retraining the LLM.

---

# 15. Repair Planner

After investigation, the Repair Planner produces candidate actions.

Example:

```text
Root cause hypothesis:
Vector DB memory pressure

Candidate actions:

1. Restart vector-db
2. Increase memory limit
3. Scale vector-db
4. Change retrieval configuration
```

Each action should have metadata:

```text
Action ID
Risk level
Required permissions
Expected effect
Rollback strategy
Sandbox requirement
Canary requirement
```

---

# 16. Decision / Safety Engine

This component determines whether the proposed action is allowed.

```text
Repair Candidate
       ↓
Risk Assessment
       ↓
Confidence Assessment
       ↓
Policy Check
       ↓
Permission Check
       ↓
Decision
```

Recommended policy:

| Risk | Example | Behaviour |
|---|---|---|
| Low | retry API, restart non-critical worker, clear cache | can be automatic |
| Medium | scale service, restart important service, rollback | sandbox/canary or stronger confidence |
| High | destructive DB operation, data deletion, major infra change | human approval / prohibited |

The system should also provide:

```text
Emergency Kill Switch
Manual Override
Audit Trail
Action Allowlist
Timeouts
Rate Limits
```

The safety engine is deterministic policy code. The LLM proposes actions, but the policy engine decides whether they are permitted.

---

# 17. Sandbox / Shadow Environment

A perfect digital twin of a production system is out of scope for the college MVP.

Instead, implement a practical **sandbox namespace**.

```text
Target system
     │
     │ candidate repair
     ▼
Sandbox namespace
     │
     ├── relevant service
     ├── required dependency
     └── test configuration
     │
     ▼
Synthetic workload
     │
     ▼
Measure result
```

Example:

```text
Candidate:
Increase vector-db memory from 512Mi → 1Gi

Sandbox:
Deploy candidate configuration
Run controlled workload
Measure:
- latency
- errors
- resource behaviour

Result:
PASS
```

A sandbox reduces risk but cannot guarantee identical production behaviour. Therefore the architecture should still support canary deployment and rollback.

---

# 18. Canary Deployment

Canary deployment is an advanced safety layer for changes that affect actual workloads.

Conceptually:

```text
Old Version ──────── 95% traffic

New Repair ───────── 5% traffic
                          │
                          ▼
                    Verification
                          │
                    ┌─────┴─────┐
                    ▼           ▼
                   PASS        FAIL
                    │           │
                    ▼           ▼
              Gradual rollout  Rollback
```

Canary is especially useful for:

- new deployment versions
- configuration changes
- model version changes
- rollback testing

It does not need to be used for every low-risk action.

---

# 19. Rust Healing Executor

## Why use Rust?

Rust should be used where it provides a real engineering benefit instead of simply adding another language.

The recommended use is the **Healing Executor / Infrastructure Control Worker**.

Responsibilities:

- execute approved recovery actions
- communicate with Kubernetes
- enforce execution-level validation
- apply timeouts
- perform pre-checks and post-checks
- create audit events
- provide a small, strongly typed action API

Current `kube-rs` provides a Rust Kubernetes client and controller/runtime tooling for applications that interact with Kubernetes. Current documentation shows the client can connect to Kubernetes and work with typed APIs/resources. 

Rust's `axum` provides a modern HTTP routing/server layer, making it suitable for exposing the internal Healing Executor API. 

## Proposed Rust service

```text
                FastAPI / LangGraph
                        │
                 approved action
                        │
                        ▼
             ┌──────────────────────┐
             │ Rust Healing         │
             │ Executor             │
             │                      │
             │ Axum                 │
             │ kube-rs              │
             │ policy guards        │
             │ timeouts             │
             │ audit logging        │
             └──────────┬───────────┘
                        │
                        ▼
                 Kubernetes API
                        │
                      RBAC
                        │
                        ▼
                  Target System
```

## Example Rust service actions

The service should expose a controlled action contract such as:

```text
POST /actions/restart-service
POST /actions/scale-service
POST /actions/rollback
POST /actions/update-resources
POST /actions/verify-pod
GET  /actions/{id}
```

The exact API can be REST for MVP simplicity. Internal gRPC can be considered later if the team has a clear need.

## Example action object

```json
{
  "incident_id": "INC-0042",
  "action": "restart_service",
  "target": "vector-db",
  "namespace": "target-system",
  "reason": "approved by safety policy",
  "timeout_seconds": 60
}
```

## What Rust should NOT do

Rust should not host the LLM reasoning or LangGraph workflow.

Do not replace the Python LangGraph layer with Rust just for the sake of using Rust.

The separation should remain:

```text
Python
→ reasoning / orchestration / AI

Rust
→ controlled infrastructure execution
```

OpenTelemetry currently documents Rust APIs/SDKs and OTLP exporters, but its Rust traces/metrics/logs implementations are currently marked Beta. Therefore, the architecture should rely on the OpenTelemetry Collector and established observability backends as the central telemetry pipeline, while the Rust service can be instrumented with OTel where appropriate. 

---

# 20. Kubernetes RBAC Boundary

The Healing Executor must not receive unrestricted cluster-admin access.

Recommended security boundary:

```text
LangGraph
    ↓
FastAPI
    ↓
Rust Healing Executor
    ↓
Kubernetes API
    ↓
ServiceAccount
    ↓
RBAC Role / RoleBinding
    ↓
Approved Namespace / Resources
```

Example permissions might allow only:

```text
read:
- pods
- events
- deployments
- services

write:
- restart approved workloads
- scale approved deployments
- rollback approved deployments
```

High-risk operations should not be available through the executor by default.

---

# 21. Verification Engine

The verification engine is a separate subsystem because successful command execution does not mean successful recovery.

```text
Recovery Action
      ↓
Wait / Stabilize
      ↓
Health Check
      ↓
Metric Comparison
      ↓
Log/Error Check
      ↓
Application Test
      ↓
Optional AI/RAG Quality Check
      ↓
PASS / FAIL
```

Example:

```text
BEFORE
error rate   = 18%
p95 latency  = 4.2 s
health       = FAIL

ACTION
restart vector-db

AFTER
error rate   = 0.8%
p95 latency  = 310 ms
health       = PASS

RESULT
VERIFIED
```

If the recovery fails:

```text
Verification FAIL
       ↓
Try approved next action OR rollback
       ↓
Verification again
       ↓
If still failing → human escalation
```

The project's supplied research explicitly treats verification as a separate post-recovery check and recommends measuring MTTD and MTTR along with recovery success. 

---

# 22. Rollback and Escalation

The system must have a failure path.

```text
                 Verification
                      │
              ┌───────┴────────┐
              ▼                ▼
           SUCCESS           FAILURE
              │                │
              ▼                ▼
            Learn        Rollback / Retry
                               │
                         ┌─────┴─────┐
                         ▼           ▼
                       PASS        FAIL
                         │           │
                         ▼           ▼
                       Learn      Escalate
```

The AI should not repeatedly execute increasingly dangerous actions without a boundary.

Recommended controls:

- maximum retry count
- maximum healing time
- action cooldown
- risk escalation
- kill switch
- human escalation

---

# 23. Knowledge / Memory Architecture

PostgreSQL should be the structured source of truth for incidents.

pgvector should provide similarity search over incident embeddings.

```text
                     PostgreSQL
             ┌────────────────────────┐
             │ incidents              │
             │ hypotheses             │
             │ actions                 │
             │ verification            │
             │ runbooks                │
             │ audit records           │
             └───────────┬────────────┘
                         │
                         ▼
                      pgvector
                         │
                         ▼
                  Similarity Search
```

The design should keep raw/high-volume telemetry outside PostgreSQL when practical and store references/context needed for incident reasoning inside PostgreSQL.

---

# 24. Suggested Database Schema

## incidents

```text
incident_id          UUID / PK
timestamp_detected   timestamp
affected_service     string
failure_type         string
severity             enum
status               enum
root_cause           text
confidence            float
trace_id             string
resolution_status    string
mttd_ms              integer
mttr_ms              integer
created_at           timestamp
```

## incident_evidence

```text
evidence_id
incident_id
source_type          metrics | logs | trace | k8s | application
source_reference
summary
created_at
```

## hypotheses

```text
hypothesis_id
incident_id
cause
confidence
evidence_summary
accepted
```

## recovery_actions

```text
action_id
incident_id
action_type
target
risk_level
parameters
status
timestamp_executed
```

## verification_results

```text
verification_id
incident_id
action_id
latency_before
latency_after
error_rate_before
error_rate_after
health_before
health_after
success
rollback_required
```

## incident_embeddings

```text
incident_id
embedding
metadata
```

---

# 25. Chaos / Fault Injection Layer

The Chaos Engine exists primarily for controlled testing, experimentation and dataset generation.

```text
                 Chaos Engine
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
      CPU/RAM      Network       Service
        faults       faults        faults
         │            │            │
         └────────────┼────────────┘
                      ▼
                Target System
```

Recommended initial fault scenarios:

1. CPU saturation
2. Memory exhaustion / OOM
3. Pod crash
4. Network delay
5. Packet loss
6. Database connection failure
7. LLM API rate limiting
8. High external API latency
9. Retrieval degradation
10. Node pressure / eviction

The supplied research recommends controlled fault injection using approaches such as LitmusChaos, Toxiproxy, `stress-ng`, Linux `tc`, and custom scripts. 

---

# 26. End-to-End Incident Example

This is the most important flow to understand before implementation.

## Step 1: Normal state

```text
RAG API
  ↓
Vector DB
  ↓
LLM

Status = HEALTHY
```

## Step 2: Fault injection

Chaos Engine injects network delay between the RAG API and vector DB.

```text
Vector DB response latency
50 ms → 1200 ms
```

## Step 3: Detection

Prometheus notices latency/error-rate deviation.

```text
ALERT:
vector_db_latency_high
```

## Step 4: Incident creation

```text
INC-0042
status = INVESTIGATING
```

## Step 5: Investigation

LangGraph queries:

```text
metrics
logs
traces
Kubernetes state
historical incidents
```

## Step 6: RCA

The agent concludes:

```text
Likely cause:
network degradation affecting vector-db communication

Confidence:
0.87
```

## Step 7: Repair candidates

```text
1. Restart vector-db
2. Restart network proxy
3. Retry connections
```

## Step 8: Safety decision

Suppose the selected action is medium risk.

```text
Safety Engine
→ Sandbox required
```

## Step 9: Sandbox

Candidate repair is tested in a temporary sandbox namespace.

```text
Result = PASS
```

## Step 10: Healing Executor

LangGraph sends an approved action to the Rust service.

```text
FastAPI
 ↓
Rust Healing Executor
 ↓
kube-rs
 ↓
Kubernetes API
 ↓
restart vector-db
```

## Step 11: Verification

```text
error rate: 17% → 0.7%
latency: 1.2 s → 280 ms
health: FAIL → PASS
```

## Step 12: Learn

```text
INC-0042
→ root cause stored
→ action stored
→ verification stored
→ embedding stored
```

Future incidents can retrieve this experience.

---

# 27. Unknown Failure Flow

Unknown failures are one of the advanced directions of the project.

The system should not assume that every failure has a predefined rule.

```text
UNKNOWN ANOMALY
      ↓
Evidence Collection
      ↓
Metrics + Logs + Traces + K8s State
      ↓
Generate Hypotheses
      ↓
Retrieve Similar Incidents
      ↓
Generate Candidate Repairs
      ↓
Risk Assessment
      ↓
Sandbox / Human Approval
      ↓
Controlled Execution
      ↓
Verification
      ↓
Success → Learn
Failure → Rollback / Escalate
```

The project claim should be:

> The platform can investigate previously unseen anomalies, evaluate risk-controlled recovery candidates, verify outcomes, and retain verified solutions for future incidents.

It should **not** claim that the AI can solve every unknown problem.

---

# 28. Web Dashboard Architecture

The dashboard should be a React/Next.js application.

```text
Next.js / React
       │
       ▼
FastAPI API Gateway
       │
       ├── system health
       ├── incident APIs
       ├── RCA APIs
       ├── healing APIs
       ├── approval APIs
       └── history APIs
```

Recommended screens:

## Overview

- overall health
- active incidents
- MTTD
- MTTR
- recovery success rate
- service status

## Incident Detail

- incident timeline
- symptoms
- metrics
- logs
- trace
- hypotheses
- confidence
- root cause

## Healing

- candidate actions
- risk level
- safety status
- sandbox status
- approval status
- execution status

## Verification

- before/after metrics
- health checks
- error rates
- recovery result
- rollback status

## Memory

- previous incidents
- similar incidents
- successful actions
- failed actions
- runbooks

## Optional AI Console

Example questions:

```text
Why is the vector DB failing?

What evidence supports the current root cause?

What did you do to recover Incident #42?

Have we seen a similar incident before?
```

---

# 29. API Gateway Responsibilities

FastAPI should expose external application APIs while hiding internal implementation.

Example endpoints:

```text
GET    /health
GET    /system/status
GET    /services
GET    /incidents
GET    /incidents/{id}
GET    /incidents/{id}/timeline
GET    /incidents/{id}/evidence
POST   /incidents/{id}/approve
POST   /incidents/{id}/reject
POST   /incidents/{id}/stop
POST   /chaos/inject
GET    /metrics/summary
GET    /learning/summary
```

FastAPI should call internal managers and the LangGraph service rather than allowing the frontend to interact directly with Kubernetes or Prometheus.

---

# 30. Internal Service Boundaries

Recommended boundary:

```text
Frontend
   │
   ▼
FastAPI
   │
   ├── Monitoring Manager
   ├── Incident Manager
   ├── Configuration Manager
   └── LangGraph Orchestrator
             │
             ├── Observability tools
             ├── Memory tools
             ├── Safety Engine
             └── Rust Healing Executor
```

This keeps the architecture understandable and testable.

---

# 31. Where Rust Fits in the Final Stack

Rust should be a **purposeful subsystem**, not a replacement for the whole project.

| Component | Language | Reason |
|---|---|---|
| Web Dashboard | TypeScript | Modern web UI |
| API Gateway | Python / FastAPI | Fits AI/agent backend and existing project stack |
| LangGraph | Python | LangGraph ecosystem |
| RCA/LLM integration | Python | AI SDK/model ecosystem |
| Incident memory | PostgreSQL | Structured persistence |
| Vector search | pgvector | Incident similarity |
| Healing Executor | **Rust** | Strongly typed, low-level, concurrent control layer |
| Kubernetes client | **Rust / kube-rs** | Typed Kubernetes API access |
| Telemetry | OpenTelemetry Collector + backends | Mature central observability architecture |
| Infrastructure | Kubernetes | Deployment and isolation |

Current `kube-rs` documentation describes it as a Rust Kubernetes client with typed API and runtime/controller capabilities. 

---

# 32. Repository Structure

Recommended repository:

```text
self-healing-aiops/
│
├── README.md
├── LICENSE
├── .env.example
├── docker-compose.dev.yml
│
├── dashboard/
│   ├── app/
│   ├── components/
│   └── lib/
│
├── api-gateway/
│   ├── app/
│   ├── routers/
│   ├── services/
│   └── models/
│
├── orchestrator/
│   ├── graph/
│   ├── nodes/
│   ├── prompts/
│   ├── tools/
│   └── state/
│
├── safety-engine/
│   ├── policies/
│   ├── risk.py
│   └── permissions.py
│
├── healing-executor-rs/
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs
│       ├── api.rs
│       ├── kubernetes.rs
│       ├── actions.rs
│       ├── policy.rs
│       └── audit.rs
│
├── target-app/
│   ├── rag-api/
│   ├── retriever/
│   ├── vector-db/
│   └── llm-gateway/
│
├── observability/
│   ├── otel/
│   ├── prometheus/
│   ├── loki/
│   └── tempo/
│
├── chaos/
│   ├── cpu/
│   ├── memory/
│   ├── network/
│   ├── database/
│   └── llm/
│
├── memory/
│   ├── migrations/
│   ├── repositories/
│   └── embeddings/
│
├── verification/
│   ├── health_checks/
│   ├── metric_checks/
│   └── evaluation/
│
├── helm/
│   └── self-healing-aiops/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│
├── k8s/
│   ├── namespaces/
│   ├── rbac/
│   └── policies/
│
├── scripts/
│   ├── setup.ps1
│   ├── setup.sh
│   ├── start.ps1
│   ├── stop.ps1
│   └── cleanup.ps1
│
├── evaluation/
│   ├── scenarios/
│   ├── metrics/
│   └── reports/
│
└── docs/
    ├── architecture.md
    ├── setup.md
    ├── api.md
    └── viva.md
```

---

# 33. User Installation Model

The project should feel like a deployable developer platform.

## User prerequisites

Recommended initial support:

- Docker Desktop or another local Kubernetes environment
- Git
- kubectl
- Helm

## User flow

```text
Install prerequisites
        ↓
Clone GitHub repository
        ↓
Create .env
        ↓
Add LLM API key
        ↓
Run setup script
        ↓
Helm deploys platform
        ↓
Target RAG app starts
        ↓
Observability starts
        ↓
AIOps services start
        ↓
Dashboard becomes available
```

Target experience:

```powershell
git clone <repository>
cd self-healing-aiops
copy .env.example .env
# add LLM API key
.\scripts\setup.ps1
```

For Linux/macOS:

```bash
git clone <repository>
cd self-healing-aiops
cp .env.example .env
# add LLM API key
./scripts/setup.sh
```

The setup script should handle:

```text
cluster check
namespace creation
Helm installation
observability deployment
target application deployment
AIOps deployment
RBAC deployment
memory database setup
port forwarding / local access
health checks
```

The user should not manually install Prometheus, Loki, Tempo, PostgreSQL, the target RAG application, or the AIOps components one by one.

---

# 34. Public Dataset vs Custom Incident Dataset

The project should use a hybrid evaluation strategy.

## Public benchmarks

Use relevant public benchmarks for:

- understanding RCA data structures
- anomaly detection comparison
- RAG/AI evaluation methodology
- agentic RCA evaluation

Examples discussed in the research include:

- RCAEval
- Cloud-OpsBench
- SREGym
- LogHub
- RAGBench
- ARES

These datasets should not be treated as a single unified production dataset.

## Custom operational dataset

Generate project-specific incident data through controlled experiments.

```text
Target System
      ↓
Fault Injection
      ↓
Telemetry
      ↓
Detection
      ↓
RCA
      ↓
Healing
      ↓
Verification
      ↓
Incident Record
```

The research recommends a hybrid approach where public benchmark methodologies are used as calibrators, while the actual end-to-end operational dataset is generated through controlled fault injection. 

---

# 35. Dataset Generation Pipeline

Recommended experimental loop:

```text
1. Deploy target application
        ↓
2. Generate baseline workload
        ↓
3. Collect normal telemetry
        ↓
4. Inject randomized fault
        ↓
5. Observe degradation
        ↓
6. Detect incident
        ↓
7. Run RCA
        ↓
8. Execute recovery
        ↓
9. Verify result
        ↓
10. Store incident
        ↓
11. Reset environment
        ↓
12. Repeat
```

Avoid deterministic signatures that allow the system to merely recognize the chaos tool.

For example:

```text
Bad:
CPU fault = exactly 99% for exactly 60 seconds every time

Better:
CPU target randomized between approximately 80–100%
```

Likewise, network degradation should use varied intensities rather than one identical fixed value.

The supplied research highlights this as important for avoiding synthetic-data leakage and overfitting to the injection mechanism. 

---

# 36. Evaluation Metrics

The project should report measurable results.

## Detection

- MTTD (Mean Time To Detect)
- detection precision/recall where appropriate
- false-positive rate

## RCA

- root-cause accuracy against known injected truth
- top-k hypothesis accuracy
- confidence calibration

## Healing

- recovery success rate
- MTTR (Mean Time To Recovery)
- rollback rate
- action failure rate

## Autonomy / Safety

- human intervention rate
- percentage of actions auto-approved
- blocked high-risk actions
- unsafe action prevention count

## Learning

- similar-incident retrieval accuracy
- repeated-incident rate
- improvement in MTTR for repeated incident classes
- percentage of verified incidents converted into reusable knowledge

The original research specifically recommends evaluating MTTD, MTTR and RCA accuracy against known injected failures. 

---

# 37. MVP Scope

The team should implement these components first:

```text
MVP
├── Target RAG application
├── Docker
├── Kubernetes
├── OpenTelemetry
├── Prometheus
├── Loki
├── Tempo
├── Detection rules
├── Incident Manager
├── LangGraph orchestrator
├── Investigation tools
├── RCA
├── Repair Planner
├── Safety Engine
├── Rust Healing Executor
├── 4–5 recovery actions
├── Verification Engine
├── PostgreSQL + pgvector
├── Web Dashboard
└── 5–10 fault scenarios
```

The MVP should demonstrate:

> **Detect → Diagnose → Repair → Verify → Remember**

---

# 38. Advanced Features

Add only after the MVP works.

```text
Phase 2
├── Unknown-failure investigation
├── Sandbox namespace automation
├── Risk scoring improvements
├── Canary deployment
└── Automatic rollback

Phase 3
├── Multi-agent specialization
├── Runbook generation
├── Incident replay
├── Predictive healing
└── Advanced self-improvement analytics
```

Do not make the project depend on all of these.

---

# 39. What Not to Build First

Avoid these as MVP requirements:

- a browser extension
- a fully autonomous unrestricted shell agent
- a perfect digital twin of an entire cloud environment
- continuous automatic LLM fine-tuning
- six independent LLM agents
- a custom deep-learning model for every detection problem
- support for every possible Kubernetes operation
- support for arbitrary third-party production clusters before the local demo works

These add complexity without improving the core demonstration enough.

---

# 40. Security Model

The minimum security model should contain:

```text
LLM
 ↓
Structured Tool Call
 ↓
Safety Engine
 ↓
Risk Policy
 ↓
Rust Executor
 ↓
Kubernetes RBAC
 ↓
Target Namespace
```

Additional controls:

- no unrestricted cluster-admin permissions
- explicit action allowlist
- action parameter validation
- timeouts
- retry limits
- audit logs
- kill switch
- human approval for high-risk actions
- sandbox before medium/high-risk changes where appropriate

---

# 41. Architectural Principles

The entire implementation should follow these principles.

### Principle 1 — Observe before acting

The agent should collect evidence before proposing a repair.

### Principle 2 — Reason, don't blindly execute

The LLM generates hypotheses and candidate actions.

### Principle 3 — Policy controls autonomy

Risk and permissions are deterministic boundaries around the agent.

### Principle 4 — Verification is mandatory

A completed command is not proof of recovery.

### Principle 5 — Failed recovery has a path

Use retry, rollback or human escalation.

### Principle 6 — Learn from verified incidents

Persist successful and failed experiences instead of continuously retraining the model.

### Principle 7 — Keep specialized data stores separate

Metrics, logs, traces and structured incident memory serve different purposes.

### Principle 8 — Use Rust where it matters

Rust owns the infrastructure-control boundary; Python owns AI reasoning/orchestration.

### Principle 9 — MVP before research extensions

The basic self-healing loop must work before adding predictive healing or multi-agent complexity.

### Principle 10 — Avoid exaggerated claims

Use terms such as:

- risk-controlled automation
- previously unseen anomalies
- isolated validation
- canary deployment
- verified recovery
- human escalation
- adaptive incident response

Avoid claiming:

- perfect autonomy
- zero failures
- guaranteed production safety
- the ability to solve every unknown problem

---

# 42. Final Architecture Decision

The combined architecture that should be implemented is:

```text
                         OPERATOR
                            │
                            ▼
                     NEXT.JS DASHBOARD
                            │
                            ▼
                       FASTAPI GATEWAY
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
          ▼                 ▼                  ▼
    Monitoring          Incident          Configuration
     Manager             Manager             Manager
          └─────────────────┼──────────────────┘
                            ▼
                     LANGGRAPH CORE
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        Investigation      RCA        Repair Planner
              └─────────────┼─────────────┘
                            ▼
                       MEMORY RAG
                            │
                            ▼
                     SAFETY ENGINE
                            │
               ┌────────────┼─────────────┐
               ▼            ▼             ▼
            Low Risk    Medium Risk    High Risk
               │            │             │
               │         Sandbox       Human
               │            │          Approval
               │         Canary           │
               └────────────┼─────────────┘
                            ▼
                 RUST HEALING EXECUTOR
                            │
                         kube-rs
                            │
                         RBAC
                            │
                            ▼
                     KUBERNETES API
                            │
                            ▼
                      TARGET AI SYSTEM
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
              Metrics      Logs       Traces
                │           │           │
           Prometheus      Loki       Tempo
                └───────────┼───────────┘
                            ▼
                    VERIFICATION ENGINE
                            │
                       ┌────┴────┐
                       ▼         ▼
                    SUCCESS    FAILURE
                       │         │
                       ▼         ▼
                     LEARN    ROLLBACK /
                               ESCALATE
                       │         │
                       └────┬────┘
                            ▼
                 POSTGRESQL + PGVECTOR
                            │
                            ▼
                     INCIDENT MEMORY

            CHAOS ENGINE ───────► TARGET AI SYSTEM
```

---

# 43. Final Project Story

The project should be presented as follows:

> **The Autonomous Self-Healing AI Operations Platform is a web-based AIOps control system that observes an AI/RAG workload and its Kubernetes infrastructure through metrics, logs and distributed traces. When an abnormal condition is detected, a LangGraph-based orchestration workflow investigates the incident, generates evidence-backed root-cause hypotheses, retrieves relevant historical incidents, and proposes recovery actions. A deterministic safety engine evaluates risk, confidence, permissions and policy before any action is executed. Medium/high-risk repairs can be validated in an isolated sandbox and, where appropriate, deployed through a controlled canary. Approved operations are executed through a Rust-based Healing Executor with restricted Kubernetes RBAC permissions. A dedicated Verification Engine measures whether the system actually recovered. Verified incidents are stored in PostgreSQL with pgvector embeddings so that future incidents can benefit from previous experience. Controlled chaos experiments generate reproducible end-to-end incidents for evaluation and dataset creation.**

The core engineering loop is:

```text
OBSERVE
   ↓
DETECT
   ↓
INVESTIGATE
   ↓
UNDERSTAND
   ↓
PLAN
   ↓
SAFETY CHECK
   ↓
EXPERIMENT / APPROVE
   ↓
HEAL
   ↓
VERIFY
   ↓
REMEMBER
   ↓
IMPROVE
```

---

# 44. Recommended Implementation Order

Build the system in this order to avoid getting stuck in advanced features too early.

```text
Phase 1
Target RAG application
        ↓
Docker
        ↓
Kubernetes

Phase 2
OpenTelemetry
        ↓
Prometheus + Loki + Tempo

Phase 3
Detection + Incident Manager

Phase 4
FastAPI + LangGraph
        ↓
Investigation
        ↓
RCA

Phase 5
Repair Planner
        ↓
Safety Engine

Phase 6
Rust Healing Executor
        ↓
Kubernetes RBAC
        ↓
Basic recovery actions

Phase 7
Verification
        ↓
Rollback

Phase 8
PostgreSQL + pgvector
        ↓
Incident memory

Phase 9
Web Dashboard

Phase 10
Chaos experiments
        ↓
Dataset generation
        ↓
Evaluation

Phase 11
Sandbox
        ↓
Canary
        ↓
Unknown-failure investigation
```

The project is complete enough for a strong MVP once this core loop works reliably:

```text
Fault
 ↓
Detect
 ↓
RCA
 ↓
Approved Repair
 ↓
Rust Executor
 ↓
Verify
 ↓
Store Incident
```

---

# 45. Key Reference Notes

This architecture is primarily based on the two project research/context documents supplied by the project team.

The research establishes that:

- AIOps operational data is multi-modal and should not be forced into a flat CSV.
- Metrics, logs and traces should remain in specialized stores and be correlated through identifiers.
- No single public dataset covers the complete self-healing lifecycle.
- Controlled fault injection is the recommended way to generate correlated end-to-end incident data.
- A custom Incident Knowledge Base can serve as the system's long-term memory.
- Conventional ML training from scratch is not required for the core architecture.
- LLM reasoning is most useful for RCA and AI evaluation, while recovery execution and verification should retain deterministic controls.
- The recommended experimental flow is deploy → load → inject fault → detect → investigate → heal → verify → archive.

The additional project context further establishes the target product as a web-based AI Operations Platform with emphasis on unknown-failure investigation, virtual/shadow healing, risk-aware autonomy, canary deployment, rollback, incident memory and measurable self-improvement.

Rust is introduced specifically for the infrastructure-control boundary. Current `kube-rs` documentation confirms a Rust client/runtime for Kubernetes, while current OpenTelemetry documentation provides Rust instrumentation and OTLP export support; the Rust OTel implementations are currently documented as Beta, so central telemetry should remain based on the OpenTelemetry Collector and established observability backends. 

---

# 46. Final One-Line Architecture

> **Next.js Dashboard → FastAPI Control Plane → LangGraph AI Orchestrator → Safety/Policy Engine → Sandbox/Human Approval → Rust Healing Executor (kube-rs) → Kubernetes Target AI System → OpenTelemetry/Prometheus/Loki/Tempo → Verification → PostgreSQL/pgvector Incident Memory → Future Incident Retrieval.**

