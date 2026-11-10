# Kavach & Simple_RAG-Pipeline Verified Startup & Recovery Runbook

**Document Version:** 1.0.0  
**Verification Date:** 2026-10-20  
**Phase:** Kavach Phase 10 — Reliable Startup and Restart Verification  
**Scope:** Kavach Control Plane, Operator Console, and Simple_RAG-Pipeline Target

---

## 1. Overview & Operational Preconditions

This runbook documents the dependency-aware startup, verification, troubleshooting, and recovery procedures for the Kavach autonomous AI operations platform and its reference target application (`Simple_RAG-Pipeline`).

### 1.1 Non-Negotiable Safety Boundaries
1. **Never run destructive commands:** Do not execute `docker compose down -v`, `docker volume rm`, or `docker system prune`. Persistent volumes contain the target vector database (`pgvector`), Ollama model weights, Kavach audit logs, and Prometheus time-series data.
2. **Preserve host PostgreSQL:** The host machine runs a Windows PostgreSQL service listening on TCP port `5432`. Project services are bound to isolated host ports (`5433` for the target database, `5434` for Kavach metadata). Never rebind a container to port `5432` or stop the host service.
3. **Branch separation:**
   - Canonical repository (`Self-Healing-AI-Ops-ops`): Branch `feat/console-midnight-redesign`.
   - Target repository (`Simple_RAG-Pipeline`): Branch `kavach/ops` with clean worktree.
4. **Safety enforcement:** Mode remains `SIMULATION` with `allowed_actions: []`. Preflight validation does **not** authorize active repairs without explicit operator intervention.

---

## 2. Service Architecture & Port Mapping

| Service Name | Container Name | Stack / Project | Working Directory | Host Port | Readiness Check Endpoint |
|---|---|---|---|---|---|
| Windows PostgreSQL | *(Host Service)* | Host OS | N/A | `5432` | TCP `127.0.0.1:5432` |
| Target Ollama | `ollama` | `simple_rag-pipeline` | `.../Simple_RAG-Pipeline` | `11434` | `http://localhost:11434/api/tags` |
| Target Database | `rag_db` | `simple_rag-pipeline` | `.../Simple_RAG-Pipeline` | `5433` | TCP `127.0.0.1:5433` (`pg_isready`) |
| Target Backend | `rag_backend` | `simple_rag-pipeline` | `.../Simple_RAG-Pipeline` | `8000` | `http://localhost:8000/healthz` |
| Target Prometheus | `prometheus` | `simple_rag-pipeline` | `.../Simple_RAG-Pipeline` | `9090` | `http://localhost:9090/-/healthy` |
| Target Frontend | `rag_frontend` | `simple_rag-pipeline` | `.../Simple_RAG-Pipeline` | `3000` | TCP `127.0.0.1:3000` |
| Kavach PostgreSQL | `kavach-postgres` | `kavach` | `.../Self-Healing-AI-Ops-ops` | `5434` | TCP `127.0.0.1:5434` |
| Kavach Jaeger UI | `kavach-jaeger` | `kavach` | `.../Self-Healing-AI-Ops-ops` | `16686` | `http://localhost:16686/` |
| Kavach Collector | `kavach-otel-collector` | `kavach` | `.../Self-Healing-AI-Ops-ops` | `4317, 4318, 8889`| TCP `127.0.0.1:4318` |
| Kavach Prometheus | `kavach-prometheus` | `kavach` | `.../Self-Healing-AI-Ops-ops` | `9091` | `http://localhost:9091/-/healthy` |
| Kavach API Engine | `kavach-api` | `kavach` | `.../Self-Healing-AI-Ops-ops` | `8080` | `http://localhost:8080/healthz` |
| Kavach Console | `kavach-console` | `kavach` | `.../Self-Healing-AI-Ops-ops` | `3001` | `http://localhost:3001/` |
| Kavach Grafana | `kavach-grafana` | `kavach` | `.../Self-Healing-AI-Ops-ops` | `3002` | `http://localhost:3002/api/health` |

---

## 3. Dependency-Aware Startup Procedure

Services must be started in strict dependency order. Target services must achieve full readiness before the Kavach control plane is started.

### Step 1: Start Target Application Stack (`simple_rag-pipeline`)
Working Directory: `C:\Users\Swaraj Shedge\Desktop\College\TY\Simple_RAG-Pipeline`

```powershell
# 1. Model server (takes longest to load model weights)
docker compose up -d ollama

# 2. Vector database
docker compose up -d db

# 3. Application backend (depends on db and ollama)
docker compose up -d backend

# 4. Target metrics scraper & frontend UI
docker compose up -d prometheus frontend
```

#### Readiness Verification (Target)
```powershell
# Wait for Ollama tags API (HTTP 200)
curl -s http://localhost:11434/api/tags

# Verify backend healthz returns db: connected, ollama: connected
curl -s http://localhost:8000/healthz
# Expected: {"status":"healthy","db":"connected","ollama":"connected"}

# Verify Prometheus scraper
curl -s http://localhost:9090/-/healthy
```

### Step 2: Start Kavach Control Plane Stack (`kavach`)
Working Directory: `C:\Users\Swaraj Shedge\Desktop\College\TY\Self-Healing-AI-Ops-ops`

```powershell
# 1. Kavach metadata store & telemetry sinks
docker compose --env-file .env -f infra/docker-compose.yml up -d postgres jaeger

# 2. Telemetry ingestion & operations Prometheus
docker compose --env-file .env -f infra/docker-compose.yml up -d otel-collector prometheus

# 3. Control plane API engine (depends on postgres, prometheus, otel-collector)
docker compose --env-file .env -f infra/docker-compose.yml up -d api

# 4. Operator console & Grafana dashboards (depends on api)
docker compose --env-file .env -f infra/docker-compose.yml up -d console grafana
```

#### Readiness Verification (Kavach)
```powershell
# Verify API engine
curl -s http://localhost:8080/healthz
# Expected: {"status":"healthy"}

# Verify Operator Console root
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/
# Expected: 200

# Verify Jaeger UI and Grafana
curl -s http://localhost:16686/api/services
curl -s http://localhost:3002/api/health
```

---

## 4. Post-Startup Warmup & Preflight Verification

### 4.1 Prometheus Rate Window Warmup
The target application metrics define:
- `availability`: `(sum(rate(http_requests_total{status="5xx"}[2m])) or vector(0)) / clamp_min(sum(rate(http_requests_total[2m])), 1e-9)`
- `chat_latency_p95`: `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{handler="/v1/chat"}[2m])))`

Prometheus `rate()` requires **at least two samples** within the 2-minute rolling window. Following a cold start or restart, send two baseline queries spaced 5 seconds apart to populate metric series:

```powershell
$body = '{"question": "What ROC-AUC did the LSTM model achieve?"}'
Invoke-RestMethod -Uri http://localhost:8000/v1/chat -Method Post -Body $body -ContentType "application/json"
Start-Sleep -Seconds 5
Invoke-RestMethod -Uri http://localhost:8000/v1/chat -Method Post -Body $body -ContentType "application/json"
```

### 4.2 Kavach Preflight Execution
Execute the 17-point preflight validation:

```powershell
curl -s http://localhost:8080/v1/preflight | jq .
```

#### Expected 17/17 Pass Matrix
1. `manifest valid`: PASS
2. `git repository`: PASS
3. `worktree clean`: PASS
4. `base branch 'main' exists`: PASS
5. `HEAD not on a protected branch`: PASS
6. `ops branch 'kavach/ops' exists`: PASS
7. `ops branch has no upstream`: PASS
8. `service 'backend' health`: PASS
9. `service 'db' health`: PASS
10. `service 'ollama' health`: PASS
11. `docker socket reachable`: PASS
12. `ownership of 'rag_backend'`: PASS
13. `ownership of 'rag_db'`: PASS
14. `ownership of 'ollama'`: PASS
15. `SLO 'availability' evaluates`: PASS
16. `SLO 'chat_latency_p95' evaluates`: PASS
17. `fast verification set`: PASS

---

## 5. Preflight Gate vs. Repair Permission

A clean 17/17 preflight result **proves environmental health, observability readiness, and contract conformance only**. It does **not** grant Kavach permission to mutate or repair services.

| Gate Component | Mechanism | Current Value / State | Meaning |
|---|---|---|---|
| **Preflight** | `/v1/preflight` | `17/17 PASS` | Target is observable, git branches exist, health endpoints answer. |
| **Safety Mode** | `kavach.yaml -> mode` | `SIMULATION` | Execution produces zero write actions against containers or git. |
| **Action Allowlist** | `kavach.yaml -> allowed_actions` | `[]` *(empty)* | No repair actions are permitted to execute autonomously. |
| **Circuit Breaker** | `safety/engine.py` | Active | Caps repair attempts and aborts repeated failures. |
| **Denied Mutations** | `kavach.yaml -> denied_mutations` | `[embed_model_change, data_delete, database_drop, scale_to_zero, migration]` | Hard-blocked actions that can never be executed under any tier. |

To permit autonomous repair, the operator must explicitly edit `kavach.yaml` to specify approved action names and switch `mode` to `SEMI_AUTONOMOUS` or `AUTONOMOUS`.

---

## 6. Troubleshooting & Recovery Without State Destruction

### Failure 1: Target Database `rag_db` Exited (Code 255)
- **Symptom:** `rag_backend` fails health check (`db: disconnected`), preflight check 09 fails.
- **Root Cause:** Container shutdown or Docker daemon restart while host Postgres (port 5432) is active.
- **Recovery:**
  ```powershell
  # Check status without deleting volume
  docker ps -a --filter "name=rag_db"
  # Start the existing container
  docker compose -f "C:\Users\Swaraj Shedge\Desktop\College\TY\Simple_RAG-Pipeline\docker-compose.yml" start db
  ```
- **Validation:** Port `5433` accepts connections. `rag_backend` auto-reconnects within 10 seconds.

### Failure 2: Target Backend Crash Loop
- **Symptom:** `rag_backend` restarts continuously.
- **Root Cause:** Ollama or `rag_db` not ready when backend started.
- **Inspection:**
  ```powershell
  docker logs rag_backend --tail 50
  ```
- **Recovery:** Ensure `ollama` responds to `/api/tags` and `rag_db` responds to port `5433`, then restart only the backend:
  ```powershell
  docker restart rag_backend
  ```

### Failure 3: SLO `chat_latency_p95` Missing Series in Preflight
- **Symptom:** Preflight check 16 reports `query is valid but returned no series`.
- **Root Cause:** No queries sent within the last 2 minutes (`[2m]` window).
- **Recovery:** Send two queries to `http://localhost:8000/v1/chat` as documented in §4.1.

### Failure 4: Console 404 on `/logs` or `/traces`
- **Symptom:** Production container `kavach-console` serves `/` and `/observability` with 200, but `/logs` returns 404.
- **Root Cause:** The `kavach-console` container was built before the Phase 9.4 routes were added to `apps/console/app/`.
- **Local Dev Alternative:** Run Next.js in hot-reload mode on the host:
  ```powershell
  cd "C:\Users\Swaraj Shedge\Desktop\College\TY\Self-Healing-AI-Ops-ops\apps\console"
  pnpm dev
  ```
  *(Note: Production container image rebuilds require explicit operator approval per Phase 10 safety constraints).*

---

## 7. Verification Evidence & Limitations

### 7.1 Verified Test Run (Phase 10)
- **Target Stack Restart:** `ollama` (15.3s) -> `db` (0.0s) -> `backend` (6.2s) -> `prometheus` (2.0s) -> `frontend` (0.1s).
- **Kavach Stack Restart:** `postgres` (0.0s) -> `jaeger` (2.0s) -> `otel-collector` (0.1s) -> `prometheus` (2.0s) -> `api` (4.0s) -> `console` (2.2s) -> `grafana` (2.0s).
- **Result:** All 12 project containers reached `healthy` / `Up` status.
- **Preflight:** `17/17 PASS` (0 WARN, 0 FAIL).
- **Distributed Tracing:** Jaeger verified active traces for service `kavach-control-plane` (Trace IDs: `751353b2f242f98e85c969e835988909`, `33d2b30ee2ff5a7b0d8d275a1e8284b7`, `9e632c9623357dd2749d6812ffc079bb`).

### 7.2 Testing Limitations
- **Host Reboot:** This verification tested a controlled Docker Compose service restart sequence. It does not certify recovery after an ungraceful Windows host crash or complete Docker daemon crash.
- **Production Console Image:** Verified on existing container builds; container image rebuilds were prohibited and not performed.
