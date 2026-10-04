# ROADMAP.md — Kavach

> Build order and acceptance criteria.
> `PRD.md` is what, `ARCHITECTURE.md` is how, `CONTRACT.md` is the contract. This is **when**.

---

## Assumptions

- ~14 working weeks.
- Four people, part-time.
- Demo-first.
- Kavach is standalone throughout the MVP.
- Developers create scenarios manually; Kavach never injects failures into another application.

---

## Two rules

**1. Vertical, not horizontal.** Build one complete fault scenario through detection, RCA, safety, execution, verification and unwind before expanding breadth.

**2. Build what proves the loop before what decorates it.** The first milestone is a working simulated self-healing loop, not external integration.

---

## Phase map

```text
P0 scaffold
 └─ P1 scenario engine
     └─ P2 DUMB LOOP ⭐
         ├─ P3 LLM RCA
         ├─ P4 console
         ├─ P5 safety + TNR
         └─ P6 declarative catalogue
              └─ P7 F02–F09
                   ├─ P8 debt + knowledge
                   └─ P9 Laya shadow
                        └─ P10 benchmark + demo
                             └─ P11 optional runtime design
```

| P | Goal | Weeks | Gate |
|---|---|---|---|
| 0 | Scaffold | 1 | `make check` green |
| 1 | Scenario engine | 1–2 | Manual F01 scenario loads and validates |
| 2 | **Dumb simulated closed loop** | 3–4 | One scenario heals and undoes correctly |
| 3 | LLM RCA | 5–6 | RCA beats symptom-only baseline |
| 4 | Console | 5–7 | Full loop watchable live |
| 5 | Safety + TNR | 6–8 | All deny cases + forced unwind pass |
| 6 | Declarative catalogue | 8–9 | New fault class requires no Python branch |
| 7 | F02–F09 | 9–11 | Each complete scenario replay works |
| 8 | Debt + knowledge | 10–12 | F01 debt lifecycle + similar incidents |
| 9 | Laya shadow | 11–12 | Agreement/calibration data recorded |
| 10 | Benchmark + demo | 12–14 | 45 replays + clean demo |
| 11 | Runtime adapter design only | post-MVP | Interface documented; no external execution |

---

## P0 — Scaffold · wk 1

**Deliverables.**

Repository structure from `ARCHITECTURE.md` · root documents · `Makefile` · Kavach infrastructure compose · FastAPI `/healthz` · empty Next.js console · tooling.

- [ ] `make setup` works
- [ ] `make up` brings Kavach infrastructure healthy
- [ ] `make check` passes
- [ ] Ollama responds with the configured local model

> Build Phase 0 only. No business logic and no target application.

---

## P1 — Scenario engine · wk 1–2

This replaces the former target/injector work.

**Deliverables.**

- `scenarios/` schema and loader
- manual scenario API
- scenario validation
- simulated application state
- scenario replay runner
- baseline/state fixture support

Example:

```text
F01 provider outage
error ratio 35%
primary model unhealthy
backup model healthy
quality 84%
```

- [ ] `make scenario NAME=F01` validates
- [ ] Scenario state is isolated
- [ ] No external network/runtime mutation exists
- [ ] A scenario can be replayed repeatedly with identical starting state

---

## P2 — Dumb simulated closed loop ⭐ · wk 3–4

No LLM.

A hardcoded mapping for one scenario proves the machinery before intelligence is added.

**Deliverables.**

`graph/` → detect → plan → gate → execute → verify → unwind

`tnr/` complete: lock, undo stack, witnesses, severity

`simulation/` executor with inverse mandatory

`verification/` probes returning deltas

`audit/` append-only hash chain

- [ ] F01 scenario detected
- [ ] `switch_model` simulated
- [ ] Verification returns availability/quality deltas
- [ ] Outcome is `MITIGATED`
- [ ] Forced verification failure triggers unwind
- [ ] Prior simulated state is restored exactly
- [ ] Forced undo failure produces `UNRECOVERABLE`
- [ ] Action without inverse cannot register
- [ ] Ten repeated replays remain deterministic

**This is the first major demo milestone.**

---

## P3 — LLM RCA · wk 5–6

**Deliverables.**

- parallel evidence collection from the scenario
- structured RCA output
- evidence citations
- rejected alternatives
- `INSUFFICIENT_EVIDENCE`
- recorded LLM fixtures
- RCA evaluation

- [ ] Correct class with confidence
- [ ] Every evidence ID resolves
- [ ] Ambiguous scenario produces `INSUFFICIENT_EVIDENCE`
- [ ] Below-threshold confidence escalates
- [ ] Compare rule mapping vs. LLM RCA on identical replays
- [ ] Local RCA p95 < 45s

---

## P4 — Console · wk 5–7

**Deliverables.**

Three-zone console · live loop timeline · incident stream · evidence viewer · diagnosis card · action plan · risk badge · verification delta strip · debt view · audit table · scenario creation UI.

- [ ] Create F01 manually
- [ ] Watch every stage live
- [ ] Diagnosis citations open evidence
- [ ] Verification shows per-objective deltas
- [ ] Simulated execution is explicitly labelled
- [ ] Keyboard navigation works
- [ ] Legible at 1280×720

---

## P5 — Full safety gate + TNR · wk 6–8

Replace early stubs with real checks.

**Deliverables.**

Allow-list · risk tiers · confidence threshold · blast radius · circuit breaker · idempotency · approval flow · simulation mode.

- [ ] Every safety rule has a deny-case test
- [ ] Non-allow-listed action is always denied
- [ ] Missing inverse is denied
- [ ] Repeated same-fault behaviour hits the breaker
- [ ] Blast radius halts automation
- [ ] `SIMULATION` performs zero simulated-state mutation
- [ ] `AUTONOMOUS` modifies only the simulator
- [ ] Approval pauses and resumes correctly

---

## P6 — Declarative catalogue · wk 8–9

The refactor that turns the engine into a platform-like interpreter.

**Deliverables.**

`catalogue/schema.py` · loader · matcher · built-in YAML definitions.

- [ ] F01 and F03 behave identically to their earlier implementations
- [ ] Adding a throwaway F99 requires no Python branch
- [ ] Missing action/inverse produces a clear validation error

**Cut line:** if this overruns, finish the remaining scenario slices first.

---

## P7 — F02–F09 · wk 9–11

One complete vertical slice per scenario.

Priority:

1. F03 crash-loop
2. F02 provider latency
3. F04 cache poisoning
4. F05 pool exhaustion
5. F07 prompt regression
6. F09 token blowout
7. F06 retrieval collapse
8. F08 config regression

Per scenario:

- manual scenario definition
- detection signal
- correct diagnosis path
- repair
- inverse
- verification deltas
- integration/replay test
- forced-verification-failure test

**No injector is added. No external application is touched.**

---

## P8 — Debt + knowledge · wk 10–12

### Debt

- [ ] F01 mitigation creates debt
- [ ] Trigger is machine-evaluable
- [ ] Repayment uses the same gate
- [ ] Successful repayment clears debt
- [ ] Overdue debt escalates

### Knowledge

- [ ] Incident summaries embedded
- [ ] Similar incidents retrieved
- [ ] Retrieved incidents appear as evidence
- [ ] No knowledge-base result can bypass safety

---

## P9 — Laya shadow · wk 11–12

**Deliverables.**

Optional `laya-serve` sidecar · shadow decision adapter · decision-frame compressor · calibration evaluation.

- [ ] Laya outputs logged beside deterministic decisions
- [ ] No `noul`
- [ ] No `act_probability` gating
- [ ] Calibration measured
- [ ] Deterministic rules remain authoritative

Cut this phase before the core loop if time is tight.

---

## P10 — Benchmark + demo · wk 12–14

Evaluation:

```text
9 fault classes × 5 manual scenario replays = 45 runs
```

- [ ] Detection, RCA, heal, undo and audit metrics recorded
- [ ] Human baseline recorded
- [ ] Undo ablation recorded
- [ ] Rule vs. LLM RCA comparison recorded
- [ ] Rule vs. Laya shadow comparison recorded if P9 shipped
- [ ] Full demo scenario:
      one LOW-risk simulated heal
      one approval flow
      one verification failure + unwind
      one unknown-failure escalation
- [ ] Demo runs clean three consecutive times
- [ ] Offline rehearsal works with local model only
- [ ] A failure/rollback path is included in the demo

---

## P11 — Optional runtime adapter design · post-MVP

This is **design only**.

Document:

```python
class RuntimeAdapter(Protocol):
    read_state(...)
    apply(...)
    restore(...)
```

Do not implement:

- Docker control
- Kubernetes control
- production execution
- external fault injection
- target-app onboarding

The goal is to prove that Kavach's core abstractions are clean enough to support a future adapter without changing the graph, safety gate or TNR design.

---

## Owner tracks

| Track | Phases | Owns |
|---|---|---|
| Control plane | 0, 2, 3, 5, 6, 8 | `graph/`, `safety/`, `tnr/`, `verification/` |
| Simulation + scenarios | 1, 2, 7 | `scenarios/`, `simulation/` |
| Console | 4 | `apps/console/` |
| Evaluation | 9, 10 | `evaluation/`, reports, baselines |
| Research | 3, 8, 9, 10 | RCA, debt, Laya, metrics |

`Safety`, `TNR` and simulated execution should have clear ownership because they carry the recoverability guarantee.

---

## Working with Claude Code

- One phase per session.
- Plan first, then stop for review.
- Never give it the entire roadmap when implementing a small phase.
- `make check` must be green before accepting the change.
- Read the summary's uncertainty and problems-not-fixed sections.
- Never let it add a target app, injector or runtime adapter because one appears in an older document.

---

## Checkpoints

| When | Question | If no |
|---|---|---|
| wk 2 | Can a manual F01 scenario load and replay deterministically? | Stop and fix scenario layer |
| wk 4 | Does one simulated repair close the loop and unwind correctly? | Move everyone to P2 |
| wk 7 | Does RCA work with evidence citations? | Cut optional work |
| wk 9 | Is the declarative catalogue working? | Finish current scenario slices first |
| wk 11 | Are F06–F09 complete? | Cut lower-priority polish |
| wk 12 | Is the benchmark running? | Protect P10 |
| wk 13 | Does the demo include success + rollback + escalation? | Rehearse only those paths |

---

## What success looks like

A reviewer creates a scenario. Kavach detects the problem, gathers evidence, produces a cited diagnosis, proposes a repair, passes it through a gate that could have refused, applies the repair **inside the simulation**, verifies multi-objective deltas, and either closes the incident or unwinds it.

The demo then shows:

1. a LOW-risk simulated heal with `MITIGATED` + debt,
2. a verification failure followed by deterministic unwind,
3. an unknown scenario escalating without unsafe execution.

Alongside that, the report shows measurable comparisons between rule-based diagnosis, LLM RCA, undo/no-undo and optional Laya shadow decisions.

That is the standalone proof of Kavach before any real application integration is attempted.
