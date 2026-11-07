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
