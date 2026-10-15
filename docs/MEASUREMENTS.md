# Measurements

Generated 2026-10-15 by `harness/report.py` from `eval_results/*.json`.
Every figure is read from those files; none is typed by hand. Reproduce with:

```bash
make bench                                                            # RCA accuracy + Laya vs rules, then this report
make target-up && make onboard APP=targets/proof2 && make bench-live  # undo ablation
```

---

## 1. Undo ablation — the headline result

F01 against the live `targets/proof2` application. Diagnosis held fixed and
verification forced to fail in every arm, so the only variable is the unwind.

| Arm | Prior state restored | Outcome reported | Median |
|---|---|---|---|
| undo works | **5/5 (100.0%)** | ESCALATED | 4.72s |
| undo runs, write is lost | **0/5 (0.0%)** | UNRECOVERABLE | 4.66s |
| unwind step removed | **0/5 (0.0%)** | ESCALATED | 4.57s |

With the undo stack, a failed repair always returns the application to the model
it was serving before. Without it, the application is left on the backup every
time. This is a state read back over HTTP, not an outcome Kavach reports about
itself.

**Is a failed rollback detectable?** `revert_effect` now writes the witnessed
value and reads it back; a mismatch appends to `unwind_unrestored`, and
`outcome_node` reports `UNRECOVERABLE`. Measured:

- undo runs but the write is lost — detected: `True`
- unwind step never runs at all — detected: `False`

The first is the operational failure: an application, proxy or sidecar that
accepts a write and does not apply it. The second is a missing code path, and it
stays invisible by construction — a step that does not execute reports nothing.
Before this, neither was detectable and ROADMAP P3's loud `UNRECOVERABLE` was
raised only by the `_force_undo_failure` test flag.

---

## 2. Shadow Laya vs the rule engine

Real inference over each fault's proposed repair.

- Agreement: **2/9 (22.2%)**
- Laya risk tiers: `{'MEDIUM': 7, 'LOW': 2}` against declared `{'LOW': 7, 'MEDIUM': 2}`
- Laya judged 7 of 9 legitimate repairs unsafe

Had Laya been gating, it would have blocked **78%** of correct repairs. That is
the strongest available evidence that `AGENTS.md`'s shadow-only rule is correct,
and the opposite of the "100% alignment" claimed in
`PROJECT_COMPLETION_REPORT.md`.

- permit() is the authority: Laya is shadow-only and cannot gate, so every disagreement is a Laya error rather than a tie.
- Laya's risk tier is reported, not scored. The declared tiers are LOW for seven faults and MEDIUM for two, and nine cases over two classes is too thin to call it agreement or disagreement.
- Laya confidence is reported as returned. The checkpoint ships invalid temperatures (runtime warning on load), so treat it as uncalibrated.

---

## 3. RCA accuracy and the conditional metrics

45 injections (5 reps x 9 faults), real local model, cold memory, and
with no answer key in the prompt.

| Metric | Value | PRD target |
|---|---|---|
| RCA accuracy | **100.0%** | >= 75% |
| Heal rate | 100.0% | >= 70% (LOW) |
| P(heal \| correct dx) | 100.0% | — |
| P(heal \| wrong dx) | n/a — no wrong diagnoses occurred | — |
| P(correct dx \| heal) | 100.0% | — |
| Median loop | 3.58s | — |

Outcomes: `{'MITIGATED': 45}`. Misdiagnoses: `none`.

PRD §11.1 warns that a headline resolution rate cannot evidence that RCA works,
because published work shows mitigation succeeding on wrong diagnoses 22–62% of
the time. Here it succeeds on a wrong diagnosis **n/a%** of the time. Per-fault
accuracy: `{'F01': 100.0, 'F02': 100.0, 'F03': 100.0, 'F04': 100.0, 'F05': 100.0, 'F06': 100.0, 'F07': 100.0, 'F08': 100.0, 'F09': 100.0}`.

**Read §3.1 before this table.** These nine scenarios each carry evidence that
points at one catalogue entry, so they measure whether the model can read
evidence that is there. They say nothing about what it does when the evidence
does not identify a fault, and that turns out to be the more important question.

- Simulated state: these scenarios are hand-authored YAML and run against Kavach's simulated state, so verification is derived from declared thresholds rather than measured. Only F01-against-proof2 is a live measurement. Treat these as RCA-engine numbers, not platform numbers.
- No rules baseline: Phase 3's symptom mapping no longer exists and the catalogue carries a detect signal for F01, F03 and F07 only, so the LLM-vs-rules comparison PRD 11.2 asks for cannot be run.
- F08's evidence was changed between runs. It previously carried one log line and no indication that the configuration had changed, so every rep answered INSUFFICIENT_EVIDENCE -- correctly, on evidence that distinguished nothing. It now surfaces the config_errors signal it already declared and the version change that preceded the errors. The instrument changed, so this run is not directly comparable with the 88.9% recorded before it; both are in git.
- The fails-closed block is scored separately, against a scenario built to be undiagnosable. It is not in the accuracy denominator: a case whose correct answer is INSUFFICIENT_EVIDENCE would reward a model for refusing to answer anywhere.
- Every heal reports MITIGATED because outcome_node can only emit MITIGATED or ESCALATED; RESOLVED appears nowhere in graph/nodes.py and is set only by debt repayment. The outcome distribution is partly structural.
- Confidence is coerced: the model has been observed returning this field as both 1.0 and 100.0, so RCAResponse now treats a value in (1, 100] as a percentage and refuses anything further out of range. Raw values are not preserved here.
- Shadow Laya stubbed; it cannot affect an outcome.
- Cold memory: knowledge-base read and write are stubbed so reps stay independent. With memory live, a repeat of the same fault retrieves its own answer and accuracy is inflated.

---

## 3.1 Failing closed on ambiguous evidence — the finding that matters

One scenario (`scenarios/FAMB.yaml`) is built so that no catalogue entry is
identifiable: a degraded service, an 8% error ratio, raised latency, and a
provider that is healthy. The correct answer is `INSUFFICIENT_EVIDENCE` and the
correct action is none. It is scored separately and is not in the accuracy
denominator above, because a case whose right answer is "I cannot tell" would
reward a model for refusing everywhere.

| Measured over 5 reps | Result |
|---|---|
| Answered `INSUFFICIENT_EVIDENCE` | **0/5** |
| Took no action | **0/5** |
| Guessed instead | `{'F02': 5}` |
| Outcomes | `{'MITIGATED': 5}` |

With 0/5 declining and 0/5 staying out of the
application, the accuracy figure above does not transfer to ambiguity. The model
answers with high confidence on evidence that does not support an answer, the
confidence gate at 0.8 does not catch it because the confidence is not low, and
the repair executes.

The gate is not a substitute. An earlier run of this study used a narrower
`allowed_actions` and the guessed repair was refused by the allow-list, which
reads from the outside exactly like a system that declined to act. The
permissions were widened to the repairs for the fault classes whose symptoms
overlap, so that what is measured is the diagnosis rather than the allow-list.

What would fix it is not a prompt change. The catalogue declares a `detect`
signal per fault, and a diagnosis whose fault class has no corresponding signal
in the incident's evidence is unsupported by construction -- a rules check the
platform could apply to the model's answer before trusting it. That needs
`detect` restored for all nine fault classes, which is the same work PRD §11.2's
LLM-vs-rules baseline needs. One change, two open items; it is not attempted
here because inventing those signals to make a check pass would be the same
mistake as the prompt that handed over its own answer.

---

## 4. Human baseline — NOT RUN

PRD §11.2 requires the same injections resolved by hand in `SIMULATION`, timed,
to give MTTR a denominator. **Nobody has done this.** It needs a person and
roughly two hours; the harness is ready and waiting:

```bash
cd apps/control-plane && uv run python -m harness.human_baseline
```

Until it is run there is no human MTTR, and any speed-up factor quoted against
one is invented.

---

## 5. What is and is not measured

| Claim | Status |
|---|---|
| Undo restores prior state on a live app | **Measured** |
| An ineffective rollback is detectable | **Measured** — readback mismatch reports `UNRECOVERABLE` |
| An unwind that never runs is detectable | **No** — a step that does not execute reports nothing |
| Laya disagrees with the rule engine | **Measured**, real inference |
| RCA accuracy | **Measured**, no answer key in the prompt |
| P(heal \| wrong diagnosis) | **Measured** |
| Declines to act on ambiguous evidence | **No** — measured 0/5; see §3.1 |
| LLM vs rules baseline | **Unavailable** — P3's mapping is gone; `detect` survives for F01, F03, F07 only |
| Human baseline | **Not run** — `harness/human_baseline.py` is ready; it needs a person |
| F02–F09 behaviour | Simulated state; verification derived from thresholds, not measured |
