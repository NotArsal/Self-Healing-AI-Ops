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

---

## 10. Pacing run, 2026-11-07 — prediction 2 is refuted

**Not a result, and the numbers below must not be quoted as one.** 7 usable
incidents (8 attempted, 1 dropped), 21 observations per arm, against the ≥60
incidents §5 asks for. It is recorded here, immediately and before the full
run, because **the pre-registered primary prediction failed** and §7 says
that is the result rather than an invitation to re-read it.

Artifact: `harness/reports/closure-ablation-pacing.json`.
Wall clock: **17 minutes for 7 incidents**, so the full run is ≈2.4 hours.

| arm | closure (detector) | 95% CI | agreement | grounded-and-wrong | items | tokens |
|---|---|---|---|---|---|---|
| A control | **1.00** | [1.00, 1.00] | 18/21 | 3/21 | 32 | 3622 |
| B size-matched noise | **1.00** | [1.00, 1.00] | **9/21** | **12/21** | 32 | 3248 |
| C unbounded noise | 0.57 | [0.14, 0.86] | 12/21 | 0/21 | 83 | 5022 |
| D no expectations | 0.86 | [0.57, 1.00] | 12/21 | 6/21 | 32 | 3257 |

McNemar, paired, exact: **A vs B drop +0.00, p = 1.0000, zero discordant
pairs.** A vs C drop +0.43, p = 0.0039. A vs D drop +0.14, p = 0.2500.
Within-cell spread across repetitions: 0.00.

### What is refuted

**Prediction 2 fails completely.** Arm B holds 32 items of which roughly 27
are distractors — 84% noise — and closure stayed at 21/21 with *not one*
discordant pair. **Curation is not what saturates Evidence Closure**, and
§4.4a's explanation, which credits exactly that, is wrong as written.

### What the data says instead, stated cautiously

**Closure appears to depend on frame LENGTH, not on signal density.** Holding
size constant and destroying the signal-to-noise ratio (B) changed nothing;
making the frame longer (C, 83 items, 5022 tokens) dropped it to 0.57 at
p = 0.0039. Size and token count covary perfectly here, so this cannot yet
distinguish "too many items to scan" from "context-length degradation" —
which §8 warned would be the likeliest way to get a wrong answer, and is.

### The finding that is stronger than the hypothesis it replaces

**In arm B the model cited the correct discriminating evidence in 21 of 21
cases while naming the wrong fault class in 12 of them.** Agreement halved,
18/21 → 9/21, with closure untouched.

That is *grounded and wrong* demonstrated directly rather than inferred from
a saturated metric: the discriminating evidence was present, the model cited
it, and it still reached another conclusion. It is the same claim §4.4a
wanted to make, reached by a route that does not depend on the saturation
argument that just failed.

> **CORRECTED 2026-11-08, see §13.1.** Of arm B's 12 wrong answers, **9 were
> `UNKNOWN`** — the model declined to conclude rather than concluding wrongly.
> Across all runs arm B produced **63 abstentions and 3 confident wrong
> classes**. The paragraph above is left as written because it is a dated
> record, but *grounded and wrong* is not what arm B shows; §13.2 relocates
> that finding to the control arm, where it is stronger.

Per class, agreement: F06 is unshakeable (6/6 in every arm); **F01 collapses
from 6/6 to 0/6 under arm B**; F07 was already weak (3/6) and goes to 0/6;
F08 holds under B but fails under C and D.

### A design gap this run exposed, to fix before the full run

**Arm B does two things at once.** Size-matching is achieved by *replacing*
non-discriminating real items with distractors, so B both **adds noise and
removes real signal**. A model getting the class wrong in B may be suffering
from the removal rather than the noise, and this design cannot separate them.

That needs a fifth arm:

> **Arm E — same real items removed as in B, replaced with nothing.**
> Shorter than A, no distractors. If E behaves like B, removal explains it;
> if E behaves like A, noise does.

Without E, the arm-B accuracy result above is suggestive and not attributable.
**The full run should not be launched until E exists**, because re-running
2.4 hours is cheap and re-interpreting an unattributable result is not.

---

## 11. Arm E, pre-registered 2026-11-07 before any five-arm run

Added because §10 found that **arm B removes and adds at once**: it reaches
size-matching by replacing non-discriminating real items with distractors,
so B's accuracy collapse (18/21 → 9/21) could be the removal rather than the
noise and the four-arm design cannot say which.

> **Arm E — the same real items B keeps, and nothing added.**
> `keep + protected`, no distractors. Shortest frame of all arms.

### What the three comparisons now separate

| comparison | holds constant | isolates |
|---|---|---|
| **B vs E** | the real signals present | **noise, alone** |
| **A vs E** | absence of noise | **removal, alone** |
| A vs B | frame size | the two combined, as before |

E is constructed from the same `keep + protected` lists as B, in the same
branch, so the two cannot drift apart about what counts as protected. A
validity check refuses an E that is not shorter than the control, or that
contains any item absent from the real frame.

### Predictions, fixed before the run

1. **E2 is the decisive one.** Compare E's *agreement* to A's and to B's:
   - E within 0.10 of **A** → the arm-B collapse is **noise**.
   - E within 0.10 of **B** → the arm-B collapse is **removal**, and B's
     headline result in §10 is not about distractors at all.
   - Between the two → both contribute, and neither may be claimed alone.
2. **E tests §10's length story in the opposite direction.** §10 suggested
   closure falls with frame *length*, from arm C. E is the **shortest** frame
   of all five. If length is what matters, E's closure should be **at or
   above A's**. If E's closure instead *falls*, the length account is wrong
   and what matters is having enough real context, not having little of it.
3. No prediction on E's closure-on-named-class. In E the non-detector
   classes' discriminating evidence has been removed, so that figure is
   partly mechanical and is reported, never scored — the same caveat that
   applies to B.

### What would make E uninterpretable

If E's frame is so short that the model refuses or returns
`INSUFFICIENT_EVIDENCE` in most cases, E measures "too little evidence to
answer" rather than removal, and the comparison dies. The n=1 check gave 5
items, 2433 tokens, and a correct diagnosis, so this is a real risk rather
than a certainty — it must be read off the run and not assumed away.

---

## 12. Five-arm pacing run, 2026-11-07 — E2 is answered

**Still not a result.** The run **aborted after twelve minutes** on a
transient Ollama HTTP 500; the fail-fast fired and the fault was reverted,
target confirmed clean. 68 of 69 diagnoses usable, arms unbalanced because
the abort landed mid-incident. Artifact:
`harness/reports/closure-ablation-pacing-5arm.json`.

Arms must therefore be compared **on the cells where all of them exist**, not
on their own totals — the per-arm totals below come from different subsets
and comparing those would be the pooling error this project has already
caught itself making once.

### On the identical 12 cells (F01 and F06, 2 incidents, 3 reps)

| arm | agreement | closure (detector) |
|---|---|---|
| A control | **12/12 = 1.00** | 12/12 = 1.00 |
| B noise added | **6/12 = 0.50** | 12/12 = 1.00 |
| E items removed, nothing added | **12/12 = 1.00** | 12/12 = 1.00 |

### E2: the collapse is the noise, not the removal

Removing the non-discriminating real items changed agreement by **0.00**.
Replacing those same items with distractors **halved it**. Per §11's rule, E
sits on A, not between A and B, so **the arm-B accuracy collapse is
attributable to the distractors** and §10's result is about noise after all.
The four-arm design could not have said this.

**Closure stayed at 1.00 in all three arms.** A frame that is 84% distractors
still gets the discriminating evidence cited every time, while the model
reaches the wrong conclusion in half of them. *Grounded and wrong*, now with
the cause isolated.

The whole collapse is **F01**: 6/6 → 0/6 under noise. **F06 is 6/6 in every
arm.** One class is destroyed by distractors and another is untouched, which
is a finding in itself and needs the full run to confirm.

### E3: the length account survives, weakly

E is the shortest frame of the five — 5 items, 2432 tokens against the
control's 32 and 3604 — and its closure is 1.00, at A's level. So short
frames do not lose closure, and only the long arm C does (0.57, p = 0.0312).
Consistent with length, though C still confounds length with item count.

### What moved between the two pacing runs, and why nothing may be read into it

Arm D closed at **0.86** in the four-arm run and **1.00** here, on 12
observations against 21. That is a swing of the size the whole experiment is
trying to detect, produced by nothing but sampling. It is the clearest
possible argument for the ≥60 incidents §5 asks for, and the clearest
possible warning against quoting any number on this page.

### Fixed before the full run

A transient HTTP 500 killed a run whose injections had already been paid
for. Transient failures (5xx, timeouts) now retry the same cell after a
pause, up to eight per incident; only a fatal error — a model that does not
exist, a 401, a 403 — still aborts. A model that answered a moment ago and
then 500s is weather, not a verdict.

---

## 13. Partial full run, 2026-11-08 — §10's headline claim is wrong

The full run was **killed by the host after 15 of 60 incidents**, when Claude
Code reaped the background shell under system memory pressure. That is not a
failure of the run: no retries fired, no incidents dropped, no errors logged.
It died between classes, so **F01 is complete** (15 incidents x 5 arms x 3
reps = 225 observations) and F06/F07/F08 never started. No JSON artifact was
written — the harness serialises at the end — so the figures below are parsed
from the run log, which carries `named`, `closed(det)`, `cited` and `tokens`
per observation but not the per-item frames.

**The kill stranded an injected fault.** F06 was active with
`rerank_threshold=0.999` when the process was SIGKILLed, so the `finally`
revert never ran. Reverted manually; target back to `config_hash
de4cfaed14a8bb98`, all four faults clear. **A fail-closed revert cannot
survive SIGKILL, and nothing in this harness notices a fault left behind** —
that belongs in the risk register, not in a footnote.

### 13.1 The correction: arm B abstains, it does not err

§10 claims arm B shows the model "naming the wrong fault class in 12 of
them", and reads that as *grounded and wrong*. **Checked against the stored
`named` values, that is wrong as written.**

| artifact | arm B wrong | of which abstained (`UNKNOWN`) | confident wrong class |
|---|---|---|---|
| pacing (§10) | 12 | **9** | 3 — F01 named F02 at conf 0.80 |
| five-arm pacing (§12) | 9 | **9** | 0 |
| this partial run, F01 | 45 | **45** | 0 |
| **total** | **66** | **63** | **3** |

Under size-matched noise the model cites the discriminating evidence and then
**declines to conclude**. It is not reaching a confident wrong answer; it is
refusing to answer. In Kavach an `UNKNOWN` diagnosis **never executes**
(`docs/AGENTS.md`), so arm B is the *safe* degradation, not the dangerous
one. §10's framing inverts the safety reading of its own data.

The surviving, weaker claim from arm B: **closure stays at 1.00 while
usable accuracy goes to zero**, so Evidence Closure cannot stand alone as a
quality metric. That holds. "Grounded and wrong" does not follow from it.

### 13.2 The real grounded-and-wrong is in the control arm

Separating abstentions from confident errors moves the finding to a different
arm — and makes it stronger:

| arm | confident wrong class | confidence | pattern |
|---|---|---|---|
| **A control** | 3/21 | **0.95** | F07 named F06 |
| C unbounded | 9/21 and 6/15 | **0.95** | F07, F08, F06 named as each other |
| D no expectations | 9/21 | **0.95** | F07, F08 named F06 |
| B noise | 3/66 | 0.80 | F01 named F02 |

**In the control arm — the real bounded frame, as shipped, with no noise
added — F07 is diagnosed as F06 at 0.95 confidence while Evidence Closure
reads 1.00.** The discriminating evidence is present, cited, and the
conclusion is confidently wrong. That is the claim §4.4a wanted, it needs no
ablation arm to make it, and unlike arm B's abstention **it is the failure
mode that would execute a repair**: a confident F06 verdict routes to the
retrieval repair, not to a human.

This also reverses which arms look dangerous. B degrades to silence; A, C and
D degrade to confident error. A metric that rewards A and punishes B has the
safety ordering backwards.

### 13.3 Why "45/45" and "p = 0.0001" must not be quoted

The log gives arm B 0/45 agreement against A's 45/45, exact McNemar
p = 0.0001 on 15 incident-level pairs. **That number is an artefact of
repeated injection, not of 15 independent trials.** Distinct observable
outcomes across all 15 F01 incidents and 3 reps:

| arm | distinct `(named, cited, tokens)` of 45 obs |
|---|---|
| A | 4 — and 39 of 45 identical |
| B | **1** |
| C | 4 |
| D | 3 |
| E | **1** |

Injecting F01 fifteen times on an idle target regenerates nearly the same
evidence frame, and the model is near-deterministic at this temperature (the
three reps differed at all in 11 of 75 cells, never in the named class — only
in token and citation counts). The effective n for F01 is **close to 1, not
45 or 15**. Repetition here measures reproducibility, which is total, and
buys no statistical power at all.

Fixing this needs incident **diversity** — concurrent load, warm versus cold
corpus, overlapping faults — not more repetitions of an identical one. Until
then F01's five-arm comparison is a demonstration, not an estimate, and §5's
"60 incidents" is the wrong unit of cost.

### 13.4 What stands, after all three pacing runs and this partial

> **SUPERSEDED 2026-11-10 by §21. Items 2, 3 and 5 are the arm-B claims and
> they come off this list.** All five were measured on F01 and F06 only, on
> partial runs. With F07 and F08 included and three full runs on the board:
> **item 2 is refuted** — size-matched noise does move closure (+0.21, +0.19
> under the shipped configuration; §21.2), so "insensitive to signal density"
> was an artefact of the two classes the model never confuses. **Item 5 is
> incomplete rather than wrong** — F06 is immune on every run, but F07 turns
> out to be the control arm's own failure (§19.4, §21.3), which this list
> could not see. **Item 3 holds** and is the only arm-B claim that does:
> arm E sits on arm A, 171/171, on all three full runs.
>
> **Items 1 and 4 are untouched** — prediction 2 is still refuted, and closure
> 1.00 still coexists with a confidently wrong diagnosis in the control arm.
> Item 4 is now the strongest claim in the whole experiment: 30 confident
> wrong diagnoses in arm A on this run, every one of them citing the right
> evidence.

1. **Prediction 2 is refuted** (§10), unchanged.
2. **Closure is insensitive to signal density and sensitive to frame length**
   — B at 84% noise holds 1.00, C at 83 items drops to 0.57, p = 0.0039.
3. **E sits on A, not between A and B** (§12), so arm B's behaviour is caused
   by the distractors, not by the removal. Confirmed again here: E is 45/45
   on F01 where B is 0/45.
4. **Closure 1.00 coexists with a confidently wrong diagnosis in the control
   arm.** New, and the most defensible claim of the four.
5. **F06 is immune and F01 is destroyed under noise** — still only two
   classes, and the partial run adds nothing about F07 or F08.

Nothing here needs the remaining 45 incidents to be *true*; items 2, 3 and 5
need them to be *general*.

---

## 14. The treatment was applied n=1, found 2026-11-08 by accident

Found while verifying the dirty-target guard of §15, not by looking for it. A
one-incident run on a target whose metric set had grown from 52 scraped
distractors to 53 gave, on **the same fault, the same model, the same arm**:

| run | distractors scraped | arm B on F01 |
|---|---|---|
| partial full run (§13) | 52 | `UNKNOWN`, 45/45, every incident |
| guard verification | 53 | **`F01` correct**, cited 2, 3171 tokens |

Token counts 3163 against 3171 — the frames are the same size. **One extra
distractor flipped arm B from total collapse to a correct diagnosis.**

### Why, and why it invalidates the strength of the arm-B claim

`scrape_distractors` is called **once per run**, and arm B takes a
deterministic **prefix** of that list (`distractors[:room]`). Verified: two
successive draws return the same names in the same order, and no `rng` touches
the selection. So within a run, every incident and every repetition in arm B
received the **identical 27 distractors**.

The experiment therefore varied:

- **repetitions** — which measure nothing at this temperature (§13.3: the
  three reps differed at all in 11 of 75 cells, never in the named class);
- **incidents** — which barely vary, because re-injecting one fault on an idle
  target regenerates nearly the same frame (§13.3: 1 distinct outcome in 45
  for arms B and E);

while holding **constant the one variable it claims causes the effect.** Arm
B's treatment has an effective n of **one draw per run**. Three draws exist
across the whole project, and they do not agree about the direction.

**So "F01 collapses from 6/6 to 0/6 under noise" (§10) and "0/45" (§13) are
one observation each, not 6 and 45.** The effect may well be real — two of
three draws broke F01 completely and deterministically — but its size is
unestimated and its sign is not established. Closure's insensitivity to noise
(1.00 in arm B under every draw) is **unaffected**: that held across all three
draws and is the claim §13.4 keeps.

### The fix, pre-registered before any run uses it

> The distractor list is shuffled **per incident**, on its own RNG stream
> seeded `draw-{class}-{incident}`, so the draw varies with the cluster unit
> the bootstrap already resamples. Every arm and every repetition within one
> incident still shares one draw, so repetitions keep measuring only model
> nondeterminism. `--shuffle` is untouched: separate stream.
>
> Each observation now records `draw`, the 8-character SHA-256 of its draw's
> names in order, so the analysis can ask whether an arm's outcome tracks the
> **draw** rather than the **arm**.

### Predictions, fixed before the next run

1. **Arm B's agreement on F01 will be intermediate, not 0/45 and not 45/45.**
   If it is again all-or-nothing across 15 independently drawn distractor
   sets, the draw does not matter after all and §13's determinism is a
   property of F01 rather than of the sampling. That would refute this
   section, and it is the cheapest way to find out.
2. **Closure stays at 1.00 in arm B under every draw.** It did under all three
   accidental draws. If it now moves, closure is draw-sensitive too and *no*
   arm-B claim survives.
3. **No prediction on arms A, C, D, E for F01.** A and E contain no
   distractors; C contains all of them in a fixed order and is unaffected by a
   reordering. Only B samples a subset, so only B can move. If A or E moves,
   something other than the draw changed and the run is not comparable.

### What this says about the experiment's cost model

§5 prices the run in incidents. On this evidence **incidents are the wrong
unit** — 15 repetitions of one fault against one draw buy almost no
information, and the three accidental draws were worth more than the 225
observations they came from. The next run's budget should buy **draws and
fault classes**, not repetitions: reps to 1, and the hours spent on reps 2
and 3 spent on F07 and F08 instead.

---

## 15. Fixed on 2026-11-08

> **NOTE 2026-11-10:** this section's named top open item — an unbuilt
> heartbeat watchdog, because "a revert cannot survive a kill" — was written
> before the dirty-target guard below existed and was not revisited after.
> The guard makes a stranded fault a loud refusal costing one command rather
> than a silent run on a contaminated target. `decisions/0022` argues the
> watchdog should therefore **not** be built, and records what would have to
> be decided if it were.

**A killed run leaves its fault injected, and nothing noticed.** The host
reaped the full run mid-F06; `one_incident`'s `finally` cannot run under
SIGKILL, so F06 stayed active at `rerank_threshold=0.999` until it was found
by hand. It then happened a **second time the same day**, when a verification
run was cut by its own timeout and stranded F01. Twice in one session, from
two unrelated causes — this is the normal consequence of any abnormal
termination, not an unlucky edge case.

> The harness now refuses to start when any of F01, F06, F07 or F08 is already
> active, and says `inject.py revert --all` clears it.

Ordering matters and was got wrong on the first attempt. The check was first
placed after the fast-set gate — but **an injected fault also fails the fast
set**, so on a dirty target the operator would have been told to *warm the
target*, which is the same species of misleading remedy as the preflight
defect fixed on 2026-11-03. The guard now runs before both the LLM probe and
the fast set, because it is read-only and the most specific. Verified both
ways: with F06 injected it refuses and injects nothing; with the target clean
it is silent and the run proceeds.

**An abstention was being counted as an error.** The analysis had no notion of
the difference, which is how §10 came to read 9 `UNKNOWN`s as the model
"naming the wrong fault class". `closure_ablation_report.py` now prints, per
arm, correct / abstained / confidently wrong with the mean confidence of the
confident errors — the split that §13.1 corrects by hand, computed from the
artifact so it cannot be missed again. Re-run against the stored pacing
artifact it reproduces §13.1's table exactly, which is the cross-check that
the parsing in §13 was right.

**Not fixed, and now the top open item:** the deterministic revert cannot
survive a kill. A guard that refuses the *next* run is a backstop, not a fix —
between the kill and the next run the target sits broken with nothing
reporting it. A watchdog that reverts on a missing heartbeat is the real
answer and is not built.

---

## 16. Cross-provider extension, pre-registered 2026-11-09

Everything measured so far is `qwen2.5:7b-instruct` on one local Ollama. A
reviewer's first question is whether any of it survives a larger model, and
the project has carried a seven-provider registry since 2026-10-19 without
ever using it for a measurement. This section fixes what will be run, and
what would count as a refutation, **before** the first cloud call.

### 16.1 Prediction read-off for F01, and what I had already seen

Honesty about the order of events, because it decides what may be called
pre-registered: at **22:30 on 2026-11-09** I read the in-flight artifact of
the third full run and saw F01's arm-B figures. F01 was complete at that
point (15 incidents, 225 observations), so these are final numbers, but I
had seen them before writing this section. Nothing below about F01 is
pre-registered. F06 was 11 incidents in; F07 and F08 had not started.

§14's three predictions, against the completed F01 block:

| § | Prediction | Observed (F01, 15 incidents x 3 reps) | Verdict |
|---|---|---|---|
| 14.1 | arm B agreement intermediate, not 0/45 or 45/45 | **18/45 = 0.40** | confirmed |
| 14.2 | arm B closure stays at 1.00 under every draw | **36/45 = 0.80** | **violated** |
| 14.3 | A, C, D, E do not move on F01 | 45/45 agreement and closure, all four | held |

### 16.2 Prediction 2 is violated substantively, and the threshold defect does not rescue it

I recorded on 2026-11-08 that prediction 2 was badly specified — it said "if
it now moves" and named no magnitude, so a single observation in 45 would
trip a condition written to catch a real effect. That defect is real and the
wording is corrected below. **It does not apply here.** The salvaged run's
44/45 was the one-observation case the defect describes. 36/45 is nine
observations and a 20-point drop. Arm B's closure is draw-sensitive, and the
pre-registration's own consequence stands as written: no claim that arm B
preserves closure survives.

What this costs elsewhere in the project: §13.4 and `REPORT_DRAFT` §4.4a both
rest on closure being saturated by frame *length* — arm B matched the control's
item count, so a length account predicted it would keep closing. It did not.
Either length is not sufficient, or closure is sensitive to *which* items fill
the budget, which is the curation account §4.4a was corrected away from. I am
not rewriting either section until F06, F07 and F08 are in; one fault class is
not grounds for a third reversal.

**Corrected threshold, binding on F07 and F08 of the current run (not yet
produced) and on every run after it.** Arm B's closure is called unchanged if
it is **>= 0.95** within a fault class, moved if **<= 0.90**, and the band
between is reported as inconclusive rather than argued either way. Chosen
because the three accidental draws and the salvaged run all sat at 0.98-1.00,
so 0.95 is one bad observation in 45 and 0.90 is five.

### 16.3 What the cross-provider run is, and what it is not

**Model substituted 2026-11-09 23:43, before any usable call.** The
pre-registered `llama-3.3-70b-versatile` **no longer exists**: the probe got
HTTP 404 "does not exist or you do not have access to it" and refused with
nothing injected. `GET /v1/models` returned 11 ids, no Llama chat model among
them. Groq decommissions models, so the registry's default was stale and is
now `openai/gpt-oss-120b` with the dated catalogue in its note. The run uses
**`openai/gpt-oss-120b`** - the largest chat model the key can reach, which is
also the harder test of the structured-output path. It is a different family
from the measured `qwen2.5:7b-instruct`, so a difference cannot be attributed
to scale alone; `qwen/qwen3.8-27b` is the scale-matched alternative on the
same key and the choice for the quotable run is still open.

**Provider (pre-registered, now unobtainable):** `groq`,
`llama-3.3-70b-versatile`. Chosen because it is the key
that exists and because 70B open-weight sits between the measured 7B and a
frontier model — a difference that is attributable to scale rather than to
also changing vendor, tokenizer and training corpus at once.

**Arms A and B only.** Arms A, C, D and E are at 45/45 on both measures on the
7B model. A larger model cannot score above 1.00, so those cells carry no
information; ~85% of a five-arm cloud replication would measure a ceiling. The
unsaturated question is arm B.

**Amended 2026-11-09 23:45, after the local run completed and before any
cloud call: arms A, B and E.** The local run's result moved the interesting
comparison. Arm E - the shipped frame with its non-discriminating,
non-service, non-baseline items removed - names F07 correctly 13/13 incidents
where the control arm manages 3/13, and it is at least as good as the control
on every class. A cross-provider check that omitted E would test the arm that
turned out not to carry the effect. This widening is recorded here rather than
applied silently, and it changes no prediction below: the smoke test's numbers
may not be quoted either way.

**Smoke test first:** 4 classes x 5 incidents x 1 rep x 3 arms = 60 calls, to
prove the key, the structured-output path and the rate limit before spending
the real run. Its numbers are for plumbing only and **may not be quoted** —
5 incidents at 1 rep cannot separate a model difference from the draw.

### Predictions, fixed before the first cloud call

1. **Arm A stays at or near 1.00 on all four classes.** The control frame is
   curated and small; if a 70B model cannot close it, the frame is broken
   rather than the model weak, and the run is a harness failure, not a result.
2. **Arm B's agreement rises above the 7B model's 0.40 on F01.** This is the
   claim being tested. If it does not rise, noise sensitivity is not a
   small-model artefact and the §13 story holds across scale.
3. **Arm B's closure moves less than the 7B model's 0.80.** Scored against
   16.2's band: >= 0.95 means closure sensitivity *was* a 7B artefact.
4. **No prediction on F07 or F08 in either model.** Both are unmeasured at
   the time of writing; a prediction made after reading the local run's F07
   block would not be one.
5. **A cloud result that is worse than the local one is a result, not a
   configuration error.** The failure mode this guards against is retrying a
   bad cloud number with a different model until it improves. Provider and
   model are recorded in the artifact's `model` field as `provider:model` for
   exactly this reason, and every attempt is reported.

### Harness changes this required

- `--model`, because `.env` holds an Ollama tag and `KAVACH_LLM_MODEL` is
  read by the local runs too; a cross-provider run must not edit it.
- `--arms`, which refuses any selection without A (every other arm is
  validated against the control's item count) and refuses unknown letters.
  Both refusals fire before the LLM probe, the fast set and any injection.
- The artifact's `model` field is now `provider:model`. Earlier artifacts
  carry a bare model tag and were all `ollama`.

### Not negotiable

No test may require a cloud key (`PL-02`). These runs stay in `harness/`,
opt-in, never in `make check`. The cloud providers remain explicitly selected
with no fallback to Ollama, so a quota failure must stop a run rather than
quietly re-measure the local model.

---

## 17. Full four-class run, 2026-11-09 — the primary hypothesis failed and arm E beat the control

First run to reach all four fault classes with per-incident draws (§14's fix).
840 observations, 56 usable incidents, 0 model errors, target verified clean
afterwards. Four incidents were dropped by the pre-registered rule — the
detector returned `INSUFFICIENT_EVIDENCE` rather than the injected class, so
every arm would have measured agreement with the wrong answer (F07#11, F07#14,
F08#4, F08#8).

Artifact: `harness/reports/closure-ablation-full.json`,
model `qwen2.5:7b-instruct`, shuffle off.

### 17.1 The pre-registered verdict: NOT MET

| arm | label | closure (detector) | 95% cluster CI | vs A (McNemar) |
|---|---|---|---|---|
| A | control, shipped frame | **0.99** | [0.96, 1.00] | — |
| B | size-matched noise (PRIMARY) | **0.90** | [0.82, 0.97] | drop +0.09, b=6 c=1, **p=0.125** |
| C | unbounded noise | **0.54** | [0.41, 0.66] | drop +0.45, b=26 c=1, p<0.0001 |
| D | expectations stripped | **0.77** | [0.64, 0.88] | drop +0.22, b=13 c=1, p=0.0018 |
| E | same items removed as B, nothing added | **1.00** | [1.00, 1.00] | drop −0.01, b=0 c=1, p=1.00 |

> **CORRECTED 2026-11-10 00:20 — the p-values above are not the ones this
> section was first written with.** `closure_ablation_report.py` paired
> McNemar **per diagnosis**, so 168 outcomes were treated as independent when
> reps of one incident share a frame and a draw and the measured within-cell
> spread is 0.01. `cluster_bootstrap` had always resampled incidents; the
> McNemar beside it had not, and the two disagreed about what an observation
> was. Pairing on the incident, as the bootstrap does, the first figures
> become: A vs B p **0.0007 -> 0.125**, A vs D p **0.0000 -> 0.0018**, A vs C
> unchanged at p<0.0001, A vs E unchanged in conclusion. Majority, `all` and
> `any` aggregation give identical b and c on this run, so the rule does not
> matter here. The table now carries the clustered values; the superseded ones
> are named above so anything quoting them can be found. The script is fixed,
> not worked around, and the fix makes every test more conservative.

Within-cell spread across repetitions: 0.01. Reps are nearly deterministic, so
the incident is the unit and reps buy almost nothing — §14's cost-model note
is confirmed a second time.

**Prediction 2 required arm B to drop >= 0.15 with p < 0.05. The drop is
+0.09 at p = 0.125.** It fails both halves of the condition — it is neither
large enough nor significant once the incident is the unit. Per §7 this does
not become a smaller claim by re-reading it: the size-matched-noise
hypothesis, which has been the experiment's primary hypothesis since §5,
**failed**. `REPORT_DRAFT`
§4.4a's explanation goes with it.

What survives, and is larger than the failed effect: **unbounded noise (C,
−0.45) and stripped expectations (D, −0.22)**. Evidence volume and stated
expectations matter. Matching the control's item count with noise does not.

### 17.2 Arm E is perfect, and the control is not

| arm | correct | abstained | confident wrong | mean conf of the wrong |
|---|---|---|---|---|
| A | 136/168 | 0 | **32** | 0.95 |
| B | 78/168 | 70 | 20 | 0.78 |
| C | 87/168 | 0 | 81 | 0.95 |
| D | 90/168 | 0 | 78 | 0.95 |
| E | **168/168** | 0 | **0** | — |

Per class, class-naming agreement:

| class | A | B | C | D | E |
|---|---|---|---|---|---|
| F01 | 45/45 | 18/45 | 45/45 | 45/45 | 45/45 |
| F06 | 43/45 | 45/45 | 42/45 | 45/45 | 45/45 |
| F07 | **9/39** | 3/39 | 0/39 | 0/39 | **39/39** |
| F08 | 39/39 | 12/39 | 0/39 | 0/39 | 39/39 |

**The control arm names F07 correctly in 3 of 13 incidents. Arm E names it in
13 of 13.** Clustered on the incident, exact McNemar b=10, c=0, p=0.00195. No
incident split across its reps, in either arm.

Arm A's 32 confident errors are 30 F07→F06 at 0.95 and 2 F06→F07 at 0.95.
This is the §13.2 signature at scale: **the grounded-and-wrong failures live
in the control arm**, and they are the arm that would execute a repair.

Closure and correctness are decoupled. On F07 arm A closes 39/39 while naming
the class right 9/39 — the frame contains what the detector needs and the
model still answers F06 confidently. A closure metric alone would have
reported this frame as healthy.

### 17.3 Arm E is an oracle arm and cannot be shipped as-is

`build_arm` composes E as `discriminating_items(frame, fault_class)` plus the
service and baseline items. **It selects evidence using the injected class.**
In production the class is the unknown being diagnosed, so "just ship arm E"
is circular, and this section must not be read as a repair recommendation.

What E does establish, and what is new:

1. **The F07 failure is not an information deficit.** The same frame, minus
   its non-discriminating real items, yields 13/13. The evidence was always
   sufficient; the model was distracted by true-but-irrelevant signal.
2. **Real, non-discriminating evidence is not free.** Every prior section
   treated added *noise* as the hazard. The hazard here is correct metrics
   that do not discriminate, and the shipped frame includes them by default.
3. **A plausible implementable direction, not yet tested:** build one frame
   per candidate class and score each separately, so item selection is
   conditioned on a hypothesis rather than on the answer. That is a design
   change with its own pre-registration, not a conclusion of this run.

### 17.4 What this costs the report

- `REPORT_DRAFT` §4.4a: the mechanism is refuted a second time, now by the
  primary test failing rather than by a correction. Rewrite required.
- §13.4's "what stands" list: the arm-B claims come off it.
- The F07 result belongs in §6 as a measured limitation of the shipped
  evidence frame, with the 3/13 figure, not as a footnote.
- Nothing here weakens a safety claim: arm B still degrades by abstaining
  (70 abstentions, 20 confident errors at mean 0.78), and an UNKNOWN never
  executes. The dangerous arm is the control.

I am not rewriting those sections in the same pass that produced this result.
They are listed so the next session does not have to rediscover them.

---

## 18. Grammar change and re-run, pre-registered 2026-11-09 23:55

### What changed and why a re-run is required

`Diagnosis.rejected_alternatives` was optional with a default; it is now a
**required key** (empty list still permitted — the key is mandatory, the
content is not). The reason was not this experiment: it is that OpenAI strict
mode refuses any schema whose properties are not all in `required`, so the
first cloud RCA call ever made died on HTTP 400.

**Corrected 00:40, an hour after writing this section:** I first wrote that no
cloud provider had ever served Kavach at all and that the registry had been
unused since 2026-10-19. That is **wrong**. The P7 patch runs used it for
real - `harness/reports/p7-e2e-groq-{2,3}.json` on Groq
`openai/gpt-oss-120b` and `p7-patch-live-gemini.json` on Gemini, quoted in
`REPORT_DRAFT` §4.5. They worked because `PatchProposal` happens to be
strict-conformant: every property required, `additionalProperties: false`.
`Diagnosis` was not, so the defect was specific to **the RCA schema**, which
no cloud provider had been asked for. Ollama's decoder accepts an optional
field, so three weeks of local RCA runs could not reveal it and the
successful patch runs did not exercise it. Verified fixed: Groq accepted the schema on 2026-11-09 23:52,
and `test_rca.py::test_diagnosis_schema_is_openai_strict_conformant` now walks
the schema so a future optional field fails locally instead of silently
breaking all seven providers. 642 tests pass, ruff and `mypy --strict` clean.

**This alters the grammar the decoder is constrained by, which is part of the
measured path.** §17's 840 observations were produced under the old grammar.
They are not discarded and not re-labelled, but a quotable result may not mix
the two, so the run is repeated with **identical parameters** — 4 classes, 15
incidents, 3 reps, all five arms, shuffle off, same baseline, same local
`qwen2.5:7b-instruct` — so that the grammar is the only difference between
§17 and §19. Reps stay at 3 despite §14 and §17 both finding they buy almost
nothing, because changing two things at once would make the comparison
useless.

**After this run, §19 is the quotable local result and §17 is the old-grammar
measurement.**

### Predictions, fixed before the run

1. **§17.2's F07 result survives:** arm A names F07 correctly in **<= 6** of
   its usable incidents and arm E in **>= 12**. If arm A reaches parity with
   E, the F07 effect was an artefact of the old grammar and §17.2 falls
   entirely.
2. **The failed primary stays failed:** arm B's closure drop against A remains
   **< 0.15**. If it now exceeds 0.15, the primary hypothesis did not fail —
   it was measured under a grammar that suppressed the effect, and §17.1 must
   be withdrawn rather than quoted.
3. **Arms C and D stay well below A:** C <= 0.70, D <= 0.90 closure.
4. **Forcing the key may improve everything, and that would be a finding.**
   The model must now emit `rejected_alternatives`, and being made to name
   what it ruled out is the kind of contrastive demand that can improve class
   discrimination. If agreement rises materially across arms — above all if
   arm A's F07 rises — that is a result about mandatory contrastive output and
   gets its own section. It may not be folded into §17 or §19 as though the
   grammar were incidental.
5. **The four detector-side drops should recur.** F07#11, F07#14, F08#4 and
   F08#8 were dropped because the detector returned
   `INSUFFICIENT_EVIDENCE`, which is upstream of the model and unaffected by
   its grammar. A materially different drop set means something other than
   the grammar changed between the runs.

### Amendment, 00:00, before the first observation: "identical" is not quite true

The distractor pool is scraped live from the target's `/metrics`, and it has
grown: **§17's run saw 49 metrics, this run sees 52.** The target accumulates
Prometheus series as new handler and method label combinations appear, and
`--distractors` sets a floor, not a cap, so the pool cannot be pinned to 49
without a code change the measured path does not need.

What this does and does not touch:

- **Arms A, D and E contain no distractors and are unaffected.** Prediction 1,
  the F07 headline, is an A-versus-E comparison and survives intact.
- **Arm B is size-matched, so its item count is unchanged**, but it draws from
  a 52-item list rather than a 49-item one, so the *content* of the noise
  differs. Prediction 2 is still testable — the pre-registered threshold is a
  drop magnitude, not a per-item comparison — but a difference from §17's arm
  B may be the pool rather than the grammar.
- **Arm C adds every distractor, so its frames are 3 items larger than
  §17's.** Prediction 3 is correspondingly weaker: C is expected to stay below
  A, and that is all this run can say about it.

This is recorded rather than corrected because the alternative - freezing a
synthetic pool - would make arm C measure a fixed fixture instead of the
target's real metric surface, which is the thing the arm is about.

---

## 19. Re-run under the corrected grammar, 2026-11-10 — the primary is MET, and §17.1 is withdrawn

885 observations, 59 usable incidents, 0 model errors, target verified clean.
Artifact `harness/reports/closure-ablation-full-g2.json`, model
`ollama:qwen2.5:7b-instruct`, distractor pool 52, shuffle off. One incident
dropped by the pre-registered detector rule (F08#15).

### 19.1 §18's five predictions, scored

| § | Prediction | Observed | Verdict |
|---|---|---|---|
| 18.1 | arm A names F07 right in **<= 6** incidents, arm E in **>= 12** | A **7**/15, E **15**/15 | **bound missed by one incident**; effect confirmed, b=8 c=0, p=0.0078 |
| 18.2 | arm B's closure drop stays **< 0.15** | drop **+0.21**, p=0.0002 | **VIOLATED** |
| 18.3 | C <= 0.70 and D <= 0.90 | C **0.51**, D **0.76** | held |
| 18.4 | forcing the key may improve everything, and that is its own finding | arm A's F07 agreement **23% to 47%** | **fired** — see 19.3 |
| 18.5 | the four detector-side drops recur | **1** drop, F08#15; none of the four recurred | **VIOLATED** |

Two violated, one held, one missed on its stated bound with the effect intact,
one fired. §7 forbids re-reading any of these into a pass, and 18.1 is the one
to watch: 7 is not <= 6, so the prediction fails as written even though arm E
beats arm A decisively. Both facts are recorded.

### 19.2 The primary hypothesis is MET, §17.1 is withdrawn, and the cause is confounded

| arm | §17 (old grammar, pool 49) | §19 (new grammar, pool 52) |
|---|---|---|
| A control | 0.99 | **1.00** |
| B size-matched noise | 0.90, drop +0.09, p=0.125 | **0.79, drop +0.21, p=0.0002** |
| C unbounded noise | 0.54 | 0.51 |
| D expectations stripped | 0.77 | 0.76 |
| E removed, nothing added | 1.00 | 1.00 |

§18.2 stated the consequence in advance: *"If it now exceeds 0.15, the primary
hypothesis did not fail — it was measured under a grammar that suppressed it,
and §17.1 must be withdrawn rather than quoted."* It does, so **§17.1 is
withdrawn. Nothing in it may be quoted**, including its own correction of the
p-values. The size-matched-noise hypothesis is **MET** on this run: the drop
is 0.21 against a pre-registered 0.15, at p=0.0002, b=13 c=0.

**But the cause cannot be attributed, and this run cannot carry the claim
alone.** Two things differed from §17: the grammar, and the distractor pool
(49 to 52), which §18's amendment recorded in advance as changing *which*
distractors arm B draws. Arm B is the only arm that samples a subset, so arm B
is exactly the arm both changes touch. A 0.09 result and a 0.21 result from
two runs differing in two variables establishes neither.

**What would settle it:** one more run under this grammar. If 0.21 reproduces,
§17's 0.09 was the outlier and the grammar is the likely cause; if 0.09
returns, the pool is. Until then the honest statement is **"the primary
hypothesis is met in one of two runs, and the two runs differ in two
variables."** That is weaker than §17.1's withdrawn claim *and* weaker than
this run's verdict line, and it is what the report should say.

### 19.3 §18.4 fired: the mandatory key helped the control arm and made the noise arm dangerous

Requiring `rejected_alternatives` is a contrastive demand — the model must
name what it ruled out. Both effects below are new and both matter.

**It roughly doubled F07 class discrimination in the control arm.**

| | §17 | §19 |
|---|---|---|
| arm A, F07 agreement | 9/39 diagnoses, 3/13 incidents (23%) | **21/45 diagnoses, 7/15 incidents (47%)** |
| arm A, correct overall | 136/168 (81%) | **153/177 (86%)** |
| arm A, confident wrong | 32 at 0.95 | **24 at 0.95** |

**It also removed arm B's safe failure mode.**

| arm B | §17 | §19 |
|---|---|---|
| abstentions | 70 | **45** |
| confident wrong | 20 | **46** |
| mean confidence of the wrong | 0.78 | **0.87** |

§13.1's correction established that arm B *abstains rather than errs*, and
that this makes noise a safe degradation because Kavach never executes an
`UNKNOWN`. **Under the corrected grammar that is no longer true.** Forced to
produce rejected alternatives, the noise arm commits to a confident wrong
class more than twice as often and abstains a third less. §13.1 stands as a
statement about the old grammar and must be qualified wherever it is quoted.

The mechanism is plausible and untested: being required to name alternatives
may push a model that would have declined into choosing between the
candidates it just enumerated. That is a hypothesis for a future
pre-registration, not a finding of this run.

### 19.4 Arm E is still perfect, and F07 is still the control arm's failure

Arm E: **177/177 correct, 0 abstentions, 0 confident errors, closure 1.00** —
on both grammars. Per class, arm A versus arm E on incident-level agreement:

| class | A | E | b | c | exact p |
|---|---|---|---|---|---|
| F01 | 15/15 | 15/15 | 0 | 0 | 1.00 |
| F06 | 15/15 | 15/15 | 0 | 0 | 1.00 |
| **F07** | **7/15** | **15/15** | 8 | 0 | **0.0078** |
| F08 | 14/14 | 14/14 | 0 | 0 | 1.00 |

The §17.2 finding survives the grammar change: removing the frame's
non-discriminating, non-service, non-baseline items takes F07 from under half
to all of it, and the control arm's remaining 24 confident errors are *all*
F07 named as F06 at 0.95. §17.3's caveat stands unchanged — arm E selects
items using the injected class, so it is an oracle and not a repair.

### 19.5 §18.5 violated: detection is not reproducible run to run

§17 dropped F07#11, F07#14, F08#4 and F08#8. §19 dropped F08#15. **No
overlap.** The prediction assumed the detector is upstream of the model and
therefore unaffected by a grammar change, which is true — and the drop set
still moved completely.

So the detector's `INSUFFICIENT_EVIDENCE` outcome on a given incident is **not
reproducible across runs**. The plausible mechanism is that
`drive_until_detectable` plus live metric windows make reaching a conclusion a
timing phenomenon rather than a deterministic one, which is consistent with
this project having already been bitten three times by windowed metrics read
over windows shorter than their own contents.

This is not a closure-ablation result; it is a **detection** result, and it
bears on every MTTD figure in `REPORT_DRAFT` §4.1. It should be measured
directly — the same incident, repeated, counting how often detection
concludes — rather than inferred from two drop sets.

### 19.6 A note that supports ADR 0023

Arm B's wrong answers now include classes with **no injector**: `F05` nine
times on F01, `F02` three times on F01, `F05` twelve times on F07. The output
space is the eight-class catalogue, so this is legal, but it is evidence for
`decisions/0023`: shown noisy LLM-endpoint evidence, the model already reaches
for `F02` as the explanation. The confusable pair that ADR argues for is one
the model is already making on its own.

### 19.7 What this costs

- **§17.1 is withdrawn.** Not corrected — withdrawn, per §18.2.
- **§13.1 must be qualified** wherever quoted: arm B abstained safely under
  the old grammar and does not under the new one.
- **The primary hypothesis cannot be reported from one run.** One more run
  under this grammar is the cheapest thing that would let it be stated at all.
- **`REPORT_DRAFT` §4.4a** is still refuted as a mechanism; nothing here
  revives it.
- **MTTD figures need a reproducibility measurement** they do not currently
  have.

---

## 20. Third run, pre-registered 2026-11-10 02:30 — a straight replication to break the §17/§19 tie

### Why

§19.2 left the primary hypothesis unreportable: 0.09 at p=0.125 in §17, 0.21
at p=0.0002 in §19, with **two** variables differing between them (the
grammar, and the distractor pool at 49 versus 52). Neither run can carry the
claim. A replication of §19 changes nothing at all, so it separates "§19's
result is real" from "§19's result is one draw of a noisy quantity" — which
is the cheapest question that stands between this experiment and a reportable
primary.

**Nothing is changed from §19.** Same grammar, same four classes, 15
incidents, 3 reps, five arms, shuffle off, same baseline, same local
`qwen2.5:7b-instruct`. The distractor pool cannot be pinned (`--distractors`
is a floor, not a cap) and is recorded with the result.

### Predictions, fixed before the run

1. **Arm B's closure drop is >= 0.15 again, at p < 0.05.** This is the whole
   point. If it reproduces, §19's verdict stands and §17's 0.09 is the
   outlier. **If it comes back below 0.15, the primary hypothesis is not met
   and is not reportable from three runs either** — it would mean the quantity
   swings across the pre-registered threshold between identical runs, which
   is a statement about the measurement rather than about curation.
2. **Arm E is 100% correct with zero confident errors**, as on both previous
   runs. If arm E moves at all, something outside the design changed and the
   run is not comparable.
3. **Arm A names F07 correctly in 5 to 9 of 15 incidents** — the 47% band
   §19 measured, stated as an interval because 7/15 is one incident wide.
   Outside that band, §19.3's doubling claim needs re-examining before it is
   quoted.
4. **Arm B's safety regression replicates:** abstentions below 55 and
   confident-wrong above 35. §19.3 is the only evidence that the mandatory
   key removed arm B's safe failure mode, and it is a single run.
5. **The drop set will differ again.** §18.5 was violated because detection
   is not reproducible; the prediction now is that it stays irreproducible. A
   drop set that matches either previous run exactly would be the surprise.

### The decision rule, fixed now so it cannot be chosen later

- **Three runs, two at >= 0.15:** report the primary as met, with all three
  figures and the two changed variables disclosed in the same paragraph. Not
  as a clean result.
- **Three runs, two below 0.15:** report the primary as not met, and §19.2's
  verdict line is withdrawn exactly as §17.1 was.
- **Any 2-1 split in either direction:** report that the measurement does not
  resolve the hypothesis at this sample size, and that the pre-registered
  threshold sits inside the run-to-run variance. This is the outcome the
  report should be most willing to state, because it is the one that is
  easiest to hide.

---

## 21. Third run, 2026-11-10 04:39 — the replication holds and the decision rule fires

855 observations, 57 usable incidents, 0 model errors, target verified clean.
Artifact `harness/reports/closure-ablation-full-g3.json`, model
`ollama:qwen2.5:7b-instruct`, **distractor pool 52 — identical to §19**,
shuffle off. Three incidents dropped by the pre-registered detector rule
(F08#2, F08#8, F08#11).

The one thing a replication must prove about itself is that it changed
nothing, and the pool is the variable that cannot be pinned by a flag. It
came back 52, the same number §19 scraped, so this run differs from §19 in
no recorded input.

### 21.1 §20's five predictions, scored

| § | Prediction | Observed | Verdict |
|---|---|---|---|
| 20.1 | arm B's drop **>= 0.15** at **p < 0.05** | drop **+0.19**, p **0.0010**, b=11 c=0 | **MET** |
| 20.2 | arm E **171/171**, zero confident errors | 171/171, 0 abstentions, 0 errors | **held** |
| 20.3 | arm A names F07 right in **5 to 9** of 15 | **5**/15 | **held at the floor** — see 21.3 |
| 20.4 | arm B abstentions **< 55**, confident-wrong **> 35** | **42** and **40** | **held** |
| 20.5 | the drop set differs again | F08#2, F08#8, F08#11 | **held**, with one recurrence |

Four held, one met, none violated — the first run in this experiment where
nothing was refuted. §7 forbids reading that as strength on its own: §20 was
written to predict a repeat of §19, and a repeat is the cheapest thing a
pre-registration can get right.

### 21.2 The decision rule fires: the primary is MET, and the wording is fixed by §20

| run | grammar | pool | arm A | arm B | drop | p |
|---|---|---|---|---|---|---|
| §17 | old | 49 | 0.99 | 0.90 | +0.09 | 0.125 |
| §19 | **new** | **52** | 1.00 | 0.79 | **+0.21** | 0.0002 |
| §21 | **new** | **52** | 1.00 | 0.81 | **+0.19** | 0.0010 |

Two of three runs at >= 0.15. §20's rule, fixed before this run was
launched: *"report the primary as met, with all three figures and the two
changed variables disclosed in the same paragraph. Not as a clean result."*
That is what the report does, and the paragraph is §21.6.

**The confound is not resolved, and the claim no longer needs it resolved.**
Why §17 measured 0.09 is still unknown — the grammar and the pool both
differed, and no run isolates them. What the three runs do establish is
narrower and sufficient: **under the grammar and pool that ship today, the
drop is reproducibly >= 0.15** (0.21 and 0.19, two independent runs, 114
incidents between them). §17's 0.09 was measured under a configuration that
no longer exists in the codebase. The honest sentence is *"met under the
current configuration, with one earlier run under a superseded configuration
measuring 0.09"* — not *"met"*, and not *"the grammar caused it"*.

**§7's refutation condition is not triggered.** Within-cell spread across
repetitions is **0.01**, against an A-to-B gap of 0.19. §7 names "within-cell
variance exceeds the A-to-B gap" as the condition that would make the gap
sampling noise; it is nineteen times smaller.

Arms C and D are stable across all three runs — C 0.54 / 0.51 / 0.57, D 0.77
/ 0.76 / 0.77 — which is the background check that the harness itself did not
drift between runs.

### 21.3 §19.3's doubling claim does not survive the replication

Prediction 20.3 held: 5 is inside the 5-to-9 band. It held **at the floor**,
and §7 forbids reading a floor as a confirmation.

| run | grammar | arm A names F07 correctly |
|---|---|---|
| §17 | old | 3/13 = **23%** |
| §19 | new | 7/15 = **47%** |
| §21 | new | 5/15 = **33%** |

**The spread between the two identical runs (47% to 33%, 14 points) is larger
than the gap between the lower of them and the old grammar (33% to 23%, 10
points).** So the F07 improvement is not separable from run-to-run noise with
only one old-grammar measurement. §19.3's "roughly doubled" is withdrawn as a
claim; what survives is *"F07 discrimination under the new grammar measured
47% and 33%, against a single old-grammar measurement of 23%"*, which is a
set of numbers rather than an effect.

This is the opposite of the §21.2 outcome and worth stating as such: the same
replication that **strengthened** the primary hypothesis **dissolved** the
incidental one. A replication that only ever confirms is not being read
honestly.

### 21.4 §19.3's safety finding replicates, and §13.1 is now qualified on two runs

| arm B | §17 (old) | §19 (new) | §21 (new) |
|---|---|---|---|
| abstentions | 70 | 45 | **42** |
| confident wrong | 20 | 46 | **40** |
| mean confidence of the wrong | 0.78 | 0.87 | **0.86** |

The two new-grammar runs agree closely, and both differ from the old one in
the same direction and by a similar margin. **This is the most solid new
result of the three runs**, because it is the only one measured twice under
identical conditions with the same answer.

§13.1 established that arm B *abstains rather than errs*, making noise a safe
degradation since Kavach never executes an `UNKNOWN`. **That is a statement
about the old grammar and must be qualified wherever it is quoted.** Under the
shipped grammar the noise arm commits to a confident wrong class twice as
often and abstains forty per cent less.

Arm A's own confident errors moved the other way: 32 (§17), 24 (§19), **30**
(§21) — a spread that contains §19's apparent improvement, so that too is
noise rather than a gain.

Arm B's confident-wrong classes again reach for classes with **no injector**:
`F05` thirty times, `F02` three times, `F01` three times, `F08` three times.
§19.6's support for `decisions/0023` is unchanged and now observed twice.

### 21.5 Detection is irreproducible on a third run, and the drops are not uniform

| run | incidents dropped by the detector |
|---|---|
| §17 | F07#11, F07#14, F08#4, F08#8 |
| §19 | F08#15 |
| §21 | F08#2, **F08#8**, F08#11 |

Three runs, three different drop sets, and the count itself moves: 4, 1, 3.
**F08#8 recurs** in §17 and §21, which is the first evidence that the drops
are not purely random — but six of the eight drops across all three runs are
F08 and the other two are F07, while **F01 and F06 have never once failed to
detect**. That pattern says the irreproducibility is concentrated in the two
classes whose detectors read windowed metrics, which is consistent with
§19.5's proposed mechanism and still does not test it.

§19.5's recommendation stands and is now more urgent: measure it directly —
the same incident, repeated, counting how often detection concludes — rather
than inferring from three drop sets. It bears on every MTTD figure in
`REPORT_DRAFT` §4.1.

### 21.6 The paragraph the report must carry

> The size-matched-noise hypothesis is **met under the configuration that
> ships**: replacing the frame's curated items with an equal number of real
> but non-discriminating metrics drops evidence closure by **0.21** (p =
> 0.0002, 59 incidents) and **0.19** (p = 0.0010, 57 incidents) across two
> independent runs. A third, earlier run measured **0.09** (p = 0.125, 56
> incidents) and did not meet the pre-registered 0.15 threshold. That run
> differed in **two** respects — the diagnosis schema did not yet require
> contrastive alternatives, and the live distractor pool held 49 metrics
> rather than 52 — so **no run isolates which change is responsible**, and
> the claim is restricted to the current configuration rather than extended
> to the mechanism. The decision rule that selected this wording was fixed in
> `EXPERIMENT_CLOSURE_ABLATION.md` §20 before the third run was launched.

### 21.7 What is still not settled

- **Why §17 was low.** A fourth run under the old grammar at pool 52 would
  isolate it. It is one run's worth of compute and nothing else in the report
  depends on the answer, so it is listed, not scheduled.
- **The F07 effect size**, per §21.3 — two new-grammar runs disagree by 14
  points and a third old-grammar point sits inside that spread.
- **Detector reproducibility**, per §21.5. This is the one that blocks a
  figure already in the report.
- **Arm E remains an oracle** (§17.3), unchanged by three runs of perfect
  scores. 171/171 is not a repair and must never be quoted as the shipped
  system's performance.

---

## 22. Audit of the statistics, 2026-11-10 — one defect, one fix, and the gap that let both through

Every p-value in §17, §19 and §21, and every one `REPORT_DRAFT` §4.4a repeats,
comes from four functions in `harness/closure_ablation_report.py`. **Nothing
tested any of them.** That is how the pairing defect of §19 survived three
full runs, and it is the finding of this audit rather than a side note.

### 22.1 The exact McNemar is correct

`mcnemar` computes the two-sided exact binomial test at p=0.5, doubling the
smaller tail — the standard exact McNemar. Checked against nine hand-computed
reference values rather than against its own output:

| b | c | p (hand) | arithmetic |
|---|---|---|---|
| 0 | 0 | 1.0 | no discordant pairs |
| 1 | 0 | 1.0 | one discordant pair **cannot** be significant |
| 5 | 5 | 1.0 | balanced; the doubling clips at 1.0 |
| 4 | 2 | 0.6875 | 2(1+6+15)/64 |
| 7 | 3 | 0.34375 | 2(1+10+45+120)/1024 |
| 8 | 0 | 0.0078125 | 2/256 — the F07 A-vs-E figure |
| 11 | 0 | 0.0009765625 | 2/2048 — §21's A-vs-B figure |
| 13 | 0 | 0.000244140625 | 2/8192 — §19's A-vs-B figure |

All nine match. Also verified: concordant pairs do not move the p-value, and
swapping the arms swaps b and c and leaves p alone.

### 22.2 The cluster bootstrap resamples the right unit, and is degenerate at the boundary

`cluster_bootstrap` resamples **incidents** with replacement, which is the
honest unit — reps of one incident share a frame, a fault and a detector
verdict. That part was always right; it is the McNemar beside it that was
wrong, and §19's correction brought them into agreement.

**The defect found here is different and was being printed on every run.** The
nonparametric bootstrap has no way to represent uncertainty at the boundary:
when every incident closes, every resample also closes, so arms A and E print

```
A    control, the shipped frame       1.00  [1.00, 1.00]       171
```

A zero-width 95% interval on 57 incidents. The arithmetic is right and the
number is misleading — a reader is entitled to read it as certainty, and
"closure is at a ceiling" is a load-bearing claim in `REPORT_DRAFT` §4.4a and
in §8's argument that epistemic uncertainty cannot be priced from closure.

**Fixed by stating the ceiling instead of hiding behind the interval.**
Observing k perfect incidents out of k bounds the per-incident failure rate at
`1 - 0.05 ** (1/k)` with 95% confidence — the exact one-sided
Clopper-Pearson bound. For 57 incidents that is **0.0512**, so the honest
statement is *"at most about 5% of incidents fail to close"*, not *"none do"*.
The report now prints it beside the degenerate interval and returns `nan` for
any arm that is not perfect, because for those the bootstrap interval is the
better statistic.

The method was **not** swapped for Wilson or Clopper-Pearson throughout.
Those ignore clustering and would overstate precision in the opposite
direction, which is a worse error than the one being corrected.

### 22.3 `within_cell_variance` computes a range, not a variance

The function returns the mean of `max - min` across the reps of each
(class, incident, arm) cell. §7's refutation condition is worded as
*"within-cell variance exceeds the A-to-B gap"*, and the printed label
already says *"within-cell spread"* and *"mean max-min"*, so the output is
honest and only the function's name is loose.

**Left as it is, with the direction recorded:** for three Bernoulli draws the
range is at least as large as any spread measure that could replace it, so
using it makes §7's refutation **harder** to trip, not easier. A statistic
that errs toward refuting our own hypothesis is the right one to keep, and
renaming it would churn a cited interface for nothing.

### 22.4 The real finding: none of this was tested

`apps/control-plane/tests/test_closure_ablation_statistics.py`, 16 test functions / 24 cases,
no network and no artifact. The one that matters most is
`tests/test_closure_ablation_statistics.py::test_cells_pairs_on_the_incident_not_the_diagnosis`
— it fails if the pairing unit ever reverts to the diagnosis, which is the
defect that read p=0.0007 where the honest answer was p=0.1250.

Also covered: that the bootstrap resamples incidents (two disagreeing
incidents must give `[0.00, 1.00]`, where a bootstrap over the six individual
diagnoses would report a narrow interval the data does not support); that it
is seeded and reproducible, because a p-value that moves between runs is not
one; and that `(class, incident, arm)` keys separate F07#1 from F08#1, since
every class numbers its incidents from 1.

**This is the project's recurring defect in miniature, for the fifth time:** a
fact recorded in one place with nothing checking that the other place still
agrees. `test_doc_citations.py`'s own header lists the first four. The
statistics were the fifth, and the reason they went unnoticed longest is that
a wrong p-value still looks like a p-value.

---

## 23. Detection reproducibility, measured 2026-11-10 — §21.5's localization is wrong, and the real pattern is positional

80 injections, 20 per class, no model calls. Script
`harness/detector_reproducibility.py`, artifact
`harness/reports/detector-reproducibility.json`, baseline
`baseline-simple-rag-20261017T163257+0000.json`, 0 errors, every trial
reverted.

§19.5 and §21.5 both said this had to be measured directly rather than
inferred from drop sets. It was, and **the inference was wrong.**

### 23.1 The result

| class | detected | rate | the misses | detect seconds (min / median / max) |
|---|---|---|---|---|
| F01 | 20/20 | **1.00** | — | 24.2 / 24.4 / **48.5** |
| F06 | 19/20 | **0.95** | trial 1: **named `F01`** | 32.3 / 33.2 / 35.8 |
| F07 | 18/20 | **0.90** | trials 1 **and** 2: `INSUFFICIENT_EVIDENCE` | 17.9 / 18.3 / 19.6 |
| F08 | 20/20 | **1.00** | — | 16.9 / 17.3 / 17.9 |

Pooled, **79 of 82** including the two-trial smoke that preceded this run
(whose single F08 trial-1 miss is recorded here rather than dropped, because
it is the same script against the same target and excluding it would be
choosing data after seeing it). **So detection concludes correctly about 96%
of the time and is not deterministic.** That is now measured rather than
inferred.

### 23.2 §21.5 said the irreproducibility was concentrated in F08. It is not.

§21.5 reasoned that six of the eight ablation drops were F08, two were F07,
and F01 and F06 never failed — therefore the instability lived in the two
classes whose detectors read windowed metrics, with F08 the worst. Direct
measurement gives almost the opposite ordering: **F08 is 20/20 here and F07
is the weakest at 0.90, while F06 — which had never appeared in a drop set —
fails too.**

**§21.5's localization claim is withdrawn.** What survives from it is only the
bare fact that the drop sets differ, which this section replaces with a rate.
The lesson is the one §21.5 itself argued for and then partly ignored: three
drop sets of size 4, 1 and 3 cannot locate anything, and reading an ordering
out of them was over-reading my own evidence.

### 23.3 The real pattern is positional, and it is not subtle

Every miss is in the **first or second trial of its class block**:

- F06 — trial 1 of 20.
- F07 — trials 1 and 2 of 20.
- F08 — trial 1 of the two-trial smoke, on a target that had just come up.
- F01 — no miss, but trial 1 took **48.5s against a 24.4s median**, the
  slowest detect in all 80 trials and nearly double the next.

Three misses landing in the eight first-two-of-a-block slots out of 80 would
happen by chance with probability **C(8,3)/C(80,3) = 0.0007**. That is not a
proof of mechanism — the slots were not chosen in advance and this is a
pattern found in the data, which §7's standards make an observation and not a
result — but it is a far better candidate than the "timing phenomenon in
windowed PromQL" §19.5 proposed, and it is cheap to test properly: inject one
class twenty times on a freshly started stack, pre-registering that only the
first trials may fail.

**And it is not a new mechanism in this project — it is the one already
measured.** `REPORT_DRAFT` §4.1 established on 2026-11-06, from
`harness/mttd_ladder.py`, that F01's MTTD ladder is built out of **warm-up
rounds**: one round of `warm_up_f01` costs 12.12s against 24.3s on a healthy
target, twelve of twenty MTTD samples lie within 0.4s of a 12.12s lattice,
and the scrape interval was ruled out rather than merely doubted. A warm-up
account of *detection latency* was already the measured explanation there.
This section finds a warm-up-shaped effect on *detection success*, from a
different script with no model in the loop. Two independent measurements
pointing at the same mechanism is much stronger than either alone, and it is
why §19.5's windowed-PromQL proposal should not be carried further.

**The consequence is that F07 and F08 may simply be missing a warm-up that
F01 and F06 have.** `one_incident` calls `drive_until_detectable` for F06 and
`warm_up_f01` for F01, and nothing for F07 or F08 — and F07 is the weakest
class here at 0.90. That is a harness asymmetry, it is one line per class to
test, and it must be **pre-registered before it is tried**, because "add a
warm-up until the number improves" is exactly the shape of tuning this
project forbids itself.

**Why this matters more than the rate does.** A warm-up effect is a
*harness* property with a fix (drive the target before measuring, which
`drive_until_detectable` and `warm_up_f01` already do for F06 and F01 and
nothing does for F07 and F08). A genuinely stochastic detector is a
*product* property with no fix. The two have opposite consequences for the
report, and the data now points at the first.

**It does not explain the ablation's drops.** Those were F07#11, F07#14,
F08#4, F08#8, F08#15, F08#2 and F08#11 — none of them the first incident of
its block. So either the ablation's per-incident work (45 diagnoses, minutes
of LLM latency between injections) produces a different timing regime, or
there are two phenomena. Stated as open rather than resolved.

### 23.4 The finding that actually bears on safety: F06 was named `F01`

F07's two misses are `INSUFFICIENT_EVIDENCE`, which escalates to a human and
is the safe outcome the architecture is built around. **F06's miss is a
confident wrong class.** The ablation's drop rule folded both into one
category — *"the detector said something other than the injected class"* —
and that folding hid the distinction, exactly as `REPORT_DRAFT` §6 records a
`broke` check being folded into an injector's pass condition and hiding a
stochastic symptom.

`PRD.md` §6 gives `F01` the repair `switch_llm_endpoint` and `F06` a
different one, so a detector that names `F01` for an injected `F06` routes to
a repair that cannot fix the fault. **What catches it is not checked here and
must not be assumed** — the verification probe should fail and the undo stack
should restore, which is the §4.5 mechanism, but that is a prediction about
the pipeline and this measurement only ran the detector. It needs its own
test before the report claims the pipeline degrades safely on a misdetection.

This is one observation in 20. It is reported because the consequence is
asymmetric, not because the rate is established.

### 23.5 What `REPORT_DRAFT` §4.1 must now say

Every MTTD figure in §4.1 is a mean over detections that **concluded**, and
the denominator was never stated because it was assumed to be all of them. It
is not: **about 4% of injections do not produce a correct detection**, and on
F07 it is 10%. §4.1 must publish the conditional nature of the mean and the
per-class rate beside it. That is a disclosure, not a new measurement, and it
is the one item from §21.7's open list that is now closed.

The detect latencies above are **not** MTTD and must not be read as such:
they time one `run_all` over an already-faulted target, where §4.1 measures
from injection to a recorded detection in the control plane. They are
reported because trial 1's 48.5s on F01 is part of the positional evidence.

---

## 24. Cross-provider smoke, 2026-11-10 — the plumbing is proven, the numbers may not be quoted, and §23.3 was corroborated by accident

Artifact `harness/reports/closure-ablation-groq-smoke2.json`, model
`groq:openai/gpt-oss-120b`, 4 classes x 5 incidents x 1 rep x arms A/B/E.
**54 of 54 diagnoses usable, 0 errors**, 4 transient LLM failures absorbed by
the retry, 11.5 minutes wall clock of which 171s was model latency.

### 24.1 What this establishes, which is only the plumbing

§16.3 fixed in advance that the smoke's *numbers* are for plumbing only and
**may not be quoted**, because 5 incidents at 1 rep cannot separate a model
difference from the draw. That still binds, and §24.3 below is the reason it
has to be said twice rather than once.

What it does establish:

- **A cloud provider now serves Kavach diagnoses end to end.** The first
  attempt, 2026-11-09, died on the first call: Groq rejected the schema
  because OpenAI strict mode requires every property in `required` and
  `rejected_alternatives` was optional. That artifact
  (`closure-ablation-groq-smoke.json`, 1 observation, 1 error) is kept as the
  record. After the schema change the same run completes with zero errors.
- **The retry handles Groq's rate limiting.** Four transient failures, all
  absorbed, none reaching the 8-failure ceiling.
- **The run is affordable.** 54 calls in 11.5 minutes at ~3.1s median
  latency, which sizes the real run at roughly 1.5 to 2 hours.

### 24.2 §23.3's positional pattern turned up again, in a script written for something else

The smoke dropped exactly two incidents: **F06#1** and **F07#1**. Both are the
**first incident of their class block**, and F06#1's detector verdict was
**`F01`** — the same wrong class, on the same injected fault, that §23.1
recorded as F06's single miss in 20 trials.

**Ordering, because it decides what this is worth.** The smoke was launched at
05:55 and §23 was written while it was in flight, from the detector
measurement alone; I had not seen the smoke's drops when §23.3 proposed that
only the first trials of a block fail. So this is **not** a pre-registered
test — §23.3 was not registered anywhere before the run started, and the
honest label is a prediction made in ignorance of a result that already
existed on disk. It is stronger than fitting the pattern after the fact and
weaker than a pre-registration, and it is recorded in that order.

Running total of misdetections across both scripts: F06#1, F07#1, F07#2 (the
detector measurement), F08#1 (the two-trial smoke), F06#1 and F07#1 (this
smoke). **Six for six at position 1 or 2 of a block.** The pre-registered
version of this test is §23.3's: one class, twenty injections, freshly started
stack, registering before the run that only the first trials may fail.

### 24.3 The part that must not be quoted, and must not be forgotten either

Arm B's closure on the detector's class came back **1.00**, against 0.79 and
0.81 on the local 7B model, with a drop of +0.00 and b=c=0.

**That number cannot be reported** — §16.3, and 18 incidents at one rep. But
it cannot be quietly dropped either, because of what it would mean if the
full run reproduces it: §16's prediction 3 scored *">= 0.95 means closure
sensitivity **was** a 7B artefact"*, and 1.00 clears that band. The primary
hypothesis §21.2 just declared met would then be **met on one model and absent
on another**, which is a scope condition on the headline result rather than a
refutation of it.

Two mechanisms are visible in the log and both need the full run to separate:

- **Arm B abstained rather than mis-cited.** 10 of its 18 diagnoses returned
  `INSUFFICIENT_EVIDENCE` while still citing the detector's discriminating
  evidence, so `closed_detector` scored True. **The primary outcome does not
  require the model to name the class** — only to cite the evidence that
  discriminates it. A larger model that declines cleanly therefore scores a
  perfect closure, and a 7B model that guesses wrong scores a poor one. That
  is a property of the metric, not of grounding, and it belongs in
  `REPORT_DRAFT` §4.4a whatever the full run says.
- **Arm E also fell to 0.44 agreement**, where it is 1.00 on every local run.
  On four items `gpt-oss-120b` abstains where `qwen2.5:7b-instruct` answers.
  If that holds, §17.3's oracle caveat gains a second one: arm E's perfection
  is a property of the local model too.

**One thing to check rather than assume in the full run.** Arms B and E
returned *identical* name distributions on this smoke — 10
`INSUFFICIENT_EVIDENCE`, 5 `F01`, 3 `F06` each. Their frames are genuinely
different (33 items / 3688 tokens against 4 items / 2952 tokens), so this is
most likely the same incidents defeating both arms rather than a harness
fault passing one frame twice. At 18 observations it is also exactly the
coincidence that a bug would produce, and it costs nothing to confirm against
540.

**Pre-registered now, before the full run's numbers exist:** if arm B's
closure on `gpt-oss-120b` comes back **>= 0.95** across 15 incidents x 3 reps,
§21.2's "met under the configuration that ships" gains the clause **"and on
the 7B model only"**, and `REPORT_DRAFT` §4.4a must carry the metric property
in the first bullet above as the explanation. If it comes back **<= 0.90**,
the effect is cross-model and §21.6's paragraph stands as written. Between
those, inconclusive, per §16.2's band.

---

## 25. `F06#1` names `F01` three times out of three — pre-registered test, 2026-11-10 08:11

### 25.1 The observation

| when | script | what happened |
|---|---|---|
| detector reproducibility, §23 | `detector_reproducibility.py`, classes in order F01, F06, F07, F08 | F06 **trial 1** named `F01`; trials 2-20 all correct |
| cross-provider smoke, §24 | `closure_ablation.py`, 5 incidents per class, same order | **F06#1** dropped, detector said `F01` |
| cross-provider full run, §26 | `closure_ablation.py`, 15 incidents per class, same order | **F06#1** dropped, detector said `F01` |

Three independent runs, three different scripts or configurations, **the same
incident and the same wrong class every time.** §23.3 filed this under a
generic "first trial of a block" pattern. It is not generic: F06#1 is
*reproducible*, which makes it a defect with a mechanism rather than a
stochastic miss.

### 25.2 The candidate mechanism, and why the obvious test discriminates it

In all three runs **F06 ran immediately after a block of F01 injections** —
20, 5 and 15 of them. `PRD.md` §6 gives F01 the signal *"error rate on LLM
spans > 20% over 60s"*, which is a windowed PromQL read. A window that still
contains the tail of the preceding F01 block would make F01's rule fire on
the first F06 evaluation, and F01 would win because it is a real signal on
stale data rather than a false one on fresh data.

This project has been bitten three separate times by a windowed metric read
over a window shorter than its own contents, which is why this is the first
candidate rather than a clever one.

**The test is to run F06 with nothing before it.** Nothing else changes.

### Prediction, fixed before the run

1. **If the mechanism is F01 residue: F06 detects correctly on trial 1, 5/5.**
   The contamination cannot exist if no F01 ran.
2. **If the mechanism is a generic cold start: F06 trial 1 misses again**,
   and the verdict may be anything.
3. **The discriminating observation is the verdict, not the rate.** A miss
   that says `INSUFFICIENT_EVIDENCE` supports a cold-start account; a miss
   that says `F01` with no F01 anywhere in the run refutes both and means the
   residue is older than this process.
4. **F07 run first, also 5 trials, as the paired control.** §23 saw F07 miss
   twice when it followed F06. F07's detector reads a prompt hash and **no
   PromQL** (`REPORT_DRAFT` §4.1), so a window-contamination account predicts
   F07 is **unaffected** by ordering and should miss at about the same rate
   whether it runs first or not. If F07-first comes back 5/5, the window
   account does not cover F07 and §23.3's single pattern is really two.

No model is called; this is detector-only and costs about three minutes.

### 25.3 Result: both predictions resolved, and §23.3's one pattern is two

Artifacts `harness/reports/detector-f06-first.json`,
`detector-f07-first.json`, `detector-f07-why.json`.

| run | order | result |
|---|---|---|
| F06 alone, 5 trials | **nothing before it** | **5/5**, trial 1 included |
| F07 alone, 5 trials | **nothing before it** | **3/5** — trials **1 and 2** missed, both `INSUFFICIENT_EVIDENCE` |
| F07 alone, 6 trials | immediately after the F07 run above | **6/6** |

**Prediction 1 is confirmed and the F06 mechanism is identified.** With no
F01 before it, F06 detects correctly on its first trial. The `F06#1` → `F01`
misdetection that reproduced three times out of three is caused by **the
preceding block of F01 injections**, and the candidate mechanism in §25.2
stands: F01's signal is an error rate over a 60-second window, and that
window still contains the tail of the F01 block when the first F06 is
evaluated, so F01's rule fires on real-but-stale data and wins.

**Prediction 4 went the other way, which is the more useful outcome.** F07
run first missed trials 1 and 2 anyway — the *same two positions* and the
*same verdict* as in §23, where F07 followed F06. **F07's misses are
ordering-independent**, so §23.3's single "first trial of a block" pattern is
really **two unrelated phenomena** that happened to look alike:

1. **F06 is contaminated by what ran before it.** Fixed by ordering, or by
   waiting out the window. Not a property of F06's detector.
2. **F07 needs to have been injected recently to be detectable.** Nothing
   before it in the process matters; what matters is whether F07 itself has
   been exercised. The third run — six trials immediately after the second —
   is **6/6**, so once F07 has been through two cycles it stays detectable.

F07 pooled across every run in this document: **27 of 31 = 0.87**, with all
four misses at trial 1 or 2 of a cold F07.

### 25.4 The branch is still unidentified, and that is recorded rather than guessed

`prompt_regression.py` has three distinct paths to `INSUFFICIENT_EVIDENCE` —
an unreachable control interface (`live_files` empty), a baseline holding
digests without the text (`not repairable`), and too few changed files — and a
bare verdict string cannot tell them apart. I had a hypothesis for which one
fires and **it is not written here as a finding**, because the honest way to
settle it is to read the detector's own reason.

So `detect_once` now returns the detector's first reason and the script prints
it on every miss (`detector_reproducibility.py`;
`tests/test_detector_reproducibility.py::test_detect_once_returns_the_detectors_first_reason`
covers it). The instrumented run then came back **6/6 with no miss to
explain**, which is not a failure of the instrumentation — it is evidence in
its own right, because it rules out F07 missing two in every six
unconditionally.

**The decisive test needs a cold F07 and is not run here.** It requires either
restarting the target's stack or leaving F07 untouched long enough to go cold,
and a stack restart is a mutation of the target that is not mine to make
unattended while nothing is broken. Named as the next step, with the
instrumentation already in place to read the answer when it is taken.

### 25.5 What this changes elsewhere

- **§23.3's localization is narrowed, not withdrawn.** The positional
  observation was real; the single mechanism behind it was not.
- **§19.5's windowed-PromQL proposal was right about F06 and wrong about
  F07.** It is now a measured mechanism for one class and refuted for another.
- **The ablation's drop rule should record the detector's reason too.** It
  currently writes *"detector said X, not the injected class"* into
  `run.dropped`, which is exactly the bare-verdict problem this section just
  instrumented away in the other script. Not changed here: the ablation's
  measured path must not be edited between runs that are being compared
  (`AGENTS.md`, and §7's control-arm rule). It belongs in the next
  pre-registration.
- **`REPORT_DRAFT` §4.1's F06 row is fine and its F07 row needs a caveat.**
  F06's 19/20 is an artefact of the measurement's ordering and would be 20/20
  in isolation; F07's 0.90 is a property of the system on a cold class.

---

## 26. Cross-provider run, 2026-11-10 — F01 is complete and decisive, and the rest was stopped by a daily token cap

Artifact `harness/reports/closure-ablation-groq-full.json`, model
`groq:openai/gpt-oss-120b`, arms A/B/E, 4 classes x 15 incidents x 3 reps
pre-registered. **It did not finish.** 142 of 540 diagnoses, 28 transient
retries absorbed, then an abort.

### 26.1 Why it stopped, and that the stop was my planning error

```
ABORTING after 9 transient LLM failures, the last: HTTP 429
Rate limit reached for model `openai/gpt-oss-120b` ... service tier
`on_demand` on tokens per day (TPD): Limit 200000, Used 196518,
Requested 4511 (all 3 keys tried). The fault has been reverted.
```

**Groq's on-demand tier allows 200,000 tokens per day per key.** Three keys
are configured, so about 600k/day. At a measured 3,480 prompt tokens per
diagnosis the pre-registered run needs **about 2.0 million tokens — roughly
3.3 days of the entire quota.** It was never going to finish.

**I sized this run on wall-clock time and never checked the token budget**,
which is the error. Worse, the smoke that preceded it consumed 191,799
tokens — essentially one whole key's daily allowance — so the real run started
already two-thirds through the day's capacity. The §16 pre-registration says a
cloud result worse than the local one is a result and not a configuration
error; it says nothing about a run that cannot physically complete, and the
honest label for that is a planning failure rather than a finding.

The abort itself behaved correctly: **the fault was reverted**, the artifact
was flushed, and the partial run is analysable — which is what the
flush-every-incident change of 2026-11-09 was for.

### 26.2 The F01 block is complete, properly powered, and decisive

15 incidents x 3 reps x 3 arms = **135 observations, every cell filled.**

| | local `qwen2.5:7b-instruct` | **`gpt-oss-120b`** |
|---|---|---|
| arm A, F01 agreement | 45/45 | **45/45** |
| arm B, F01 agreement | **18/45 = 0.40** | **45/45 = 1.00** |
| arm B, F01 closure | **36/45 = 0.80** | **45/45 = 1.00** |
| arm B, F01 abstentions | high (§16.1) | **0** |
| arm E, F01 agreement | 45/45 | **45/45** |

§16's predictions, scored:

| § | Prediction | Observed | Verdict |
|---|---|---|---|
| 16, 1 | arm A at or near 1.00 **on all four classes** | 1.00 on F01; F06-F08 never ran | **partial** — held where measured |
| 16, 2 | arm B's agreement rises above the 7B's **0.40** on F01 | **1.00** | **MET, decisively** |
| 16, 3 | arm B's closure moves less than the 7B's 0.80; **>= 0.95** means the sensitivity was a 7B artefact | **1.00** | **MET** |
| 16, 4 | no prediction on F07 or F08 | still none, and now none measured either | n/a |
| 16, 5 | a worse cloud result is a result | not exercised — the cloud result is better | n/a |

**So on F01, closure sensitivity to size-matched noise is a small-model
artefact.** The 120B model is completely immune to the noise that takes the 7B
from 45/45 to 18/45, in every arm, with zero abstentions.

### 26.3 §24.3's pre-registered consequence fires, and only as far as F01

§24.3 fixed this in advance: *"if arm B's closure comes back >= 0.95, §21.2's
'met under the configuration that ships' gains the clause 'and on the 7B model
only'."* It came back 1.00 on F01, so **the clause is owed** — and the
pre-registration scoped it to a run that would have covered four classes,
while what exists covers one.

The precise statement the report may make:

> On `F01`, the size-matched-noise effect is absent on
> `openai/gpt-oss-120b` (45/45 in every arm, 15 incidents x 3 reps) and
> present on `qwen2.5:7b-instruct` (arm B 18/45 agreement, 36/45 closure).
> **The effect is therefore model-dependent on at least one of the four
> classes.** Whether it is model-dependent on `F06`, `F07` or `F08` is
> **unmeasured**: the cross-provider run was stopped by a provider token cap
> before reaching them.

**This does not overturn §21.2 and must not be reported as though it does.**
The +0.19 and +0.21 drops are pooled over four classes, and §19.4 and §21.3
locate the interesting part of the effect in **F07**, which has no
cross-provider measurement at all. F01 vanishing at 120B removes one
contributor to the pooled drop and says nothing about the others.

### 26.4 What the remaining measurement costs, and the design that fits

At 3,480 tokens per diagnosis against ~600k tokens/day:

| design | calls | tokens | days of full quota |
|---|---|---|---|
| the run as pre-registered, 4 classes x 15 x 3 | 540 | ~2.0M | **3.3** |
| the three unmeasured classes, 15 x 3 | 405 | ~1.5M | 2.5 |
| all four classes at **reps = 1** | 180 | ~0.67M | 1.1 |
| **F07 only, 15 x 3** | 135 | ~0.50M | **0.8** |

**The recommendation is F07 only.** It is the class carrying the effect
(§21.3, §19.4), it is the one class with no cross-provider data, it fits
inside a single day's quota with headroom, and at 15 incidents x 3 reps it is
as well powered as the F01 block that just settled F01. Dropping reps to 1
across four classes buys breadth at the price of being unable to separate a
model difference from the draw, which is the mistake §16.3 already refused
once for the smoke.

The alternative is a paid tier, which is the owner's call and not a
measurement decision.

### 26.5 Two things left open by the stop

- **The F06 block never ran**, so the only F06 cross-provider observation is
  the dropped `F06#1` — which §25.3 has now explained as F01-window
  contamination rather than a model property. F06 is unmeasured.
- **§24's arms-B-and-E coincidence is still open.** On this run both are
  perfect on F01 (48/48 and 46/46 including the F06 partial), so the data
  cannot discriminate a shared-frame bug from two arms that simply both
  succeed. It needs a class where the arms differ, which means F07.

---

## 27. Pre-registration: the F07-only cross-provider run, written 2026-11-10 before it starts

§26.4 recommended this design and the owner chose it. Registered here with
its predictions **before any of its numbers exist**, which is the only thing
that makes §24.2's complaint about itself not repeat.

### 27.1 The design, and the budget arithmetic corrected

```
harness/closure_ablation.py --classes F07 --incidents 15 --reps 3
    --arms ABE --provider groq --model openai/gpt-oss-120b
```

135 diagnoses. One class, the same 15x3 shape as the F01 block that settled
F01 in §26.2, so it is as well powered as the result it is being compared
against.

**A correction to §26.1's arithmetic, measured rather than assumed.** §26.1
said three keys give "about 600k/day" on the strength of the limit being
200,000 tokens per day per key. That was an assumption: an org-wide counter
would have produced exactly the same abort message, because the rotation
tries every key and reports the last failure. It was tested directly today -
four requests on key 0, then one on key 1, reading
`x-ratelimit-remaining-requests` each time:

```
key 0: 998, 997, 996, 995        <- its own counter decrements
key 1: 998                       <- untouched by key 0's four
```

**The counters are per key.** So ~600k/day across three stands, and at a
measured 3,480 prompt tokens per diagnosis this run needs **~470k, with
~130k of headroom** - about 37 retries' worth. All three keys' daily
counters had reset before the run started.

> **WRONG, AND CORRECTED BY §28.1 THE SAME DAY.** The counter read above is
> `x-ratelimit-remaining-requests`, the **requests**-per-day limit, which is
> per key. The **tokens**-per-day limit is per **organization**, which the
> next abort message said in words I had truncated out of §26.1 with an
> ellipsis. The day's budget is 200,000 tokens in total, not 600,000. The
> paragraph is left standing because what it got wrong - presenting an
> inference about one limit as a measurement of another - is the error worth
> keeping on the page.

### 27.2 Why F07 and not breadth

F07 is the class §19.4 and §21.3 locate the pooled effect in, it is the one
class with no cross-provider data, and §26.5 needs a class where arms B and E
*differ* to discriminate its shared-frame suspicion. Dropping reps to 1 for
four classes would buy breadth at the price of being unable to separate a
model difference from the draw, which §16.3 already refused once.

**F06 and F08 remain unmeasured cross-provider after this run**, and the
report must keep saying so.

### 27.3 The predictions

| # | Prediction | Why it is risky |
|---|---|---|
| 1 | arm A's agreement on F07 >= 0.93 (at least 14 of 15 incidents) | arm A is 1.00 locally and 1.00 on F01 at 120B; below 0.93 would mean the control frame itself does not transfer, and nothing in this document would survive that |
| 2 | **arm B's closure on F07 is the discriminating number.** >= 0.95 and F01's result generalizes to the class that carries the effect; <= 0.90 and the effect is cross-model where it matters most; between, inconclusive per §16.2's band | locally this is 0.79 and 0.81. A 120B model could go either way and the two outcomes say opposite things about §21.2 |
| 3 | arms B and E give **different** name distributions on F07 | they were byte-identical on §24's 18-observation smoke. Identical again at 135 observations is to be treated as a suspected harness fault and inspected in code, **not** reported as a finding |
| 4 | in arm B, `INSUFFICIENT_EVIDENCE` outnumbers confident-wrong answers | this is §24.3's metric-orthogonality claim as a test. At 120B on F01 there were zero abstentions because nothing was hard; on F07 the model should decline rather than guess if the claim is right |
| 5 | 1 or 2 of the 15 incidents are dropped by the detector, concentrated at the start | F07's measured detection rate is 27/31 = 0.87 with every miss at trial 1 or 2 of a cold class (§25.3) |

**The warm-up is deliberately NOT added**, even though §25.3 identified it and
`one_incident` already warms up for F06 and F01. Adding a warm-up to F07
between two runs that are being compared is exactly the tuning this document
forbids itself (§7), and it would change the measured path mid-comparison
(`AGENTS.md`). It belongs in its own pre-registration with its own run.

### 27.4 What is recorded whatever happens

If the run aborts again, the partial artifact is analysable per the
flush-every-incident change and the abort is recorded as what it was - §26.1
is the precedent, and a planning failure gets that label rather than a
finding's.

---

## 28. The F07 run aborted at 3 incidents, §27.1's correction was itself wrong, and the 28 diagnoses it did produce say something the four classes pooled could not

Artifact `harness/reports/closure-ablation-groq-f07.json`, model
`groq:openai/gpt-oss-120b`, arms A/B/E. **29 of 135 diagnoses, 28 usable,
one incident dropped by the detector, then the same provider wall as §26.**

### 28.1 I got the budget wrong a second time, in a worse way

§27.1 said the daily token limit is per key and claimed to have *measured*
it. The abort message:

```
Rate limit reached for model `openai/gpt-oss-120b` in organization
`org_01m15ty1wke7mv33003mt6w6dq` service tier `on_demand` on tokens per
day (TPD): Limit 200000, Used 196017 ... (all 3 keys tried)
```

**The TPD limit is per ORGANIZATION.** All three keys belong to one org, so
the day's budget is **200,000 tokens in total, not 600,000.**

> **ITS SECOND SENTENCE IS WRONG, AND §29.11 CORRECTS IT THE SAME DAY.**
> That the limit is per organization holds. That **all three keys belong to
> one organization was never checked** - it was inferred from one org id
> appearing in one message. Two artifacts written five hours apart on
> 2026-11-10 carry two **different** org ids, each independently drained to
> ~196k of its own 200,000. The keys span at least two organizations and the
> day's budget is **at least 400,000 tokens**, not 200,000. Left standing
> because the error is the same shape a fifth time: one organization's limit
> measured, the whole account's budget reported.

What §27.1 actually measured was `x-ratelimit-remaining-requests` — the
**requests**-per-day counter, which *is* per key. Two different limits, and I
generalised from the one I could read to the one I needed. That is worse than
§26.1's error, because §26.1 was an untested assumption while this was an
assumption dressed as a measurement, and the sentence "tested directly today"
made it harder to doubt rather than easier.

The decisive evidence was in §26.1's own quoted text, and **I truncated the
message with an ellipsis immediately before the words "in organization"**.
Both errors were avoidable by reading what was already on the page.

**The real budget:** 200,000 tokens/day across all keys, at a measured 3,609
prompt tokens per diagnosis = **about 54 diagnoses per day**. The
pre-registered 135 is a 2.5-day job and could not have run today under any
key arrangement. §26.4's whole table is wrong by a factor of three and is
superseded by §28.6.

### 28.2 What the 28 diagnoses show

Three incidents complete in all three arms (F07#1, #2, #4), a fourth
(F07#3) dropped by the detector, a fifth cut off mid-arm.

| arm | items | agreement | closure (detector) | abstentions | **confident-wrong** | mean confidence | evidence cited |
|---|---|---|---|---|---|---|---|
| A control | 35 | **10/10 = 1.00** | 10/10 = 1.00 | 0 | **0** | **0.90** | 4-5 |
| B size-matched noise | 35 | **3/9 = 0.33** | **9/9 = 1.00** | **6** | **0** | **0.58** | 2 |
| E same items removed | 4 | **0/9 = 0.00** | **9/9 = 1.00** | **9** | **0** | **0.52** | 2 |

**Zero confident-wrong answers in 18 degraded diagnoses** (arms B and E,
F07 only). The local 7B model's arm B produced 20, 46 and 40 confident-wrong
answers across the three full runs at mean confidences of 0.78, 0.87 and
0.86 (§21.4) - out of roughly 171 arm-B diagnoses each, and **pooled over
four classes**, so that is a rate of order 0.25 against this run's 0 of 18
on one class. Stated that way rather than as 106 against 0, which would
compare a four-class total with a one-class sample. The 120B model
responds to diluted or missing discriminating evidence by **declining** —
which is the escalate-to-a-human path the architecture is built around — and
its stated confidence tracks the degradation, 0.90 to 0.58 to 0.52.

**This is the headline safety regression reversing with model scale**, and it
is the thing the F01 block could not show, because nothing about F01 was hard
enough for the 120B model to decline anything at all (§26.2: zero
abstentions, 45/45 in every arm).

### 28.3 The primary outcome saturated, so it measured nothing here

`closed_detector` is **1.00 in every arm**, including the arm whose agreement
is 0.00. §24.3 predicted exactly this and called it a property of the metric;
this is that property measured on the class that carries the effect.

Closure asks only whether the diagnosis cited the evidence that discriminates
the injected class. An abstention that cites it scores 1.00. So on a model
that abstains cleanly, **the pre-registered PRIMARY cannot distinguish a
correct diagnosis from a refusal**, and the informative outcomes are
agreement and stated confidence.

§16's prediction 3 scored ">= 0.95 means the sensitivity was a 7B artefact."
Arm B came back 9/9. **The band fires and the inference it licensed does
not**: the honest reading is that the metric saturated on this model, not
that grounding survived the noise — agreement fell from 1.00 to 0.33 in the
same nine diagnoses. A pre-registered threshold can be met by a mechanism the
pre-registration did not anticipate, and this is one.

### 28.4 §27.3's predictions, scored

| # | Prediction | Observed | Verdict |
|---|---|---|---|
| 1 | arm A agreement >= 0.93 | 10/10 on 4 incidents | **held where measured** |
| 2 | arm B closure >= 0.95 or <= 0.90, discriminating | 1.00 — but see §28.3 | **band met, inference void** |
| 3 | arms B and E give **different** name distributions | 3 F07 + 6 abstain vs 0 F07 + 9 abstain | **MET** |
| 4 | abstentions outnumber confident-wrong in arm B | 6 against **0** | **MET decisively** |
| 5 | 1-2 incidents dropped, **concentrated at the start** | 1 dropped, at **#3**, after #1 and #2 both succeeded | **count held, position did not** |

**Prediction 3 settles §26.5.** The arms are genuinely different frames
producing genuinely different behaviour, so the smoke's byte-identical
distributions were the same 18 observations defeating both arms, not a
harness fault passing one frame twice. That suspicion is closed.

**Prediction 5's position failed, and one drop cannot adjudicate it.** F07
had been exercised hours earlier by §25's runs, so a cold-class account
predicts no drop at all; a drop at #3 after two clean incidents fits neither
the positional story nor a flat 0.87 especially well. Recorded as not
supporting §25.3's mechanism rather than refuting it, because n=1.

### 28.5 Power, stated rather than implied

Three incidents. `perfect_arm_ceiling` on three clusters is
**1 - 0.05^(1/3) = 0.632** — a perfect arm here bounds the per-incident
failure rate only below 63%, which is no bound at all. The 18 degraded
diagnoses are six clusters, so the zero-confident-wrong count bounds that
rate below **0.393**.

**So §28.2 is a direction, not a rate, and §16.3's rule binds: these numbers
are not quotable in the report as measurements.** What is quotable is the
qualitative contrast with a named sample size — 0 confident-wrong in 18
against 106 in the local runs' equivalent arms — and only with the 3-incident
denominator in the same sentence.

### 28.6 The design that fits 200,000 tokens, and what it gives up

| design | diagnoses | tokens | fits one day |
|---|---|---|---|
| §27's, F07 15x3 arms ABE | 135 | ~490k | no, 2.5 days |
| F07 15x3 arms AB | 90 | ~350k | no, 1.8 days |
| **F07 15x1 arms AB** | **30** | **~117k** | **yes, with 40% headroom** |
| F07 15x1 arms ABE | 45 | ~160k | marginal once retries are counted |

**The recommendation is 15 incidents x 1 rep, arms A and B.**

§26.4 rejected reps=1 and the reason it gave was wrong. It said reps=1 would
leave the run "unable to separate a model difference from the draw" — but
**the draw varies per incident, not per rep**, and since the pairing-unit fix
of 2026-11-10 the unit of analysis *is* the incident, with reps collapsed by
majority. Reps buy cell stability, not power. §16.3's objection was to **5
incidents** at one rep, and transplanting it onto 15 incidents at one rep was
sloppy.

**What reps=1 genuinely gives up**, named rather than buried: the within-cell
spread that §7's refutation condition reads. Arm A's 10/10 across three reps
of four incidents says that spread is nil here, which is evidence and not a
guarantee. Arm E is dropped because prediction 3 already answered the only
question that needed it.

**Nothing is being run on this design yet.** It changes the pre-registered
shape and the quota is spent (196,017 of 200,000 used on a rolling window),
so it needs its own registration and the owner's agreement first.

---

## 29. Pre-registration: F07, 15 incidents x 1 rep, arms A and B, written 2026-11-10 before the quota resets

The owner approved §28.6's design. Registered before the run, as §27 was,
and this time with the **outcome variable changed on the record** rather than
chosen after seeing which one moved.

### 29.1 The design

```
harness/closure_ablation.py --classes F07 --incidents 15 --reps 1
    --arms AB --provider groq --model openai/gpt-oss-120b
```

30 diagnoses. Measured cost from §28: arm A 4,073 and arm B 3,739 prompt
tokens per diagnosis, so **~117k prompt tokens, ~125k with completions**,
against the organization's 200,000/day (§28.1). Fits one day with headroom
for retries.

**Arm E is not run.** §28.4's prediction 3 answered the only question that
needed it, and its absence buys the headroom that makes 15 incidents fit.

### 29.2 The primary outcome for this run is AGREEMENT, not closure

§28.3 measured `closed_detector` at 1.00 in an arm whose agreement was 0.00.
On this model the pre-registered PRIMARY **cannot distinguish a correct
diagnosis from a refusal**, so continuing to lead with it would be reporting
a number known in advance to be uninformative.

**So for this run, and only on the record here before it starts:** the
primary outcome is **agreement with the injected class**, and closure is
reported as a secondary that is expected to saturate. This is a change of
outcome variable mid-programme, which is exactly the move that invalidates
a result when it is made *after* seeing the data - it is made here before,
with the reason being a measured property of the metric (§28.3) rather than
which number came out better.

**The pooled four-class result in §21.2 and §21.6 is unaffected and is not
restated on this basis.** It was measured on closure, on the local model,
where closure does not saturate - arm B scored 0.79 and 0.81 there.

### 29.3 The predictions

| # | Prediction | If it fails |
|---|---|---|
| 1 | arm A agreement >= 0.93 (at least 14 of 15) | the control frame does not transfer and nothing downstream survives |
| 2 | **PRIMARY: arm B agreement <= 0.50** | at >= 0.80 the collapse in §28.2 was the 3-incident draw, and the model-scale failure-mode story is withdrawn |
| 3 | arm B confident-wrong count <= 2 of 15 | at >= 6 the zero-confident-wrong result was the draw, and §28.2's safety reading goes with it |
| 4 | closure (detector) >= 0.95 in **both** arms | below that, §28.3's claim that the metric saturates on this model is wrong, and the primary should have stayed closure |
| 5 | arm A mean confidence exceeds arm B's by >= 0.15 | the confidence signal does not track degradation on this model |
| 6 | 1 to 3 of the 15 incidents dropped by the detector | outside that range, F07's 0.87 detection rate (§25.3) does not hold at this n |

Prediction 4 is deliberately a prediction that the **metric fails**. If it
holds, the report says so; a saturated primary is a finding about the
measurement, and §22's audit exists because nothing had tested the
measurement before.

### 29.4 Analysis fixed in advance

- McNemar, exact, **paired on the incident** - which with `reps=1` is the
  diagnosis, so the pairing-unit fix is a no-op here and the cells are
  unambiguous.
- A perfect arm reports the Clopper-Pearson one-sided bound, not a
  zero-width bootstrap interval (`perfect_arm_ceiling`). At 15 incidents
  that bound is **0.181**; at 13, if two drop, **0.206**.
- Dropped incidents are reported as dropped, not refilled. Refilling after
  seeing which ones dropped would select on the outcome.

### 29.5 What this run still cannot answer

`F06` and `F08` remain unmeasured cross-provider and the report must keep
saying so. One cloud model, one scale. And `reps=1` gives up the within-cell
spread that §7's refutation condition reads - §28's arm A was 10/10 across
three reps of four incidents, which is evidence that the spread is nil on
this model and not a guarantee.

### 29.6 When it runs

Groq exposes **no remaining-tokens-per-day header** - only TPM (8,000) and
RPD (1,000), both per key, which is what misled §27.1. The only reading of
the daily figure is the `Used N` inside a 429, so the reset cannot be
watched directly.

The window is a rolling one: the abort at 06:00 UTC on 2026-11-10 reported
196,017 used, and the ~100k spent between 00:05 and 02:00 UTC that day ages
out at 00:05 to 02:00 UTC on 2026-11-11. **The run is therefore armed to
start once a cheap probe confirms headroom, no earlier than 06:15 UTC on
2026-11-11**, by which point the whole of the previous day's spend has aged
out. The probe costs about 30 tokens and tests for ~6k of headroom by asking
for a large completion the model will not use - the admission check reads the
request, the accounting reads the actual tokens.

**Measured while writing this, and it refines the window.** The probe was
run once at 05:55 UTC on 2026-11-10 - about 25 minutes after the 429 that
reported 196,017 of 200,000 used - and it was **admitted**, spending 111
tokens. So the window is not a midnight bucket: capacity returns
continuously as individual spends age out, which is consistent with the
`try again in 13m11s` the abort offered. ~6k was already free 25 minutes
later.

That does **not** license starting early. The probe can only ever test for
about 6k, because a request above the 8,000-token-per-minute limit is
refused by the minute check instead and never reaches the daily one, so
there is no probe that proves 125k of headroom. The clock gate stays where
it is: by 06:15 UTC on 2026-11-11 the whole of the previous day's spend has
aged out, and the run does not need to guess.

**If the window turns out not to be 24h rolling, the run aborts the way §26
and §28 did** - artifact flushed per incident, fault reverted - and the abort
is the measurement of the window, recorded as such rather than as a finding
about the model.

### 29.7 AMENDMENT, written 2026-11-10 07:30 UTC, before the run: the rail changes, the model does not

§29.6 above armed a 24-hour waiter on the Groq daily cap. The owner asked
the obvious question - **why wait** - and the answer is that there was no
good reason. The cap is a property of ONE ROUTE to the model, not of the
model, and the route was never checked for alternatives before a day was
committed to waiting on it. That is the error in §29.6, and it is a worse
class of error than §27.1's: that one mistook which limit it had measured,
this one did not look.

**What was checked, 07:14-07:20 UTC.** OpenRouter serves
`openai/gpt-oss-120b` from 26 upstreams, and **Groq is one of them**. A probe
returned HTTP 200 with `provider: "Groq"` in the body, 96 tokens, cost
$0.0000234. Same model id, same vendor, a billing rail the organization's
200,000/day does not touch. The run costs an estimated **$0.03** there.

**So the run is `--provider openrouter --model openai/gpt-oss-120b`, pinned
to the `groq` upstream, today.** Everything else in §29.1-§29.5 is unchanged:
same classes, same 15x1, same arms, same primary outcome (agreement), same
six predictions, same analysis.

**Why the pin is not optional.** Those 26 upstreams quantize from int4 to
bf16. Unpinned, arm A of incident 7 could be served by an fp4 host and arm B
by a bf16 one, and the A-vs-B contrast - the whole content of this run -
would be confounded by hardware that nothing in the artifact names. An
unpinned OpenRouter run would be strictly worse than waiting. `payload
["provider"] = {"order": ["groq"], "allow_fallbacks": false}`, set by
`KAVACH_OPENROUTER_PIN` and scoped to a run rather than written into the
provider table, because pinning the row would route this provider's default
`anthropic/claude-sonnet-4.5` to an upstream that has never served it.

**The pin is recorded, not asserted.** `LlmResponse.provider` now carries
`openrouter>Groq` when the body names an upstream, so if the pin is ever
ignored, dropped or misspelled the artifact says which host actually answered
each of the 30 calls. Four tests cover it and none needs a key (`PL-02`).

**WHAT THIS RUN CANNOT ESTABLISH, and it is a real cost.** That
OpenRouter-to-Groq is identical to Groq-direct **cannot be verified today,
precisely because the direct rail is capped** - there is nothing to compare
against. The specific risk is `reasoning_effort`: `gpt-oss-120b` spends
hidden thinking tokens (18 of them on a two-word probe), and if the two rails
default differently the model thinks a different amount for the same prompt.

Two things bound that cost, and neither is a dismissal:

- **The primary outcome is unaffected.** §29.3's prediction 2 is arm A
  against arm B *within this run*, both arms on the same rail. A rail
  difference shifts both arms together and cannot manufacture the contrast.
- **The continuity with §28 is affected.** §28's 10/10 -> 3/9 was measured on
  Groq-direct, so comparing §30 to it crosses a rail as well as an n. §28 is
  3 incidents and already carries §28.5's statement that its numbers are not
  quotable as rates; this adds a second reason, and the report must say both.

The equivalence check - the identical design on Groq-direct once the cap
lifts - is a separate run with its own pre-registration, and it is NOT
assumed here. Until it exists, §30 reports a rail it did not control for.

### 29.8 SECOND AMENDMENT, written 2026-11-10 07:45 UTC, before the run: the Groq pin was unaffordable, and three probes in a row measured the wrong thing

§29.7's run was launched and **aborted after 1 incident on HTTP 402**:
`"This request requires more credits, or fewer max_tokens. You requested up
to 2048 tokens, but can only afford 1455"`. The OpenRouter key is
`is_free_tier: true`. Artifact kept as
`closure-ablation-openrouter-groq-f07-ab-ABORTED.json`; the target was left
clean and all four injectors read `clear` afterwards.

**THE ERROR, AND IT IS THE SAME ERROR THREE TIMES.** §29.7 justified the rail
on a probe that asked for `max_tokens: 20`. OpenRouter's affordability check
reserves against the **requested** `max_tokens`, which a real diagnosis sets
to 2048 - a fact written in this repository's own provider table, in the
comment explaining why `max_tokens` is bounded at all, which names HTTP 402
and quotes almost this message. It was read earlier the same morning and not
connected.

Then the correction was botched twice more:

1. A "realistic" probe was built with 540 lines of filler and sent **16,316**
   prompt tokens. Groq answered HTTP 413 - *tokens per minute (TPM): Limit
   8000, Requested 17172* - which is the **per-minute** ceiling and says
   nothing whatever about the daily budget. That probe was briefly taken as
   evidence Groq was still capped. It was not evidence of anything.
2. The same probe reached OpenRouter **unpinned**, succeeded, and was served
   by `PrimeIntellect`. Had the pin been set it would have 402'd again.

A probe sized to §28's measured 3,739-4,073 prompt tokens, with the real
2048 output budget and the real strict schema, finally measured the thing:

```
pin=groq            FAIL HTTP 402 (unaffordable)
pin=deepinfra       OK   openrouter>DeepInfra      prompt=3895  bf16   22.3s
pin=primeintellect  OK   openrouter>PrimeIntellect prompt=3926  fp4     6.1s
pin=(none)          OK   openrouter>Crusoe         prompt=4471  bf16    5.8s
```

**The common shape of all three errors: a quantity adjacent to the one that
mattered was measured, and the generalisation was not checked.** §27.1 read
the requests counter and reported the tokens limit. §29.7 read a 96-token
call and reported that a 4,000-token one would work. The 16k probe read the
per-minute ceiling and reported the daily one. Logging it here because the
pattern, not any single instance, is the finding.

**THE RUN AS IT NOW STANDS.** `--provider openrouter --model
openai/gpt-oss-120b`, `KAVACH_OPENROUTER_PIN=deepinfra`, everything in
§29.1-§29.5 unchanged: F07, 15x1, arms AB, primary outcome agreement, the
same six predictions, the same analysis. Estimated cost under $0.01.

**bf16 is a stronger host to report than Groq was, not a weaker one.**
DeepInfra serves this model at bf16 - the unquantized native precision -
whereas Groq's quantization is listed `unknown` and is not published. A third
party can reproduce a bf16 result; they cannot reproduce an undisclosed one.
So the rail change costs continuity with §28 and buys specificity.

**WHAT IS NOW UNCONTROLLED, stated before the data exists.** §28 ran on
Groq-direct at an undisclosed quantization; §30 runs at bf16 through a
router. Comparing them crosses an n (3 to 15), a rail, and a precision.
§29.3's primary is arm A against arm B *within* §30, both arms on one host,
and that comparison is untouched by any of it. Every statement relating §30
to §28 must name all three differences, and §28's numbers remain not
quotable as rates (§28.5).

**The free-tier balance may not last 15 incidents.** If it does not, the run
aborts as §26, §28 and §29.7 did - artifact flushed per incident, fault
reverted - and the partial is reported as a partial. That is a funding
boundary, not a result about the model, and it will be labelled as one.

### 29.9 THIRD AMENDMENT, 2026-11-10 07:45 UTC: the same error a fourth time, and the wait was right for a reason never given

The bf16 run aborted after **2 incidents** on the same HTTP 402, `"can only
afford 1770"`. The OpenRouter account reads `total_credits: 0`, `total_usage:
$0.198` - it was never funded and had roughly four diagnoses of dribble left.
Artifact `closure-ablation-openrouter-deepinfra-f07-ab.json`, 4 usable
observations, `complete: false`. Target clean afterwards, all four injectors
`clear`.

**§29.8 named the pattern and the very next action repeated it.** The probes
in §29.8 established that **one** correctly-sized call is served. The run
needs **thirty**. Nothing in that probe spoke to the thirtieth, and the
balance was read in the same session - `is_free_tier: true`, `total_credits:
0` - and not connected. Fourth instance:

| | measured | reported |
|---|---|---|
| §27.1 | the requests-per-day counter | the tokens-per-day limit |
| §29.7 | a 96-token call is served | a 4,000-token call will be |
| §29.8a | the 8,000/min ceiling | the 200,000/day budget |
| §29.9 | one call is affordable | thirty calls are |

Writing the pattern down did not stop it. What would have: the probe's
unit was never the run's unit, and no probe was ever asked to be.

**THE TEMPTING FIX IS FORBIDDEN AND IS NOT TAKEN.** The 402 is a reservation
against `max_tokens: 2048`; dropping it to 1024 would be admitted. The
provider table records why 2048 exists - a reasoning model spends hidden
thinking tokens from the same budget, and a smaller cap returned answers cut
mid-string. Halving the output budget to fit a free tier would be weakening a
measurement to make it pass, which `AGENTS.md` forbids outright. The budget
stays; the run waits.

**THE ROUTE SURVEY, now complete and measured rather than assumed.**

| rail | serves `gpt-oss-120b` | state |
|---|---|---|
| groq direct | yes | **free**, 200k/day org-wide, spent until ~00:05-06:00 UTC 11 Nov |
| openrouter | yes, 26 upstreams | credits 0, ~4 diagnoses of dribble |
| ollamacloud | `gpt-oss:120b` | HTTP 402, add credits |
| tokenrouter | yes | HTTP 403, $0.00 remaining |
| nvidia | **no** - `gpt-oss-20b` only | would be a different model |
| opencodezen | **no** - 45 models, none | - |

**So the wait was right, and the reason given for it in §29.6 was not the
reason.** §29.6 said wait because the cap is per-organization. The true
reason is that every other route to this model is unfunded, which §29.6 never
checked and §29.7-§29.9 then checked four times badly. A correct conclusion
reached through an unchecked premise is not a correct inference, and the
record says so rather than quietly keeping the right answer.

**The run is re-armed on Groq-direct for 06:15 UTC on 11 Nov**, §29.1-§29.5
unchanged, `KAVACH_OPENROUTER_PIN` unset. One day's 200,000 tokens covers
~105k of prompt plus completions with roughly 70k spare, so it fits a single
window without splitting.

### 29.10 What the three partials already agree on, before the real run

Not a result - 13 arm-A diagnoses across three hosts, which §16.3 binds, not
§7. Recorded because it is cheap and it is consistent.

| rail | precision | incidents | arm A named F07 | arm B named F07 |
|---|---|---|---|---|
| groq direct (§28) | undisclosed | 3 | 10/10 | 3/9 |
| openrouter>Groq (§29.7) | undisclosed | 1 | 1/1 | 0/1 |
| openrouter>DeepInfra | **bf16** | 2 | 2/2 | 0/2 |
| pooled | - | 6 | **13/13** | **3/12** |

Arm A perfect at 13 draws bounds the one-sided Clopper-Pearson ceiling at
**0.206** - which is no bound worth quoting, and is stated so it cannot be
mistaken for one.

Two things do survive the thrashing:

- **`closure(detector)` was 1.00 in every arm of all three runs**, on two
  providers and two precisions, including arms whose agreement was 0.00.
  §28.3's claim that the pre-registered PRIMARY saturates on this model class
  has now replicated across rails, which is more than the aborted runs were
  designed to show. §29.3's prediction 4 predicted exactly this.
- **§29.3's prediction 6 is already in trouble.** It expected 1 to 3 of 15
  incidents dropped; this run dropped **2 of 4** - `F07#2` and `F07#4`, both
  because the DETECTOR said `INSUFFICIENT_EVIDENCE` rather than the injected
  class. At that rate 15 incidents would drop ~7. n=4, so this is a signal to
  watch and not a refutation, and it is logged now so that noticing it later
  cannot be mistaken for having predicted it.

### 29.11 The keys span at least two organizations, so the budget was never the binding constraint

Prompted by the owner asking why three keys had not helped. §28.1 answered
what every section since has repeated: one organization, 200,000 a day.
**That is wrong, and the evidence was already in this repository.**

| artifact | finished (UTC) | organization | Used of 200,000 |
|---|---|---|---|
| `closure-ablation-groq-full.json` | 2026-11-10 00:24 | `org_01jhmy8t...sh73` | 196,518 |
| `closure-ablation-groq-f07.json` | 2026-11-10 05:44 | `org_01m15ty1...6w6dq` | 196,017 |

Two organizations, each drained to within 4k of its own ceiling, five hours
apart, on one day. `keys_for` reports **3 distinct keys**, and the rotation
in `providers.py` emits `(all N keys tried)` only after the **last** key
fails, so at both aborts every key was capped - which is why the rotation
looked like it was not working. It was working. It bought a second full
budget and that was spent too.

**So the day's budget is at least 400,000 tokens and the run needs ~125,000.**
There was room for three attempts. What consumed it was two runs aborted on
unfunded rails (§29.7, §29.8) and four mis-sized probes (§29.9), not the
size of the free tier. §29.6 and §29.9 both reported a cap as the obstacle.
The obstacle was the spending.

**What is still not known, and cannot be probed.** Whether the third key is a
third organization or shares one of the two is unrecorded; a probe of each
key separately at 09:50 UTC returned **admitted on all three**, which reveals
no org id, because the id appears only inside a 429. And the admission check
reads the requested tokens while the tokens-per-minute ceiling is 8,000, so
**no probe can ever ask for more than 8,000 and no probe can confirm the
125,000 the run needs.** A probe can falsify headroom and never establish it.

**The 06:15 gate stands, with a reason that survives being checked.** Tokens
spent now age out ~24h from now, which is *after* 06:15 on 2026-11-11, so an
attempt today that aborts would consume the gate's own headroom. That is an
argument from the window's mechanics rather than from a cap figure, and it is
the first reason given for waiting that does not rest on a number measured
somewhere adjacent to the one that mattered.

---

## 30. Read-off: the F07 arms-AB run reached 12 of 15 incidents, and five of §29.3's six predictions are met

Ran 2026-11-10 ~09:55-10:40 UTC on **Groq-direct**, §29.1's design unchanged,
after §29.11 established that the budget was never the obstacle. Artifact
`closure-ablation-groq-f07-ab-TRUNCATED-12of15.json`, `complete: false`.
**24 observations, 23 usable, 12 incidents in arm A and 11 in arm B, no
incident dropped by the detector.** It stopped on the daily token cap at
incident 12, fault reverted, target verified clear on all four classes.

### 30.1 The predictions, scored

| # | Prediction | Measured | |
|---|---|---|---|
| 1 | arm A agreement >= 0.93 | **12/12 = 1.00** | met |
| 2 | **PRIMARY: arm B agreement <= 0.50** | **0/11 = 0.00** | met |
| 3 | arm B confident-wrong <= 2 | **0** - every arm B answer was `INSUFFICIENT_EVIDENCE`, a refusal, not a wrong class | met |
| 4 | closure(detector) >= 0.95 in both arms | **1.00 and 1.00** | met |
| 5 | arm A mean confidence exceeds arm B's by >= 0.15 | **0.894 - 0.734 = 0.160** | met by 0.010 |
| 6 | 1 to 3 of 15 incidents dropped by the detector | **0 of 12** | **NOT met** |

**Prediction 4 was a prediction that the metric fails, and it holds for the
fourth rail running.** `closure(detector)` is 1.00 in an arm whose agreement
is 0.00: the pre-registered PRIMARY cannot tell a correct diagnosis from a
refusal on this model. §29.2 demoted it before the run for exactly this
reason, and §28.3's claim now has 12 more incidents behind it.

**Prediction 6 fails in the opposite direction to the one §29.10 warned**
**about.** §29.10 logged 2 of 4 incidents dropped and said 15 would drop ~7.
The full run dropped **none** of 12. So that signal was the small sample and
not a trend - the warning was right to be logged and wrong in its direction.
Under §25.3's 0.87 detection rate, 0 of 12 has probability 0.188, so this
refutes the stated range without being evidence of anything much.

### 30.2 The primary, on the outcome §29.2 registered

**The harness printed `p=1.0000  <- prediction NOT met`, and that line is
about the superseded primary.** It computes McNemar on `closed_detector`,
which is 1.00 in both arms, so the test is comparing two saturated columns
and can only return 1.0. §29.2 changed this run's primary to **agreement
with the injected class**, on the record before the run started. On that
outcome, paired on the incident:

```
b = 11  (arm A named F07, arm B did not)
c =  0  (arm B named F07, arm A did not)
exact McNemar, two-sided p = 0.000977     one-sided p = 0.000488
```

Complete separation on 11 paired incidents. Arm A's perfect score reports
the **Clopper-Pearson one-sided ceiling of 0.2209** at k=12 (§29.4), not a
zero-width interval - so the true arm A failure rate could be as high as 22%
and this run would still look perfect. That bound is the honest limit of what
12 incidents buy, and it is why the registered n is 15.

### 30.3 Why the artifact was renamed and the registered run still stands

The pre-registration says **15** incidents. Reporting 12 under the
pre-registered filename would quietly substitute a smaller n for the one on
the record, so the artifact is renamed to name its truncation and the
pre-registered name is left free. The armed waiter fires at 06:15 UTC on
2026-11-11 into a replenished window and runs the registered 15.

**This section is written before that run exists.** If the 15-incident run
disagrees with the numbers above, both are on the page and the full one is
the result; recording the truncated run only after seeing whether the full
one agreed would be choosing which to report. Note this is a *re-run of the
same registered design*, not §29.4's forbidden move - that forbids refilling
incidents **after seeing which ones dropped**, and nothing here was dropped.

### 30.4 The pool, measured rather than inferred

The abort reported `org_01m15ty1...` at **Used 198,820** of 200,000. At the
05:44 abort the same organization read **196,017**, so only ~2,800 tokens of
this run landed on it - while the run spent **~90,000 prompt tokens**
(12 x 4,073 + 11 x 3,749). **~87,000 of it was served by other keys.** This
is the first direct measurement that the rotation draws on more than one
organization's budget, and it confirms §29.11 by a route that does not
depend on reading org ids out of error messages.

---

## 31. Pre-registration: F08, 15 incidents x 1 rep, arms A and B, on Groq-direct - written 2026-11-10, before the run, and NOT blind

Written before any of this run's data exists, while the registered F07 run
(§29) is still pending. **It is not a blind pre-registration, and §31.2 says
exactly what has already been seen.**

### 31.1 Why F08, and not F06

§30's most quotable reading - that what reverses with model scale is the
**failure mode**, from confident error to refusal - currently compares F07 at
120B against four classes pooled on the local model. It crosses a class
boundary. The next run should remove that confound, and only one class can:

| local `qwen2.5:7b`, arm B | agreement | confident wrong, rep 1 only |
|---|---|---|
| F06, three full runs | 135/135 | 0 |
| F08, three full runs | 33/117 | **6/39 = 0.154** |

Size-matched noise has **no effect on F06 locally**, so an F06 run on 120B
can only return a null that both models share. **F08 is the one class where
the local model gave confident wrong answers under noise**, so it is the only
within-class test of the scale reading. F06 runs after this one, with a
predicted null.

### 31.2 What has already been seen

| artifact | class | incidents | arm A agreement | arm B agreement | arm B confident wrong |
|---|---|---|---|---|---|
| `closure-ablation-groq-smoke2.json` | F08 | **#1-#5**, rep 1 | 5/5 | 0/5 | 0 |
| `groq-full` + `groq-smoke2` | F06 | 7 incidents | 6/7 | 6/7 | 0 |

**Incidents are seeded per class and index** (`closure_ablation.py:509`,
`:551`), so F08#1-#5 here are **the same draws** the registered run will
produce, on the same model with `seed=42`. A third of this run therefore
re-measures incidents whose outcome I have seen. **Only F08#6-#15 are blind,
and every F08-alone confirmatory figure below is computed on #6-#15 first**,
then on all 15 with #1-#5 flagged. Choosing which subset to lead with after
seeing the data would defeat the point, so it is fixed here.

### 31.3 The design

```
harness/closure_ablation.py --classes F08 --incidents 15 --reps 1
    --arms AB --provider groq --model openai/gpt-oss-120b
    --json-out harness/reports/closure-ablation-groq-f08-ab.json
```

30 diagnoses. Measured in `groq-smoke2` at 4,081 (A) and 3,711 (B) prompt
tokens, so **~117k prompt, ~125k with completions** - the same size as §29.1.

**When.** Not before the registered F07 artifact exists (complete, or renamed
after an abort), and not before **11:00 UTC on 2026-11-11**. The day holds at
least 400,000 tokens across at least two organizations (§29.11). The F07 run
spends ~125k from 06:15, and §30's run spent ~90k between 09:55 and 10:40 UTC
on 2026-11-10, which ages out of the 24h window at ~10:40. After 11:00 the
estimate is >= 275k free. **That is an estimate and no probe can confirm it**
(the per-minute ceiling is 8,000), so an abort stays possible, and the abort
path - fault reverted, artifact flushed per incident - is the fallback, as
before.

### 31.4 The primary outcome is agreement

As §29.2, and now on more evidence than §29.2 had: `closed_detector` read
**1.00 in every arm on both classes measured at 120B** - F01 at 45/45 in A,
B and E, and F07 at 12/12 and 11/11 (§30). It cannot separate a correct
diagnosis from a refusal on this model and is reported as a secondary that is
expected to saturate.

### 31.5 The predictions

| # | Prediction | If it fails |
|---|---|---|
| 1 | arm A agreement >= 14 of 15 | the shipped frame does not transfer on F08 at 120B |
| 2 | **PRIMARY: arm B agreement <= 0.50** | noise does not cost F08 the class at 120B; the effect is F07-specific |
| 3 | arm B confident wrong <= 1 of 15 | the local rate (0.154, ~2.3 expected at 15) holds at 120B on F08 |
| 4 | closure (detector) >= 0.95 in both arms | §30's saturation claim is wrong on F08 |
| 5 | arm A mean confidence exceeds arm B's by >= 0.15 | confidence does not track degradation on F08 |
| 6 | 0 to 2 of 15 incidents dropped by the detector | see below |

**Prediction 6 has no measured rate behind it.** No F08 detection rate is
recorded anywhere in this programme; the range rests on `groq-smoke2`
dropping 0 of 5 F08 incidents and §30 dropping 0 of 12 F07. It is stated so
that a surprising drop count is noticed, not because it is grounded.

**Refutation of the scale reading.** If arm B shows **3 or more** confident
wrong answers of 15 - the local rate - then 'the failure mode reverses with
scale' is withdrawn to 'F07, at 120B, refuses', and §4.4a of the report
says so.

### 31.6 The scale test, with its power stated before the data

**Confident wrong**, fixed here: the diagnosis names a fault class other than
the injected one, and is not `INSUFFICIENT_EVIDENCE` or `UNKNOWN`, at any
stated confidence. No threshold is needed: every such answer in the local
comparator below stated confidence >= 0.8.

**Local comparator, fixed now:** arm B, **rep 1 only**, so one diagnosis per
incident and the clustering that `reps=3` introduces is not counted as
independent evidence. F07: 17/43. F08: 6/39. Pooled: **23/82 = 0.280**.

Two tests, one-sided Fisher exact (fewer confident wrong at 120B):

1. **F08 alone, 120B vs local.** **Underpowered, whatever happens:** 0 of 15
   gives p = 0.126, 1 of 15 gives p = 0.363. This test cannot establish the
   scale reading at this n. It can only refute it, through 31.5's rule.
2. **Class-matched pool, F07 + F08 at 120B vs F07 + F08 local.** With the
   registered F07 run's 15, n = 30 at 120B. One-sided p = 0.0003 at 0
   confident wrong, 0.0025 at 1, 0.0113 at 2, **0.0349 at 3**, 0.0829 at 4. The
   rule: **p < 0.05 supports the scale reading on class-matched data.**
   **Its F07 half is not blind** - §30 has 0 of 11 - so this is reported as a
   class-matched comparison with half its data seen, never as a confirmatory
   test.

Both carry the confound §6 of the report names: the decoder path differs
(Ollama grammar locally, strict `json_schema` on Groq), so model scale is the
leading explanation, not an isolated one.

### 31.7 Analysis fixed in advance

- McNemar, exact, on **agreement**, paired on the incident.
- A perfect arm reports the Clopper-Pearson one-sided ceiling: **0.181 at
  15, 0.259 at 10** (the blind subset).
- Dropped incidents are reported as dropped, not refilled.
- F08-alone figures are computed on **#6-#15 first**, then on all 15 (§31.2).

### 31.8 One harness change before this run, and why not before F07

A detector drop records the verdict (`detector said INSUFFICIENT_EVIDENCE`)
but not **why**, so §29.10's dropped incidents cannot be explained after the
fact. `Detection.reasons` already carries that
(`kavach/detection/base.py:76`). The detector-drop entry in
`closure_ablation.py` gains the first three reasons, truncated.

It is a change to a log string. It touches no observation, arm, prompt or
metric, lands with a unit test, and must pass `make check`. **It is not made
before the registered F07 run**, because that run is compared against §30's
12 incidents and the measured path is frozen between runs being compared. It
is made after the F07 artifact exists and before this run starts.

### 31.9 What this run still cannot answer

`F06` cross-provider is next, with a predicted null. One cloud model, one
scale, one decoder path per model. And `reps=1` again gives up the
within-cell spread §7 reads.
