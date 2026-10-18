# Kavach — report draft

**Status: a draft with real numbers, not a finished report.** Every figure
below is traceable to a file in `harness/reports/`, and the filename is given.
Where a number is missing or provisional it says so rather than being filled
in. Nothing here is estimated.

Written 2026-10-19. The full `make bench` run was still executing when this
was drafted; §4.1 is marked accordingly.

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

### 4.1 Mean time to repair — `kavach-baseline.json`

Deterministic path, one run per class:

| class | detected → resolved | gate decision | end state |
|---|---|---|---|
| F08 | **60.6s** | 21.2s | clean |
| F07 | **63.5s** | 21.2s | clean |
| F01 | **84.8s** | 51.6s | clean |
| F06 | **114.7s** | 75.5s | clean |

Median **84.8s** against the `PRD.md` §10 target of 180s. The target is met
with margin on every class.

> The full 4×5 `make bench` run was still executing at the time of writing.
> These are single runs; the bench supplies the repeated denominator and
> replaces this table.

### 4.2 Does the LLM help? — the honest answer is "not yet"

Running the same classes with the RCA stage enabled:

| class | deterministic | with RCA |
|---|---|---|
| F06 | 114.7s resolved | 169.8s resolved |
| F01 | 84.8s resolved | **escalated** |
| F07 | 63.5s resolved | **escalated** |
| F08 | 60.6s resolved | **escalated** |

**The LLM path is slower where it works and escalates where it does not.**
This is reported because it is true. The escalations are the cross-check
refusing a diagnosis it could not corroborate, which is the designed behaviour
and the system's central safety property working — but it is not a speed-up,
and the report should not imply one.

### 4.3 Diagnosis accuracy — `p6-*-rca*.json`, 10 repetitions each

| model | F01 | F07 | F08 |
|---|---|---|---|
| llama3.2 | **10/10** | 0/10 | 0/10 |
| qwen2.5:7b-instruct | — | **10/10** | **10/10** |

Validator approval tracked class accuracy exactly in every run.

Two caveats that matter more than the numbers:

- These measure **consistency on one fixed evidence frame**, not accuracy
  across frames. On a fresh frame, qwen got F07 wrong.
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
| wrong diagnoses rejected by the cross-check | 21 / 21 |
| generated patches refused before production | all of them |
| patches refused *by the sandbox after passing every static check* | 2 |
| incidents leaving the target unclean | 0 |

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

**Single runs.** §4.1 and §4.2 are one run per class pending the bench.

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

1. Full `make bench` → replaces §4.1 and §4.2
2. Re-measure §4.3 at the corrected context window
3. `make scenario` — three clean runs, an hour apart
4. Human baseline: run it, or record the decision to drop it
5. The one-line `allowed_actions` decision for `apply_patch` (ADR 0012)
