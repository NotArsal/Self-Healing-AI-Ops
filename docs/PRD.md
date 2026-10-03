# PRD.md — Kavach

> **Autonomous Self-Healing AI Operations Platform**
> VIT · CSE-AI (E) · Group 14 · Engineering Research & Innovation (ERI) · AY 2026-27
>
> `Kavach` (कवच, "shield") is a working codename used for package names, container
> names and the repo. Swap it globally if the team prefers a different name — it
> appears only in `pyproject.toml`, `package.json`, the compose project name and
> the UI wordmark.

---

## 1. Product overview

**Name:** Kavach

**One line:** Kavach watches an AI application, works out why it broke, fixes it, and proves the fix worked — without waking anyone up.

**Vision:** Observability tools tell you something is wrong. Kavach closes the loop. It treats an AI application as a system that can be driven back to a declared healthy state by an agent that reasons over evidence, picks a bounded repair, executes it under a risk gate, verifies the outcome against an SLO contract, and rolls back automatically when verification fails.

**What makes it different.** Two things, stated narrowly because the field is more populated than it first appears (see §2.2):

1. **The failure classes are AI-application-level, not infrastructure-level.** Prompt regressions, retrieval collapse, LLM endpoint degradation and token blowout are operational state that nobody currently manages with SRE discipline. The infrastructure agents don't model them; the LLM-observability tools measure them but never act.
2. **The write is governed by a formal recoverability guarantee**, not by a prompt asking the model to be careful. Every repair records its inverse before executing, and verification failure unwinds it automatically.

Positioned on the autonomy ladder the field now uses (L0 read-only copilot → L4 closed-loop self-healing), the mature open-source tools sit at L2–L3 and Kavach targets a *bounded* L4: full closed-loop autonomy, but only over eight enumerated fault classes and only for actions tiered LOW.

---

## 2. Problem

Modern AI applications are chains of fragile, independently-owned parts: a model endpoint, a vector store, an embedding model, a prompt version, a retrieval configuration, a connection pool, a container runtime. A failure in any one of them surfaces as the same symptom to the user — a bad answer, a slow answer, or no answer.

Three things make this harder than classic infrastructure ops:

1. **Failure is often silent.** The service returns HTTP 200 with an ungrounded or empty-context answer. No alert fires. Liveness probes pass. The system is "up" and wrong.
2. **The diagnosis space is wide.** A latency spike could be the LLM endpoint, the vector DB, the embedding call, or a prompt that suddenly produces 4× the tokens. The symptom does not identify the layer.
3. **The repair is layer-specific.** Restarting a container does nothing for a prompt regression. Rolling back a prompt does nothing for an exhausted connection pool. Generic auto-remediation (restart, rescale) applies the wrong remedy and masks the real fault.

Current tooling splits this problem in half and solves neither end-to-end. Engineers sit in the middle, correlating a dashboard against a trace against `docker logs` at 2 a.m.

### 2.1 Why this is hard (grounded in current results)

This is not a solved problem dressed up as a project. Figures below are from the papers themselves, not from secondary summaries.

**AIOpsLab** (UIUC / UC Berkeley / Microsoft / IISc, arXiv:2501.06706) defines the four-level task ladder Kavach's loop follows — detection, localization, root cause analysis, mitigation — and evaluates agents against live fault-injected microservice environments. Overall accuracy across all problems: Flash 59.32%, ReAct 55.93%, GPT-4-with-shell 49.15%, GPT-3.5-with-shell 15.25%. On detection alone, Flash reaches 100% and ReAct 76.92%, while the non-LLM baselines sit at 15.38%. On mitigation, the paper reports GPT-4-with-shell and ReAct at roughly 43% correctness, TaskWeaver at 29%, and notes plainly that GPT-3.5-with-shell **fails to recover any failure at all**. The paper's own conclusion is that RCA and mitigation are the hardest levels and no agent is consistently strong across all four.

**STRATUS** (NeurIPS'25, arXiv:2506.02009, `xlab-uiuc/stratus`) is the current state of the art on that mitigation task and the closest prior art to Kavach's safety design. With GPT-4o it solves 69.2% (9/13) of AIOpsLab mitigation problems and 50.0% (9/18) of ITBench's, at least 1.5× the baselines.

**OpenRCA 2.0** reports that across 11 frontier LLMs, recovering the exact root-cause set succeeds in only 20.7% of cases on average. **ITBench** frontier agents resolve under a third of its 94 scenarios.

**SREGym** adds the finding that most threatens naive measurement: when an agent diagnoses correctly, mitigation still only succeeds 68–89% of the time; when the diagnosis is *wrong*, mitigation still succeeds 22–62% of the time, because agents pattern-match a symptom to a fix that happens to work without understanding the cause. **A successful heal is therefore not evidence of a correct diagnosis.** §10 measures the two independently for exactly this reason.

**Detection is solved. Diagnosis and mitigation are not.** That is where Kavach's contribution lives, and it is why v1 constrains the fault space to a finite enumerated catalogue rather than claiming to heal anything.

### 2.2 Prior art, honestly

Two clusters already exist. Kavach is not in an empty field and the PRD should not pretend otherwise.

**Cluster A — request-level self-correction inside an LLM app.** `self-healing-rag` and similar LangGraph projects classify retrieval as healthy/weak/insufficient and retry or abstain within a single request. `error-recovery` intercepts agent errors and injects recovery prompts. Published frameworks add reliability scoring with re-planning, prompt correction and tool re-selection. All of these heal *an answer*. None of them touches the deployed system's operational state.

**Cluster B — infrastructure-level agentic SRE.** K8sGPT runs deterministic Kubernetes analysers and uses an LLM only to explain findings, strictly read-only (this one is accurate). HolmesGPT is a CNCF Sandbox multi-step ReAct agent co-maintained by Robusta and Microsoft; its README still says read-only by design, **but it now ships a Kubernetes Remediation MCP toolset that applies scaling, rollbacks and resource edits, plus a Beta GitHub toolset that opens fix PRs.** It is actively crossing the read/write line. Aurora generates remediation pull requests behind a human approval gate. STRATUS executes mitigations under a formal guarantee, but it is a research system evaluated on benchmarks, not a deployable platform.

**Genuine overlaps to acknowledge, not ignore:**
- `EvoAgents` detects failures with an LLM evaluator, generates targeted prompt patches, validates them by replay against past traces, versions every prompt and offers one-command rollback. This overlaps `F07` substantially. Kavach's difference is that the prompt rollback is triggered by a production SLO breach and gated by a risk engine, not by an offline improvement loop.
- `EvoUndo` implements deterministic rollback for agent harnesses with captured pre-state witnesses, and makes the same argument Kavach does: asking an LLM to "undo what you just did" fails, hallucinates, or produces incomplete inverses. Deterministic inverses are the only workable approach.

**What remains genuinely unoccupied:** nothing in either cluster manages an LLM application's operational state (prompt version, retrieval configuration, endpoint selection) under a declared SLO contract with a recoverability guarantee and automatic verification. That is the claim, and it is narrower than "nobody does self-healing for AI."

---

## 3. Goals

**G1.** Reduce time-to-detect and time-to-recover for a declared set of AI-application failures to the point where no human is involved in the common path.

**G2.** Make every autonomous action *justifiable after the fact* — cited evidence, stated confidence, recorded risk decision, recorded inverse action, verification result.

**G3.** Make the system safe to point at a real project: it must be impossible for Kavach to take an action the project owner did not explicitly allow.

**G4.** Prove the loop end-to-end on a live demo: inject a fault, watch the console, see it resolved, inspect the audit trail.

### 3.1 Non-goals for v1

- **Not a Kubernetes operator.** Kavach v1 drives Docker Compose only. See §5.3 — the system under management happens to contain Kubernetes manifests, and that is not the same thing as Kavach supporting Kubernetes.
- Not a general AIOps platform. Not a Datadog competitor.
- Not a replacement for Langfuse/Phoenix tracing. Kavach *consumes* OTLP; it does not try to be the best trace viewer.
- Not multi-tenant, not SaaS, not hardened for untrusted input.
- Not claiming to handle novel/unseen failures autonomously. Unknown failures route to a human and are **never** auto-executed in v1 (§8.4).

---

## 4. Target users

**Primary — the solo AI builder / small team (the demo persona).**
Runs a RAG or agent application in Docker. Has no SRE. Finds out the app is broken when a user tells them. Wants something that watches it and fixes the obvious things.

**Secondary — the platform engineer evaluating autonomy.**
Already has Prometheus and tracing. Does not trust an LLM with write access. Needs the simulation and approval modes, the risk tiers, and the audit log before they would ever flip anything to autonomous.

**Tertiary — the project reviewer (faculty / panel).**
Needs to see the loop work live, understand where the AI contribution actually is, and see measurement rather than assertion.

---

## 5. Locked scope decisions

These decisions constrain everything downstream. Do not widen them without an explicit decision record in `docs/decisions/`.

| Decision | v1 | Deferred |
|---|---|---|
| **System under management** | `Simple_RAG-Pipeline`, an existing local `docker-compose` RAG application (§5.1) | Kubernetes, Vercel/Render/Netlify deploy APIs, multi-cloud |
| **Runtime** | Docker Compose only | Kubernetes (`RuntimeAdapter` is the seam) |
| **Optimisation target** | A convincing live demo for review | Benchmark runs against AIOpsLab / RCAEval |
| **Default mode** | **`SIMULATION`**, globally and for every newly onboarded project (§5.4) | — |
| **Autonomy ceiling** | A project explicitly moved to `AUTONOMOUS` executes **only LOW-risk** actions; MEDIUM goes to sandbox-then-approval, HIGH goes to human, UNKNOWN never auto-executes | Autonomous MEDIUM after a fine-tuned decision model and sufficient labelled outcomes |
| **Fault catalogue** | **Eight** classes: `F01`–`F03`, `F05`–`F09` (§6) | `F04`, index rebuild, anything outside the catalogue |

### 5.1 The System Under Management (SUM)

**Kavach does not ship its own target application.** The SUM is a pre-existing, independently-developed RAG application:

| | |
|---|---|
| **Repository** | `NotArsal/Simple_RAG-Pipeline` |
| **Local path** | `D:\Vit\Academics Sem-5\EDI\Target_RAG-App` |
| **Base branch** | `modernize-stack` (the branch carrying the working code — **not** `main`) |
| **Relationship** | A separate git repository, a separate compose project, a separate codebase |

Using a real, pre-existing application instead of a purpose-built `demo-rag` is a deliberate strengthening of the project: the target was not designed to be healed, so none of its failure modes are staged for Kavach's convenience.

**What the target actually is** (verified against the code, not its README):

| Service | What it is | Notes |
|---|---|---|
| `backend` | FastAPI RAG service | `POST /v1/chat`, `POST /v1/upload`, `GET /metrics` |
| `db` | `ankane/pgvector` Postgres | `document_chunks` table, `vector(768)`, **no vector index** |
| `frontend` | Next.js 14 chat UI | Browser calls the backend directly; governed by its own conventions, **not** `DESIGN_SYSTEM.md` |
| `ollama` | Local LLM + embedding server | `llama3.2` for generation, `nomic-embed-text` for embeddings |
| `prometheus` | Bundled Prometheus | Superseded by the control-plane Prometheus during Kavach operation (`ARCHITECTURE.md` §2.4) |

The RAG query path is: one LLM call for query expansion → four embedding calls → four pgvector similarity queries → an optional `BAAI/bge-reranker-base` CrossEncoder rerank filtered by `RERANK_THRESHOLD` → one LLM call for generation.

**What the target does *not* have**, and therefore what Kavach cannot assume:

- **No OpenTelemetry of any kind.** No SDK, no instrumentation, no exporter. The README's claim that "FastAPI 0.115+ natively supports OpenTelemetry" is false; FastAPI has no built-in OTel. There are currently zero traces.
- **No token accounting.** Ollama returns a `usage` block; the target discards it.
- **No cache.** No Redis, no response cache, no embedding cache. This is why `F04` is retired (§6.1).
- **No externalised prompts.** Both prompts are inline f-strings in `rag.py`.
- **No vector index.** Retrieval is a sequential scan. This is why `F06`'s repair is a config rollback, not an index rebuild (§6).
- **No `/healthz`.** `GET /` returns `{"status":"ok"}` without checking any dependency.

§5.2 lists exactly what Kavach is permitted to add to close those gaps.

### 5.2 The target boundary

**Kavach is a control plane. The target is an application. Neither imports the other.** The full rule set lives in `AGENTS.md` § Target boundary; the scope consequence is here.

Kavach may add to the target **only** the following, and nothing else:

| # | Addition | Purpose | Touches business logic? |
|---|---|---|---|
| 1 | OpenTelemetry SDK + FastAPI/psycopg2/requests instrumentation | `FR-06` has no data source without it | No |
| 2 | `GET /healthz` checking Postgres and Ollama | Preflight + verification probe 1 | No |
| 3 | A narrow, token-gated config interface (`ARCHITECTURE.md` §7.2) | `switch_llm_endpoint`, `rollback_config` | No |
| 4 | Read Ollama's `usage` block into a span attribute | `F09` is impossible without it | **Two lines in `rag.py`** |
| 5 | Lower the 1200-second LLM request timeout to ~30s | Otherwise `F02` is a 20-minute hang, not a fault | **Two lines in `rag.py`** |
| 6 | Move the two prompts to `prompts/*.txt`, loaded at request time | `F07` and `F09` are impossible without it | **Mechanical extraction from `rag.py`** |
| 7 | `CHAOS_ENABLED` flag around the existing jitter middleware, default `false` | Otherwise 10–150ms of random noise contaminates every latency baseline | No |
| 8 | Toxiproxy with two listeners in front of Ollama; compose healthchecks | `F01`/`F02` injection point | No (compose only) |
| 9 | `kavach.yaml` | The onboarding contract | No |
| 10 | **Release Postgres connections in `finally` blocks** (`docs/decisions/0005`) | `F05` and repeated injection are untrustworthy without it | **Cleanup only in `rag.py`** |

Additions 4, 5, 6 and 10 are the only ones that touch `rag.py`, and they are deliberately the smallest change that makes the novel faults real. **No Kavach reasoning, orchestration, detection, decision or healing code goes into the target.**

**On addition 10 — a reliability fix, not a feature.** `rag.py` calls `release_connection()` inline rather than in a `finally`, so `store_chunks` (rag.py:14–38) and `retrieve_relevant_chunks` (rag.py:103–152) leak a pooled connection on any exception. With `SimpleConnectionPool(1, 10)`, ten failed requests exhaust the pool. That matters to Kavach specifically for two reasons:

1. **It makes `F05` untestable.** A pool-exhaustion fault cannot be measured on a system that exhausts its own pool as a side effect of unrelated failures.
2. **It makes every repeated injection untrustworthy.** Each failed injection of *any* fault leaks a connection, so run 9 of a 20-cycle stability test is not operating on the same system as run 1. That invalidates the `ROADMAP.md` acceptance criterion "20 cycles leave the stack identical to the start state."

Scope is strictly bounded: wrap acquire/release in `try/finally`. **No redesign of the database layer, no schema change, no pooling-strategy change.** Recorded as a required target reliability fix in `docs/decisions/0005-target-reliability-fixes.md`, and scheduled in `ROADMAP.md` P1.

### 5.3 Kavach is the sole self-healing controller

The target repository already contains its own partial self-healing mechanism, built before Kavach existed:

- `backend/aiops_agent.py` — a LangGraph `StateGraph` whose `heal_service` node deletes Kubernetes pods
- `POST /v1/webhook/alert` — an **unauthenticated** route that invokes it with a service label and namespace taken from the request body
- `k8s/` — Deployment and Service manifests
- `docs/ADR-002-AIOps-and-Resilience.md` — which declares Kubernetes mandatory for self-healing

**In v1, Kavach is the only component permitted to mutate the system under management.** A second writer breaks `FR-15a` (writer exclusivity) outright, and the existing mechanism satisfies none of Kavach's safety requirements: no allow-list, no risk tier, no inverse, no idempotency key, no pre-state witness.

Resolution, recorded in `docs/decisions/0003-sole-healing-controller.md`:

| Artefact | Disposition |
|---|---|
| `backend/aiops_agent.py` | **Kept on disk** for historical and reference value. Not imported, not reachable, not executed |
| `POST /v1/webhook/alert` | **Removed from the running application.** The route is not registered |
| Pod deletion | **Unreachable.** No code path can invoke it |
| `k8s/` manifests | **Left on disk, unused by Kavach v1** |
| `langgraph` / `langchain` / `kubernetes` deps in the target | Left in place unless removing the route makes them unused; not a Kavach concern |
| The target's `ADR-001` / `ADR-002` | **Not modified.** Kavach records its own decision on its own side |

**For reviewers, stated plainly:** the target repository contains Kubernetes manifests and a Kubernetes client dependency. Kavach v1 does not support Kubernetes, does not read those manifests, and does not call the Kubernetes API. "The target contains Kubernetes files" and "Kavach supports Kubernetes" are different statements, and only the first is true.

### 5.4 Operating modes and the default

Three modes, defined once here and referenced everywhere else:

| Mode | Behaviour |
|---|---|
| **`SIMULATION`** | Produces a complete plan and a dry-run diff. **Zero writes of any kind.** This is the global default and the default for every newly onboarded project |
| `APPROVAL` | Every action, at every risk tier, goes to a human |
| `AUTONOMOUS` | LOW executes automatically · MEDIUM goes to sandbox-then-approval · HIGH goes to a human · `UNKNOWN` never auto-executes |

A project may only be moved out of `SIMULATION` after preflight passes (§8.1) **and** an explicit per-project configuration change. Nothing moves a project to `AUTONOMOUS` implicitly, and `kavach.yaml` omitting `mode` means `SIMULATION`.

---

## 6. The fault catalogue

v1 defines exactly these **eight** classes. Each one is a closed tuple: **injector → detection signal → RCA path → repair action → verification probe → risk tier.** Anything outside the catalogue is an `UNKNOWN` failure and follows the unknown-failure flow (§8.4).

**Seven of the eight have a v1 injector.** `F03`'s injector is deferred (§6.4) because no honest way to inject it against this target has been found yet. The class stays in the catalogue — its detection signal, repair and risk tier are all defined and its repair action is shared with `F05` — but it is excluded from `make bench` until its injector exists.

| ID | Fault class | Detection signal | Repair action | Risk |
|---|---|---|---|---|
| `F01` | **Primary LLM endpoint outage** (5xx / connection refused) | Error rate on LLM spans > 20% over 60s | `switch_llm_endpoint` (primary → backup path) | LOW |
| `F02` | **Primary LLM endpoint latency degradation** | p95 LLM operation duration > SLO × 2 | `switch_llm_endpoint` | LOW |
| `F03` | Container crash-loop / OOM — **injector deferred, §6.4** | Restart count > 2 in 5 min, or exit code 137 | `restart_container`; `raise_memory_limit` one step | LOW |
| `F05` | Connection pool exhaustion | Postgres connection errors; pool saturation gauge | `restart_container` (dependent service) | LOW |
| `F06` | Retrieval collapse (empty / low-similarity hits) | Mean top-k similarity below floor; empty-context rate up; fast-eval pass rate drop | `rollback_config` — restore last-known-good `RERANK_THRESHOLD` | MEDIUM |
| `F07` | Prompt version regression | Fast-eval pass rate drops after a prompt change | `rollback_prompt` to last-known-good version | MEDIUM |
| `F08` | Config / env regression | Config hash changed + SLO breach within the window | `rollback_config` to last-known-good | MEDIUM |
| `F09` | Token/cost blowout | Tokens per request > 3× baseline | `rollback_prompt`; clamp `max_tokens` | MEDIUM |

**Why this list:** every entry is AI-application-specific or directly upstream of AI behaviour, injectable deterministically **against this target**, repairable with a bounded action, and verifiable. `F06`–`F09` are the ones no existing open-source tool heals, and they carry the novelty claim (§2.2).

**IDs are stable identifiers, not indices.** `F04` is retired and its number is **not** reused or renumbered. The catalogue runs `F01, F02, F03, F05, F06, F07, F08, F09` — eight entries with a gap. IDs appear in logs, the UI, tests and the metrics table, so renumbering would silently invalidate recorded results.

### 6.1 `F04` is retired

The original catalogue included `F04` cache poisoning / stale cache, repaired by `flush_cache`.

**The target has no cache.** No Redis, no response cache, no embedding cache. The one cache-shaped object in the codebase (`_cached_ranker` in `rag.py`) is a loaded model handle, not a data cache — poisoning it is not possible and flushing it means reloading a model.

`F04` is therefore **dropped from v1**, and Redis is **not** added to the target merely to manufacture a fault for it. Building a feature in order to have something to break is the wrong direction, and a reviewer would be right to say so.

Consequences, applied throughout: the catalogue is eight entries, not nine; `flush_cache` is removed from the action registry and the risk-tier table; there is no `F04` integration test. The benchmark denominator is **seven** injectable faults — eight classes minus `F03`, whose injector is separately deferred (§6.4) — so `make bench` is 7 × 5 = **35 injections**, not 45.

> **Noted for a possible future decision record.** The target recomputes embeddings on every query, serially, four per request. An embedding cache would be a genuine ~4× latency improvement the application should arguably have on its own merits — at which point `F04` becomes legitimate rather than contrived. That is an improvement to the target, proposed on the target's terms, and is explicitly **not** in v1 scope.

### 6.2 Retired and unimplementable actions

Recorded so nobody re-adds them from an older draft:

| Action | Status | Why |
|---|---|---|
| `flush_cache` | **Removed** | No cache exists; `F04` is retired |
| `rebuild_index` | **Future scope** | The target has no vector index and no snapshot mechanism. `F06` repairs by config rollback instead (§6) |
| `scale_replicas_up` | **Unimplementable** | The target's compose binds host port `8000:8000`; a second backend replica cannot start |
| `retry_request` | **Removed** | No hook exists in the target's request path |
| `switch_model` | **Renamed** to `switch_llm_endpoint` | See §6.3 — it switches endpoint, not provider |

### 6.4 `F03`'s injector is deferred

`F03` container crash-loop / OOM looks like the easiest fault in the catalogue. Against this target it is not, and the reason is worth recording rather than discovering in week 10.

The target's `docker-compose.yml` sets **`restart: always`** on `backend`. Docker therefore restarts a killed or OOM-killed container within seconds, unprompted. Three consequences:

1. **Docker wins the race.** Kavach's detection tick is 15s and its loop budget is 3 minutes. Docker's restart is immediate. A demo of `F03` would show Docker self-healing and Kavach arriving afterwards to announce that the problem is gone — which is a demonstration of Docker, not of Kavach.
2. **The obvious workaround is dishonest.** Removing `restart: always` would make `F03` injectable, but it would do so by *deliberately degrading the target's existing resilience in order to manufacture a failure Kavach can be seen fixing*. That inverts the entire premise of the project. **It is forbidden** — the target's resilience is not ours to weaken, and a reviewer who reads the diff would be right to treat it as staged.
3. **A crash the restart cannot fix is a different fault.** A memory limit low enough that the process OOMs again on every boot produces a genuine crash-*loop*, which `restart: always` cannot resolve and Kavach legitimately can (by `raise_memory_limit`). This is the honest version — but it requires finding a limit that reliably OOMs the target's Python process during startup without being so low the container never starts at all, and that is empirical work, not a design decision.

**Therefore:** `F03` stays in the catalogue as a defined class. Its injector is **deferred until option 3 is demonstrated to be deterministic** (20 cycles, same outcome). It is excluded from `make bench` and from the metrics denominator until then. **No placeholder or simulated `F03` injector is to be written** — a fault injector that does not really inject the fault it claims is worse than an absent one, because it silently corrupts every number computed from it.

If `F03` is never implemented, that is an acceptable v1 outcome and is reported as such. It is an infrastructure-level fault that prior art already covers (§2.2); none of the project's novelty claim depends on it.

### 6.3 `F01`/`F02` are endpoint faults, not provider failover

The target has exactly **one** Ollama service. Calling `F01`'s repair a "multi-provider failover" would be dishonest, and a reviewer who reads the compose file will notice.

The real mechanism is a fault injected into one **path** to a single model server:

```
                     ┌─ Toxiproxy listener A ─┐
  target backend ────┤   (PRIMARY path)       ├──▶ ollama:11434
   (configurable     │   fault injected here  │
    endpoint)        └────────────────────────┘
                     ┌────────────────────────┐
                  ───┤ Toxiproxy listener B   ├──▶ ollama:11434
                     │   (BACKUP path)        │
                     │   never faulted        │
                     └────────────────────────┘

  Kavach RCA calls ───────────── direct ──────▶ ollama:11434
                        (bypasses Toxiproxy entirely)
```

- `F01` injects a `down` toxic on **listener A only**. Listener B stays healthy.
- `F02` injects a `latency` toxic on listener A only.
- The repair, `switch_llm_endpoint`, points the target's LLM base URL at listener B. Its inverse points it back at listener A.
- **Kavach's own RCA and evaluation calls go directly to Ollama**, never through Toxiproxy. Breaking the target's primary path must never blind the control plane that is diagnosing it.

The honest property being demonstrated is **endpoint-level failover with a recorded inverse**, not multi-provider resilience. The mechanism generalises to real independent providers without a code change — the endpoint is configuration — but v1 does not claim to have tested that.

---

## 7. Core features

Two orthogonal axes, deliberately separated because conflating them caused the Laya contradiction in the previous draft:

- **Priority** — `P0` required for the demo · `P1` required for the report · `P2` stretch.
- **Phase** — *when* it is built (`ROADMAP.md`). A `P1` feature may legitimately be scheduled late.

| ID | Feature | Priority | Phase |
|---|---|---|---|
| `F-ONB` | Project onboarding + preflight validation against a `kavach.yaml` manifest | P0 | P1 |
| `F-SLO` | SLO contract declaration as PromQL expressions — the machine-checkable definition of "healthy" | P0 | P1 |
| `F-TEL` | Telemetry ingestion: OTLP traces/metrics/logs + Prometheus query | P0 | P2 |
| `F-VER-FAST` | **Fast verification**: health probe + short SLO window + 3 deterministic quality checks | P0 | P3 |
| `F-DET` | Detection layer: SLO breach + statistical anomaly detection | P0 | P3 |
| `F-SAFE` | Safety / decision engine: risk tiering, allow-list, blast radius, circuit breaker | P0 | P3 → P7 |
| `F-HEAL` | Executor with an undo stack and a recorded inverse for every repair | P0 | P3 |
| `F-VER` | Three-probe verification + automatic rollback on failure | P0 | P3 |
| `F-AUD` | Immutable, hash-chained audit trail of every autonomous action | P0 | P3 |
| `F-INJ` | Fault injection harness for the eight catalogue entries | P0 | P2 → P6 |
| `F-RCA` | Evidence-grounded RCA with cited evidence and calibrated confidence | P0 | P4 |
| `F-UI` | Live operations console | P0 | P5 |
| `F-MODE` | Three operating modes: `SIMULATION` / `APPROVAL` / `AUTONOMOUS` (§5.4) | P0 | P3 → P7 |
| `F-GIT` | Git isolation: `kavach/ops` branch off `modernize-stack`, commits for every config/prompt change | P0 | P6 → P8 |
| `F-UNK` | Unknown-failure flow — evidence → hypotheses → risk → escalate (never auto-execute) | P1 | P7 |
| `F-EVAL-FULL` | Full offline evaluation runner for research measurement | P1 | P8 |
| `F-MEM` | Incident knowledge base with similarity retrieval over past incidents | P1 | P8 |
| `F-DEC` | **Pluggable decision model — rule engine is authority, Laya adapter in shadow** (§7.1) | **P1** | **P8** |
| `F-SBX` | Sandbox: clone the stack, apply the repair there first | P1 | P7 |
| `F-BENCH` | AIOpsLab / RCAEval harness adapter | P2 | — |

**`F-MODE` note.** `SIMULATION` is the default from the first line of code written in P3 — the safety engine's mode check is not a late addition. What P7 adds is `APPROVAL`'s interrupt/resume flow and the full `AUTONOMOUS` tier routing.

### 7.1 On the decision model — read the model card before building this

**Resolution of the P1/P2 contradiction: `F-DEC` is `P1` in priority and scheduled in `P8`. Laya is shadow-only in v1 and never gates an action.** Priority and phase are separate concepts; the previous draft conflated them and stated both P1 and P2 in four different places.

Laya is real and a much better fit than the synopsis assumed, but it has three documented defects that will silently break a naive integration. All figures below are from the official model card (`huggingface.co/convaiinnovations/laya`), not from secondary coverage.

**What it is.** An Apache-2.0, non-autoregressive "System 1" decision model from Convai Innovations. ModernBERT-large backbone fully fine-tuned plus a decision head trained from scratch (2 transformer layers, an option-marker scorer, an act/escalate head) — 421M total. Trained with RLCD: reinforcement learning against strictly proper scoring rules, so honest probabilities are the reward-maximising output. Every question in a call is answered in one forward pass, ~33–40ms on a T4. `pip install laya`. It never generates text, so there is nothing to parse and nothing to hallucinate.

**Three primitives:** `choice` (select an option, with a distribution), `score` (ordinal), `noul` (boolean probability).

| Checkpoint | Backbone | Params | Context |
|---|---|---|---|
| `laya` | ModernBERT-large | 421M | 512 (`head_max_len` 192, ~320 for state) |
| `laya-multilingual` | mmBERT-base | 322M | 1024, up to 8192 |
| `laya-typed-decisions` | ModernBERT-large | 421M | 1024 (`head_max_len` 256, ~768 for state) |

**The finding that makes it worth doing at all.** `laya-typed-decisions` is already fine-tuned on four workflows, and two of them are our problem domain: **agent-trace observability (0.730)** and **security incidents (0.766)**. By primitive: `noul` 0.857, `choice` 0.733, `score` 0.723. This is far closer to Kavach's decision shape than "a generic classifier we'd have to train from scratch."

**Three defects to design around. These are not speculation; they are in the card's own "Honest Limits" section.**

1. **Never use `noul` for the gate decisions.** `noul` renders its options as `false:`/`true:` and the card reports that this label pair can dominate the answer, returning a confident "no" for clearly positive input (issue #156). The synopsis's "Should this action be executed automatically? Yes/No" is precisely a `noul` question. **Ask it as a two-option `choice` with neutral keys `A`/`B` and the yes/no wording as the descriptions.** The card recommends exactly this workaround.
2. **Never gate on `action.act_probability`.** It reads 1.0 for almost every input and its raw logits run *against* correctness — AUROC 0.30 on 396 labelled decisions (issue #185). The act/escalate head is the obvious thing to wire a safety gate to, and it is the wrong thing. **Gate on `confidence`, which reaches AUROC 0.77 on the same items.**
3. **It ships over-confident and must be temperature-refit on our own data.** Refitting one temperature per (question type, option count) moves mean ECE from 0.466 to 0.081. Since the console displays confidence, uncalibrated probabilities are a correctness bug, not a polish item.

Also: `score` is the weakest primitive (SST-5 0.372), so **risk tier must be a `choice` over LOW/MEDIUM/HIGH, not an ordinal `score`**. High-cardinality questions degrade past ~20 options; with eight fault classes and five actions we are comfortably inside that.

**Therefore the v1 plan:**

- **The deterministic rule engine is the decision authority, permanently, in v1.** It is auditable, explainable to a panel, and correct by construction over an eight-entry catalogue.
- **Laya runs in shadow.** It receives the same decision inputs, produces its decision independently, and its agreement/disagreement with the rule engine is logged. It **never** gates execution, **never** overrides the safety engine, and is **never** the source of truth for a risk decision in v1.
- Decisions are logged in Laya's typed-decision format from P3 onward regardless of whether Laya itself is running, building the fine-tuning corpus at zero cost.
- The fine-tuning loop runs on **Kaggle's free 2×T4 GPUs** via the project's published notebook, so no GPU budget is required. The fine-tuned model in the live path is out of scope (§11).
- Integration is cheap: `laya[serve]` exposes `laya-serve` as an HTTP sidecar. A sidecar container is the lowest-coupling option and keeps Laya's dependencies out of the control-plane image entirely.
- The ~768-token state budget on `laya-typed-decisions` means the graph must compress an incident into a **decision frame**, not pass raw evidence. That compression is real work and is scheduled in P8.

One operational note: `transformers` probes for TensorFlow at import and its abseil runtime can deadlock model construction, so `laya.load()` hangs if TF is installed. Running Laya as a sidecar makes this a property of one container rather than a constraint on the whole stack.

---

## 8. User flows

### 8.1 Onboarding a project

1. User points Kavach at a directory containing a compose file.
2. Kavach runs **preflight** and reports pass/fail per check:
   - Git repository initialised and worktree clean
   - The declared base branch exists (`modernize-stack` for this target) and `kavach/ops` can be created from it
   - Docker socket reachable; compose file parses; all services resolve
   - **Every resolved container carries the onboarded project's compose-project label** (§9.1, `FR-26`)
   - Every service declares a health endpoint, and each one responds
   - OTLP endpoint reachable from inside the target network
   - `kavach.yaml` present and valid
   - SLO contract declared, every PromQL expression parses and evaluates, and is currently satisfied (baseline capture succeeds)
   - Allowed actions declared; no action requires a credential Kavach does not hold
   - **No competing writer:** the target exposes no self-healing route (§5.3)
3. Any failed check blocks enablement and shows the exact remediation command.
4. On pass, Kavach captures a **baseline**: 10 minutes of metrics, the fast-verification scores, the config hash, the prompt version (git SHA of the prompts directory), and the current `RERANK_THRESHOLD`. This baseline is what "last-known-good" means.
5. Project moves to `ARMED`, in `SIMULATION` mode (§5.4). Moving it further is a separate, explicit act.

**Preflight is a differentiator.** No tool in the current field has a formal onboarding contract; they attach to whatever is running and hope.

### 8.2 Autonomous low-risk heal (the demo path)

Project is in `AUTONOMOUS`. Fault `F01` is injected. The console shows, in sequence:

1. **Detected** — error rate breach, with the breaching PromQL expression and window.
2. **Evidence** — spans, logs, container states, recent changes, collected in parallel.
3. **Diagnosed** — `primary_llm_endpoint_outage`, confidence 0.91, with three cited pieces of evidence and the alternatives that were ruled out.
4. **Planned** — `switch_llm_endpoint(primary → backup)`, inverse `switch_llm_endpoint(backup → primary)`.
5. **Risk: LOW** — allow-listed, project ownership verified, blast radius OK, circuit breaker OK → auto-execute.
6. **Executing** — live action log, under the writer lock.
7. **Verifying** — fast verification: health probe, 120s SLO window, 3 deterministic quality checks. All three green.
8. **Resolved** — MTTD 14s, MTTR 96s. Audit entry written, new baseline captured.

### 8.3 Medium-risk approval heal

Same until step 5. Risk is MEDIUM, so:

5. Kavach clones the stack into an isolated sandbox project, applies the repair there, runs fast verification against the sandbox. *(If `F-SBX` is cut, this step is skipped and the proposal carries no sandbox result — see `ROADMAP.md` P7 cut line.)*
6. Console shows a **proposal**: diagnosis, proposed diff, sandbox verification result, risk rationale, inverse action.
7. Human approves or rejects. Rejection is recorded with a reason and feeds the knowledge base.
8. On approval, execute → verify → resolve, identical to the low-risk path.

### 8.4 Unknown failure — never auto-executed in v1

SLO is breached but no catalogue entry matches. The v1 rule is explicit and unconditional:

```
Unknown failure
  → collect evidence (wider window, all signals)
  → generate ranked hypotheses with confidence
  → risk-assess every candidate repair
  → optionally test the top candidate safely (sandbox, if available)
  → ALWAYS escalate to a human
  → store the episode
```

1. Collect evidence across a wider window and all signals.
2. Generate ranked hypotheses with confidence.
3. For each hypothesis above threshold, derive a candidate repair.
4. **Risk-assess every candidate.** This is recorded for the audit trail and the report; it does **not** authorise execution. Any candidate that is not LOW and allow-listed is marked ineligible-for-sandbox and carried forward as evidence only.
5. **Optionally** test the top *eligible* candidate in the sandbox, if a sandbox is available. No sandbox, or no eligible candidate, is not a failure — the flow proceeds.
6. **Always escalate to a human**, with the full hypothesis set and any sandbox evidence. **v1 never auto-executes against an unknown failure, at any risk tier, in any mode.**
7. Store the episode — hypotheses, human decision, outcome — in the knowledge base.

Steps 4 and 5 exist to produce evidence and a decision corpus, not to unlock execution. The previous draft's "anything not LOW and allow-listed stops here" wrongly implied the flow terminates; it does not — it always reaches step 6.

### 8.5 Failed verification → rollback

1. Repair executes, fast verification fails on any of its three probes.
2. Kavach unwinds the **undo stack** in reverse order, under the same writer lock (`ARCHITECTURE.md` §6.0).
3. Re-verifies that the unwind restored the pre-repair state against the recorded pre-state witnesses.
4. Marks the incident `ESCALATED`, freezes further automation on that service, notifies.
5. Records the failed hypothesis so the same repair is ranked lower next time.

**Early abort.** Independently of the above, if the scalar severity metric *increases* after any action, the stack unwinds immediately without waiting for the verification window to close (`FR-15c`).

---

## 9. Requirements

### 9.1 Functional

**Onboarding**
- `FR-01` The system shall refuse to enable self-healing on a project failing any preflight check.
- `FR-02` The system shall require a declared SLO contract before enabling.
- `FR-03` The system shall require an explicit action allow-list; the default allow-list is empty.
- `FR-04` The system shall capture a last-known-good baseline at enablement and after each verified heal.
- `FR-05` The system shall create and use a dedicated `kavach/ops` git branch, **branched from the declared base branch (`modernize-stack`)**, for any change it makes to project files. It shall never commit to `main`, never commit to the user's working branch, and **never push to any remote**.
- `FR-26` **Project ownership.** Before any Docker mutation, the system shall verify that the target container belongs to the onboarded compose project, by compose-project label and service name. A container that does not match is not actionable, regardless of allow-list or risk tier.
- `FR-27` **No arbitrary execution.** The system shall expose no interface that runs a shell command, a script, or an operator-supplied string against the target. Every action is a named, registered adapter with a typed parameter model.

**Observation & evaluation**
- `FR-06` The system shall ingest OTLP traces, metrics and logs over HTTP, and shall normalise LLM span attributes into Kavach's internal schema at the ingestion boundary (`ARCHITECTURE.md` §2.3).
- `FR-07` The system shall run a **fast verification** check set on demand, completing well inside the `PF-04` loop budget. It consists of exactly three probes:
  1. **Health** — `GET /healthz` on every declared service returns healthy.
  2. **SLO / latency** — every declared SLO expression is satisfied over a short window.
  3. **Deterministic answer quality** — **exactly 3 cases, run serially (never concurrently)**, within a **120-second** budget, each asserting **expected-keyword presence** in the answer **and** that the answer is **not a refusal** (the target returns the literal strings "I don't know based on the provided document(s)" and "I don't have any documents to search through yet" when retrieval yields nothing).
- `FR-07c` **The 3 cases are selected empirically against the live clean baseline, never assumed.** A case qualifies only if it passes on repeated runs against a healthy system. A case that is intermittent on a healthy system generates false rollbacks, which is a worse failure than no probe at all. The same 3 cases are used before injection, during injected degradation, and after recovery, so the three measurements are comparable.
- `FR-07d` **A quality probe must fail when retrieval fails.** A case whose answer the model can produce from its own parameters, without any retrieved context, cannot detect `F06` and must not be selected — it would report healthy while retrieval is destroyed. Grounding is checkable deterministically: the target appends a `**Sources:**` block to an answer if and only if chunks were retrieved and the answer is not a refusal.
- `FR-07b` **Fast verification shall contain no model-scored metric.** Keyword presence and refusal detection are string operations. No LLM judge, no embedding similarity, no RAGAS metric, and therefore no cloud API key (`PL-02`) and no nondeterminism in the recovery path. A probe that cannot return the same verdict twice on the same answer is not a verification probe.
- `FR-07a` The system shall run a **full evaluation** on a schedule and on demand for research measurement. The full evaluation is **never** a mandatory probe in the live recovery loop.
- `FR-08` The system shall maintain rolling baselines per metric for anomaly detection.
- `FR-28` The system shall record per-request token usage, read from the LLM response's `usage` field, and shall **never** log prompt bodies, user content, or secrets.

**Detection & diagnosis**
- `FR-09` The system shall detect SLO breaches within 30 seconds of the breach window closing.
- `FR-09a` **SLO contracts are PromQL expressions.** The detection engine shall evaluate a declared expression against Prometheus and compare the scalar result to a threshold. It shall not assume a bare metric name, and shall not reference metrics or labels that the target does not expose.
- `FR-10` The RCA engine shall emit a root cause, a confidence score, a list of cited evidence IDs, and the alternatives considered and rejected.
- `FR-11` The RCA engine shall be able to return `INSUFFICIENT_EVIDENCE` and shall do so rather than produce an uncited diagnosis.
- `FR-12` No action shall be proposed from a diagnosis below the configured confidence threshold.
- `FR-29` A diagnosis of `UNKNOWN` shall never result in an automatically executed action, in any mode, at any risk tier (§8.4).

**Safety**
- `FR-13` Every action shall carry a risk tier assigned before execution.
- `FR-14` The system shall execute only actions present in the project's allow-list, regardless of risk tier or mode.
- `FR-15` The system shall record an inverse action before executing any repair; a repair with no inverse is not executable in `AUTONOMOUS` mode.
- `FR-15a` **Writer exclusivity.** At most one component may mutate the system under management at any time, enforced by an explicit lock. Execution and rollback can never interleave. The target shall expose no self-healing mechanism of its own (§5.3).
- `FR-15b` **Stack-based faithful undo.** A repair may be a sequence of actions. Each state-mutating action pushes its inverse onto a per-incident undo stack, and abort unwinds the stack in reverse order. A single recorded inverse is not sufficient for multi-action repairs.
- `FR-15c` **No regression.** The incident's severity metric must not increase across an incident's lifetime. If a repair makes the SLO breach worse, the stack unwinds immediately without waiting for full verification.

> These three are **Transactional No-Regression (TNR)**, formalised in STRATUS (NeurIPS'25). They are not optional polish. STRATUS's own ablation on AIOpsLab's 13 mitigation problems shows naive retry *without* undo scoring 23.1% against 69.2% with TNR — roughly a 3× difference attributable to the undo mechanism alone. If one safety feature survives a schedule cut, it is this one.

- `FR-16` Blast radius: at most 3 actions per incident and 5 incidents per hour per project, then automation halts and escalates.
- `FR-17` Circuit breaker: if the same `(service, fault_class)` pair is healed more than 3 times in 30 minutes, automation for that pair halts and escalates. This prevents the restart-forever loop on a genuinely broken service.
- `FR-18` Every action shall carry an idempotency key; a duplicate key is a no-op.
- `FR-19` `SIMULATION` mode shall produce a complete plan and a dry-run diff and shall make no write of any kind. `SIMULATION` is the default mode (§5.4).
- `FR-30` **Forbidden mutations.** No action shall delete data, drop a database, scale to zero, run a migration, or change `EMBED_MODEL`. The last is specific to this target: `backend/db.py` infers vector dimension from the embed-model name and executes `DROP TABLE document_chunks CASCADE` on mismatch, so an `EMBED_MODEL` change destroys the corpus. It is on a permanent deny-list, never an allow-list.

**Verification**
- `FR-20` **Fast verification** shall require all three probes to pass: health endpoint, SLO window, and the deterministic quality subset (`FR-07`). Failure of any one triggers rollback. The **full** evaluator (`FR-07a`) is never a gate on a live recovery.
- `FR-21` Verification failure shall trigger the undo stack automatically.
- `FR-22` The system shall verify that the unwind itself succeeded against the recorded pre-state witnesses, and escalate loudly if it did not.

**Audit & learning**
- `FR-23` Every autonomous action shall produce an immutable audit record: incident ID, diagnosis, confidence, proposed action, risk, approver (engine or human), execution timestamp, verification result, outcome.
- `FR-24` Audit records shall be append-only; the API shall expose no update or delete.
- `FR-25` Resolved incidents shall be embedded and stored for similarity retrieval on future incidents.

### 9.2 UX

- `UX-01` The current mode (`SIMULATION` / `APPROVAL` / `AUTONOMOUS`) shall be visible on every screen without scrolling.
- `UX-02` The live incident view shall update without a manual refresh.
- `UX-03` Confidence shall be displayed as a value, never implied by phrasing alone.
- `UX-04` Every claim in a diagnosis shall link to the evidence it came from.
- `UX-05` A pending approval shall show the proposed diff, the sandbox result (or its explicit absence), and the inverse action before the approve control is reachable.
- `UX-06` The console shall be usable in a lecture hall on a projector: legible at 1280×720 downscaled, no information carried by colour alone.

### 9.3 Performance

- `PF-01` Detection latency: under 30s from breach window close.
- `PF-02` RCA latency: under 45s at p95 with a local model.
- `PF-03` Low-risk execution: under 10s from decision.
- `PF-04` Full loop (detect → resolved) for a LOW-risk catalogue fault: under 3 minutes. **Fast verification (`FR-07`) exists to make this achievable; the full evaluation (`FR-07a`) cannot fit and is not in the loop.**
- `PF-05` Console first paint under 1.5s; live updates under 500ms end-to-end.

### 9.4 Platform

- `PL-01` Entire system runs on a developer laptop with 16GB RAM. **One** Ollama and **one** Prometheus are shared between the target and the control plane (`ARCHITECTURE.md` §2.4) specifically to fit this budget.
- `PL-02` **No cloud API key required for any v1 path**, including the live loop and fast verification. The target's existing RAGAS evaluator requires `GEMINI_API_KEY`; it is therefore **not** used by Kavach's live loop, and the research evaluator must offer a fully local scoring path (§17 of the decision log; `FR-07a`).
- `PL-03` **Primary demo platform is Windows 11 with Docker Desktop**, because that is the demo machine. Linux and macOS are supported. The Docker socket mount is the executor's only route to the target, so its behaviour on the actual demo machine is validated in Phase 0, not discovered in Phase 7.

---

## 10. Success metrics

Measured over a scripted run of every **injectable** catalogue fault, 5 repetitions each: **7 faults × 5 = 35 injections.**

The denominator is seven, not eight: `F04` is retired (§6.1) and `F03`'s injector is deferred (§6.4). **Report the denominator alongside every rate.** If `F03` lands later, the run becomes 8 × 5 = 40 and the earlier numbers are restated, not silently replaced.

| Metric | Target | Why it matters |
|---|---|---|
| Detection rate | ≥ 95% | Should be near-solved; a miss here is a bug |
| Localization accuracy (correct service) | ≥ 80% | See §10.2 — report the denominator, the space is small |
| RCA accuracy (correct fault class) | ≥ 75% | Published agents reach 36–46% on an open space |
| **Auto-resolution rate** | **≥ 70% of LOW-risk** | The headline number; published mitigation is 0–55% |
| **False-healing rate** | **≤ 5%** | Verification passed but the fault persisted. The most dangerous metric |
| Rollback correctness | 100% | Every failed verification must restore the prior state |
| MTTD | < 30s | vs. a human baseline of "when a user complains" |
| MTTR (LOW-risk) | < 3 min | The core claim |
| Audit completeness | 100% | No action without a record |

### 10.1 Conditional metrics — the part most projects get wrong

SREGym's finding is that mitigation succeeds 22–62% of the time even when the diagnosis is *wrong*, because an agent can pattern-match a symptom to a fix that happens to work. A headline auto-resolution rate therefore cannot be read as evidence that the RCA engine works. Report both conditionals:

| Metric | What it tells you |
|---|---|
| P(heal succeeds \| diagnosis correct) | How good the repair catalogue and executor are |
| P(heal succeeds \| diagnosis wrong) | How much of the headline number is luck |
| P(diagnosis correct \| heal succeeds) | The one a reviewer will actually ask about |

A high auto-resolution rate sitting next to a high P(heal | wrong diagnosis) means the system is a symptom-matcher with an LLM attached. That is a finding worth reporting honestly, and reporting it is more defensible than hiding it.

### 10.2 Report localization honestly

The target has four actionable services (`backend`, `db`, `ollama`, `frontend`), and most catalogue faults land on `backend` or `ollama`. Localization accuracy against a 4-way choice where the answer is usually the same service is a weak result dressed as a strong one.

**Report it with the denominator stated**, alongside the per-service confusion matrix, and say in the report that the localization task is easy on this target by construction. A reviewer will find this out in one question; stating it first is worth more than the number.

### 10.3 Baselines

**Human baseline:** run the same 35 injections in `SIMULATION` mode and have a team member resolve each one manually, timing it. That is what makes the MTTR number mean something. Without it, MTTR is a number with no denominator.

**Ablation baseline:** run the catalogue with the undo stack disabled. STRATUS's equivalent ablation is the single most quotable result in its paper, and reproducing the shape of it on your own system — even at small scale — is a stronger research contribution than any absolute number you can report.

**Non-LLM baseline:** P3's hardcoded signal→action mapping, measured before the LLM RCA engine exists. This number cannot be recovered later.

**Decision-engine comparison:** rule engine vs. shadowed Laya on identical incidents — agreement rate, disagreement cases, and which was right.

---

## 11. Out of scope for v1

Explicitly not built. Listing these protects the schedule.

- **Kubernetes support of any kind.** The target contains `k8s/` manifests and a `kubernetes` dependency; Kavach v1 reads neither (§5.3)
- Multi-cloud / Vercel / Render / Netlify deploy integrations
- Multi-tenancy, user accounts, RBAC, SSO
- Reinforcement learning for adaptive healing policies
- Predictive failure forecasting (time-series prediction of future faults)
- Multi-agent collaboration across distributed incidents
- Edge / IoT deployments
- CI/CD pipeline integration
- Autonomous execution of MEDIUM-risk actions
- Autonomous execution of any `UNKNOWN` failure (§8.4)
- Fine-tuned Laya decision model in the live path; Laya gating any decision at all (§7.1)
- `F04` cache poisoning, and adding a cache to the target to enable it (§6.1)
- `rebuild_index` and vector-index snapshotting (§6.2)
- TimescaleDB (`ARCHITECTURE.md` §5 — plain Postgres in v1, kept additive)
- A trace viewer competing with Langfuse or Phoenix
- Horizontal scaling of the control plane itself
- Any action that deletes data, scales down, runs a migration, or changes `EMBED_MODEL` (`FR-30`)

---

## 12. Known risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Confabulated RCA.** An LLM will produce a fluent root-cause narrative whether or not the evidence supports one. | A confident wrong diagnosis drives a wrong repair | Evidence citation required; `INSUFFICIENT_EVIDENCE` is a valid output; confidence threshold gates action; the eight-class output space is closed, not free-text |
| **Scope creep back toward the synopsis.** The synopsis targets all AI systems, nine layers, multi-cloud, Kubernetes. | Nothing ships | §11 is binding; widening needs a decision record. The synopsis is archived reference material only |
| **Scope creep back toward the target's own ADRs.** `ADR-002` in the target declares Kubernetes mandatory for self-healing. | A reviewer reads it as Kavach's position | §5.3 states the resolution explicitly and is the document to cite |
| **Verification theatre.** "Metrics look fine now" passing as proof. | False-healing, the worst failure mode | Three independent probes, one of which measures output quality, not system health |
| **The demo depends on a local model being good enough for RCA.** | Weak RCA on stage | Eight-class classification with structured evidence is well within a small local model; the prompt is a classification task, not open reasoning. Have an API key path as fallback |
| **Shared Ollama couples the control plane to the target.** | Breaking the target's LLM path blinds the diagnostician | `F01`/`F02` fault only the primary Toxiproxy listener; Kavach's own calls go direct (§6.3). This is a design requirement, not a convention |
| **The target's jitter middleware contaminates every latency baseline.** 10–150ms random on every request. | ~7% noise on a 2s p95; spurious `F02` detections | `CHAOS_ENABLED=false` by default (§5.2 item 7). Fault injection enables what it needs explicitly |
| **The target's RAGAS evaluator cannot be trusted as a signal.** It monkeypatches `PydanticOutputParser.parse` so a parse failure scores 0.0 silently, requires `GEMINI_API_KEY`, runs serially, and uses a different model than the backend. | An SLO built on it partly measures parser failures | Fast verification is a separate, deterministic, local check set (`FR-07`). The RAGAS evaluator is research-only and adapted, not adopted (`FR-07a`) |
| **The target leaks Postgres connections on exception.** `rag.py` releases connections inline, not in a `finally`. | Repeated failed injections exhaust the pool and produce a spurious `F05` mid-demo | Known and documented. Fixing it is a genuine bug fix in the target but sits outside the §5.2 addition list — it needs its own decision |
| **Windows demo machine.** Docker socket semantics, `host.docker.internal`, and the nvidia GPU reservation all differ. | The executor's only route to the target may not mount | `PL-03`; validated in Phase 0 |
| **Sandbox cloning is harder than it looks** (ports, volumes, state). | `F-SBX` slips | P1, not P0. The approval path works without it |
| **Four people, one semester.** | Over-commitment | The P0 set is 13 features over 8 faults. Everything P1 and below can be cut and the demo still works |

---

## 13. Resolved decisions

These were open questions in the previous draft. They are now decided; recorded here so they are not reopened.

| Question | Decision |
|---|---|
| Does the golden eval set live in the target repo or in Kavach? | **The fast-verification set lives in Kavach**, declared in `kavach.yaml`, because it must be deterministic, local, and independent of the target's RAGAS harness. The target's 40-case `evaluation_dataset.csv` is the source material for it and remains the basis of the research evaluator |
| Is prompt versioning Kavach's responsibility or the target's? | **The target versions prompts in files; Kavach reads their git history.** This is §5.2 addition 6 — the two prompts move to `prompts/*.txt`, loaded at request time, and the prompt version is the git SHA of that directory |
| How is the human notified outside the console? | **Console-only for v1.** A webhook is P2 |
| Is TimescaleDB required? | **No.** Plain Postgres + pgvector in v1; the schema is written so Timescale can be added later if telemetry volume justifies it (`ARCHITECTURE.md` §5) |
| One Prometheus or two? | **One**, in the control plane, scraping both the target and Kavach. The target's bundled Prometheus is moved behind a compose profile (`ARCHITECTURE.md` §2.4) |
| One Ollama or two? | **One**, the target's. Kavach's RCA calls route to it directly, bypassing Toxiproxy (§6.3) |
