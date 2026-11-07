# Experiment: does the bounded frame saturate Evidence Closure?

**Status: designed 2026-11-07, NOT RUN.** This is a pre-registration. The
predictions in §6 and the refutation conditions in §7 are written before any
data exists, and must not be edited after the first run — if they turn out to
be wrong, that is the result.

---

## 1. The question

`REPORT_DRAFT.md` §4.4a reports that Evidence Closure, measured on the class
the deterministic detector named, is **37/37 = 1.00** in the shipped
configuration. Cloud-OpsBench (arXiv 2603.00468) reports **0.38** on the same
idea and concludes that final-answer correctness substantially overestimates
evidence-grounded diagnosis.

The report currently explains our 1.00 as an architectural effect: the model
is handed a bounded frame built by a deterministic extractor, so the
discriminating evidence is already in front of it and citing it is nearly
free.

**That explanation is an observation, not a result.** Nothing has varied the
frame and watched closure move. A reviewer is entitled to the alternative
reading — that our model is simply better grounded — and we cannot currently
refuse it.

## 2. What the frame actually does, which is three things at once

Read `rca/evidence.py`: each item renders as

```
EV-M01 [metric] retrieval_top_similarity_p50 = 0.658  (healthy: >= 0.50 …)  — note
```

So the frame simultaneously provides:

1. **Curation** — only signals some detector uses are present, ~14 items.
2. **Labelling** — a short stable ID per item, which makes citation a copy.
3. **Interpretation** — an `expected` field stating what healthy looks like,
   so "is this abnormal?" is answered *before* the model reads it.

Any of the three could produce saturation, and the report currently credits
only the first. **The experiment must separate them or it proves nothing
about why.**

## 3. Arms

One frame is collected per incident and every arm is **derived from that same
frame object**, so detection, timing, target state and the underlying
readings are identical across arms by construction. This is a **paired,
within-incident design**: each incident contributes one observation per arm.

| arm | curated | labelled | interpreted | items |
|---|---|---|---|---|
| **A** control — the shipped frame | yes | yes | yes | k ≈ 14 |
| **B** noise, size-matched | **no** | yes | yes | k |
| **C** noise, unbounded | **no** | yes | yes | ~2k |
| **D** no expectations | yes | yes | **no** | k |

**Arm B is the primary comparison**, because it is the only one that changes
signal density *without* changing frame size. Construction: keep every
discriminating item for the detector's class (otherwise closure is trivially
0 and the arm measures nothing), then replace non-discriminating items with
distractors until the item count equals A's.

**Arm C** is the realistic case — a frame that was never pruned — and is
reported because it is what an unbounded system actually faces. It is *not*
the primary comparison, because it confounds density with length.

**Arm D** strips the `expected` field only. If closure survives A→B intact
but drops in D, the cause is interpretation rather than curation, and the
report's current wording is wrong in an interesting way.

### Distractors must be real

Distractors are **real metrics the target already exports that no detector
reads** — `python_gc_collections_total`, `process_resident_memory_bytes`,
`http_request_duration_seconds` by handler, `ragapp_llm_duration_seconds`
for `operation="embedding"`, and so on. Pulled live from the target's
`/metrics`, formatted identically, given IDs in the same scheme.

Synthetic or obviously-fake noise would be rejected by a reviewer and would
deserve to be: a model ignoring `EV-X99 [metric] foo_bar = 1.0` tells us
nothing about an operator's real telemetry.

### IDs may be renumbered, and this is safe

Checked before designing: `evidence_closure.py` resolves discriminating
signals **by name**, through `id_for_name()`, not by literal ID. So arms may
renumber and shuffle freely as long as the closure map is recomputed
per-arm from names. Render order is **shuffled with a per-incident seed** in
every arm, including A, so position effects cannot differ between arms.

## 4. Measurement

**Primary outcome, per diagnosis, binary:** did the diagnosis cite at least
one evidence item that discriminates **the deterministic detector's class**?
This is the quantity reported as 37/37, and the one claimed to be saturated.

**Secondary outcomes:** closure on the class the model *named*; whether the
model's class matched the detector's; number of items cited; number of cited
IDs that resolve to nothing (`validate.py` already rejects these, and under
noise they should appear).

**Not measured, deliberately:** whether a repair executed. No arm executes
anything. The experiment calls `collect()` and `diagnose()` directly, the way
`harness/rca_f08_live.py` already does, and never reaches `permit()`.

## 5. Sample size and sampling

- **Fault classes:** all four, so a single class cannot carry the result.
- **Incidents:** ≥ 15 per class = 60 incidents, each yielding 4 observations
  (one per arm) = 240 diagnoses. The current closure analysis rests on 37.
- **Repetitions:** 3 samples per (incident, arm) at the shipped temperature,
  because a single sample cannot distinguish an arm effect from sampling
  noise. Fix the seed where the provider supports it and record whether it
  did.
- **Test:** McNemar's test on the paired binary outcome, A vs B. Report the
  exact counts in the 2×2, not only the p-value, and bootstrap CIs on each
  arm's rate.

## 6. Predictions, fixed in advance

1. **Arm A closure ≈ 1.00.** Replicating 37/37 at a larger n. If A is not
   near-saturated, the finding this experiment exists to explain does not
   exist and everything below is moot.
2. **Arm B closure < Arm A, materially** — the pre-registered threshold is a
   drop of **≥ 0.15 absolute**, significant by McNemar at α = 0.05.
3. **Arm C ≤ Arm B.** More noise, no better.
4. **Arm D:** no directional prediction. This arm is exploratory and is
   labelled as such.
5. **Accuracy will fall in B and C**, and this is *not* the finding — it is
   expected and uninteresting. The claim is about the **metric's blindness**,
   not about the model getting worse.

## 7. What would refute the hypothesis

Stated because an experiment that cannot fail is the defect this project has
already found in itself once.

- **Arm B closure stays ≈ 1.00.** Then curation is not what saturates the
  metric, and the report's §4.4a explanation is wrong and must be rewritten.
  Arm D becomes the lead.
- **Arm B accuracy collapses while closure holds.** Then the model is citing
  correctly and reasoning worse, which would be a *different* and arguably
  more interesting paper — but not this one, and the claim must change.
- **A and B differ but C ≈ A.** Incoherent ordering; suspect the distractor
  construction and re-examine before publishing anything.
- **Within-cell variance across the 3 repetitions exceeds the A→B gap.** The
  effect is sampling noise. Report it as such.

## 8. Implementation constraints

- **Do not edit `rca/evidence.py`.** `AGENTS.md` forbids changing the code
  every published number was measured with, and an ablation that mutates the
  measured path invalidates the control arm. The arms are built by
  transforming the returned `EvidenceFrame` object inside a new harness
  script, `harness/closure_ablation.py`.
- **Reuse `evidence_closure.py`'s `DISCRIMINATING` map and `id_for_name()`**
  rather than restating them, for the reason that file already gives: a
  copied lookup table that drifts is how `RCA accuracy` once read the wrong
  field.
- **Record the token count of every frame**, per arm. If Arm C exceeds the
  model's context the result is a context-length artifact and must be
  reported as one. This is the single most likely way to get a wrong answer.
- **Assert the arm is valid before using it**: every arm must contain the
  detector-class discriminating items, and B must match A's item count
  exactly. An arm that fails its assertion is dropped and counted, never
  silently repaired — the dose-sweep failure of 2026-11-02 happened because
  an arm was used without checking it was the arm intended.

## 9. What it would let the paper claim

With prediction 2 confirmed:

> Evidence Closure, introduced to detect ungrounded LLM diagnoses, is
> **saturated by the bounded-frame architecture the field has converged on**.
> Holding frame size, model, incident and detector verdict constant and
> varying only signal density, closure falls from X to Y (McNemar p = …).
> The metric therefore cannot discriminate among systems built this way, and
> a high closure score under a curated frame is not evidence of grounded
> reasoning. The residual failures in such systems are **grounded and wrong**
> — the model cites the correct evidence and draws the wrong conclusion —
> which no grounding metric detects and which is why an independent
> deterministic cross-check is load-bearing rather than redundant.

That is a claim about the field's measurement apparatus, supported by a
controlled experiment, and it does not depend on Kavach being novel.

**Without prediction 2**, the honest paper is smaller and still real: three
uncertainty channels tested and found not to separate, with the saturation
reported as an observation whose cause is unresolved.
