# Kavach — report draft

**Status: a draft with real numbers, not a finished report.** Every figure
below is traceable to a file in `harness/reports/`, and the filename is given.
Where a number is missing or provisional it says so rather than being filled
in. Nothing here is estimated.

`harness/reports/` is in `.gitignore`, so those files exist on the machine
that produced them and not in a clone. For a report whose argument is
traceability that is a gap; committing the artifacts is a one-line change to
`.gitignore` and is left as a deliberate decision rather than made quietly.

Written 2026-10-19, updated after the full `make bench` run completed at
08:55 UTC. §4.1 and §4.2 are now the bench's twenty injections, not single
runs.

---

## 1. One paragraph

Kavach is an autonomous self-healing control plane for AI applications. It
watches a running retrieval-augmented generation service, detects four classes
of regression, diagnoses them with an LLM whose answer is cross-checked against
deterministic detectors, and repairs them with actions that each carry a
recorded inverse. The contribution is not that an LLM can diagnose an incident —
it is that **a deterministic layer, not the model, decides whether anything is
written**, and that this is measured rather than asserted.

## 2. The claim, stated so it can fail

> An LLM may propose a repair. It may never authorise one.

Three measurements would falsify this:

1. an action executing without passing `permit()`
2. the deterministic cross-check accepting a wrong diagnosis
3. an incident leaving the target in a state the undo stack cannot restore

None has occurred. §5 gives the numbers; §7 gives the limits of that claim.

## 3. What was built

Two repositories, never merged. The control plane is this one. The target is
`Simple_RAG-Pipeline`, pre-existing, not written for this project, and modified
only by the eleven additions `PRD.md` §5.2 permits, each with a decision record.

**Detection** — four implemented fault classes:

| class | fault | signal | repair | tier |
|---|---|---|---|---|
| F01 | LLM endpoint outage | error ratio > 20% over 60s | `switch_llm_endpoint` | LOW |
| F06 | Retrieval collapse | kept-chunks mean, empty-context ratio | `rollback_config` | MEDIUM |
| F07 | Prompt regression | fast-set drop after a prompt change | `rollback_prompt` | MEDIUM |
| F08 | Config regression | config hash moved + SLO breach | `rollback_config` | MEDIUM |
| — | generated repair | *(not a class; an escalation path)* | `apply_patch` | **HIGH** |

F02, F03, F05 and F09 were each dropped for a stated reason, recorded rather
than quietly omitted. F09 was closed **on measurement** — it was not
injectable honestly.

**The safety engine.** A ten-step gate. Deny-list before allow-list, so adding
an action to `allowed_actions` cannot enable a denied mutation. Four verdicts:
`ALLOW_AUTO`, `REQUIRE_SANDBOX`, `REQUIRE_APPROVAL`, `DENY`. A blast radius of
five incident starts per sliding hour, where an approved heal costs two.

**Recoverability.** Every action declares an inverse, and an action without one
*cannot be registered* — `register()` raises at import time, so the failure
happens in the test suite rather than at 3 a.m.

**Audit.** A hash-chained append-only log. `make postmortem` renders any
incident from it, and verifies the chain while doing so.

## 4. Results

### 4.1 The bench — `bench-full.json`, 4 classes x 5 reps = 20 injections

Run unattended overnight in `APPROVAL` mode, 2026-10-18 19:12 to 2026-10-19
08:55 UTC. Every injection was real, every approval was issued by the harness
acting as the operator, and nothing was reset, raised or disabled.

| class | MTTD median [min–max] | MTTR median [min–max] | healed |
|---|---|---|---|
| F08 config regression | 36.4s [30.3–39.3] | **99.9s** [90.9–105.8] | 5/5 |
| F07 prompt regression | 39.4s [39.4–42.4] | — | **0/5** |
| F01 endpoint outage | 78.9s [54.6–94.0] | **124.4s** [96.9–154.6] | 5/5 |
| F06 retrieval collapse | 87.9s [84.0–93.5] | **150.8s** [147.5–160.0] | 5/5 |

| metric | value | `PRD.md` §10 target | |
|---|---|---|---|
| detection rate | 100% (20/20) | ≥ 95% | met |
| localisation | 100% (20/20) | ≥ 80% | met *(one-way, see §6)* |
| RCA accuracy, the model's own answer | 85% (17/20) | ≥ 75% | met |
| auto-resolution | 75% (15/20) | ≥ 70% | met |
| **false healing** | **0% (0/20)** | ≤ 5% | met |
| MTTR median | 124.4s (n=15) | < 180s | met |
| **MTTD median** | **48.5s** | < 30s | **missed** |
| target state clean after run | 100% (20/20) | 100% | met |
| audit chain intact | yes | yes | met |

**MTTD misses its target and the target was the wrong number.** Detection is
bounded below by the detector's own evaluation window — F06 claims on a 60s
`empty_context_ratio` ratio and F01 on a 60s error ratio, so a sub-30s median
across those classes is arithmetically impossible, not merely unachieved. The
two classes that do not wait on a rate window (F07 39.4s, F08 36.4s) still sit
above 30s because the loop polls. The honest correction is to the target, in
the report, with the window arithmetic shown — not to the measurement.

### 4.2 F07 healed 0 times out of 5, and that is the most interesting row

F07 is the only class the bench never repaired, and it failed twice over for
two different reasons:

| rep | first RCA | after approval | end |
|---|---|---|---|
| 1 | F07 ✓ | **F06 ✗** | escalated |
| 2 | F06 ✗ | — | escalated |
| 3 | F07 ✓ | **F06 ✗** | escalated |
| 4 | F06 ✗ | — | escalated |
| 5 | F06 ✗ | — | escalated |

The model scored 2/5 on the first evidence frame. Both of those two then
**flipped to F06 on a second, freshly-built frame** taken after the operator
approved. `runner.approve()` re-detects and re-diagnoses rather than replaying
a stored plan, deliberately — the world may have moved while the dialog was
open, and a replayed plan would restore a value that was true when it opened.
The cost of that correctness is that an approved F07 must be diagnosed
correctly *twice*, and qwen2.5:7b cannot do it once reliably.

Three things follow, and all three belong in the report:

1. **The cross-check held.** Every one of the five is an escalation with
   nothing written and the target left as found. A system that healed F07 by
   acting on an F06 diagnosis would have scored better on this table and been
   worse.
2. **§4.3's 10/10 for qwen on F07 was consistency, not accuracy.** The same
   model on fresh frames of the same fault scores 2/5. Fixed-frame repetition
   measures decoder determinism; it does not measure diagnosis. §4.3 is
   re-labelled accordingly.
3. **Approval doubles the model's exposure.** Not a defect — a measured
   property of re-deriving the plan, and the argument for routing a
   deterministically-detected fault around RCA entirely when the detector is
   already unambiguous.

### 4.2a The conditionals — the part a reviewer asks about

| | |
|---|---|
| P(heal \| diagnosis correct) | 88% (15/17) |
| P(heal \| diagnosis **wrong**) | **0% (0/3)** |
| P(diagnosis correct \| heal) | **100% (15/15)** |

A high auto-resolution rate next to a high P(heal | wrong) would mean a
symptom-matcher with an LLM bolted on. Both are reported, or neither is worth
reporting.

### 4.2b The throughput ceiling, measured not assumed

The bench spent **7.4 hours of its 13.7-hour wall clock waiting** for the
blast-radius window to slide. `permit()` allows five incident starts per
sliding hour and an approved heal costs two, so Kavach performs **at most two
approved heals per hour** and halts rather than widening. That is a demo
constraint as much as an operational one, and it is the reason the bench ran
overnight instead of in twenty minutes.

### 4.3 Decoder consistency, NOT diagnosis accuracy — `p6-*-rca*.json`

| model | F01 | F07 | F08 |
|---|---|---|---|
| llama3.2 | **10/10** | 0/10 | 0/10 |
| qwen2.5:7b-instruct | — | **10/10** | **10/10** |

**This table was mis-titled in the first draft and the bench proves it.** Ten
repetitions against *one frozen evidence frame* measure whether the decoder
returns the same answer twice, which at temperature 0 it should. They do not
measure diagnosis. The same qwen2.5:7b that scores 10/10 here scores **2/5 on
F07 across fresh frames** (§4.2) and flips its own correct answer when asked a
second time about the same live fault.

§4.1's `RCA accuracy 85% (17/20)` is the accuracy figure. This one is a
determinism check, and it is kept only because a *failure* here would have
invalidated everything downstream.

Two further caveats:

- Validator approval tracked class agreement exactly in every run — the
  cross-check added nothing on a frame the model had already got right, which
  is the expected null result.
- **All of these were measured with a context window that was sometimes
  exceeded.** See §6.

### 4.4 The deterministic cross-check — the headline safety result

**21 of 21 wrong diagnoses rejected.** No wrong diagnosis has ever driven a
repair. This is the measurement the central claim rests on.

### 4.5 Generated repairs — `p7-*.json`

Applicability: does `git apply --check` accept the patch? Ten samples each.

| model | applies |
|---|---|
| gpt-oss-120b (Groq) | **10/10** |
| gemini-3.8-flash | 7/10 *(measured before a fix; a floor)* |
| llama3.1, llama3.2, qwen2.5:7b (local) | **0/30** |

End to end against the live sandbox:

- **gemini-3.8-flash: PASS.** F07 injected for real; production fast set 0%;
  the generated patch applied to the clone; the clone returned **100%**;
  production untouched and restored byte-exact.
- **gpt-oss-120b, 3 runs: 1 inapplicable, 2 refused by the sandbox at 67%.**

The two refusals are the most informative result in the project. Each patch
passed all six deterministic checks and applied cleanly, and still did not
repair the behaviour. **No amount of static checking finds that.** It is
exactly what a mandatory sandbox is for.

### 4.6 Injector determinism

20 cycles F07, 20 cycles F01, 30 cycles F08 — stack identical at start and end
in every case. A fault injector that does not reliably inject its fault makes
every number above meaningless, so it is measured separately.

### 4.7 Undo

With the undo stack, the target is left exactly as found. With it ablated, the
target is stranded in a third state — neither faulted nor healed.

### 4.8 Human comparison — incomplete

A scripted runbook baseline (`runbook-baseline.json`) diagnosed 8/8 with a
median of 37.5s. **It is not a human baseline** and must not be presented as
one: a script following a written procedure has no search cost. A real human
baseline has a protocol and an instrument but has not been run. Report it as
missing.

## 5. What the safety engine refused

| event | count |
|---|---|
| wrong diagnoses rejected by the cross-check | 26 / 26 |
| of those, from this bench | 5 / 5 |
| F07 incidents escalated rather than guessed | 5 / 5 |
| generated patches refused before production | all of them |
| patches refused *by the sandbox after passing every static check* | 2 |
| incidents leaving the target unclean | **0 / 20** |
| false healings — resolved while still broken | **0 / 20** |

False healing is checked by an **independent** fast-set run after the loop
declares `RESOLVED`, not by the loop's own verification, because a
verification bug would otherwise hide inside the number meant to catch it.

The bench's own summary prints `LLM diagnoses refused: 3/20` because its
denominator is one diagnosis per run. Two more were refused on the
post-approval re-runs of F07 reps 1 and 3, which that denominator does not
see — 22 diagnoses were issued across 20 injections. Five were wrong and five
were refused.

## 6. Threats to validity — read this before quoting §4

**One workload.** Every number describes one RAG application. The seams for a
second exist and have not been exercised.

**One-way localisation.** Every implemented fault lands on `backend`, so
"localisation accuracy" is a one-way choice dressed as a four-way one. Stated
first wherever it appears.

**Two instrument bugs were found in two days.**

1. A 0/15 result was published blaming model capability. The largest cause was
   Kavach writing patch files without a trailing newline, which `git apply`
   reports as `corrupt patch`. One model went from 4/10 to 10/10 on the fix.
2. The LLM context window was never set. Measured across six real incidents,
   every diagnosis ran within 10% of the 4096-token ceiling and one exceeded
   it at 4158. Ollama slides the window silently, dropping the system prompt
   first. Every accuracy figure in §4.3 was measured under this condition.
   Truncation can only *remove* instructions, so those figures are a **floor** —
   but they need re-measuring at the corrected 8192 before being quoted.

The generalisable lesson, and the one worth putting in the conclusion: **a
measurement is a finding about the instrument until proven otherwise.** Both
bugs were found by checking the rig against a known-good input, which is now a
test in both cases.

**Five repetitions, one machine, one night.** n=5 per class is enough to
show F07 failing consistently and not enough for a confidence interval on
MTTR. Every run shares one host, one Ollama and one corpus.

**The bench ran in `APPROVAL`, so every MTTR includes an operator round
trip.** The harness approves instantly; a human would not. MTTR here is a
floor for the approval posture and is not comparable to an `AUTONOMOUS` one.

**MTTD misses its target and the target is wrong, not the system.** See §4.1.
Stated as a missed target anyway, because moving a threshold after seeing the
data is how acceptance criteria stop meaning anything.

## 7. What Kavach is not

It is **not an autoscaler**. Asked whether it would fix a Flipkart Big Billion
Days traffic slowdown: no. No detector matches a pure load surge, no action
adds capacity, and `FR-30` forbids any scaling action. It would return
`UNKNOWN`, escalate to a human, and that is correct. Capacity is a solved
problem with good tools; conflating the two would weaken a claim that is
currently sharp.

It does **not** rewrite its own source, refactor the target, or do autonomous
development.

## 8. Related work

- **AIOpsLab** (Microsoft Research, arXiv 2501.06706) — deploys microservice
  environments, injects faults, generates workloads. Kavach's harness is a
  narrow instance of the same methodology. AIOpsLab is broad and has no safety
  engine; Kavach is narrow and its contribution is the gate.
- **ITBench** (IBM, arXiv 2502.05352) — broader IT automation benchmarking
  with a public leaderboard.
- **AegisFlow** (arXiv 2610.06971) — the closest related system.
- **"Stalled, Biased, and Confused"** (FORGE 2026) — independently corroborates
  the finding that small local models stall at symptoms.
- Commercial AI-SRE vendors converge on the same boundary: *remediation is
  genuinely automatable only in bounded cases.* Kavach built the bounded case
  and measured it.

## 9. Still to do

1. ~~Full `make bench`~~ — **done 2026-10-19 08:55**, §4.1/§4.2
2. Re-measure RCA at the corrected context window. The bench's API image
   predates the `num_ctx` fix, so its 85% carries the §6 caveat; its MTTR
   figures do not, because repairs run on the deterministic path.
3. Re-state the MTTD target with its window arithmetic (§4.1)
4. `make scenario` — three clean runs, an hour apart
5. Human baseline: run it, or record the decision to drop it
6. The one-line `allowed_actions` decision for `apply_patch` (ADR 0012)
