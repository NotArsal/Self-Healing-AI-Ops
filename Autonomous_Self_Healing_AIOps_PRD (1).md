# Product Requirements Document (PRD)

# Autonomous Self-Healing AI Operations Platform

**Version:** 1.0  
**Document Status:** Final Proposed PRD  
**Project Type:** Major College Engineering / AI Systems Project  
**Primary Product:** Web-based Autonomous AI Operations Platform  
**Primary Deployment:** Docker + Kubernetes  
**AI Orchestration:** LangGraph + OpenAI-compatible LLM  
**Infrastructure Control:** Rust Healing Executor + Kubernetes API (`kube-rs`)  
**Backend API:** FastAPI  
**Memory:** PostgreSQL + pgvector  
**Observability:** OpenTelemetry + Prometheus + Loki + Tempo  

---

## 1. Product Overview

### 1.1 Product Name

**Autonomous Self-Healing AI Operations Platform**

### 1.2 Product Definition

The Autonomous Self-Healing AI Operations Platform is a web-based AIOps platform designed to monitor AI applications and their infrastructure, detect failures and previously unseen anomalies, investigate possible root causes, propose recovery actions, safely execute approved repairs, verify whether recovery succeeded, and retain verified incident knowledge for future incidents.

The core lifecycle is:

> **Monitor → Detect → Diagnose → Decide → Repair → Verify → Learn**

The project is not intended to be only a chatbot, a dashboard, a collection of restart scripts, or a static dataset. The primary product is an operational control platform containing a web dashboard, backend services, an AI orchestration workflow, controlled recovery tools, verification, and incident memory.

---

## 2. Problem Statement

Modern AI applications can fail at multiple layers:

- Application/service crashes
- High CPU, RAM, or GPU utilization
- Model inference failures
- LLM/API failures
- High latency and timeouts
- Database and vector-database failures
- Container/Kubernetes failures
- Configuration problems
- Deployment regressions
- Dependency failures
- Retrieval degradation
- Abnormal AI behavior
- Previously unseen combinations of symptoms

Traditional monitoring can identify that something is wrong, but an operator still has to determine:

1. Why did it happen?
2. Which service is responsible?
3. What evidence supports the diagnosis?
4. What recovery action should be attempted?
5. Is that action safe to execute?
6. Did the repair actually work?
7. Should the same knowledge be used for a future incident?

This project automates as much of this lifecycle as is practical while keeping risk controls, verification, rollback, and human escalation in the loop.

---

# 3. Product Vision

Build an operational AI system that behaves like an **AI Operations Engineer / autonomous SRE assistant**:

> **Observe → Investigate → Experiment Safely → Act → Verify → Remember → Improve**

The platform should be capable of detecting anomalies that have not been seen before and investigating them using available evidence. It must not claim to solve every unknown failure automatically.

The project should demonstrate measurable value through:

- Mean Time to Detection (MTTD)
- Mean Time to Recovery (MTTR)
- Root-cause accuracy
- Recovery success rate
- False-diagnosis rate
- Rollback rate
- Human intervention rate
- Repeated-incident rate
- Improvement from historical incident retrieval

---

# 4. Goals

## 4.1 Primary Goals

### G1. Continuous Observability

Collect and correlate:

- Metrics
- Logs
- Distributed traces
- Service health
- Infrastructure signals
- AI/RAG quality signals

### G2. Failure Detection

Detect:

- Known failure conditions
- Threshold violations
- Abnormal trends
- Previously unseen anomalies

### G3. AI-Assisted Investigation

Allow the platform to:

- Gather relevant evidence
- Inspect logs, metrics, traces, and Kubernetes state
- Generate root-cause hypotheses
- Compare competing explanations
- Retrieve similar historical incidents

### G4. Safe Repair Planning

Generate one or more candidate repairs and evaluate:

- Confidence
- Risk
- Permissions
- Policy
- Required validation level

### G5. Controlled Self-Healing

Execute only authorized actions through explicit recovery tools.

### G6. Verification

Never consider an incident resolved simply because a command succeeded.

Recovery must be verified using measurable application and infrastructure signals.

### G7. Learning Through Memory

Store verified incidents and use embeddings/similarity retrieval to improve future decisions.

### G8. Demonstrable Engineering Platform

Provide a complete, reproducible environment that can be installed locally and demonstrated through controlled failure injection.

---

# 5. Non-Goals

The following are intentionally outside the core MVP:

- Fully autonomous unrestricted production administration
- Guaranteed solutions for every unknown incident
- Blind LLM-generated shell command execution
- Continuous automatic modification of the LLM's own weights
- Autonomous database/data destruction
- A perfect production digital twin
- Building a huge custom foundation model
- Replacing all existing observability/SRE platforms
- Claiming that no previous self-healing AIOps system exists

The system should use realistic wording such as:

- Previously unseen anomalies
- Risk-controlled automation
- Isolated validation
- Canary deployment
- Automatic rollback where applicable
- Verified recovery
- Human escalation

---

# 6. Target Users

## 6.1 Primary User — SRE / AI Operations Engineer

Needs:

- System health
- Incident visibility
- Root-cause evidence
- Suggested repairs
- Recovery status
- Audit trail
- Historical incident knowledge

## 6.2 Secondary User — Developer / ML Engineer

Needs:

- Application health
- Logs and traces
- AI/RAG quality signals
- Deployment status
- Failure replay
- Recovery history

## 6.3 Project Evaluator / Research User

Needs:

- Clear demonstration
- Reproducible experiments
- Fault scenarios
- Quantitative evaluation
- Incident dataset
- Architecture transparency

---

# 7. Product Scope

The final product consists of the following major subsystems:

```text
Operator
   ↓
Web Dashboard
   ↓
FastAPI API Gateway
   ↓
Management Layer
   ├── Monitoring Manager
   ├── Incident Manager
   └── Configuration Manager
   ↓
LangGraph AI Orchestrator
   ├── Investigation
   ├── RCA / Hypothesis Analysis
   └── Repair Planning
   ↓
Decision / Safety Engine
   ├── Risk
   ├── Confidence
   ├── Permissions
   └── Policy
   ↓
Safe Execution Path
   ├── Auto Execute
   ├── Sandbox Validation
   ├── Canary Deployment
   └── Human Approval
   ↓
Rust Healing Executor
   ↓
Kubernetes / Docker / Approved APIs
   ↓
Target AI System
   ↓
Verification Engine
   ├── Success → Learn
   └── Failure → Rollback / Escalate
   ↓
PostgreSQL + pgvector
```

A separate fault-injection subsystem is used to deliberately create test incidents against the target system.

---

# 8. Final Technical Architecture

## 8.1 High-Level Architecture

```text
                         ┌─────────────────────────┐
                         │        OPERATOR         │
                         │                         │
                         │     Web Dashboard       │
                         │     Optional AI Console │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │       API GATEWAY       │
                         │          FastAPI        │
                         └────────────┬────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
             Monitoring          Incident          Configuration
              Manager             Manager             Manager
                    │                 │
                    └────────────┬────┘
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │    AI ORCHESTRATOR     │
                     │       LangGraph        │
                     └────────────┬───────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
          Investigation       RCA /             Repair
             Node           Hypothesis           Planner
                               Node                  │
                └─────────────────┼─────────────────┘
                                  │
                                  ▼
                     ┌────────────────────────┐
                     │   SAFETY / DECISION    │
                     │        ENGINE          │
                     │                        │
                     │ Risk                   │
                     │ Confidence             │
                     │ Policy                 │
                     │ Permissions             │
                     └────────────┬───────────┘
                                  │
                ┌─────────────────┼───────────────────┐
                │                 │                   │
                ▼                 ▼                   ▼
             LOW RISK        MEDIUM RISK          HIGH RISK
                │                 │                   │
                │                 ▼                   ▼
                │             SANDBOX             HUMAN
                │                 │              APPROVAL
                │                 ▼
                │              CANARY
                │                 │
                └─────────────────┼───────────────────┘
                                  ▼
                     ┌────────────────────────┐
                     │    HEALING EXECUTOR    │
                     │         RUST           │
                     └────────────┬───────────┘
                                  │
                     ┌────────────┼────────────┐
                     ▼            ▼            ▼
                 Kubernetes     Docker        APIs
                     │
                     ▼
                 RBAC / Policy
                     │
                     ▼
            ┌───────────────────────┐
            │     TARGET SYSTEM     │
            │                       │
            │ FastAPI / RAG         │
            │ Vector DB             │
            │ LLM Gateway           │
            └───────────┬───────────┘
                        │
                        ▼
              ┌────────────────────┐
              │   OBSERVABILITY    │
              │                    │
              │ OpenTelemetry      │
              │ Prometheus         │
              │ Loki               │
              │ Tempo              │
              └─────────┬──────────┘
                        │
                        └──────► Monitoring Manager


                  HEALING EXECUTOR
                         │
                         ▼
                VERIFICATION ENGINE
                         │
                   ┌─────┴─────┐
                   ▼           ▼
                SUCCESS      FAILURE
                   │           │
                   ▼           ▼
                 LEARN      ROLLBACK /
                             ESCALATE
                   │
                   └──────┬────┘
                          ▼
               ┌─────────────────────┐
               │  KNOWLEDGE/MEMORY   │
               │                     │
               │ PostgreSQL          │
               │ pgvector            │
               │ Incident History    │
               │ Repair Knowledge    │
               └─────────────────────┘


               ┌─────────────────────┐
               │   CHAOS ENGINE      │
               │                     │
               │ Fault Injection      │
               └──────────┬──────────┘
                          │
                          ▼
                    TARGET SYSTEM
```

---

# 9. Architecture Principles

## 9.1 Separation of Concerns

Different components have different responsibilities.

### AI / Probabilistic

- LLM reasoning
- Hypothesis generation
- RCA
- Repair candidate generation
- Historical incident retrieval

### Deterministic

- Alert rules
- Risk policy
- RBAC
- Kubernetes actions
- Health checks
- Verification
- Rollback

This prevents the LLM from becoming the single uncontrolled authority.

---

# 10. Component Requirements

## 10.1 Web Dashboard

### Purpose

Provide the operator with a visual control and observability interface.

### Required Views

#### Overview

Display:

- Global health
- Service health
- Active incidents
- MTTD
- MTTR
- Recovery success rate
- Recent activity

#### Incident Details

Display:

- Incident ID
- Timestamp
- Affected service
- Symptoms
- Severity
- Trace IDs
- Relevant logs
- Metrics
- Traces
- Hypotheses
- RCA reasoning summary
- Confidence
- Risk
- Proposed repairs
- Sandbox result
- Execution result
- Verification result

#### Healing

Display:

- Proposed action
- Risk level
- Required approval
- Sandbox state
- Canary state
- Execution status
- Rollback state

#### Learning / History

Display:

- Historical incidents
- Similar incidents
- Successful repairs
- Failed repairs
- Recovery times
- Repeated incidents

---

# 11. FastAPI API Gateway

FastAPI acts as the external backend/control layer.

The dashboard communicates with FastAPI rather than directly accessing Prometheus, Kubernetes, PostgreSQL, or other internal infrastructure.

## Example API groups

```text
GET    /health
GET    /system/health

GET    /services
GET    /services/{service}

GET    /incidents
GET    /incidents/{incident_id}

GET    /incidents/{incident_id}/timeline
GET    /incidents/{incident_id}/telemetry

POST   /incidents/{incident_id}/investigate
POST   /incidents/{incident_id}/repair-plan
POST   /incidents/{incident_id}/approve
POST   /incidents/{incident_id}/reject

POST   /chaos/inject
GET    /chaos/scenarios

GET    /memory/incidents
GET    /memory/similar/{incident_id}

GET    /metrics/mttd
GET    /metrics/mttr
GET    /metrics/recovery
```

The exact API design can evolve during implementation.

---

# 12. Monitoring Manager

The Monitoring Manager provides a common interface over the observability stack.

### Responsibilities

- Query Prometheus
- Query Loki
- Query Tempo
- Retrieve service health
- Correlate telemetry by incident time window
- Correlate data using trace IDs
- Normalize evidence for the AI orchestrator

### Underlying tools

```text
OpenTelemetry
Prometheus
Loki
Tempo
Grafana
```

Metrics, logs, and traces remain in specialized stores instead of being forced into one flat dataset.

---

# 13. Incident Manager

The Incident Manager transforms raw detection events into structured incident objects.

### Responsibilities

- Create incident
- Assign incident ID
- Track lifecycle state
- Store severity
- Link trace IDs
- Store evidence references
- Trigger investigation
- Track actions
- Track verification
- Close or escalate incident

### Incident states

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
SANDBOX_TEST
   ↓
APPROVAL / CANARY
   ↓
EXECUTING
   ↓
VERIFYING
   ↓
RESOLVED
```

Alternative terminal states:

```text
REJECTED
ROLLED_BACK
ESCALATED
```

---

# 14. Configuration Manager

The Configuration Manager maintains approved system configuration.

It may manage:

- Service configuration
- Alert thresholds
- Recovery policy
- Risk levels
- Allowed actions
- Model/provider configuration
- Canary rules
- Verification thresholds

Configuration changes should be auditable.

---

# 15. AI Orchestrator — LangGraph

LangGraph is the central stateful workflow engine.

The orchestration flow is:

```text
Incident
   ↓
Investigation
   ↓
Evidence Collection
   ↓
Hypothesis Generation
   ↓
RCA
   ↓
Historical Retrieval
   ↓
Repair Candidate Generation
   ↓
Safety Evaluation
   ↓
Sandbox / Approval / Execution
   ↓
Verification
   ↓
Learning
```

The workflow should maintain structured state rather than relying on one enormous LLM prompt.

---

# 16. Investigation Node

The Investigation Node gathers evidence.

### Available tools

```text
query_metrics()
query_logs()
get_trace()
inspect_pod()
inspect_deployment()
inspect_kubernetes_events()
inspect_service_health()
inspect_dependencies()
retrieve_similar_incidents()
```

The investigation should focus only on evidence relevant to the current incident.

---

# 17. RCA / Hypothesis Node

The RCA component should reason about evidence and generate hypotheses.

Example:

```text
Observed:
- p95 latency increased
- vector-db requests timeout
- CPU normal
- database pod reports connection failures

Hypotheses:

H1: Vector DB network failure
H2: Database overload
H3: API application regression
H4: LLM provider latency
```

The agent should provide:

- Hypothesis
- Supporting evidence
- Contradicting evidence
- Confidence
- Additional evidence required

The system must not present an uncertain diagnosis as absolute truth.

---

# 18. Repair Planner

The Repair Planner generates candidate actions.

Example:

```text
Root Cause Candidate:
Vector DB connectivity failure

Candidate Actions:
1. Restart vector-db
2. Restart network proxy
3. Redirect traffic
4. Scale vector-db
```

Each action should contain:

```text
action
reason
expected_effect
risk_level
required_permission
verification_plan
rollback_plan
```

---

# 19. Safety / Decision Engine

The Safety Engine is the final policy boundary before healing.

### Inputs

- Proposed action
- Confidence
- Risk
- Service criticality
- Current system state
- Allowed permissions
- Policy
- Sandbox availability

### Decision classes

```text
LOW RISK
→ Automatic execution may be allowed

MEDIUM RISK
→ Sandbox and/or canary validation

HIGH RISK
→ Human approval
```

### Example risk policy

| Risk | Examples | Default |
|---|---|---|
| Low | Retry, cache clear, restart non-critical worker | Automatic |
| Medium | Scale service, restart important component, deployment rollback | Sandbox / Canary |
| High | Database mutation, data deletion, major infrastructure changes | Human approval |

An emergency kill switch/manual override should always be available.

---

# 20. Virtual Sandbox

The initial implementation should use a practical **shadow namespace** rather than attempting to build a perfect digital twin.

Example:

```text
Production / Target Namespace
        │
        │ suspected repair
        ▼
sandbox-inc-042
        │
        ├── application
        ├── dependencies
        └── test configuration
```

### Sandbox flow

```text
Candidate repair
      ↓
Create sandbox
      ↓
Apply repair
      ↓
Run synthetic workload
      ↓
Measure health
      ↓
PASS / FAIL
```

A sandbox reduces risk but cannot guarantee production behavior.

---

# 21. Canary Deployment

Canary deployment is used for higher-impact repairs.

Example:

```text
Old Version → 95% traffic
New Version → 5% traffic
```

Measure:

- Error rate
- Latency
- CPU/RAM/GPU
- Service health
- AI/RAG quality

If healthy:

```text
5% → 25% → 50% → 100%
```

If unhealthy:

```text
Rollback
```

Canary can be implemented later using a Kubernetes-native progressive delivery solution if required.

---

# 22. Rust Healing Executor

## 22.1 Purpose

Rust should be used in the **infrastructure-control and healing execution layer**, where strong typing, explicit error handling, safe concurrency, and controlled interaction with Kubernetes are valuable.

### Recommended role

```text
FastAPI
   ↓
LangGraph
   ↓
Safety Engine
   ↓
Rust Healing Executor
   ↓
Kubernetes API / Docker / Approved APIs
```

### Why Rust?

Rust is a good fit for:

- Infrastructure control
- Kubernetes API interaction
- Long-running execution service
- Concurrent health/recovery operations
- Strong error handling
- Explicit typed action definitions
- Safe systems programming

### Recommended Rust stack

```text
Rust
├── Axum               → optional internal HTTP API
├── Tokio              → async runtime
├── kube               → Kubernetes client
├── Serde              → serialization
├── tracing            → structured application logs
└── reqwest            → external HTTP APIs
```

### Rust Executor responsibilities

```text
execute_restart()
execute_scale()
execute_rollback()
execute_config_change()
check_pod()
check_deployment()
check_health()
```

The Rust component should not decide whether an arbitrary action is safe. That decision belongs to the Safety Engine and Kubernetes RBAC/policy.

---

# 23. Why not use Rust for the entire project?

Rust should not replace Python/LangGraph for LLM orchestration.

The project has two different engineering needs:

### Python

Best used for:

- FastAPI
- LangGraph
- LLM integration
- Prompting
- RAG
- AI evaluation
- Experiment logic

### Rust

Best used for:

- Recovery executor
- Infrastructure control
- Kubernetes operations
- High-confidence typed action execution
- Internal operational service

This gives the project a practical polyglot architecture instead of using Rust purely for novelty.

---

# 24. Kubernetes Access and RBAC

The Healing Executor must not use unrestricted cluster-admin permissions.

Architecture:

```text
Rust Healing Executor
       ↓
Kubernetes API
       ↓
ServiceAccount
       ↓
Role / RoleBinding
       ↓
Approved Namespace / Resources
```

Example permission categories:

```text
READ:
- pods
- logs
- events
- deployments
- services

WRITE:
- restart approved pods
- scale approved deployments
- update approved deployment resources
- perform approved rollback
```

High-risk operations should be blocked by policy or require human approval.

---

# 25. Verification Engine

Verification is an independent subsystem.

A successful Kubernetes API call is not equivalent to successful recovery.

## Verification signals

- HTTP health
- Error rate
- Latency
- Pod readiness
- Resource usage
- Service availability
- Application-level tests
- RAG quality where relevant

### Example

Before:

```text
error rate = 18%
p95 latency = 4.2s
health = FAIL
```

After repair:

```text
error rate = 0.7%
p95 latency = 300ms
health = PASS
```

Result:

```text
RECOVERY VERIFIED
```

Otherwise:

```text
RECOVERY FAILED
→ rollback / retry / escalate
```

---

# 26. Target AI Application

The initial target system should be a controlled RAG application.

```text
User
 ↓
FastAPI RAG API
 ↓
Retriever
 ↓
pgvector
 ↓
LLM Gateway
 ↓
Response
```

The application should run in Kubernetes.

This target application exists so that the AIOps platform can:

- Observe it
- Break it
- Investigate it
- Repair it
- Verify it

The target application is not the primary product.

---

# 27. Observability Architecture

```text
Target AI System
      │
      ▼
OpenTelemetry
      │
 ┌────┼──────────┐
 ▼    ▼          ▼
Metrics Logs    Traces
 │     │          │
 ▼     ▼          ▼
Prometheus Loki  Tempo
 └─────┬──────────┘
       ▼
Monitoring Manager
```

### Example metrics

- CPU
- Memory
- Request count
- Error rate
- P95/P99 latency
- Pod restarts
- LLM latency
- Token usage
- Retrieval latency
- RAG evaluation score

### Example logs

- Exceptions
- Timeouts
- HTTP 500
- HTTP 429
- OOMKilled
- Connection errors

### Example traces

```text
API
 ↓
Retriever
 ↓
Vector DB
 ↓
LLM
```

Trace IDs connect the incident context across multiple services.

---

# 28. Knowledge / Memory Layer

Use:

```text
PostgreSQL
+
pgvector
```

PostgreSQL stores structured information.

pgvector stores embeddings for similarity retrieval.

## Memory contents

- Incident
- Symptoms
- Telemetry references
- Hypotheses
- RCA
- Actions attempted
- Successful action
- Failed actions
- Side effects
- Verification
- Recovery time
- Confidence
- Risk
- Human intervention
- Generated/approved runbook

---

# 29. Core Data Model

## incidents

```text
incident_id
trace_id
timestamp_detected
affected_service
failure_type
severity
status
root_cause
confidence
```

## evidence

```text
evidence_id
incident_id
source_type
reference
timestamp_start
timestamp_end
summary
```

## hypotheses

```text
hypothesis_id
incident_id
description
supporting_evidence
contradicting_evidence
confidence
status
```

## recovery_actions

```text
action_id
incident_id
action_taken
risk_level
timestamp_executed
execution_status
verification_result
rollback_available
recovery_time_ms
```

## incidents_embeddings

```text
incident_id
embedding
```

## runbooks

```text
runbook_id
incident_pattern
action
preconditions
verification
rollback
approval_level
success_rate
```

---

# 30. Incident Knowledge Retrieval

When a new incident occurs:

```text
Current incident
      ↓
Create incident summary
      ↓
Generate embedding
      ↓
pgvector similarity search
      ↓
Retrieve similar incidents
      ↓
Retrieve verified successful repairs
      ↓
Provide context to LangGraph
```

The system does not need to retrain the LLM after every incident.

The main learning mechanism is:

> **Persistent verified memory + retrieval + runbooks + policy improvement**

---

# 31. Unknown Failure Handling

An unknown incident should follow:

```text
UNKNOWN ANOMALY
      ↓
Collect evidence
      ↓
Investigate dependencies
      ↓
Generate hypotheses
      ↓
Evaluate evidence
      ↓
Generate candidate repairs
      ↓
Risk assessment
      ↓
Sandbox test
      ↓
Verification
      ↓
Canary / approved execution
      ↓
Verification
      ↓
Remember result
```

The system should escalate if confidence remains low or if no safe repair can be identified.

---

# 32. Chaos / Fault Injection Engine

The platform needs controlled fault injection for development and evaluation.

Possible scenarios:

```text
1. CPU exhaustion
2. Memory exhaustion / OOM
3. Pod crash
4. Network delay
5. Packet loss
6. Database connection drop
7. LLM API rate limit
8. High external API latency
9. Retrieval degradation
10. Node pressure / eviction
```

Possible implementation tools:

- Kubernetes-native chaos experiments
- Linux utilities
- Network traffic controls
- Purpose-built test scripts

The chaos subsystem should operate only in controlled environments.

---

# 33. End-to-End Incident Workflow

## Example: Vector DB Network Failure

### Step 1 — Normal operation

```text
RAG API → Vector DB → LLM
```

### Step 2 — Fault injection

```text
Chaos Engine
→ network delay / connectivity failure
```

### Step 3 — Detection

Prometheus notices:

```text
latency ↑
error rate ↑
```

### Step 4 — Incident creation

```text
INC-0042
status = INVESTIGATING
```

### Step 5 — Investigation

Agent retrieves:

```text
metrics
logs
traces
Kubernetes status
similar incidents
```

### Step 6 — RCA

Possible diagnosis:

```text
Vector DB network connectivity failure
confidence = 0.88
```

### Step 7 — Repair planning

Candidates:

```text
restart vector-db
restart network proxy
redirect traffic
```

### Step 8 — Safety

```text
Risk = Medium
→ Sandbox required
```

### Step 9 — Sandbox

Candidate repair tested.

```text
PASS
```

### Step 10 — Execution

Rust Healing Executor calls Kubernetes API.

### Step 11 — Verification

```text
HTTP = 200
error rate = normal
latency = baseline
```

### Step 12 — Learning

Incident is stored as:

```text
verified successful incident
```

---

# 34. User Experience / Installation

The user should not manually install every internal component.

## Prerequisites

```text
Docker Desktop
Git
kubectl
Helm
```

## Setup

```bash
git clone <repository>
cd self-healing-aiops
```

Configure:

```text
.env
```

Then run one setup command.

Windows:

```powershell
.\scripts\setup.ps1
```

Linux/macOS:

```bash
./scripts/setup.sh
```

The installer should:

```text
1. Check prerequisites
2. Check Kubernetes
3. Create namespaces
4. Deploy observability
5. Deploy target RAG app
6. Deploy AIOps platform
7. Configure RBAC
8. Configure incident database
9. Start services
10. Print dashboard URL
```

Expected user experience:

```text
Install prerequisites
      ↓
Clone repository
      ↓
Configure API key
      ↓
Run setup script
      ↓
Open dashboard
      ↓
Inject test failure
      ↓
Watch:
Detect → Diagnose → Repair → Verify
```

---

# 35. Kubernetes Namespace Design

```text
Kubernetes Cluster
│
├── target-system
│   ├── rag-api
│   ├── vector-db
│   └── llm-gateway
│
├── aiops
│   ├── dashboard
│   ├── fastapi
│   ├── langgraph
│   └── rust-healing-executor
│
├── observability
│   ├── prometheus
│   ├── loki
│   ├── tempo
│   └── otel-collector
│
├── incident-memory
│   └── postgres + pgvector
│
├── chaos
│   └── fault experiments
│
└── sandbox-*
    └── temporary validation environments
```

---

# 36. Repository Structure

```text
self-healing-aiops/
│
├── README.md
├── PRD.md
├── LICENSE
├── .env.example
│
├── frontend/
│   └── dashboard/
│
├── backend/
│   ├── api/
│   ├── monitoring/
│   ├── incidents/
│   ├── configuration/
│   └── memory/
│
├── ai-orchestrator/
│   ├── langgraph/
│   ├── investigation/
│   ├── rca/
│   ├── repair_planner/
│   └── prompts/
│
├── healing-executor/
│   └── rust/
│       ├── src/
│       ├── Cargo.toml
│       └── tests/
│
├── target-app/
│   ├── fastapi/
│   ├── rag/
│   └── vector-db/
│
├── observability/
│   ├── prometheus/
│   ├── loki/
│   ├── tempo/
│   └── opentelemetry/
│
├── chaos/
│   ├── cpu/
│   ├── memory/
│   ├── network/
│   ├── database/
│   └── llm/
│
├── kubernetes/
│   ├── rbac/
│   ├── namespaces/
│   └── manifests/
│
├── helm/
│   └── self-healing-aiops/
│
├── evaluation/
│   ├── scenarios/
│   ├── metrics/
│   └── reports/
│
├── dataset/
│
└── scripts/
    ├── setup.ps1
    ├── setup.sh
    ├── start.ps1
    ├── stop.ps1
    └── cleanup.ps1
```

---

# 37. Functional Requirements

## FR-01 — System Monitoring

The system shall collect application and infrastructure telemetry.

## FR-02 — Anomaly Detection

The system shall identify configured failure conditions and abnormal behavior.

## FR-03 — Incident Creation

The system shall automatically create a structured incident when a monitored failure condition is detected.

## FR-04 — Evidence Collection

The system shall collect relevant metrics, logs, traces, Kubernetes state, and application signals.

## FR-05 — RCA

The system shall use an LLM-based reasoning workflow to generate root-cause hypotheses and confidence.

## FR-06 — Historical Retrieval

The system shall search historical incident memory for similar verified incidents.

## FR-07 — Repair Planning

The system shall generate candidate recovery actions.

## FR-08 — Safety Evaluation

The system shall classify recovery actions according to risk and policy.

## FR-09 — Controlled Execution

The system shall execute only approved actions using controlled tools.

## FR-10 — Sandbox Validation

The system shall support isolated testing of appropriate medium/high-risk repairs.

## FR-11 — Human Approval

The system shall support human approval for configured high-risk operations.

## FR-12 — Verification

The system shall verify recovery using measurable system/application signals.

## FR-13 — Rollback

The system shall support rollback when configured recovery fails.

## FR-14 — Incident Memory

The system shall store incident histories and verified recovery outcomes.

## FR-15 — Dashboard

The system shall provide an operator-facing web interface.

## FR-16 — Fault Injection

The system shall support controlled fault injection for testing/evaluation.

---

# 38. Non-Functional Requirements

## NFR-01 — Safety

The system shall never provide unrestricted arbitrary execution privileges to the LLM.

## NFR-02 — Auditability

Every recovery action shall record:

- Who/what initiated it
- Action
- Timestamp
- Risk
- Result
- Verification
- Rollback outcome

## NFR-03 — Reproducibility

The complete demonstration environment should be reproducible using documented scripts and configuration.

## NFR-04 — Isolation

Sandbox/chaos experiments must be isolated from unintended environments.

## NFR-05 — Observability

All major components should produce structured logs and telemetry.

## NFR-06 — Fault Tolerance

Failure of the AI reasoning layer should not automatically imply unrestricted infrastructure changes.

## NFR-07 — Explainability

The operator should be able to understand why a repair was proposed and why it was executed.

## NFR-08 — Extensibility

New recovery actions and fault scenarios should be addable without redesigning the entire platform.

## NFR-09 — Performance

The platform should perform incident processing fast enough for a realistic prototype demonstration.

## NFR-10 — Security

Credentials, API keys, Kubernetes permissions, and secrets must be isolated from source code and uncontrolled prompts.

---

# 39. MVP Scope

The MVP should implement:

```text
1. Web dashboard
2. FastAPI backend
3. Kubernetes target RAG application
4. OpenTelemetry
5. Prometheus
6. Loki
7. Tempo
8. Detection rules
9. Incident Manager
10. LangGraph orchestration
11. Investigation
12. AI-based RCA
13. Repair planner
14. Safety engine
15. Rust Healing Executor
16. Kubernetes RBAC
17. Verification engine
18. PostgreSQL + pgvector
19. 5+ recovery actions
20. 5+ fault-injection scenarios
```

A working MVP must demonstrate:

> **Detect → Diagnose → Repair → Verify → Remember**

---

# 40. Advanced Features

After MVP:

```text
1. Unknown-failure investigation
2. Shadow/sandbox environments
3. Canary deployment
4. Automatic rollback
5. Multi-agent specialization
6. Runbook generation
7. Incident replay
8. Predictive healing
9. Confidence calibration
10. Expanded failure library
11. Self-improvement analytics
```

These are enhancement layers, not prerequisites for the core platform.

---

# 41. Evaluation Strategy

## 41.1 Detection

Measure:

- Detection accuracy
- False positives
- False negatives
- Detection latency

## 41.2 RCA

Measure:

- Root-cause accuracy
- Top-1 hypothesis accuracy
- Top-k hypothesis coverage
- Confidence calibration

## 41.3 Healing

Measure:

- Repair success rate
- Recovery time
- Rollback rate
- Human intervention rate

## 41.4 Verification

Measure:

- Successful recovery verification
- False recovery claims
- Post-repair health

## 41.5 Learning

Compare:

```text
Before historical retrieval
vs.
After historical retrieval
```

Measure:

- MTTR
- Repair success rate
- Repeated incidents
- Human intervention
- RCA quality

---

# 42. Dataset Strategy

The platform should not depend on one public dataset for the entire lifecycle.

Instead:

```text
Public benchmarks
       +
Controlled fault injection
       +
Live telemetry
       +
Incident archival
```

Public datasets/benchmarks can support research and component-level evaluation.

The final end-to-end incident dataset is generated by running the target system and intentionally injecting faults.

A strong experimental target is:

```text
10 fault types
×
multiple randomized repetitions
≈
300–500 documented incidents
```

The exact number can be reduced for the MVP.

The quality and correlation of incidents are more important than generating millions of records.

---

# 43. Data Leakage Prevention

Fault injection must not produce an overly predictable signature.

Example:

Bad:

```text
CPU = exactly 99%
for exactly 60 seconds
every run
```

Better:

```text
CPU target varies
Duration varies
Workload varies
Network delay varies
```

The RCA agent should not be told:

```text
"The chaos script caused this."
```

It should reason from the same types of evidence available during a real incident.

---

# 44. Security Requirements

### API security

- Authentication for operator endpoints where needed
- Input validation
- Rate limits for sensitive actions

### Secret management

Do not commit:

```text
LLM API keys
Database passwords
Kubernetes secrets
Tokens
```

### Kubernetes security

- Dedicated ServiceAccount
- Least-privilege RBAC
- Restricted namespace access
- Explicit action allowlist

### LLM security

- No unrestricted shell access
- No unrestricted Kubernetes access
- Tool-level permission checks
- Action validation
- Output/schema validation

---

# 45. Failure Handling

The platform itself can fail.

Therefore:

### If LLM unavailable

Fall back to:

- deterministic alerts
- incident logging
- human escalation

### If Rust Executor unavailable

Do not execute repair.

### If Verification fails

Trigger:

```text
retry / rollback / escalation
```

### If confidence is too low

```text
human review
```

### If no safe repair exists

```text
ESCALATE
```

The system should prefer safe non-action over unsafe autonomous action.

---

# 46. Product Success Criteria

The project is considered successful when a user can:

1. Install the platform using documented setup steps.
2. Open the web dashboard.
3. See the target AI application and observability status.
4. Inject a controlled failure.
5. See an incident automatically created.
6. See telemetry-based investigation.
7. See an AI-generated RCA/hypothesis.
8. See proposed recovery actions.
9. See risk/confidence evaluation.
10. See sandbox/approval behavior where applicable.
11. See the Rust Healing Executor perform an approved action.
12. See the system verify recovery.
13. See the incident stored in memory.
14. Trigger a similar future incident and see historical knowledge retrieved.

---

# 47. Example Demo Scenario

A recommended final demonstration:

```text
SYSTEM HEALTHY
      ↓
Inject Vector DB Network Failure
      ↓
Latency ↑
Error Rate ↑
      ↓
Prometheus Alert
      ↓
Incident Created
      ↓
LangGraph Investigation
      ↓
Logs + Metrics + Traces
      ↓
RCA:
Vector DB connectivity issue
      ↓
Repair Plan:
Restart / network recovery
      ↓
Safety:
Medium Risk
      ↓
Sandbox:
PASS
      ↓
Rust Healing Executor
      ↓
Kubernetes Action
      ↓
Verification
      ↓
Latency NORMAL
Error Rate NORMAL
Health PASS
      ↓
RECOVERY VERIFIED
      ↓
Store Incident
      ↓
Knowledge Available for Future Incidents
```

This single demonstration covers most of the central project features.

---

# 48. Recommended Implementation Order

## Phase 1 — Foundation

```text
Docker
Kubernetes
Target RAG app
PostgreSQL
```

## Phase 2 — Observability

```text
OpenTelemetry
Prometheus
Loki
Tempo
```

## Phase 3 — Detection + Incidents

```text
Detection rules
Incident Manager
FastAPI APIs
```

## Phase 4 — AI Orchestration

```text
LangGraph
Investigation
RCA
Repair Planner
```

## Phase 5 — Safety

```text
Risk engine
Confidence
Policies
RBAC
```

## Phase 6 — Healing

```text
Rust Executor
Kubernetes tools
Recovery actions
```

## Phase 7 — Verification

```text
Health checks
Metrics comparison
Rollback
```

## Phase 8 — Memory

```text
PostgreSQL
pgvector
Historical retrieval
```

## Phase 9 — Dashboard

```text
Incidents
RCA
Actions
Verification
Memory
```

## Phase 10 — Advanced

```text
Sandbox
Canary
Unknown failure
Replay
Predictive healing
```

---

# 49. Recommended Development Ownership

For a group project, responsibilities can be divided approximately as:

### Member 1 — Frontend

- React/Next.js
- Dashboard
- Incident visualization
- Charts
- Operator actions

### Member 2 — Backend / API

- FastAPI
- Incident APIs
- Monitoring Manager
- Configuration
- Database APIs

### Member 3 — AI / Agent

- LangGraph
- Investigation
- RCA
- Repair planning
- Prompt/tool orchestration
- Historical retrieval

### Member 4 — Infrastructure / Rust

- Docker
- Kubernetes
- Observability
- Rust Healing Executor
- RBAC
- Chaos experiments
- Verification

Responsibilities can overlap, but ownership should remain clear.

---

# 50. Architectural Decisions to Freeze

The following decisions should be treated as the current baseline:

| Decision | Choice |
|---|---|
| Product type | Web-based AIOps platform |
| Target environment | Kubernetes |
| Target application | Controlled RAG application |
| Frontend | React / Next.js |
| Backend | FastAPI |
| AI orchestration | LangGraph |
| LLM role | Investigation, RCA, planning |
| Infrastructure executor | Rust |
| Rust Kubernetes client | kube-rs |
| Metrics | Prometheus |
| Logs | Loki |
| Traces | OpenTelemetry + Tempo |
| Database | PostgreSQL |
| Vector memory | pgvector |
| Caching | Redis if required |
| Recovery security | Kubernetes RBAC |
| Fault injection | Controlled chaos experiments |
| Sandbox | Shadow namespace initially |
| Canary | Advanced feature |
| Learning | Memory + retrieval, not continuous retraining |
| Primary UI | Web dashboard |
| Chat | Optional secondary interface |
| Distribution | GitHub + Helm + setup scripts |

---

# 51. Final Product Definition

The final project should be presented as:

> **A Kubernetes-based, web-accessible Autonomous AI Operations Platform that monitors AI systems, detects known and previously unseen anomalies, investigates root causes using AI-assisted reasoning, safely evaluates recovery strategies, performs risk-controlled healing through a typed Rust infrastructure executor, verifies recovery using measurable signals, and learns from verified incidents through persistent incident memory.**

The central loop is:

> **Detect → Understand → Experiment → Heal → Verify → Remember → Improve**

The project does not claim perfect autonomy.

Its value is in integrating:

```text
Observability
+
AI reasoning
+
Controlled infrastructure actions
+
Risk policy
+
Sandbox/canary validation
+
Verification
+
Incident memory
```

into one reproducible engineering platform.
