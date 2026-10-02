# ROADMAP.md — Kavach

> Build order, acceptance criteria, and owner tracks.
> Read with `PRD.md` (what) and `ARCHITECTURE.md` (how). This file is **when** and **in what order**.

---

## Assumptions — correct these before using the schedule

- **~14 working weeks.** Adjust every week number if your deadline differs; the *order* holds regardless.
- **Four people**, part-time alongside other coursework.
- The demo is the deliverable (`PRD.md` §5), so every phase ends in something demonstrable.
- **The target application already exists.** `Simple_RAG-Pipeline` is not built here — it is onboarded and instrumented (`PRD.md` §5.1). The old "build `demo-rag`" phase is deleted, not re-pointed.

---

## The two rules

**1. Vertical, not horizontal.** Never build a layer across all fault classes. Build one fault class through every layer, then the next. A horizontal build means nothing works until the final week.

**2. Build what breaks before what fixes.** The fault injector is Phase 2, not Phase 7. You cannot test detection without deterministic failure, measure MTTD without a known injection timestamp, or write a single integration test without an injector.

---

## Phase map

```
P0 scaffold
 └─ P1 onboard + instrument Simple_RAG-Pipeline ─┐
     └─ P2 F06 injector + telemetry ─────────────┤
         └─ P3 DUMB LOOP (F06) ◀━━━━━━━━━━━━━━━━┷━ first demoable milestone (~week 6)
             ├─ P4 LLM RCA ────┐
             ├─ P5 console     │
             │                 ├─ P6 remaining 7 faults ─┐
             └─ P7 safety ─────┘                         ├─ P8 git · memory · Laya
                                                          │
                                                          └─ P9 measure, report, demo
```

| Phase | Goal | Weeks | Gate |
|---|---|---|---|
| P0 | Kavach scaffold | 1 | `make check` green; docker socket proven on the demo machine |
| P1 | Onboard + instrument the target | 2–3 | Preflight passes against `Simple_RAG-Pipeline` |
| P2 | `F06` injector + telemetry proven | 3 | Break/unbreak 20× deterministically, visible in Prometheus |
| P3 | **Dumb closed loop, no LLM** | 4–6 | **`F06` auto-heals end to end, with a working rollback** |
| P4 | LLM RCA engine | 6–8 | Beats the P3 baseline on the same injections |
| P5 | Console | 6–9 | Loop watchable live |
| P6 | The remaining seven faults | 8–11 | Each a complete vertical slice |
| P7 | Full safety engine | 9–11 | Three modes, ownership, breaker, blast radius |
| P8 | Git isolation, knowledge base, Laya shadow | 11–13 | `make bench` emits the metrics table |
| P9 | Measure, report, rehearse | 12–14 | Demo runs clean 3× in a row |

---

## P0 — Kavach scaffold

**Week 1 · Owner: control-plane track**

**Deliverables**
- `git init` the Kavach repository. It is not one today, and `docs/decisions/` is meaningless without it
- Repo at the structure in `ARCHITECTURE.md` §3 (directories with `.gitkeep`, **no stub code**)
- `Makefile` with every target in `AGENTS.md`, failing loudly where unimplemented
- `infra/docker-compose.yml`: postgres+pgvector, redis, prometheus, otel-collector. **No Ollama, no second Prometheus** (`ARCHITECTURE.md` §2.4)
- FastAPI app with `/healthz` only; Next.js app with one page
- `pyproject.toml` (uv, ruff, mypy strict, pytest), `package.json` (pnpm, eslint, prettier, vitest)
- Pre-commit hooks, `.env.example` with placeholders only
- `targets/simple-rag.yaml` — the pointer file (path, base branch, compose project, service map)
- Decision records: `0001-locked-scope.md`, `0002-target-is-external-repo.md`, `0003-sole-healing-controller.md`, `0004-eight-fault-catalogue.md`
- `docs/synopsis-original.md` — the archived synopsis with a header marking it superseded

**Acceptance**
- [ ] `make setup` works on a clean machine
- [ ] `make up` brings every control-plane container healthy
- [ ] `make check` passes (lint + mypy strict + tsc + tests)
- [ ] `curl localhost:8000/healthz` returns 200
- [ ] **The docker socket mount works on the Windows demo machine, and a container can be listed, inspected and restarted from inside the control-plane container.** This is `PL-03` and it is the one thing that stops the entire project if it fails. Do not defer it to P3
- [ ] Kavach can reach the target's `ollama` by service name across the joined network

**Kickoff prompt**
> Read PRD.md, ARCHITECTURE.md and AGENTS.md. Build Phase 0 only: repo scaffold, compose files, tooling, Makefile, a FastAPI healthz route and an empty Next.js app. No business logic, no stub classes for future phases. Prove the docker socket works on this machine. Plan first, then stop for approval.

---

## P1 — Onboard and instrument `Simple_RAG-Pipeline`

**Weeks 2–3 · Owner: target track**

This replaces the deleted "build `demo-rag`" phase. The application exists; what does not exist is any way to observe or control it. **The complete, closed list of permitted additions is `PRD.md` §5.2 — ten items. Do not add an eleventh without a decision record.**

All work lands on `kavach/ops`, branched from `modernize-stack`. **Never `main`. Never pushed.**

**Deliverables**

*Observation (`PRD.md` §5.2 items 1, 2, 4)*
- OpenTelemetry SDK + `opentelemetry-instrumentation-fastapi` / `-psycopg2` / `-requests` in the target's backend, exporting OTLP to the collector. **The target has none today** — the README's "FastAPI natively supports OpenTelemetry" claim is false
- Manual spans around the two Ollama calls and the pgvector query, emitting Kavach's internal attribute schema (`ARCHITECTURE.md` §2.3)
- The metrics in `ARCHITECTURE.md` §4.1: `ragapp_llm_requests_total`, `ragapp_llm_duration_seconds`, `ragapp_llm_tokens_total`, `ragapp_retrieval_top_similarity`, `ragapp_retrieval_empty_context_total`, `ragapp_db_pool_in_use`
- Read Ollama's `usage` block into the span (two lines in `rag.py`). **Never log prompt bodies or secrets** (`FR-28`)
- `GET /healthz` checking Postgres **and** Ollama, not just liveness

*Control (items 3, 5, 6, 7)*
- The config interface, `ARCHITECTURE.md` §7.2. `embed_model` is **not** settable
- Lower the 1200-second LLM timeout to ~30s (two lines in `rag.py`)
- Move both prompts to `prompts/answer.txt` and `prompts/query_expansion.txt`, loaded at request time so a rollback needs no rebuild. **Mechanical extraction — do not redesign the RAG pipeline**
- `CHAOS_ENABLED` around the existing jitter middleware, **default `false`**

*Reliability (item 10, `docs/decisions/0005`)*
- **Release Postgres connections in `finally` blocks** in `store_chunks` and `retrieve_relevant_chunks`. Minimal: wrap acquire/release in `try/finally`. **No database-layer redesign, no schema change, no pooling-strategy change.** Without this, every failed injection leaks a pooled connection and the "20 cycles leave the stack identical" criterion is untestable (`PRD.md` §5.2)

*Infrastructure (items 8, 9)*
- Toxiproxy in the target compose with **two listeners** to the one Ollama (`PRD.md` §6.3)
- Healthchecks on `backend`, `frontend`, `ollama`
- The target's bundled `prometheus` service moved behind `profiles: [standalone]` (`ARCHITECTURE.md` §2.4)
- `kavach.yaml` — the full manifest from `ARCHITECTURE.md` §7

*Neutralisation (`PRD.md` §5.3)*
- `POST /v1/webhook/alert` **removed from the running application.** `backend/aiops_agent.py` stays on disk, unimported and unreachable
- Verified: no code path can reach `delete_namespaced_pod`
- The target's `ADR-001` / `ADR-002` are **not modified**

*Control plane*
- `onboarding/` — manifest parsing, the preflight check registry, baseline capture
- `verification/fast_set.yaml` — 3–5 deterministic cases drawn from the target's 40-case dataset, scored locally with **no cloud API key** (`PL-02`)

**Acceptance**
- [ ] `make target-up` → the app answers a question correctly from the corpus
- [ ] Spans reach the collector carrying model, **token counts** and duration
- [ ] Every one of the six new metrics is scrapeable and non-zero under load
- [ ] `GET /healthz` returns 503 when Postgres is stopped, and 503 when Ollama is unreachable
- [ ] `PUT /v1/admin/config` changes `rerank_threshold` and the next query reflects it, with **no container restart**
- [ ] `PUT /v1/admin/config` with `embed_model` is rejected, and the `document_chunks` table is intact
- [ ] Rewriting `prompts/answer.txt` changes the next answer with no rebuild
- [ ] `CHAOS_ENABLED=false` → p95 latency variance measurably drops
- [ ] `POST /v1/webhook/alert` returns 404
- [ ] Both Toxiproxy listeners proxy to Ollama; a toxic on A leaves B working
- [ ] `make onboard` → preflight passes; baseline captured (metrics, fast-eval scores, config hash, prompt SHA, `rerank_threshold`)
- [ ] Every SLO expression in `kavach.yaml` parses and evaluates against the live Prometheus
- [ ] Fast verification completes in **under 45s** with zero network egress, and its quality probe is keyword-presence + non-refusal only — **no model-scored metric** (`FR-07b`)
- [ ] **Connection-leak fix proven:** force 15 consecutive `/v1/chat` failures, then confirm the pool still serves requests and `ragapp_db_pool_in_use` returns to its idle value
- [ ] `git log kavach/ops` shows the work; `main` and `modernize-stack` are untouched; nothing was pushed

**Cut line:** the fast-verification set is 3–5 cases. That is the ceiling, not a target. The 40-case RAGAS evaluator is P8 research work and is **never** in the live loop.

---

## P2 — The `F06` injector and the harness

**Week 3 · Owner: target track**

**`F06` retrieval collapse is the first fault**, reversing the previous draft's `F01`-first order. Three reasons:

1. It works against the target **as it already is** — `rerank_threshold` is live config. No new provider, no second model, no new infrastructure.
2. It produces the **silent HTTP 200 with "I don't know based on the provided documents"** failure. Detection cannot come from HTTP error rate; it must come from retrieval similarity or fast-eval pass rate. That forces the quality-driven detection path to be real in P3 instead of deferred, and that path is the project's actual contribution (`PRD.md` §2.1).
3. It is a **novelty fault** (`PRD.md` §2.2). The cheapest faults to build, `F03` and `F05`, are the infrastructure-level ones that prior art already covers.

`F01` is *not* first because its repair needs the two-listener Toxiproxy design and a configurable endpoint, both of which are P1 deliverables that want a week to settle. `F03` is not first — or scheduled at all — because the target sets `restart: always` on `backend`, so **Docker heals it before Kavach can**, and the only way to change that would be to weaken the target's own resilience. Its injector is deferred (`PRD.md` §6.4).

**Deliverables**
- `harness/inject.py` CLI: `make inject FAULT=F06`
- `harness/faults/base.py` — `inject()` / `revert()` / `is_active()` protocol
- `harness/faults/f06_retrieval_collapse.py` — raises `rerank_threshold` via the config interface, records the prior value
- Pytest fixture that always reverts in teardown, including on test failure
- Injection timestamp recorded, so MTTD is measurable

**Acceptance**
- [ ] `make inject FAULT=F06` → retrieval similarity drops and empty-context rate rises within 5s
- [ ] The app returns HTTP **200** with a non-answer — confirm the failure is silent, because that is the point
- [ ] `revert()` → retrieval recovers within 5s
- [ ] 20 consecutive inject/revert cycles leave the stack identical to the start state
- [ ] A test that raises mid-fault still reverts
- [ ] `ragapp_retrieval_top_similarity` and `kavach_fast_eval_pass_rate` both visibly move in Prometheus
- [ ] Injection timestamp is recorded

**Why this is week 3:** every integration test in `AGENTS.md` depends on it, and MTTD has no meaning without a known t₀.

---

## P3 — The dumb closed loop ⭐

**Weeks 4–6 · Owner: control-plane track · The milestone that de-risks the project**

No LLM. No RCA engine. A hardcoded mapping from one signal to one action. The point is to close the loop early and cheaply.

**Deliverables**
- `ingestion/` — OTLP receiver, attribute normalisation into the internal schema, PromQL expression evaluation
- `detection/slo.py` — PromQL expression evaluation on a 15s tick (`FR-09a`)
- `graph/` — LangGraph graph with `PostgresSaver`, but only: detect → plan → gate → execute → verify → resolve/rollback
- `plan` node is **a literal dict**: `{retrieval_similarity_breach: rollback_config}`. No intelligence. This is deliberate
- `safety/` — `permit()` with **project ownership, the deny-list, and the allow-list** implemented; the rest stubbed returning ALLOW with a TODO
- **`SIMULATION` is the default mode from this phase's first commit**, not a P7 addition (`PRD.md` §5.4)
- `executor/` — registry, the `Action` protocol with a mandatory `inverse()` enforced at registration, http (config interface) + docker adapters
- **The undo stack and the writer lock** (`ARCHITECTURE.md` §6.0) — these are in from day one, not retrofitted
- **A minimal git adapter** — checkout `kavach/ops`, commit, revert by blob SHA. *Scheduled earlier than the suggested P8 slot because `rollback_config` writes a versioned project file, so `FR-05` applies from the first file-touching action. P8 completes the model (incident branches, full deny-case suite)*
- `verification/` — all three fast probes (`FR-07`)
- `audit/` — append-only log with the hash chain

**Acceptance**
- [ ] `make inject FAULT=F06` → detected within 30s, no human involved
- [ ] `rollback_config` executes, three fast probes pass, incident resolves
- [ ] MTTD and MTTR recorded and visible in the database
- [ ] **`SIMULATION` is the default**, and in it the loop produces a full plan and a dry-run diff while writing nothing
- [ ] **Ownership deny case:** an action naming a container outside the onboarded compose project is denied (`FR-26`)
- [ ] **Deny-list case:** an `embed_model` change is denied in every mode, and `document_chunks` survives (`FR-30`)
- [ ] **Forced-failure test:** make verification fail artificially → the undo stack unwinds, prior state is restored from the witness, incident escalates
- [ ] **Severity-regression test:** make the severity metric worsen after the action → the stack unwinds *immediately*, without waiting for the verification window (`FR-15c`)
- [ ] An action registered without an `inverse()` raises at import time
- [ ] Every step produced an audit row; the hash chain verifies
- [ ] 10 consecutive injections all auto-heal
- [ ] `main` untouched, nothing pushed

**At the end of P3 you have a working self-healing platform.** Ugly, one fault, zero intelligence — but demoable. If everything after this slips, you still have something to show.

**Also: P3 is your non-LLM baseline.** Record its auto-resolution rate and MTTR before touching Phase 4. **You cannot recover this number later.**

**Kickoff prompt**
> Read PRD.md, ARCHITECTURE.md (especially §6.0 TNR and §6.3 docker ownership) and AGENTS.md. Build Phase 3: the closed loop for F06 only, with NO LLM anywhere. The plan node is a hardcoded dict mapping one detection signal to one action. The undo stack, writer lock, project-ownership check, deny-list and append-only audit log are in scope and must be correct. SIMULATION is the default mode. Other safety checks are stubs returning ALLOW with a TODO. Plan first, then stop.

---

## P4 — Swap in the LLM RCA engine

**Weeks 6–8 · Owner: control-plane track**

**Deliverables**
- `graph/nodes/collect_evidence.py` — parallel collection: spans, logs, container state, recent git diffs, config snapshot, verification history
- `graph/nodes/diagnose.py` — structured Pydantic output: `fault_class`, `confidence`, `evidence_ids[]`, `rejected_alternatives[]`. The class enum is the **eight** catalogue IDs plus `UNKNOWN` and `INSUFFICIENT_EVIDENCE` — note there is no `F04`
- `INSUFFICIENT_EVIDENCE` as a first-class return value
- Confidence threshold gating in `permit()`
- **The `UNKNOWN` gate** — a diagnosis of `UNKNOWN` can never reach execution, in any mode (`FR-29`)
- `llm/prompts/` — versioned prompt files
- Kavach's LLM client pointing **directly at Ollama**, bypassing Toxiproxy (`PRD.md` §6.3)
- Recorded LLM fixtures so CI never calls a model

**Acceptance**
- [ ] Diagnosis names `F06` with confidence and at least two cited evidence IDs
- [ ] Every cited `evidence_id` resolves to a real stored row
- [ ] Fabricate an ambiguous incident → returns `INSUFFICIENT_EVIDENCE`, no action proposed
- [ ] Below-threshold confidence → escalates instead of executing
- [ ] An `UNKNOWN` diagnosis escalates and executes nothing, even in `AUTONOMOUS` with a LOW-risk allow-listed candidate
- [ ] **With `F01` injected (Toxiproxy down on listener A), RCA still completes** — the control plane's own LLM path is unaffected
- [ ] **Comparison recorded:** P3 hardcoded mapping vs. P4 LLM RCA on the same 10 injections
- [ ] RCA completes under 45s p95 on the local model
- [ ] Unit tests run with zero network calls

**This phase produces a research result**, not just a feature: a measured comparison between symptom-matching and evidence-grounded diagnosis on identical faults.

---

## P5 — The console

**Weeks 6–9 · Owner: console track · Parallel with P4**

Can start as soon as P3's routes exist. Generate the client from OpenAPI; never hand-write a fetch. **`DESIGN_SYSTEM.md` governs `apps/console/` and nothing else** — the target's Next.js 14 frontend is out of its jurisdiction (`DESIGN_SYSTEM.md` §0).

**Deliverables**
- Design tokens as CSS variables and TS constants, both themes
- Three-zone layout (`DESIGN_SYSTEM.md` §6)
- Loop Ring, incident row, evidence item, diagnosis card, action plan, verification strip, risk badge, mode switch, audit table
- WebSocket hub + live incident updates via Redis pub/sub
- Onboarding preflight checklist screen
- `make gen-client` wired into `make check`

**Acceptance**
- [ ] Inject `F06` and watch the whole loop live without refreshing
- [ ] Every diagnosis citation is clickable and opens the evidence
- [ ] Mode indicator visible on every screen without scrolling, and it reads `SIMULATION` by default
- [ ] Legible at 1280×720 (projector test — do this on the actual projector)
- [ ] Keyboard-only navigation works; focus is always visible
- [ ] No colour-only state indicators anywhere
- [ ] Contrast audit passes on both themes
- [ ] A backend type change breaks the frontend build

---

## P6 — The remaining seven fault classes

**Weeks 8–11 · Owner: target track leads, control-plane supports**

`F06` shipped in P3. Seven remain. One complete vertical slice each: injector → detection signal → RCA path → repair action + inverse → verification probe → integration test. **Never start the next until the previous passes.**

| Order | Fault | Note |
|---|---|---|
| 1 | `F01` primary LLM endpoint outage | Toxiproxy from P1; gives the LOW-risk autonomous demo path of `PRD.md` §8.2 |
| 2 | `F08` config regression | Reuses the config interface already built for `F06` |
| 3 | **`F07` prompt regression** | **Needs the git adapter extended to prompt blobs.** Prompts were externalised in P1, so this is the git work, not the extraction |
| 4 | **`F09` token blowout** | Reuses `F07`'s machinery; token capture landed in P1 |
| 5 | `F02` latency degradation | Toxiproxy already in place. **Confirm the ~30s timeout from P1 holds** — at 1200s this is a hang, not a fault |
| 6 | `F05` pool exhaustion | Watch for the target's pre-existing connection leak confounding results (`PRD.md` §12) |
| — | ~~`F03` crash-loop / OOM~~ | **Deferred, not scheduled.** `restart: always` means Docker heals it first, and removing that would weaken the target's resilience to manufacture a fault. See `PRD.md` §6.4 |

**There is no `F04`** — the target has no cache (`PRD.md` §6.1). Do not add Redis to the target to create one.

**`F03` is not in this phase.** If a deterministic, honest crash-loop injector is found (a memory limit that OOMs on every boot, proven over 20 cycles), it can be added as an eighth slice. **Do not write a placeholder injector to make the catalogue look complete** — `AGENTS.md` forbids it, and a fake injector corrupts every number derived from it.

**Acceptance per fault**
- [ ] Injector is deterministic, reverts cleanly, 20 cycles stable
- [ ] Detection fires within 30s
- [ ] Diagnosis names the right class in ≥8 of 10 runs
- [ ] Repair executes; the inverse restores prior state exactly, verified against the pre-state witness
- [ ] All three fast verification probes pass
- [ ] Integration test green in CI
- [ ] Forced-verification-failure test green
- [ ] Ownership and deny-list checks still pass for this fault's action

**Cut line — this is the one that matters.** `F06`–`F09` carry your novelty claim (`PRD.md` §2.2), and `F06` is already banked from P3. If time runs out, **cut `F02` and `F05` — never `F07` or `F09`.** Five faults including all four novel ones beats eight faults where the novel ones are half-finished.

---

## P7 — The full safety engine

**Weeks 9–11 · Owner: control-plane track · Parallel with P6**

Replaces the P3 stubs. Ownership, deny-list and allow-list are already real from P3; this phase adds the rest.

**Deliverables**
- Deterministic risk-tier table (`ARCHITECTURE.md` §6.2) — five actions, everything else HIGH
- Blast radius: ≤3 actions/incident, ≤5 incidents/hour
- Circuit breaker: ≤3 heals per `(service, fault_class)` per 30 min
- Idempotency keys
- The full ten-step `permit()` order (`ARCHITECTURE.md` §6.1)
- `APPROVAL` mode via LangGraph `interrupt()` + `Command` resume; full `AUTONOMOUS` tier routing
- `risk_decisions` rows including the Laya-format `typed_decision_frame`
- `F-UNK` — the unknown-failure flow, which **always** reaches human escalation (`PRD.md` §8.4)
- Sandbox (`F-SBX`, priority P1 — see cut line)

**Acceptance**
- [ ] **Every rule has a passing deny-case test** — this is the phase's real deliverable
- [ ] `SIMULATION` produces a full plan and writes nothing, verified by filesystem **and** docker state diff
- [ ] An action not on the allow-list is denied regardless of mode or risk tier
- [ ] An `embed_model` change is denied even if someone adds it to the allow-list — the deny-list wins
- [ ] A container outside the compose project is denied even with a matching service name
- [ ] Circuit breaker: inject the same fault 4× in 30 min → the 4th escalates instead of healing
- [ ] Blast radius halts automation at the limit
- [ ] Approval flow: proposal → interrupt → human approves → resume → execute. Graph state survives a control-plane restart mid-interrupt
- [ ] Duplicate idempotency key is a no-op
- [ ] An `UNKNOWN` failure runs the full hypothesis flow and **always** ends at human escalation, never execution
- [ ] No route, parameter or adapter accepts an arbitrary command string (`FR-27`) — grep to confirm

**Cut line:** the sandbox is the most likely thing to overrun — ports, volumes and stateful services make it harder than it reads. The approval path works without it; the proposal simply shows "no sandbox result". Drop the sandbox before dropping anything else here.

---

## P8 — Git isolation, knowledge base, Laya shadow

**Weeks 11–13 · Owner: evaluation track**

**Deliverables**

*Git isolation, completed*
- The full model in `ARCHITECTURE.md` §13: incident branches derived from `kavach/ops`, pre-state blob witnesses, the complete deny-case suite
- Deny-case tests for: write while `HEAD` is `main`, any `push`, `commit --amend`, force-push, committing a `.env`-shaped path

*Knowledge base*
- `knowledge/` — incident embedding, pgvector similarity retrieval, wired into evidence collection

*Laya shadow (`F-DEC`, priority P1, phase P8)*
- `laya-serve` sidecar in the control-plane compose
- `decision/laya.py` implementing `DecisionEngine`, **shadow-only, never gating**
- Decision-frame compressor fitting the ~768-token state budget
- Temperature refit on collected decisions
- `shadow_engine` / `shadow_verdict` / `shadow_agreed` populated on every `risk_decisions` row

*Research evaluator (`F-EVAL-FULL`, `FR-07a`)*
- A clean evaluation interface, adapted from the target's RAGAS harness rather than adopted. It must: not require `GEMINI_API_KEY` for its default path (`PL-02`), not monkeypatch `PydanticOutputParser`, and use the same model the backend uses
- `harness/report.py` → `make bench`: **7 injectable faults × 5 reps = 35 injections**, metrics table including the `PRD.md` §10.1 conditionals and the stated denominator

**Acceptance**
- [ ] Laya answers every decision in shadow; agreement/disagreement rate logged
- [ ] **Laya's output is never read by `permit()`** — grep to confirm
- [ ] **No `noul` questions anywhere** — all booleans are two-option `choice` with neutral keys
- [ ] **Nothing gates on `act_probability`** — grep to confirm
- [ ] Temperature refit done; ECE recorded before and after
- [ ] Decision frames never exceed the state budget; overflow raises rather than truncating
- [ ] Similar past incidents appear in evidence collection
- [ ] The research evaluator runs with **no cloud API key** and no monkeypatch, and its scores are reproducible across two runs
- [ ] `make bench` emits a complete metrics table unattended, with **35** injections and the denominator printed
- [ ] Every git deny case has a passing test

---

## P9 — Measure, write, rehearse

**Weeks 12–14 · Owner: everyone**

The phase most teams skip and most reviewers notice.

**Deliverables**
- **Human baseline run** — all 35 injections in `SIMULATION` mode, resolved manually by a teammate, timed. ~2 hours of work and it is what makes MTTR mean anything
- **Undo ablation run** — the catalogue with the undo stack disabled. Reproducing the shape of STRATUS's result on your own system is your strongest research contribution
- Full `make bench` with conditional metrics
- **Localization reported honestly** — with the denominator and the per-service confusion matrix (`PRD.md` §10.2)
- `make scenario NAME=demo-full` — a scripted sequence: one autonomous heal, one approval heal, one rollback, one unknown-failure escalation
- Report, slides, demo rehearsal

**Acceptance**
- [ ] Human baseline MTTR recorded per fault class
- [ ] Undo ablation numbers recorded
- [ ] P(heal | correct diagnosis) and P(heal | wrong diagnosis) both reported
- [ ] P3 vs. P4 and rule-engine vs. Laya comparisons written up
- [ ] The eight-fault catalogue and `F04`'s retirement are stated in the report, with the reason
- [ ] The target's Kubernetes files are explained as *not* a Kavach capability (`PRD.md` §5.3)
- [ ] **Demo script runs clean three times consecutively on the demo machine**
- [ ] Offline rehearsal — no network, local model only, no `GEMINI_API_KEY` present
- [ ] A failure path is in the demo. Showing a rollback that works is more persuasive than four successes

---

## Owner tracks

| Track | Phases | Owns |
|---|---|---|
| **Control plane** | P0, P3, P4, P7 | `graph/`, **`safety/`, `executor/`, `verification/`** |
| **Target + faults** | P1, P2, P6 | The target's instrumentation, `harness/faults/` |
| **Console** | P5 | `apps/console/` |
| **Evaluation** | P8, P9 | `evaluation/`, `harness/report.py`, all baselines |

**`safety/` and `executor/` have one author.** Those two directories carry the recoverability guarantee; split ownership is how an inverse quietly stops being recorded.

**The target track has a second responsibility:** every change to `Simple_RAG-Pipeline` stays inside the ten permitted additions (`PRD.md` §5.2), lands on `kavach/ops`, and is never pushed. That track owns the boundary, not just the code.

---

## Working with Claude Code

- **One phase per session.** Never hand it the whole roadmap.
- **Always plan-then-stop.** Review the plan before any code.
- **`make check` green before you accept anything.**
- Read the "Problems I noticed but did not fix" section of every summary. That is where the real information is.
- **Keep the synopsis out of context.** It contradicts `PRD.md` on scope — Kubernetes, nine layers, multi-cloud, MongoDB — and both in context means Claude Code averages them.
- **Keep the target's `ADR-002` out of context too**, for the same reason: it declares Kubernetes mandatory for self-healing, which is the opposite of Kavach's scope.

Three failure modes to watch for: building adjacent phases because they appear in the PRD; quietly weakening a safety check to make a test pass; and widening the ten permitted target additions. `AGENTS.md` forbids all three. Check anyway.

---

## Checkpoints

| When | Question | If no |
|---|---|---|
| End of week 1 | Does the docker socket work from inside a container on the demo machine? | **Stop.** The executor has no other route to the target |
| End of week 3 | Does `F06` inject and revert deterministically, 20×, with the metrics moving? | Stop. Nothing downstream works without this |
| End of week 6 | Does one fault auto-heal end to end with a working rollback? | Cut P8 entirely, move everyone onto the loop |
| End of week 8 | Are `F07` and `F09` started? | Drop `F02` and `F05` now, not later |
| End of week 11 | Does `make bench` run unattended? | Cut the Laya shadow, protect P9 |
| End of week 12 | Has the human baseline been run? | Do it this week. It is 2 hours and it is load-bearing |

---

## What success looks like

A reviewer sees a fault injected into a **real, pre-existing RAG application that was never designed to be healed**. They watch the application return HTTP 200 with a useless answer while every liveness probe stays green — and they watch Kavach notice anyway. The system diagnoses it with cited evidence and a stated confidence, a risk decision is made and recorded, a repair executes under a writer lock with its inverse already captured, and verification confirms it. Then a *second* fault where verification fails and the system unwinds itself cleanly.

Alongside that: a table showing LLM RCA beating symptom-matching, and undo beating no-undo, on the same injections — and an honest note that `F04` was dropped because the target has no cache, rather than a cache added to make the number nine.

That is a stronger project than nine fault classes half-working.
