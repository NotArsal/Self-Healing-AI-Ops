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
verification forced to fail in both arms, so the only variable is the unwind.

| Arm | Prior state restored | Outcome reported | Median |
|---|---|---|---|
| undo enabled | **5/5 (100.0%)** | ESCALATED | 0.32s |
| undo disabled | **0/5 (0.0%)** | ESCALATED | 0.3s |

With the undo stack, a failed repair always returns the application to the model
it was serving before. Without it, the application is left on the backup every
time. This is a state read back over HTTP, not an outcome Kavach reports about
itself.

**The second finding matters as much.** `outcome_distinguishes_arms` is
`None`: both arms report the same outcome, so the reported
outcome cannot tell an operator whether the application was left in a mutated
state. Kavach never verifies that its own rollback achieved anything —
`UNRECOVERABLE` is raised only by the `_force_undo_failure` test flag. ROADMAP P3
requires a forced-undo-failure path to report `UNRECOVERABLE` loudly; it cannot.

---

## 2. Shadow Laya vs the rule engine

Real inference over each fault's proposed repair.

- Agreement: **2/9 (22.2%)**
- Laya risk tiers: `{'MEDIUM': 7, 'LOW': 2}` against declared `{'LOW': 9}`
- Laya judged 7 of 9 legitimate repairs unsafe

Had Laya been gating, it would have blocked **78%** of correct repairs. That is
the strongest available evidence that `AGENTS.md`'s shadow-only rule is correct,
and the opposite of the "100% alignment" claimed in
`PROJECT_COMPLETION_REPORT.md`.

- permit() is the authority: Laya is shadow-only and cannot gate, so every disagreement is a Laya error rather than a tie.
- Laya's risk tier is not scored: every fault loads as LOW because the per-fault catalogue files replace core.yaml's entries instead of merging, so the declared tiers are not usable as ground truth.
- Laya confidence is reported as returned. The checkpoint ships invalid temperatures (runtime warning on load), so treat it as uncalibrated.

---

## 3. RCA accuracy and the conditional metrics

45 injections (5 reps x 9 faults), real local model, cold memory, and
with no answer key in the prompt.

| Metric | Value | PRD target |
|---|---|---|
| RCA accuracy | **88.9%** | >= 75% |
| Heal rate | 88.9% | >= 70% (LOW) |
| P(heal \| correct dx) | 100.0% | — |
| P(heal \| wrong dx) | **0.0%** | — |
| P(correct dx \| heal) | 100.0% | — |
| Median loop | 2.34s | — |

Outcomes: `{'MITIGATED': 40, 'ESCALATED': 5}`. Misdiagnoses: `{'F08->INSUFFICIENT_EVIDENCE': 5}`.

PRD §11.1 warns that a headline resolution rate cannot evidence that RCA works,
because published work shows mitigation succeeding on wrong diagnoses 22–62% of
the time. Here it succeeds on a wrong diagnosis **0.0%** of the time, so the
headline is not luck. Per-fault accuracy: `{'F01': 100.0, 'F02': 100.0, 'F03': 100.0, 'F04': 100.0, 'F05': 100.0, 'F06': 100.0, 'F07': 100.0, 'F08': 0.0, 'F09': 100.0}`.

- Simulated state: these scenarios are hand-authored YAML and run against Kavach's simulated state, so verification is derived from declared thresholds rather than measured. Only F01-against-proof2 is a live measurement. Treat these as RCA-engine numbers, not platform numbers.
- No rules baseline: Phase 3's symptom mapping no longer exists and the catalogue retains a detect signal for F01 only, so the LLM-vs-rules comparison PRD 11.2 asks for cannot be run.
- F08 fails on every rep, answering INSUFFICIENT_EVIDENCE at confidence 0.3. Its scenario carries a config_errors signal and evidence sourced only from 'api', which does not distinguish a config regression from several other candidates. This is a gap in the evaluation set, not a model failure -- and the system failing closed (low confidence, escalate, take no action) is the designed behaviour.
- Every heal reports MITIGATED because outcome_node can only emit MITIGATED or ESCALATED; RESOLVED appears nowhere in graph/nodes.py and is set only by debt repayment. The outcome distribution is partly structural.
- Confidence is coerced: the model has been observed returning this field as both 1.0 and 100.0, so RCAResponse now treats a value in (1, 100] as a percentage and refuses anything further out of range. Raw values are not preserved here.
- Shadow Laya stubbed; it cannot affect an outcome.
- Cold memory: knowledge-base read and write are stubbed so reps stay independent. With memory live, a repeat of the same fault retrieves its own answer and accuracy is inflated.

---

## 4. Human baseline — NOT RUN

PRD §11.2 requires the same injections resolved by hand in `SIMULATION`, timed,
to give MTTR a denominator. **Nobody has done this.** It is roughly two hours of
one person's time and cannot be automated. Until it is run there is no human
MTTR, and any speed-up factor quoted against one is invented.

---

## 5. What is and is not measured

| Claim | Status |
|---|---|
| Undo restores prior state on a live app | **Measured** |
| A failed rollback is detectable | **No** — both ablation arms report the same outcome |
| Laya disagrees with the rule engine | **Measured**, real inference |
| RCA accuracy | **Measured**, no answer key in the prompt |
| P(heal \| wrong diagnosis) | **Measured** |
| LLM vs rules baseline | **Unavailable** — P3's mapping is gone; `detect` survives for F01 only |
| Human baseline | **Not run** |
| F02–F09 behaviour | Simulated state; verification derived from thresholds, not measured |
