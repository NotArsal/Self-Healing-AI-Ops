# Measurements

Generated 2026-10-15 from `eval_results/*.json`. Every number below is read
from those files; none is typed by hand. Reproduce with:

```bash
make bench                                                            # RCA accuracy + Laya vs rules
make target-up && make onboard APP=targets/proof2 && make bench-live  # undo ablation
```

> **Supersedes `Phase11_Report.md` and `docs/phase11_report.md`.** Those two
> predate any measurement, contradict each other on every number, and cite the
> two scripts that were deleted for fabricating their results.

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
time. This is a state read back over HTTP, not an inferred outcome.

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

Reported confidences run 0.01–0.16 — near-uniform and very low, consistent with
the runtime warning that the checkpoint ships invalid temperatures. Treat every
Laya confidence as uncalibrated.

- permit() is the authority: Laya is shadow-only and cannot gate, so every disagreement is a Laya error rather than a tie.
- Laya's risk tier is not scored: every fault loads as LOW because the per-fault catalogue files replace core.yaml's entries instead of merging, so the declared tiers are not usable as ground truth.
- Laya confidence is reported as returned. The checkpoint ships invalid temperatures (runtime warning on load), so treat it as uncalibrated.

---

## 3. RCA accuracy and the conditional metrics

45 injections (5 reps x 9 faults), real local model, cold memory.

| Metric | Value | PRD target |
|---|---|---|
| RCA accuracy | 100.0% | >= 75% |
| Heal rate | 100.0% | >= 70% (LOW) |
| P(heal \| correct dx) | 100.0% | — |
| P(heal \| wrong dx) | **n/a — no wrong diagnoses occurred** | — |
| P(correct dx \| heal) | 100.0% | — |
| Median loop | 2.97s | — |

**These numbers must not be reported as a success.** They say the evaluation is
degenerate, not that RCA works:

- DEGENERATE EVALUATION -- do not read 100% as RCA working. The RCA prompt (llm/rca.py) contains an explicit answer key: 'If you see gen_ai_error_ratio -> output F01' and one such rule per fault class. Each scenario's evidence contains exactly the giveaway string its rule names, so the model performs a lookup the prompt spells out. This arm is a symptom matcher executed through a 7B model, which is also why PRD 11.2's LLM-vs-rules comparison is vacuous here: both arms would be the same mechanism.
- P(heal | wrong diagnosis) is uncomputable: there were zero wrong diagnoses, so the stratum PRD 11.1 calls the point of the exercise is empty. The headline heal rate cannot be separated from luck on this scenario set.
- Confidence is returned on inconsistent scales: 40 runs returned 1.0 and 5 returned 100.0. RCAResponse.confidence is an unconstrained float and the gate compares it against 0.8, so an out-of-range value passes trivially and a 0..100 reading of 50 would escalate where 0.5 would too -- by accident.
- Every outcome is MITIGATED because outcome_node can only emit MITIGATED or ESCALATED; RESOLVED appears nowhere in graph/nodes.py and is set only by debt repayment. The outcome distribution is structural, not measured.
- To get a meaningful number: remove the answer key from the prompt, and add scenarios whose evidence is ambiguous between two fault classes.
- Simulated state: verification is derived from declared thresholds, not measured. Only F01-against-proof2 is a live measurement.
- No rules baseline: Phase 3's symptom mapping no longer exists and the catalogue retains a detect signal for F01 only, so the LLM-vs-rules comparison PRD 11.2 asks for cannot be run.
- Shadow Laya stubbed; it cannot affect an outcome.
- Cold memory: knowledge-base read and write are stubbed so reps stay independent. With memory live, a repeat of the same fault retrieves its own answer and accuracy is inflated.

---

## 4. Human baseline — NOT RUN

PRD §11.2 requires the same injections resolved by hand in `SIMULATION`, timed,
to give MTTR a denominator. **Nobody has done this.** It is roughly two hours of
one person's time and cannot be automated. Until it is run there is no human
MTTR, and any speed-up factor quoted against one is invented.

Both superseded reports quote a human baseline in detail — 11 min and 8m 20s
MTTR respectively. Neither was measured.

---

## 5. What is and is not measured

| Claim | Status |
|---|---|
| Undo restores prior state on a live app | **Measured**, 5 reps per arm |
| Laya disagrees with the rule engine | **Measured**, real inference |
| RCA accuracy | Measured but **not meaningful** — the prompt contains the answer key |
| P(heal \| wrong diagnosis) | **Uncomputable** — no wrong diagnoses occurred |
| LLM vs rules baseline | **Unavailable** — P3's mapping no longer exists; `detect` survives for F01 only |
| Human baseline | **Not run** |
| F02–F09 behaviour | Simulated state; verification derived from thresholds, not measured |
