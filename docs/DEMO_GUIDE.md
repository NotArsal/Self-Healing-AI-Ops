# Kavach Demonstration & Operational Readiness Guide

**Document Version:** 1.0.0  
**Date:** 2026-10-21  
**Target Audience:** University Evaluators, Operators, and Technical Reviewers  
**Platform Scope:** Kavach Autonomous AI Operations Platform (`Self-Healing-AI-Ops-ops`)  
**Target Under Management:** Simple_RAG-Pipeline (`Simple_RAG-Pipeline`)  

---

## 1. Project Purpose & Architecture

Kavach is an **autonomous AI operations platform** designed to observe, diagnose, heal, and verify containerized LLM/RAG applications. It is defined by contract (`CONTRACT.md`): any application conforming to the contract can be autonomously monitored and repaired with zero changes to Kavach's source code.

### Core Architecture & Healing Lifecycle
The Kavach incident response lifecycle executes in seven sequential stages:
1. **Detect:** Multi-signal detectors evaluate live telemetry (Prometheus PromQL, OpenTelemetry) and fast functional probes (`fast_set.yaml`).
2. **Collect:** Captures pre-state witness data, configuration snapshots, and corpus chunk fingerprints (`corpus_before`).
3. **Diagnose:** Maps symptoms to fault classes (deterministic detector catalogue `F01`–`F09` or LLM RCA engine with Context7 evidence).
4. **Gate (`safety.engine.permit`):** Evaluates ten sequential security and safety invariants. **Fail-closed by default**:
   - `project_ownership` -> `deny_list` -> `allow_list` -> `action_known` -> `inverse_recorded` -> `unknown_gate` -> `confidence` -> `risk_tier` -> `blast_radius` -> `circuit_breaker` -> `mode_policy`.
5. **Execute:** If and only if permitted, registers inverse on the `UndoStack` and dispatches mutation via the appropriate executor adapter.
6. **Verify:** Executes post-repair fast verification probes. **Verification returns deltas, never raw booleans**; availability restored with degraded quality yields `MITIGATED`, not `RESOLVED`.
7. **Rollback / Resolve:** If verification fails or quality drops, the `UndoStack` immediately unwinds mutations in reverse order, restoring the exact pre-state witness.

---

## 2. Environment Prerequisites & Service Architecture

Refer to [STARTUP_RUNBOOK.md](STARTUP_RUNBOOK.md) for full deployment details.

### Confirmed Service Topology & Port Mappings
| Service | Container Name | Stack / Project | Host Port | Verified Readiness Check |
|---|---|---|---|---|
| **Host PostgreSQL** | *(Windows Host)* | Non-Project | `5432` | Reserved for host (untouched) |
| **Target Ollama** | `ollama` | `simple_rag-pipeline` | `11434` | `http://localhost:11434/api/tags` |
| **Target Database** | `rag_db` | `simple_rag-pipeline` | `5433` | TCP `127.0.0.1:5433` |
| **Target Backend** | `rag_backend` | `simple_rag-pipeline` | `8000` | `http://localhost:8000/healthz` |
| **Target Prometheus**| `prometheus` | `simple_rag-pipeline` | `9090` | `http://localhost:9090/-/healthy` |
| **Target Frontend** | `rag_frontend` | `simple_rag-pipeline` | `3000` | TCP `127.0.0.1:3000` |
| **Kavach PostgreSQL**| `kavach-postgres` | `kavach` | `5434` | TCP `127.0.0.1:5434` |
| **Kavach Jaeger UI** | `kavach-jaeger` | `kavach` | `16686` | `http://localhost:16686/` |
| **Kavach Collector** | `kavach-otel-collector` | `kavach` | `4317, 4318, 8889`| TCP `127.0.0.1:4318` |
| **Kavach Prometheus**| `kavach-prometheus` | `kavach` | `9091` | `http://localhost:9091/-/healthy` |
| **Kavach API Engine**| `kavach-api` | `kavach` | `8080` | `http://localhost:8080/healthz` |
| **Kavach Console** | `kavach-console` | `kavach` | `3001` | `http://localhost:3001/` |
| **Kavach Grafana** | `kavach-grafana` | `kavach` | `3002` | `http://localhost:3002/api/health` |

---

## 3. Console Interfaces & Navigation Map

The Midnight Operations console is accessible at `http://localhost:3001`:

- **Active Incident & Fleet Health (`/`):** Real-time incident lifecycle view, seven-stage horizontal pipeline (`Detect` -> `Collect` -> `Diagnose` -> `Gate` -> `Execute` -> `Verify` -> `Resolve`), and system status.
- **Environmental Gate (`/preflight`):** Complete 17-point preflight contract verification table.
- **Telemetry & Observability (`/observability`):** Real-time sparklines, P95 latency histograms, error ratio trends, validator verdicts, and external observability links.
- **Operational Logs (`/logs`):** Structured log stream with severity badges (`INFO`, `WARN`, `ERROR`), subsystem filtering, and keyword search.
- **Distributed Traces (`/traces`):** Jaeger OTLP integration view, trace ID correlation, span waterfalls, and direct links to Jaeger UI.

---

## 4. Safe Demonstration Sequence

A technically honest and repeatable live presentation follows this four-part sequence without modifying target files or breaking safety invariants.

### Step 1: Environmental Readiness & Preflight Gate
1. Navigate to `http://localhost:3001/preflight` in your browser.
2. Demonstrate that all **17/17 environmental checks PASS**:
   - Contract manifest valid, clean Git worktrees, base and ops branches intact.
   - All three target services (`backend`, `db`, `ollama`) healthy.
   - Docker socket reachable and container ownerships confirmed.
   - SLOs (`availability` and `chat_latency_p95`) actively evaluate against Prometheus.
   - Fast verification suite runnable.
3. **Presenter Talking Point:** *"A 17/17 green preflight proves that the application satisfies all contract obligations and is observable. It does NOT authorize Kavach to make changes."*

### Step 2: Policy Gate & Safety Guardrails
1. Inspect the target application's configuration:
   `Simple_RAG-Pipeline/kavach.yaml`
2. Point out the core safety invariants:
   ```yaml
   mode: SIMULATION
   allowed_actions: []
   denied_mutations:
     - embed_model_change
     - data_delete
     - database_drop
     - scale_to_zero
     - migration
   ```
3. **Presenter Talking Point:** *"By specification, the default allowed actions list is completely empty. Autonomous operations cannot be granted by accident; even with 100% healthy preflight, any repair attempt is immediately refused by the safety engine."*

### Step 3: Lifecycle Simulation & Rollback Guarantee
Run the verified simulation test suite from PowerShell:
```powershell
cd "C:\Users\Swaraj Shedge\Desktop\College\TY\Self-Healing-AI-Ops-ops\apps\control-plane"
uv run pytest tests/test_simulation_workflow.py -v
```

Demonstrate the three tested scenarios:
1. **Scenario A (`test_scenario_a_production_policy_refuses_execution`):**
   - **Fault:** Simulated `F06` retrieval collapse (`rerank_threshold = 0.999`).
   - **Detect & Collect:** Fast set fails (`pass_rate = 0.0`), pre-state witness captured.
   - **Diagnose:** Detector identifies `F06` / `retrieval_collapse` on `backend`.
   - **Gate:** `safety.permit()` evaluates `allowed_actions: []`. Check 3 fails (`allow_list: 'rollback_config' is not in allowed_actions: empty`).
   - **Execution Blocked:** `target.writes == 0`. Zero mutations occur. Status: `ESCALATED`.
2. **Scenario B (`test_scenario_b_simulation_mode_with_allowlist_parks_at_awaiting`):**
   - Shows that even if `rollback_config` is allowlisted, `mode: SIMULATION` prevents automated writes and parks at `AWAITING_APPROVAL` with zero target mutations.
3. **Scenario C (`test_scenario_c_undo_stack_rollback_guarantee`):**
   - Proves AGENTS.md Rule 4a: when an action executes and verification fails, the `UndoStack` unwinds immediately and restores the pre-state witness (`0.999`).

### Step 4: Observability, Logs & Distributed Traces Walkthrough
1. Navigate to `http://localhost:3001/observability`:
   - Inspect the interactive sparklines and error ratio trends.
   - Review AI validator filter controls.
2. Navigate to `http://localhost:3001/logs`:
   - Review operational log messages with timestamps and severity filters.
3. Navigate to `http://localhost:3001/traces`:
   - Demonstrate the external explorer links to Jaeger UI (`:16686`) and Grafana (`:3002`).
   - Click the Jaeger UI link or visit `http://localhost:16686` to show real OTLP spans emitted for control-plane HTTP calls (`GET /v1/preflight`).

---

## 5. Technical Limitations & Operational Realities

To maintain absolute technical honesty during review:

1. **No Live Target Fault Injection in Demo:**
   - Injecting faults directly into the live target application alters live state and violates the strict read-only safety rules of the operational evaluation. The simulated harness accurately proves the exact same code paths without risking target corruption.
2. **Missing Baseline Capture on Disk:**
   - `harness/baselines/` currently contains no baseline capture. In the live control plane, calling `/v1/loop/run` directly raises `NoBaselineError`. This is an intended architectural fail-closed mechanism: Kavach refuses to guess what baseline values to restore.
3. **Trace Correlation Scope:**
   - Jaeger currently contains verified HTTP distributed traces for control plane operations (`kavach-control-plane`). Active healing traces (`kavach.heal`) are only emitted during an active loop execution.
4. **Standalone Console Rebuild Requirement:**
   - The production container `kavach-console` serves all routes (`/`, `/observability`, `/preflight`, `/logs`, `/traces`) only after being rebuilt with `docker compose build console` following new page commits.

---

## 6. Troubleshooting & Recovery Commands

If any service encounters issues during demonstration setup:

### Target Database Disconnected (`rag_db`)
```powershell
docker compose -f "C:\Users\Swaraj Shedge\Desktop\College\TY\Simple_RAG-Pipeline\docker-compose.yml" start db
```

### Warm Prometheus Rate Window
Prometheus `rate(...[2m])` requires two queries within the 2-minute window:
```powershell
$body = '{"question": "What ROC-AUC did the LSTM model achieve?"}'
Invoke-RestMethod -Uri http://localhost:8000/v1/chat -Method Post -Body $body -ContentType "application/json"
Start-Sleep -Seconds 5
Invoke-RestMethod -Uri http://localhost:8000/v1/chat -Method Post -Body $body -ContentType "application/json"
```

### View Live Container Logs
```powershell
docker logs kavach-api --tail 50
docker logs rag_backend --tail 50
```
