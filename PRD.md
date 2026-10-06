# PRD.md — Kavach

> **Autonomous AI Operations Platform**
> VIT · CSE-AI (E) · Group 14 · Engineering Research & Innovation · AY 2026-27
>
> `Kavach` (कवच, "shield") is a working codename. It appears in package names,
> container names and the UI wordmark. Swap it globally now if at all.

**Companion documents:** `CONTRACT.md` (the specification), `ARCHITECTURE.md` (how), `ROADMAP.md` (when), `AGENTS.md` (rules for AI coding agents), `DESIGN_SYSTEM.md` (visual rules).

---

## 1. Product overview

**One line:** Kavach watches an AI application, works out why it broke, fixes it, proves the fix did not make things worse, and tracks what it still owes.

**The thesis.** This is a *platform*, not a script with a config file, and the difference is testable. A platform is defined by a contract, not by a feature count. `CONTRACT.md` specifies what an AI application must expose to be autonomously recoverable; Kavach is the reference implementation. The narrow fault catalogue and the general interfaces are not in tension — the catalogue is data, the platform is the interpreter.

**The conformance test, which the project lives or dies by:**

> A teammate who has not read Kavach's source onboards a second, unseen RAG application in under one hour, by writing `kavach.yaml` and satisfying preflight, with **zero changes to Kavach's source code.**

If proof #2 requires a code change, we built a project. If it does not, we built a platform.

**Two substantive departures from existing practice**, both arising from the application layer being AI:

1. **Health is a vector, not a boolean.** A repair that restores availability by failing over to a weaker model has traded quality for uptime. Scalar verification reports that as success and learns the wrong lesson. Kavach verifies against a multi-objective contract and reports a delta per objective.
2. **Mitigation is not resolution.** Failing over does not fix the provider outage. Every mitigation creates **remediation debt** — a tracked obligation with a machine-evaluable repayment trigger. No existing system models the return path.

---

## 2. Problem

AI applications are chains of independently-failing parts: a model provider, a vector store, an embedding model, a prompt version, a retrieval index, a cache, a container runtime. A failure anywhere surfaces to the user identically — a bad answer, a slow answer, or no answer.

Three properties make this harder than classic infrastructure operations:

1. **Failure is often silent.** The service returns 200 with an ungrounded answer. Liveness passes. No alert fires. The system is "up" and wrong.
2. **The diagnosis space is wide.** A latency spike could be the provider, the vector store, the embedding call, a cold cache, or a prompt that suddenly emits 4× the tokens.
3. **The repair is layer-specific.** Restarting a container does nothing for a prompt regression. Generic auto-remediation applies the wrong remedy and masks the real fault.

### 2.1 This is not a solved problem

Figures from the papers, not from secondary summaries.

**AIOpsLab** (arXiv:2501.06706) defines the four-level ladder this loop follows — detection, localization, RCA, mitigation — against live fault-injected environments. Overall accuracy: Flash 59.32%, ReAct 55.93%, GPT-4-with-shell 49.15%, GPT-3.5-with-shell 15.25%. Detection alone reaches 100% for Flash and 76.92% for ReAct against 15.38% for non-LLM baselines. On mitigation, GPT-4-with-shell and ReAct reach roughly 43% correctness, TaskWeaver 29%, and **GPT-3.5-with-shell recovers nothing at all**.

**STRATUS** (NeurIPS'25, arXiv:2506.02009) is the current state of the art on that task and the closest prior art to our safety design: 69.2% (9/13) on AIOpsLab mitigation with GPT-4o, 50.0% (9/18) on ITBench, at least 1.5× the baselines.

**OpenRCA 2.0:** exact root-cause set recovery succeeds 20.7% of the time on average across 11 frontier LLMs. **ITBench:** frontier agents resolve under a third of 94 scenarios.

**SREGym** reports the finding that most threatens naive measurement: when an agent diagnoses correctly, mitigation succeeds only 68–89% of the time; when the diagnosis is *wrong*, mitigation still succeeds 22–62% of the time, because agents pattern-match symptoms to fixes. **A successful heal is not evidence of a correct diagnosis.** §11 measures the two independently.

**Detection is solved. Diagnosis and mitigation are not.**

### 2.2 Prior art, honestly

Two clusters exist. This is not an empty field.

**Cluster A — request-level self-correction.** `self-healing-rag` and similar LangGraph projects classify retrieval quality and retry or abstain within a single request. `error-recovery` intercepts agent errors and injects recovery prompts. Published frameworks add reliability scoring with re-planning and tool re-selection. All heal *an answer*. None touches deployed operational state.

**Cluster B — infrastructure-level agentic SRE.** K8sGPT runs deterministic Kubernetes analysers with an LLM only explaining findings, strictly read-only. HolmesGPT is a CNCF Sandbox ReAct agent whose README still claims read-only but which now ships a Kubernetes Remediation MCP toolset applying scaling, rollbacks and resource edits, plus a Beta GitHub toolset opening fix PRs — it is actively crossing the read/write line. Aurora generates remediation PRs behind human approval. STRATUS executes under a formal guarantee but is a benchmark-evaluated research system, not a deployable platform.

**Genuine overlaps to acknowledge:**
- **EvoAgents** detects failures with an LLM evaluator, generates targeted prompt patches, validates by replay against past traces, versions prompts and offers one-command rollback. Substantial overlap with `F07`. Our difference: the rollback is triggered by a production SLO breach and gated by a safety engine, not by an offline improvement loop.
- **EvoUndo** implements deterministic rollback for agent harnesses with captured pre-state witnesses, and makes our argument for us: asking an LLM to undo its own action hallucinates or produces incomplete inverses.

**What remains unoccupied:** a declarative contract for recoverability; multi-objective verification that can detect a repair degrading answer quality; and remediation debt. Those three are the claim.

---

## 3. Goals

- **G1** Close the loop: detect, diagnose, repair, verify and unwind without a human on the common path.
- **G2** Make every autonomous action justifiable after the fact — cited evidence, stated confidence, recorded risk decision, recorded inverse, verification deltas.
- **G3** Make it impossible for Kavach to take an action the application owner did not explicitly allow.
- **G4** Pass the conformance test in §1 against a second, unseen application.

### 3.1 Non-goals

Not a general AIOps platform. Not a Kubernetes operator. Not a trace viewer competing with Langfuse or Phoenix. Not multi-tenant. Not claiming autonomous handling of novel failures — unknown failures route to a human.

---

## 4. Target users

**Primary — the small AI team with no SRE.** Finds out the app is broken when a user says so.

**Secondary — the platform engineer evaluating autonomy.** Does not trust an LLM with write access. Needs the modes, risk tiers, conformance levels and audit log before flipping anything on.

**Tertiary — the project panel.** Needs the loop to work live, needs to see where the AI contribution actually is, and needs measurement rather than assertion.

---

## 5. Locked scope

Do not widen without a decision record in `docs/decisions/`.

| Decision | v1 | Deferred |
|---|---|---|
| Runtime | Local `docker-compose` | Kubernetes via a second `RuntimeAdapter` |
| Optimisation target | A convincing live demo | Benchmark runs against AIOpsLab / RCAEval |
| Autonomy ceiling | `AUTONOMOUS` default, executes **LOW risk only**; MEDIUM → sandbox then approval; HIGH → human | Autonomous MEDIUM after a fine-tuned decision model |
| Progressive rollout | **Staged verification** (sandbox → production → observation window) | **Canary traffic splitting**, which needs replicas and a router that compose does not provide |
| Fault catalogue | 9 classes, **declarative** | Application-authored catalogues |
| Remediation debt | Implemented for `F01` only | All mitigating repairs |
| Multi-objective verification | **All faults** | Application-supplied scorers |
| Decision model | **Fine-tuned Laya, shadow-mode in the live path** | Laya gating actions |
| Application types | **Any AI app satisfying `CONTRACT.md`**; faults apply by declared role | Non-containerised apps |
| Documentation evidence | **Context7, cached and optional** | Documentation-driven code repair |
| Code-level repair | **Not built.** Repairs act on config, prompts, state and containers only | PR-only, HIGH risk, human-always — if ever |

### 5.1 On canary

Canary means traffic splitting across replicas. The v1 target is single-instance compose services, so there is no traffic to split and a canary stage would be a box in a diagram with no code behind it. v1 ships **staged verification** instead: sandbox for MEDIUM risk, then production execution, then an observation window before the incident closes. Canary returns with the Kubernetes adapter, where replicas make it meaningful. Prompt-level canarying via a request router is a genuinely interesting idea and is recorded in `docs/decisions/` as deliberately deferred.

---

## 6. The targets

### 6.1 Proof #1 — `targets/ragpipe`

A fork of the team's existing `Simple_RAG-Pipeline`: FastAPI backend, Next.js frontend, Postgres with pgvector, Ollama (`llama3.2`, `nomic-embed-text`), docker-compose, Prometheus `/metrics`.

**The fork must strip the AIOps half.** That repo already contains a LangGraph agent, a Prometheus alert webhook and Kubernetes pod-restart code. Leaving it in means two autonomous systems acting on the same resources with no shared lock — precisely the writer-exclusivity violation TNR exists to prevent, producing the worst failure mode available: Kavach unwinds a change while the embedded agent restarts the service, verification passes for reasons neither caused, and the audit log records a lie. The stripped agent code is not wasted; it becomes the reference for the Kubernetes `RuntimeAdapter`.

**Five known blockers** (`ROADMAP.md` P1):

| # | Blocker | Fix |
|---|---|---|
| B1 | **Jitter middleware** injects randomized latency into responses | Remove or flag off. This is deliberate non-determinism in the exact signal `F02` detects on, and it poisons p95 SLOs, rolling baselines and MTTD |
| B2 | Ollama runs on the **host**, not in a container | Containerise. The executor reaches services through the docker socket |
| B3 | **No primary provider to break** — only Ollama exists | Build `llm-proxy` + Toxiproxy. Ollama becomes the backup we fail over *to* |
| B4 | Kubernetes manifests and minikube path | Keep for later; do not let them pull v1 toward k8s |
| B5 | **Probably HTTP-only instrumentation** | Verify P12. Generic framework auto-instrumentation produces request traces with no model, token or provider attributes, which leaves `F09` and most of `F02` with no signal |

### 6.2 Proof #2 — `targets/proof2`

A second RAG application, built or forked by a team member who has not read Kavach's source. Its purpose is to execute the conformance test in §1. It is not a feature; it is the experiment that validates the central claim.

**Protocol:** the onboarder receives `CONTRACT.md` and nothing else. Time to first successful heal is recorded. **Every Kavach source change required is a contract defect**, logged with the obligation it should have been.

---

## 7. The fault catalogue

Nine classes. Each is a closed tuple — injector, detection signal, RCA path, repair, inverse, verification probes, risk tier. Anything outside routes to the unknown-failure flow (§9.4).

| ID | Fault | Detection signal | Repair | Risk | Outcome |
|---|---|---|---|---|---|
| `F01` | Provider outage | Error rate on `gen_ai` spans > 20% / 60s | Fail over to backup model | LOW | **MITIGATED** + debt |
| `F02` | Provider latency degradation | p95 operation duration > SLO × 2 | Fail over; enable semantic cache | LOW | MITIGATED + debt |
| `F03` | Container crash-loop / OOM | Restart count > 2 / 5 min, or exit 137 | Restart; raise memory one step | LOW | RESOLVED |
| `F04` | Cache poisoning | Eval pass rate drops, retrieval scores healthy | Flush cache namespace | LOW | RESOLVED |
| `F05` | Connection pool exhaustion | Vector store connection errors; pool saturated | Restart dependent; reset pool | LOW | RESOLVED |
| `F06` | **Retrieval collapse** | Mean top-k similarity below floor; empty-context rate up | Rebuild index from snapshot | MEDIUM | RESOLVED |
| `F07` | **Prompt regression** | Golden-set pass rate drops after a prompt change | Roll back prompt | MEDIUM | RESOLVED |
| `F08` | **Config regression** | Config hash changed + objective breach in window | Roll back config | MEDIUM | RESOLVED |
| `F09` | **Token/cost blowout** | Tokens per request > 3× baseline | Roll back prompt; clamp `max_tokens` | MEDIUM | RESOLVED |

`F06`–`F09` carry the novelty claim. **If the schedule slips, cut `F03`–`F05`.**

### 7.0a Beyond RAG — how the catalogue generalises

The platform is not RAG-specific. A RAG pipeline is proof #1 because it exercises the most fault classes, not because the design assumes one.

The mechanism is **roles**. `CONTRACT.md` §2 makes every service declare one from a closed vocabulary — `application`, `vector_store`, `cache`, `model_primary`, `model_backup`, `datastore`. Every fault definition declares `applies_to_roles`. The matcher intersects the two, so an application without a vector store never sees `F06` and no code knows the difference.

| Application type | Applicable faults |
|---|---|
| RAG pipeline | All nine |
| Tool-calling agent | F01–F05, F07–F09 |
| Plain LLM API service | F01–F05, F07, F09 |
| ML inference, no LLM | F03, F05, F08 |

An application declaring no `model_primary` is told at onboarding, in words, that provider faults are unreachable for it. Partial applicability is a conformance outcome (`CONTRACT.md` §9), not an error.

### 7.1 The catalogue is data, not code

This is the single decision that most separates platform from project. A fault class is a declarative bundle:

```yaml
id: F07
name: prompt_regression
applies_to_roles: [application]
detect:
  signal: kavach_eval_pass_rate
  condition: drop_from_baseline
  threshold_pct: 10
  window_s: 300
  requires: [reversible_state.prompts]
evidence: [eval_history, git_diff:prompts, spans:gen_ai]
repair:
  action: rollback_prompt
  params: {to: last_known_good}
verify: [health, objectives, golden_eval]
risk: MEDIUM
```

Adding `F10` must require **no change** to the graph, the safety engine, the executor or the console. Applications ship their own catalogues alongside `kavach.yaml`.

**Sequencing:** build `F01` and `F03` as hardcoded Python first, then refactor those two into the declarative form and build the rest as data. Designing the schema from two working examples beats guessing, and if the refactor proves harder than expected only two faults' work is at risk.

---

## 8. Core features

**P0** = required for the demo · **P1** = required for the report · **P2** = stretch

| ID | Feature | Pri |
|---|---|---|
| `F-ONB` | Preflight validation (P01–P13) + conformance level reporting | P0 |
| `F-CON` | `kavach.yaml` contract parsing and schema validation | P0 |
| `F-TEL` | OTLP ingestion, GenAI normalisation into an internal schema | P0 |
| `F-EVAL` | Golden-set runner + four scorers | P0 |
| `F-DET` | Objective breach + statistical anomaly detection | P0 |
| `F-RCA` | Evidence-grounded RCA with citations and calibrated confidence | P0 |
| `F-SAFE` | Safety gate: allow-list, risk tier, blast radius, circuit breaker | P0 |
| `F-TNR` | Writer lock, undo stack, no-regression check | P0 |
| `F-HEAL` | Executor with a mandatory inverse per action | P0 |
| `F-VER` | **Multi-objective verification** returning a delta vector | P0 |
| `F-AUD` | Append-only hash-chained audit trail | P0 |
| `F-UI` | Live operations console | P0 |
| `F-INJ` | Fault injection harness | P0 |
| `F-MODE` | `SIMULATION` / `APPROVAL` / `AUTONOMOUS` | P0 |
| `F-CAT` | **Declarative fault catalogue interpreter** | P1 |
| `F-DEBT` | **Remediation debt** (`F01`) — tracking, trigger, repayment | P1 |
| `F-MEM` | Incident knowledge base with similarity retrieval | P1 |
| `F-UNK` | Unknown-failure hypothesis loop | P1 |
| `F-SBX` | Sandbox for MEDIUM-risk repairs | P1 |
| `F-GIT` | `kavach/ops` branch; commits for every file change | P1 |
| `F-P2` | **Proof #2 onboarding** | P1 |
| `F-LAYA` | **Fine-tuned Laya decision engine (shadow)** | P1 |
| `F-ROLE` | Role-based fault applicability — non-RAG application support | P1 |
| `F-DOC` | **Context7 documentation evidence** — cached, optional, offline-safe | P1 |
| `F-BENCH` | AIOpsLab / RCAEval adapter | P2 |

### 8.1 Multi-objective verification

Verification returns a **delta vector**, never a boolean.

```python
VerificationResult(
    passed=True,
    outcome=MITIGATED,
    deltas={
        "availability": +0.99,   # restored
        "quality":      -0.12,   # 12% worse — within the 15% tolerance
        "latency":      -0.30,   # slower
        "cost":         +0.60,   # local model is cheaper
    },
    tolerance_consumed={"quality": 0.80},   # 80% of budget used
    probes={"health": PASS, "objectives": PASS, "golden_eval": DEGRADED},
)
```

A repair that restores availability at a measured 12% quality cost is a **different outcome** from a clean repair. It is recorded as `MITIGATED`, surfaced in the console as degraded, and creates debt. Tolerance comes from the application's own `objectives.tolerance` declaration, so the application owner defines acceptable damage, not us.

This is the feature that makes it an *AI* operations platform.

### 8.1a Context7 as documentation evidence

Three of the nine fault classes are configuration-shaped, and a model diagnosing them is working from whatever it remembers about a library's settings at training time. `Context7` provides current, version-accurate library documentation, which turns that recall into retrieval.

**Where it is used:**

| Fault | What is fetched | Why |
|---|---|---|
| `F05` pool exhaustion | Vector store / driver pooling docs | Valid pool settings and defaults change between versions |
| `F08` config regression | The library's documented config schema | Distinguish "config changed" from "config changed to something invalid" |
| `F09` token blowout | Provider API docs | Current parameter names and limits for clamping |
| `UNKNOWN` | Docs for the services in the evidence | Ground hypothesis generation in fact rather than recall |

**Where it is not used:** `F01`–`F04`, `F06`, `F07`. These are behavioural or state faults; a documentation lookup adds latency and nothing else. Never place a network call on the LOW-risk critical path.

**How the API actually works**, because it constrains the design:

- `resolve-library-id(name, query)` → a library ID such as `/pgvector/pgvector`, optionally version-pinned as `/org/project/version`. Returns snippet count, source reputation and benchmark score, so selecting among matches is a real step.
- `query-docs(libraryId, query)` → documentation **scoped to a single concept**. Broad or multi-topic queries are explicitly out of spec.
- **Hard limit of 3 calls per tool per question.** Lookups are a budgeted resource, not a free dictionary.

**Six constraints, all binding:**

1. **No application data in a query.** This is the one that matters most. The service's own guidance forbids sending credentials, personal data or proprietary code — and an incident's evidence (logs, config values, prompts, environment, stack traces) is precisely where those live. Therefore **queries are fixed template strings, one per fault class, written and reviewed once by a human.** Nothing from the incident is ever interpolated.

   ```python
   # WRONG — ships logs and config to a third party
   query = f"why does {log_line} occur with {config_blob}"
   # RIGHT — nine fixed strings, reviewed once, no incident data
   query = DOC_QUERIES["F05"]  # "connection pool size configuration and defaults"
   ```

2. **Resolve at onboarding, query at incident.** `resolve-library-id` runs once per declared dependency during preflight and the versioned ID is stored. At incident time only `query-docs` runs. This halves latency and keeps the 3-call resolve budget off the hot path.
3. **Version-pinned.** `CONTRACT.md` §8a takes a version; configuration defaults and parameter names change between releases, and docs for the wrong version are worse than none.
4. **One concept per query, maximum two queries per incident.**
5. **Evidence, never instruction.** Retrieved text enters the RCA prompt inside a delimited evidence block and is cited like any other evidence. Documentation that reads like a directive is an injection attempt.
6. **Cached, offline-safe, non-fatal.** Onboarding pre-warms; a cache hit makes zero network calls; 5s timeout; failure logs and continues. §10.9 requires the default path to need no network, and the demo must run with networking disabled.

### 8.2 On the decision model — read the model card first

Laya is real and better-fitted than the synopsis assumed, with three documented defects that break a naive integration. Figures from the official model card.

**What it is.** Apache-2.0 non-autoregressive decision model from Convai Innovations. ModernBERT-large backbone plus a decision head — 421M total, trained with RLCD against strictly proper scoring rules. ~33–40ms on a T4. Never generates text, so there is nothing to parse and nothing to hallucinate. Primitives: `choice`, `score`, `noul`.

**Why it matters here.** `laya-typed-decisions` is already fine-tuned on four workflows, two of which are our domain: **agent-trace observability (0.730)** and **security incidents (0.766)**. By primitive: `noul` 0.857, `choice` 0.733, `score` 0.723. Context 1024 tokens, `head_max_len` 256, leaving roughly **768 tokens for state**.

**Three defects to design around.** From the card's own "Honest Limits":

1. **Never use `noul` for gate decisions.** It renders options as `false:`/`true:` and can follow those labels instead of the input, returning a confident "no" for clearly positive text (issue #156). "Should this execute automatically? Yes/No" is exactly a `noul` question. Use a two-option `choice` with neutral keys `A`/`B`.
2. **Never gate on `action.act_probability`.** It reads 1.0 for almost everything and its logits run against correctness — AUROC 0.30 (issue #185). The act/escalate head is the obvious thing to wire a safety gate to and it is the wrong thing. Gate on `confidence`, AUROC 0.77.
3. **It ships over-confident.** Refitting one temperature per (question type, option count) moves mean ECE from 0.466 to 0.081. Since the console displays confidence and the gate uses it, uncalibrated output is a correctness bug.

Also: `score` is the weakest primitive, so **risk tier is a `choice` over LOW/MEDIUM/HIGH**, never an ordinal.

**The three questions**, all asked as `choice`:

1. Which repair should be selected?
2. What is the risk tier? (`choice` over LOW/MEDIUM/HIGH — never `score`)
3. Should this execute automatically? (two-option `choice` with neutral keys `A`/`B` — **never `noul`**)

**Fine-tuning plan.** Base checkpoint is `laya-typed-decisions`, already fine-tuned on agent-trace observability and security-incident workflows, so we are adapting rather than starting cold. Two data sources:

| Source | Approx. count | Label derived from |
|---|---|---|
| Synthetic, generated from the catalogue | ~3000 | Rule engine, across fault class × service × severity × context variants |
| Real runs from `make bench` and development | ~400 | **Verification outcome** — whether the repair actually worked |

**The critique to pre-empt, because a panel will raise it.** Training on rule-engine labels teaches the model to imitate the rules. That is distillation, and a distilled copy of a rule table is worth nothing over the rule table.

The answer: **question 3 is labelled from real verification outcomes, not from rule-engine output.** Ground truth is whether the repair passed verification, which the rules do not know in advance. Questions 1 and 2 use synthetic labels for coverage of the decision space; question 3 — the one that actually gates autonomy — learns from what happened. Report the two label sources separately and state the limitation.

**After training:** refit one temperature per (question type, option count). Evaluate on held-out real incidents against the rule engine — agreement rate, disagreement cases, and which was right.

**The rule engine still ships alongside and remains the authority in v1.** Laya runs in shadow, never gating an action. That comparison is the research result; letting a model gate production actions on 3400 training examples is not defensible at this scale.

Integration is cheap: `laya[langchain]` supports LangGraph, `laya[serve]` runs as an HTTP sidecar. Training runs on Kaggle's free 2×T4 with the project's published notebook.

One operational note: `transformers` probes for TensorFlow at import and its abseil runtime deadlocks `laya.load()`. A second independent reason the stack excludes TensorFlow.

---

## 9. User flows

### 9.1 Onboarding
Point Kavach at a directory → preflight runs P01–P13 → each failure reports its exact remediation → **conformance level is stated, with the fault classes it cannot handle enumerated in words** → baseline captured → `ARMED`.

### 9.2 Autonomous LOW-risk heal (the demo path)
`F01` injected. Console shows: **Detected** (breaching objective, window) → **Evidence** (spans, logs, state, git, similar past incidents) → **Diagnosed** (`provider_outage`, 0.91, three citations, alternatives ruled out) → **Planned** (`switch_model`, inverse recorded, pre-state witness captured) → **Gate: LOW, permitted** (allow-list ✓, inverse ✓, confidence ✓, blast radius ✓, breaker ✓) → **Executing** (writer lock held, inverse pushed first) → **Verifying** (health ✓, objectives ✓, eval DEGRADED −12%) → **MITIGATED**, debt created → **Observation window** → closed. MTTD 14s, MTTR 96s.

### 9.3 Medium-risk approval heal
Identical through the gate. Risk MEDIUM → clone to sandbox → apply → verify in sandbox → console shows a **proposal**: diagnosis, diff, sandbox deltas, risk rationale, inverse → human approves or rejects with a reason → execute → verify → resolve.

### 9.4 Unknown failure
Objective breached, no catalogue match. Collect wider evidence → ranked hypotheses with confidence → candidate repairs → risk-assess each → test the top candidate in sandbox → **escalate to a human regardless of sandbox outcome.** v1 never auto-executes against an unknown failure. The episode, hypotheses and human decision are stored.

### 9.5 Verification failure → unwind
Verification fails any probe → **unwind the undo stack in reverse order immediately**, before any analysis → verify the undo restored prior state → if the undo succeeded, `ESCALATED`; if it failed, `UNRECOVERABLE` and alert loudly → freeze automation on that service → record the failed hypothesis so the repair ranks lower next time.

Analysis happens after the system is safe, never instead of making it safe.

### 9.6 Debt repayment
`F01` mitigated → debt recorded with trigger `llm_proxy healthy for 600s` → background checker evaluates → trigger fires → `switch_model` back to primary, risk LOW, same gate → verify → debt cleared, incident `RESOLVED`. Unpaid past `max_age_s` → escalate.

---

## 10. Requirements

### 10.1 Contract and onboarding
- `R-01` Refuse to enable any application failing a preflight check.
- `R-02` State the achieved conformance level and enumerate unreachable fault classes, in words, at onboarding.
- `R-03` Require a declared multi-objective contract with at least one availability and one quality objective.
- `R-04` Require an explicit allow-list. The default is empty.
- `R-05` Capture a last-known-good baseline at enablement and after each verified heal.
- `R-06` Use a dedicated `kavach/ops` branch for all file changes. Never commit to the working branch, never push, never amend.

### 10.2 Observation and diagnosis
- `R-07` Ingest OTLP and normalise GenAI attributes into an internal schema at the boundary. Nothing downstream references a raw `gen_ai.*` name.
- `R-08` Run the golden set on schedule and on demand.
- `R-09` Detect objective breaches within 30s of the window closing.
- `R-10` RCA emits root cause, confidence, cited evidence IDs, and rejected alternatives with reasons.
- `R-11` RCA can return `INSUFFICIENT_EVIDENCE` and must, rather than produce an uncited diagnosis.
- `R-12` No action is proposed below the confidence threshold.

### 10.3 Safety — TNR
These three are **Transactional No-Regression**, from STRATUS. The paper's ablation on AIOpsLab's 13 mitigation problems puts naive retry without undo at 23.1% against 69.2% with TNR. Roughly 3×, attributable to the undo mechanism alone. **If one safety feature survives a schedule cut, it is this one.**

- `R-13` **Writer exclusivity.** At most one component mutates the target at a time, under an explicit lock. Execution and unwind never interleave.
- `R-14` **Stack-based faithful undo.** Each state-mutating action pushes `(action, inverse, pre_state_witness)` before executing. Abort unwinds in reverse. A single stored inverse is insufficient for multi-action repairs.
- `R-15` **No regression.** A weighted severity scalar derived from the objectives must not increase. If a repair worsens it, unwind immediately without waiting for the full window.
- `R-16` The inverse is deterministic data from a captured pre-state witness, **never a model call.**

### 10.4 Safety — the gate
- `R-17` The gate can refuse. Scoring and permission are distinct; a well-scored action still gets denied.
- `R-18` Allow-list checked **first**, deny-by-default, unbypassable by mode, tier or confidence.
- `R-19` An action with no working inverse is never auto-executable.
- `R-20` Blast radius: ≤3 actions per incident, ≤5 incidents per hour, then halt and escalate.
- `R-21` Circuit breaker: ≤3 heals per `(service, fault_class)` per 30 min, then halt and escalate. Prevents restart-forever on a genuinely broken service.
- `R-22` Idempotency key on every action; duplicates are no-ops.
- `R-23` `SIMULATION` produces a complete plan and dry-run diff with zero side effects.

### 10.5 Verification and debt
- `R-24` Verification requires health, objectives and golden-set eval, and returns a **delta per objective**.
- `R-25` A repair restoring availability while degrading another objective within tolerance is `MITIGATED`, not `RESOLVED`.
- `R-26` Exceeding declared tolerance is a verification failure and triggers unwind.
- `R-27` Every `MITIGATED` outcome creates debt with a repayment action and machine-evaluable trigger.
- `R-28` Debt past `max_age_s` escalates.

### 10.6 Audit
- `R-29` Every autonomous action produces an immutable record: incident, diagnosis, confidence, action, risk, approver, timestamps, verification deltas, outcome.
- `R-30` Append-only. No update or delete route exists.
- `R-31` Hash-chained, so alteration is detectable.

### 10.7 UX
- `R-32` Operating mode visible on every screen without scrolling.
- `R-33` Live updates without manual refresh.
- `R-34` Confidence shown as a calibrated value, never implied by phrasing.
- `R-35` Every diagnosis claim links to its evidence.
- `R-36` Verification shows per-objective deltas, not a green tick.
- `R-37` Outstanding debt is a first-class view, not buried in history.
- `R-38` Approval shows diff, sandbox deltas and inverse before the approve control is reachable.
- `R-39` Legible at 1280×720. No information carried by colour alone.

### 10.8 Performance
Detection < 30s · RCA < 45s p95 local · LOW execution < 10s · full LOW loop < 3 min · console first paint < 1.5s · live updates < 500ms.

### 10.9 Platform
Single `docker compose up` on a 16GB laptop · no cloud API key on the default path · Linux and macOS, Windows via WSL2.

---

## 11. Success metrics

Scripted run: 9 faults × 5 reps = 45 injections.

| Metric | Target |
|---|---|
| Detection rate | ≥ 95% |
| Localization accuracy | ≥ 80% |
| RCA accuracy (correct class) | ≥ 75% |
| Auto-resolution rate (LOW) | ≥ 70% |
| **False-healing rate** | **≤ 5%** |
| Undo correctness | 100% |
| MTTD | < 30s |
| MTTR (LOW) | < 3 min |
| Audit completeness | 100% |
| **Proof #2 onboarding time** | **< 1 hour** |
| **Kavach source changes for proof #2** | **0** |

### 11.1 Conditional metrics — the part most projects get wrong

SREGym shows mitigation succeeding 22–62% of the time on *wrong* diagnoses. A headline auto-resolution rate therefore cannot evidence that RCA works. Report both conditionals:

| Metric | What it tells you |
|---|---|
| P(heal succeeds \| diagnosis correct) | Quality of the repair catalogue and executor |
| P(heal succeeds \| diagnosis wrong) | How much of the headline is luck |
| P(diagnosis correct \| heal succeeds) | The one a reviewer will actually ask |

A high resolution rate beside a high P(heal \| wrong diagnosis) means the system is a symptom-matcher with an LLM attached. Reporting that honestly is more defensible than hiding it.

### 11.2 Baselines

- **Human baseline.** The same 45 injections in `SIMULATION`, resolved by hand, timed. Two hours of work, and it is what gives MTTR a denominator.
- **Undo ablation.** The catalogue with the undo stack disabled. Reproducing the shape of STRATUS's result on your own system is the strongest research output available here.
- **LLM vs. rules.** Phase 3's hardcoded mapping against Phase 4's RCA engine on identical injections.
- **Rule engine vs. Laya.** Agreement rate, disagreement cases, which was right.
- **Contract sufficiency.** Every Kavach source change proof #2 required, logged as a contract defect.

---

## 12. Out of scope for v1

Kubernetes · canary traffic splitting · **autonomous code repair** · **GitHub PR-based remediation** · **Loki and Tempo** (traces and logs go to Postgres + TimescaleDB) · **autonomous execution against an unknown failure** · cloud deploy integrations (Vercel, Render, Netlify) · multi-tenancy, accounts, RBAC, SSO · reinforcement learning for healing policies · predictive failure forecasting · multi-agent distributed incident management · edge/IoT · CI/CD integration · a fine-tuned Laya in the live path · a competing trace viewer · horizontal scaling of the control plane · **any action that deletes data, scales down, or runs a migration.**

---

## 13. Known risks

| Risk | Mitigation |
|---|---|
| **Confabulated RCA.** An LLM produces fluent root causes whether or not evidence supports one | Citation required; `INSUFFICIENT_EVIDENCE` is valid output; confidence gates action; the output space is closed, not free text |
| **Scope creep back toward the synopsis** | §12 is binding; widening needs a decision record |
| **Verification theatre** — "metrics look fine now" | Three probes, one measuring output quality; multi-objective deltas make a quality drop visible instead of invisible |
| **Proof #2 reveals contract gaps late** | Run it at week 10, not week 13. A gap found early is a finding; found late it is a failure |
| **The declarative catalogue refactor overruns** | Only `F01` and `F03` are at risk; the rest are built as data from the start |
| **Sandbox is harder than it reads** (ports, volumes, state) | P1, not P0. The approval path works without it |
| **Forked target carries five blockers** | §6.1; all are week-1 work, but B5 is unscoped until verified |
| **Four people, one semester** | 14 P0 features. Everything else is cuttable with the demo intact |
| **Context7 breaks the offline guarantee** | Cache pre-warmed at onboarding; 5s timeout; non-fatal; off the LOW-risk path. Rehearse the demo with networking disabled |
| **Documentation text as a prompt-injection vector** | Retrieved docs enter the RCA prompt as a clearly delimited evidence block, never as instructions, and are cited like any other evidence |
| **Leaking application data to an external service via doc queries** | Queries are fixed per-fault-class templates, human-reviewed, with zero interpolation of incident data. A test asserts no query string contains any value sourced from an incident |
