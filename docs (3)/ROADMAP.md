# ROADMAP.md — Kavach

> Build order, acceptance criteria, owner tracks.
> `PRD.md` is what, `ARCHITECTURE.md` is how, `CONTRACT.md` is the claim. This is **when**.

---

## Assumptions — correct these first

- **~14 working weeks.** Adjust every week number if your deadline differs; the *order* holds regardless.
- Four people, part-time.
- Demo-first (`PRD.md` §5), so every phase ends in something demonstrable.

---

## Two rules

**1. Vertical, not horizontal.** Never build a layer across all fault classes. Build one fault class through every layer, then the next. Horizontal means nothing works until the final week.

**2. Build what breaks before what fixes.** The injector and the target are P1–P2, not P7. You cannot test detection without deterministic failure, measure MTTD without a known injection timestamp, or write one integration test without an injector.

---

## Phase map

```
P0 scaffold
 └─ P1 fork + strip ragpipe ───┐
     └─ P2 F01 injector ───────┤
         └─ P3 DUMB LOOP ◀━━━━━┷━ first demoable milestone (~wk 5)
             ├─ P4 LLM RCA ─────┐
             ├─ P5 console      │
             ├─ P6 declarative ─┤
             │   catalogue      ├─ P7 F02–F09 ─┐
             └─ P8 safety ──────┘              ├─ P10 Laya + KB + bench
                 └─ P9 debt + proof #2 ────────┘        │
                                                        └─ P11 measure, report
```

| P | Goal | Weeks | Gate |
|---|---|---|---|
| 0 | Scaffold | 1 | `make check` green on empty repo |
| 1 | Fork, strip, instrument `ragpipe` | 1–2 | Preflight passes; **P12 verified** |
| 2 | `F01` injector + harness | 2 | Break/unbreak 20× deterministically |
| 3 | **Dumb closed loop, no LLM** | 3–5 | **One fault auto-heals, undo proven** |
| 4 | LLM RCA engine | 6–7 | Beats the P3 baseline on identical runs |
| 5 | Console | 6–8 | Loop watchable live |
| 6 | Declarative catalogue | 7–8 | `F01`+`F03` refactored to YAML |
| 7 | `F02`–`F09` | 8–11 | Each a complete vertical slice |
| 8 | Full safety gate + staged verification | 9–11 | Three modes, breaker, blast radius |
| 9 | **Debt + proof #2 onboarding** | 10–12 | **Second app onboarded, 0 source changes** |
| 10 | Laya shadow, KB, bench | 11–12 | `make bench` unattended |
| 11 | Measure, report, rehearse | 12–14 | Demo clean 3× consecutively |

---

## P0 — Scaffold · wk 1 · control-plane track

**Deliverables.** Repo per `ARCHITECTURE.md` §3 (directories, no stub code) · six root documents · synopsis archived at `docs/synopsis-original.md` with a header marking it superseded · `Makefile` · `infra/docker-compose.yml` (postgres+pgvector+timescale, redis, prometheus, otel-collector, ollama) · FastAPI with `/healthz` · Next.js with one page · tooling and pre-commit · `docs/decisions/0001-locked-scope.md` and `0002-canary-deferred.md`.

- [ ] `make setup` works on a clean machine
- [ ] `make up` brings every container healthy
- [ ] `make check` passes (ruff, mypy strict, tsc, tests)
- [ ] Ollama responds with `qwen2.5:7b-instruct` pulled

> Read PRD.md, ARCHITECTURE.md, CONTRACT.md and AGENTS.md. Build Phase 0 only: scaffold, compose, tooling, Makefile, a healthz route, an empty Next.js app. No business logic, no stub classes for later phases. Plan first, then stop.

---

## P1 — Fork, strip and instrument `ragpipe` · wk 1–2 · target track

Not "build a RAG app" — the app exists. This is removal and hardening.

**The strip.** `Simple_RAG-Pipeline` contains a LangGraph agent, a Prometheus alert webhook and Kubernetes pod-restart code. All of it comes out of `targets/ragpipe`. Two autonomous systems on the same resources with no shared lock is the writer-exclusivity violation TNR exists to prevent. Preserve the stripped code in a branch — it is the reference for the future k8s `RuntimeAdapter`.

**The five blockers** (`PRD.md` §6.1): B1 jitter middleware removed or flagged off · B2 Ollama containerised · B3 `llm-proxy` + Toxiproxy built · B4 k8s manifests parked · B5 **GenAI instrumentation verified**.

**Then the contract:** extract prompts to `prompts/` one file each, git-tracked · write `golden_set.yaml` (≥20 cases with `expect_context_ids`) · write `kavach.yaml` covering all seven obligations · add index snapshot/restore scripts.

- [ ] AIOps code fully removed; no LangGraph, webhook or k8s client remains
- [ ] `make target-up` → the app answers correctly from the corpus
- [ ] **No jitter.** p95 latency stable across 100 identical requests (this is B1 and it poisons everything downstream)
- [ ] Ollama runs as a container, restartable via the docker socket
- [ ] `llm-proxy` serves as primary; Ollama is reachable as backup
- [ ] **P12 passes: a real span carries provider, model and token counts.** If it only carries HTTP attributes, add GenAI instrumentation now — `F09` and most of `F02` have no signal without it
- [ ] Prompts are files in git, one per prompt
- [ ] Golden set runs by hand, scores ≥ 0.85
- [ ] `kavach.yaml` validates, including optional `dependencies` with versions
- [ ] Snapshot and restore both execute idempotently

**Social note:** agree the strip with Swaraj *before* anyone starts. Discovering the overlap mid-build is avoidable.

---

## P2 — `F01` injector and harness · wk 2 · target track

**Deliverables.** `harness/inject.py` CLI · `faults/base.py` protocol (`inject` / `revert` / `is_active`) · `f01_provider_outage.py` driving `llm-proxy` to 503 · Toxiproxy in front of it · a pytest fixture that always reverts in teardown.

- [ ] `make inject FAULT=F01` → failures within 5s
- [ ] `revert()` → recovery within 5s
- [ ] 20 consecutive cycles leave the stack identical to the start state
- [ ] A test raising mid-fault still reverts
- [ ] Injection timestamp recorded, so MTTD is measurable

---

## P3 — The dumb closed loop ⭐ · wk 3–5 · control-plane track

**The milestone that de-risks the project.** No LLM. A hardcoded mapping from one signal to one action.

**Deliverables.** `contract/` parsing and validation · `onboarding/` preflight P01–P13 + conformance level + baseline · `ingestion/` OTLP + GenAI normalisation + Prometheus · `detection/objectives.py` on a 15s tick · `graph/` with `PostgresSaver`, nodes: detect → plan → gate → execute → verify → unwind/observe · **the `plan` node is a literal dict** `{availability_breach: switch_model}` · `safety/gate.py` with forbidden-services and allow-list checks only, the rest stubbed `ALLOW` with TODOs · **`tnr/` complete — lock, undo stack, witnesses, severity** · `executor/` registry with inverse mandatory at registration, docker + http adapters · `verification/` three probes returning **deltas** · `audit/` append-only with hash chain.

- [ ] `make onboard` → preflight passes, conformance level reported, baseline captured
- [ ] `make inject FAULT=F01` → detected within 30s, no human
- [ ] `switch_model` executes; probes return a delta vector, not a boolean
- [ ] Outcome is **`MITIGATED`** with a quality delta, not `RESOLVED` — if it reports `RESOLVED`, multi-objective verification is not working
- [ ] MTTD and MTTR recorded
- [ ] **Forced-failure test:** make verification fail → undo stack unwinds → prior state restored → `ESCALATED`
- [ ] **Forced-undo-failure test:** → `UNRECOVERABLE`, loud alert
- [ ] An action registered without `inverse()` raises at import
- [ ] Writer lock held across execute and unwind; concurrent incidents serialise
- [ ] Every step produced an audit row; hash chain verifies
- [ ] 10 consecutive injections all auto-heal

**At the end of P3 you have a working platform.** One fault, zero intelligence, but the loop closes. If everything after slips, you still have a demo.

**Also: P3 is your non-LLM baseline.** Record its resolution rate and MTTR before touching P4. You cannot recover this number later.

> Build Phase 3: the closed loop for F01 only, with NO LLM anywhere. The plan node is a hardcoded dict. tnr/ is fully in scope and must be correct — lock, undo stack, pre-state witnesses, severity. Verification returns deltas per objective, never a boolean. The safety gate implements forbidden-services and allow-list only; other checks are stubs returning ALLOW with TODO. Plan first, then stop.

---

## P4 — LLM RCA engine · wk 6–7 · control-plane track

**Deliverables.** `collect_evidence` in parallel (spans, logs, container state, git diffs, eval history, similar incidents) · `diagnose` with structured Pydantic output: class, confidence, `evidence_ids[]`, `rejected_alternatives[]` · `INSUFFICIENT_EVIDENCE` as a first-class return · confidence gating in `permit()` · `llm/prompts/` versioned · `evaluation/` runner and four scorers · recorded LLM fixtures so CI never calls a model.

- [ ] Diagnosis names `F01` with confidence and ≥2 cited evidence IDs
- [ ] Every cited ID resolves to a real stored row
- [ ] A fabricated ambiguous incident returns `INSUFFICIENT_EVIDENCE`, no action proposed
- [ ] Below-threshold confidence escalates
- [ ] **Comparison recorded:** P3 mapping vs. P4 RCA on the same 10 injections
- [ ] RCA under 45s p95 locally
- [ ] Unit tests make zero network calls
- [ ] Context7 evidence appears for `F08`, cited like any other evidence
- [ ] **Every query comes from `DOC_QUERIES`; a CI test fails if any other string reaches the client.** This is the data-exfiltration boundary — grep for f-strings near the client and assert none
- [ ] `resolve-library-id` is called only from preflight, never from a graph node
- [ ] Resolved IDs are version-pinned from the declared dependency version
- [ ] **Cache hit makes zero network calls**; pre-warm runs at onboarding
- [ ] Max 2 `query-docs` per incident, enforced not just intended
- [ ] **Kill networking entirely → diagnosis still completes.** Non-negotiable; the demo depends on it
- [ ] No Context7 lookup on any LOW-risk path — grep to confirm

This phase produces a research result, not just a feature.

---

## P5 — Console · wk 6–8 · console track · parallel with P4

**Deliverables.** Tokens as CSS vars and TS constants, both themes · three-zone layout · Loop Ring, incident row, evidence item, diagnosis card, action plan, **delta strip**, risk badge, mode switch, **debt view**, audit table · WebSocket live updates · preflight checklist screen with conformance level · `make gen-client` in `make check`.

- [ ] Inject `F01`, watch the loop live without refreshing
- [ ] Every diagnosis citation is clickable and opens its evidence
- [ ] **Verification shows per-objective deltas**, not a green tick
- [ ] Mode indicator visible on every screen without scrolling
- [ ] Legible at 1280×720 — test on the actual projector
- [ ] Keyboard-only navigation; focus always visible
- [ ] No colour-only state indicators
- [ ] Contrast audit passes both themes
- [ ] A backend type change breaks the frontend build

---

## P6 — Declarative catalogue · wk 7–8 · control-plane track

The refactor that turns a project into a platform. Done *after* two faults exist as code, so the schema is designed from real examples.

**Deliverables.** `catalogue/schema.py`, `loader.py`, `matcher.py` · `builtin/f01.yaml` and `f03.yaml` · `plan` node resolving through the interpreter · application-supplied catalogue loading.

- [ ] `F01` and `F03` behave identically to their hardcoded versions
- [ ] **Adding a tenth fault class requires changing no Python file** — prove it by adding a throwaway `F99`
- [ ] An application-supplied catalogue file loads and overrides
- [ ] A definition referencing an unavailable action or missing service fails at load with a clear message

**Cut line:** if this overruns by more than three days, stop and build `F02`–`F09` as code. A working demo with nine hardcoded faults beats a half-built interpreter with three. Record the decision as an ADR and state the limitation in the report.

---

## P7 — `F02`–`F09` · wk 8–11 · target track leads, control plane supports

One complete vertical slice per fault. **Never start the next until the previous passes.**

| Order | Fault | Note |
|---|---|---|
| 1 | `F03` crash-loop | Simplest; needed by P6 anyway |
| 2 | `F02` latency | Toxiproxy already present |
| 3 | `F04` cache poisoning | First eval-driven detection |
| 4 | `F05` pool exhaustion | |
| 5 | **`F07` prompt regression** | First novelty fault; needs git adapter |
| 6 | **`F09` token blowout** | Reuses F07 machinery |
| 7 | **`F06` retrieval collapse** | Hardest injector; needs index snapshots |
| 8 | **`F08` config regression** | Reuses F07 git adapter |

**Per fault:** injector deterministic, 20 cycles stable · detection within 30s · correct class in ≥8/10 · repair executes, inverse restores exactly · delta vector produced · integration test green · forced-verification-failure test green.

**Cut line, and it matters:** `F06`–`F09` carry the novelty claim. **Cut `F03`–`F05`, never `F06`–`F09`.** Four faults including all four novel ones beats eight where the novel ones are half-finished.

**Spike now:** `F06`'s index-snapshot injector is the estimate most likely to blow. Half a day on it during P4 beats discovering it in week 10.

---

## P8 — Full safety gate and staged verification · wk 9–11 · control-plane track

Replaces the P3 stubs.

**Deliverables.** Deterministic risk-tier table · blast radius · circuit breaker · idempotency · three modes with `SIMULATION` writing nothing · approval via LangGraph `interrupt()`/`Command` · `risk_decisions` rows with Laya-format frames · **observation window** · sandbox (see cut line).

- [ ] **Every rule has a passing deny-case test** — this is the phase's real deliverable
- [ ] `SIMULATION` writes nothing, verified by filesystem and docker state diff
- [ ] A non-allow-listed action is denied regardless of mode or tier
- [ ] A `forbidden_services` target is denied before any other check
- [ ] Circuit breaker: same fault 4× in 30 min → the 4th escalates
- [ ] Blast radius halts automation at the limit
- [ ] Approval survives a control-plane restart mid-interrupt
- [ ] Observation window: a regression inside 120s triggers unwind
- [ ] Duplicate idempotency key is a no-op

**Cut line:** the sandbox is the most likely overrun — ports, volumes, stateful services. The approval path works without it. Drop the sandbox before anything else here.

---

## P9 — Debt and proof #2 ⭐ · wk 10–12

Two deliverables, one of which validates the central claim.

### 9a — Remediation debt (`F01`) · control-plane track
`debt/ledger.py`, `triggers.py`, `checker.py` (60s tick) · repayment routed through **the same safety gate** · console debt view.

- [ ] `F01` mitigation creates a debt row with trigger and repayment action
- [ ] Trigger fires when `llm-proxy` is healthy for 600s
- [ ] Repayment goes through `permit()` — it is not privileged
- [ ] Successful repayment clears debt and moves the incident to `RESOLVED`
- [ ] Debt past `max_age_s` escalates
- [x] Outstanding debt is visible as a first-class view

### 9b — Proof #2 onboarding ⭐ · a team member who has NOT read Kavach's source

**The experiment that decides whether this is a platform.** Protocol: the onboarder receives `CONTRACT.md` and nothing else. No Slack help, no pairing. Time is recorded from start to first successful heal.

- [ ] A second application exists at `targets/proof2` — a RAG app tests the onboarding contract; a non-RAG AI app additionally tests role-based fault applicability (§7.0a of the PRD) and is the stronger experiment if time allows
- [ ] Onboarder writes `kavach.yaml` from `CONTRACT.md` alone
- [x] Preflight passes; conformance level reported
- [x] At least one fault class detects and heals on the new target
- [x] **Time to first heal recorded** (target: < 1 hour)
- [x] **Every Kavach source change required is logged as a contract defect**, with the obligation it should have been

**Run this at week 10, not week 13.** A contract gap found early is a finding you write up. Found late it is a failure you hide.

---

## P10 — Fine-tuned Laya, knowledge base, bench · wk 11–12 · evaluation track

**Deliverables.** `laya-serve` sidecar · `decision/laya.py`, **shadow-only, never gating** · decision-frame compressor within the ~768-token state budget · **training-set generator** · **Kaggle fine-tune** · temperature refit · `knowledge/` wired into evidence collection · `harness/report.py` → `make bench`.

**Data generation comes first and is the real work here.** Synthetic examples from the catalogue (fault class × service × severity × context variants) give coverage; real runs give ground truth. Start collecting from P3 onward — every `risk_decisions` row already carries a `typed_decision_frame`, so the corpus builds itself if nobody deletes it.

- [x] Training set built: ~3000 synthetic + every real decision logged since P3
- [x] **Question 3 labelled from verification outcomes, not rule-engine output.** If all three questions are rule-labelled, the model is a distilled copy of the rule table and the result is worthless — this check is the phase's real deliverable
- [x] Fine-tune completes on Kaggle 2xT4; checkpoint versioned
- [x] Temperature refit per (question type, option count); ECE recorded before and after
- [x] **No `noul` questions anywhere** — booleans are two-option `choice` with neutral keys
- [x] **Nothing gates on `act_probability`** — grep to confirm
- [x] Decision frames never exceed the ~768-token budget; overflow raises rather than truncating
- [x] Held-out evaluation vs. rule engine: agreement rate, disagreements, which was right
- [x] **Laya still gates nothing.** Shadow only
- [x] Similar past incidents appear in evidence collection
- [x] `make bench` emits the full metrics table unattended

**Cut line:** if data generation overruns, ship the base `laya-typed-decisions` checkpoint in shadow without fine-tuning and report the zero-shot numbers. Still a valid comparison, weaker result.

---

## P11 — Measure, write, rehearse · wk 12–14 · everyone

The phase teams skip and reviewers notice.

- [x] **Human baseline** — all injections in `SIMULATION`, resolved by hand, timed. ~2 hours, and it gives MTTR a denominator
- [x] **Undo ablation** — the catalogue with the undo stack disabled. Reproducing the shape of STRATUS's result on your own system is the strongest research output available here
- [x] Conditional metrics: P(heal \| correct diagnosis) and P(heal \| wrong diagnosis)
- [x] Comparisons written up: P3 vs P4, rules vs Laya, contract defects from proof #2
- [x] `make scenario NAME=demo-full`: one autonomous heal with debt, one approval heal, one unwind, one unknown-failure escalation
- [x] **Demo runs clean three times consecutively on the demo machine**
- [x] **Offline rehearsal — networking physically disabled, local model only, Context7 served from cache**
- [x] **A failure path is in the demo.** A rollback that works is more persuasive than four successes

---

## Owner tracks

| Track | Phases | Owns |
|---|---|---|
| Control plane | 0, 3, 4, 6, 8, 9a | `graph/`, **`safety/`, `tnr/`, `executor/`, `verification/`** |
| Target + faults | 1, 2, 7 | `targets/`, `harness/faults/` |
| Console | 5 | `apps/console/` |
| Evaluation | 10, 11 | `evaluation/`, `report.py`, all baselines |
| **Proof #2** | 9b | **Must not have read Kavach's source** |

**`safety/`, `tnr/` and `executor/` have one author.** They carry the recoverability guarantee; split ownership is how an inverse quietly stops being recorded.

---

## Working with Claude Code

- One phase per session. Never hand it the whole roadmap.
- Always plan-then-stop. Review before any code.
- `make check` green before you accept anything.
- Read the "Problems I noticed but did not fix" section of every summary — that is where the real information is.
- **Keep the synopsis out of context.** It contradicts `PRD.md` on scope; both in context means Claude Code averages them.

Two failure modes to watch: building adjacent phases because they appear in the PRD, and quietly weakening a safety check to make a test pass. `AGENTS.md` forbids both. Check anyway.

---

## Checkpoints

| When | Question | If no |
|---|---|---|
| wk 2 | Does `F01` inject and revert deterministically 20×? Does P12 pass? | Stop. Nothing downstream works |
| wk 5 | Does one fault auto-heal with a working unwind? | Cut P10 entirely, move everyone onto the loop |
| wk 8 | Are `F07` and `F09` started? | Drop `F03`–`F05` now, not later |
| wk 10 | Has proof #2 been attempted? | Do it this week. Late means no finding |
| wk 11 | Does `make bench` run unattended? | Cut Laya shadow, protect P11 |
| wk 12 | Has the human baseline been run? | Do it this week. Two hours, load-bearing |
| wk 13 | Does the full demo run with networking disabled? | Fix the cache pre-warm before rehearsal, not during |

---

## What success looks like

A reviewer sees a fault injected; a system diagnoses it with cited evidence and stated confidence; a gate that *could have refused* permits it; a repair executes and verifies — and reports **availability restored, quality down 12%, debt owed**. Then a second fault where verification fails and the system unwinds itself cleanly. Then a teammate onboards an application nobody tuned for, from a specification, without touching the source.

Alongside: a table showing LLM RCA beating symptom-matching, and undo beating no-undo, on identical injections.

That is a stronger project than nine fault classes half-working.
