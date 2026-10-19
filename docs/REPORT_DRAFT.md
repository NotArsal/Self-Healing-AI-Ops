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

**The catalogue is eight classes and four are implemented.** Every gap has a
recorded reason rather than a quiet omission, and the IDs are stable
identifiers, not indices — `F04`'s number is not reused, so the catalogue
reads `F01, F02, F03, F05, F06, F07, F08, F09`: eight entries with a gap.

| class | why it is not in the results |
|---|---|
| **F04** cache poisoning / stale cache | **Retired.** The target has no cache — no Redis, no response cache, no embedding cache — so `flush_cache` repairs nothing. Redis was **not** added to manufacture a fault for it. Building a feature in order to have something to break is the wrong direction, and a reviewer would be right to say so |
| F09 | **Closed on measurement**, not on opinion. Three mechanisms were tried and none moved the signal enough to inject honestly: `rerank_threshold` 1.20×, verbose prompts 0.87–1.17×, and `max_tokens` is a ceiling rather than a lever |
| F02, F05 | Dropped at the week-10 checkpoint to protect P6 and P8 |
| F03 | Injector deferred; the class is specified but cannot be injected, so it has no denominator |

The consequence is stated rather than hidden: the benchmark denominator is
**four classes, not eight**, and every rate in §4.1 is over 20 injections.
`PRD.md` §10's original "7 × 5 = 35" assumed seven injectable classes.

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
| **MTTD median** | **withdrawn — never measured** | < 30s | **no result** |
| first verdict median *(see below)* | 48.5s | *no target* | — |
| target state clean after run | 100% (20/20) | 100% | met |
| audit chain intact | yes | yes | met |

**MTTD is withdrawn, because this project has never measured it.** An earlier
draft of this section argued that the < 30s target was arithmetically
unreachable and should be restated. That argument was wrong, and so was the
48.5s figure it defended.

The harness computed `mttd_s` as wall time from injection to the loop's first
*terminal* status (`harness/report.py`, and `wait_terminal` counts
`AWAITING_APPROVAL` as terminal). So the figure labelled "time to detect"
contained, in order: the F01/F06 traffic warm-up, the pre-detection fast set,
detection itself, the **entire LLM diagnosis**, and the `permit()` gate. The
warm-up alone has a median of 48.6s for F01 and 51.6s for F06 — recorded
separately in the same artifact, and larger than the whole "MTTD" target.
Nothing else was available to use: `detected_at` is stamped at the top of
`run_once`, *before* detection runs, so the instant detection concluded was
never written down anywhere.

A metric compared against a target for three phases, where neither endpoint of
the interval marks the event being measured, is not a missed target. It is an
absent measurement, and it is reported here as absent.

The four windows, for the restatement that is now possible but not yet
evidenced: F01's error ratio is `rate(...[2m])` behind a `min_requests ≥ 3.0`
gate, F06's is `rate(...[1m])`, Prometheus scrapes at 15s, and F07 and F08
read no PromQL at all — their detectors compare a prompt hash and a config
snapshot, so their floor is the fast set, not a metric window. That spread
makes a single cross-class MTTD target questionable in itself. **The fix is
instrumentation, not arithmetic:** `loop.py` now stamps
`detection.concluded_at` the moment `run_all` returns, the harness computes
MTTD from it, and the old quantity is reported under its true name,
`first_verdict_s`. The number will come from the next bench run; this one
cannot produce it retroactively.

### 4.2 F07 healed 0 times out of 5, and that is the most interesting row

F07 is the only class the bench never repaired, and it failed twice over for
two different reasons.

Read this section with **§4.8**: a human operator and a scripted runbook were
each given F07 on the same system, and both produced a **false recovery** —
the runbook while diagnosing it *correctly*. All three approaches fail on
F07. Kavach is the only one that does not claim otherwise.

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

**And the F07 row does not even survive as a determinism check** — see
`docs/decisions/0013`. Re-run on 2026-10-19 with the same model, the same
baseline and the same ten repetitions, it returns **0/10**. One variable
explains it:

| frame window | `num_ctx` | F07 |
|---|---|---|
| `[10m]` | 4096 | **10/10** |
| `[1m]` | 4096 | **0/10** |
| `[1m]` | 8192 | **0/10** |
| `[10m]` | 8192 | **10/10** |

The context window is exonerated. The cause is ADR 0010's correct, tested
change moving the frame's retrieval queries from `[10m]` to `[1m]` so the
frame and the detector read the same signal. Nobody re-measured F07, because
F07's accuracy had no visible dependency on a retrieval metric.

**The window is not being reverted.** Reverting would buy back a 10/10 by
putting the frame and the detector out of step again — weakening a verified
invariant to improve a number. F07's LLM path is reported as **0/10** and
`ROADMAP.md`'s P6 F07 acceptance is **failed**. F07's deterministic path is
untouched and still heals it.

What the model does when it fails is the part worth presenting: it returns
`fault_class: "F06"` with `fault_name: "Prompt version regression"` — and
F07 *is* prompt version regression. It cites `EV-C08`, the one line that
distinguishes the two classes, in 10 of 10 failing runs. It reads the right
evidence, names the fault correctly in prose, and emits the wrong code.

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

### 4.8 The two comparison baselines, and the thing they have in common

Two baselines exist and both have been run. Neither is large. Both found the
same failure, which is why they are reported together.

**The scripted runbook** — `runbook-baseline.json`, 4 classes x 2 reps, the
documented diagnostic procedure executed as code. No person, no search cost,
no hesitation, so its timings are a **lower bound on the manual path**: the
best a perfectly-prepared operator could do, not a realistic one.

| | result |
|---|---|
| diagnosis correct | **8/8** |
| resolve verified | 7/8 |
| median resolve | 37.5s |
| **false recoveries** | **1/8 — F07** |

A runbook scoring 8/8 on the four faults it was written for is the expected
result and is not a finding. It would score zero on a fifth. The finding is
the row it got *wrong while believing it was right*.

**The human pilot** — `human-baseline.json`, 2026-10-18, one operator, three
runs against blind injections, with Kavach observing the same incident in
`SIMULATION` so each observation is **paired** rather than two unpaired
samples.

| fault | operator's diagnosis | correct | outcome | Kavach, same incident |
|---|---|---|---|---|
| F07 | *"idk based on provided docs"* | no | declared resolved at 104.6s, **fast set 0%** | **F07**, conf 0.95 |
| F01 | *"i fucking dont know"* | no | gave up at 67.8s | escalated |
| F01 | *"I think its connection issue"* | no | gave up at 26.2s | **F01**, conf 0.95 |

**0/3 correct, 2 give-ups, 1 false recovery. Kavach 2/3 correct on the
identical incidents.**

#### What both baselines found, which neither was looking for

Line up the three approaches on **F07**, the class §4.2 reports Kavach
healing zero times out of five:

| | diagnosed F07 | repaired it | **claimed success while broken** |
|---|---|---|---|
| human operator | no | no | **yes** — declared fixed at 0% pass rate |
| scripted runbook | yes, 2/2 | 1 of 2 | **yes** — 1/2, `verified: false` |
| Kavach | deterministic yes 5/5, model no 0/5 | no, 0/5 | **no — 0/5, target clean 5/5** |

Every approach fails on F07. **Two of the three lie about it.** The runbook is
the sharper case: it diagnosed the fault *correctly*, applied the correct
repair action, and the system was still broken — a false recovery produced by
a procedure that did everything right on paper.

That reframes §4.2. Kavach's zero on F07 is not its weakest row against these
baselines; it is the only one of the three that fails without claiming
otherwise, and the mechanism that produced the difference — the deterministic
cross-check refusing a diagnosis it could not corroborate — is the thing this
project is arguing for.

#### Limits, stated plainly

- **n = 3 for the human pilot**, against a protocol that asks for 12. One
  operator, not a panel. **F06 and F08 were never attempted by a human.** It
  is a pilot and is reported as one; it is not a study.
- The operator was a project author, which cuts both ways: more familiar with
  the system than a stranger, and therefore a *conservative* baseline — a
  neutral operator would not do better.
- The runbook is n=2 per class, and its single F07 false recovery is 1 of 2,
  so prompt restoration is flaky rather than reliably broken. Two runs cannot
  tell those apart.
- Neither baseline is large enough to support a significance claim and none
  is made.

### 4.9 What the LLM layer costs — `kavach-baseline*.json`

The deterministic loop (P2) and the same loop with LLM RCA in front of it
(P3), on the same four faults, same baseline, same target.

| class | deterministic resolve | with RCA | outcome with RCA |
|---|---|---|---|
| F08 | **60.6s** | 102.7s | resolved |
| F07 | **63.5s** | — | escalated (both runs) |
| F01 | **84.8s** | 127.2s | resolved |
| F06 | **114.7s** | 160.0s | resolved |
| | **4/4 resolved** | **4/8 resolved** | |

**The deterministic loop is faster on every class and heals more often.**
Adding the model costs 40–70% more wall time and halves the resolution rate.
That is the honest headline and it should not be buried.

#### Why that is the architecture working, not a defect

RCA **cannot** widen what executes. Deterministic detection still has to find
the fault, the plan still comes from the same literal dict, and the repair is
the same single action (`loop.py`). The model adds a gate and an explanation;
it cannot authorise anything. So the RCA arm resolving *at most* as often as
the deterministic arm is structurally guaranteed. The only question a
measurement can answer is **whether the refusals were right.**

#### They were mostly right, and that "mostly" is the cost

Four escalations in the RCA arm:

| | model said | refused correctly? |
|---|---|---|
| F01 | **F06 — wrong** | **yes.** A wrong diagnosis was stopped |
| F07 ×2 | F07 — correct | **no.** A correct diagnosis was blocked |
| F08 | F08 — correct | **no.** A correct diagnosis was blocked |

**Three of four refusals blocked a correct answer.** The cross-check is
conservative, and this is the price: it has never let a wrong diagnosis
drive a repair (0/20 in §4.1, 0/3 wrong diagnoses acted on), and it also
refuses correct ones. A reviewer should see both numbers, because a gate
that refuses everything would score perfectly on the first and be useless.

#### So what is the model for

Not speed and not throughput — it demonstrably costs both. On this
catalogue, the model buys three things the deterministic path does not have:

1. **A stated confidence and cited evidence** per incident, which is what
   makes the refusal legible to an operator rather than an opaque stop.
2. **A refusal mechanism that generalises.** The deterministic detectors
   each recognise one fault; the cross-check compares two independent
   derivations and can disagree on a fault neither was tuned for.
3. **An answer at all on faults outside the catalogue**, where the
   deterministic path returns `INSUFFICIENT_EVIDENCE` by construction.

Only (1) is measured here. **(2) and (3) are untested claims** — every fault
in this catalogue has a deterministic detector, so the configuration where
the model would add capability is exactly the one never exercised. Stated as
a limitation, not a result.

#### Limits

**n = 1 per class in the deterministic arm**, 1–2 in the RCA arm. These are
single runs, not distributions, and the bench (§4.1) is the only large
sample — and it has **no deterministic arm at all**. The percentages above
are indicative of direction, not magnitude. A paired deterministic bench at
the same 4 × 5 denominator is the measurement this section deserves and does
not have.

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

**MTTD was never measured, and the figure is withdrawn.** The harness timed
injection-to-first-terminal-status and called it detection. See §4.1.
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

**It does not support Kubernetes, and the target's repository will suggest
otherwise.** The target contains `k8s/` Deployment and Service manifests, a
`kubernetes` client dependency, a LangGraph agent whose `heal_service` node
deletes pods, and its own `ADR-002` declaring Kubernetes mandatory for
self-healing. All of that pre-dates Kavach and none of it is Kavach.

Kavach v1 does not read those manifests, does not call the Kubernetes API,
and has no Kubernetes action in its registry. The target's own healing path
is **unreachable** — the `POST /v1/webhook/alert` route that invoked it is
not registered, which also closed an unauthenticated endpoint that could
delete pods on request. The agent file is left on disk for reference,
imported by nothing (`ADR 0003`).

The reason it was disabled is `FR-15a`, writer exclusivity: two controllers
mutating one system makes every recoverability claim void, because neither
can know whether it caused the state it observes. The pre-existing mechanism
also satisfies none of Kavach's safety requirements — no allow-list, no risk
tier, no inverse, no idempotency key, no pre-state witness.

Stated plainly for a reviewer: *"the target contains Kubernetes files"* and
*"Kavach supports Kubernetes"* are different statements, and only the first
is true.

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
2. ~~Re-measure RCA at the corrected context window~~ — **done.** The
   window was not the cause; ADR 0013 identifies the real one. F01, F06 and
   F08 need no fixed-frame re-run: the bench already measures them on the
   current frame across twenty fresh frames, at 5/5 each.
3. Re-run the bench for a real MTTD, now that `detection.concluded_at`
   exists (§4.1). Only then is it worth asking whether < 30s is the right
   target.
4. `make scenario` — three clean runs, an hour apart
5. ~~Human baseline: run it, or record the decision to drop it~~ —
   **closed 2026-10-19, written up in §4.8.** It was run on 2026-10-18 and
   the result had been sitting in `human-baseline.json` unreported. It
   stays at n=3 against a protocol asking for 12: the decision is to report
   a paired pilot with its limits stated rather than pad it. Padding would
   make the number prettier and the claim no truer.
6. The one-line `allowed_actions` decision for `apply_patch` (ADR 0012)
