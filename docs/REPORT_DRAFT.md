# Kavach — report draft

**Status: a draft with real numbers, not a finished report.** Every figure
below is traceable to a file in `harness/reports/`, and the filename is given.
Where a number is missing or provisional it says so rather than being filled
in. Nothing here is estimated.

**`harness/reports/` is committed** as of 2026-10-20 — 70 files, 760K, every
artifact named below plus the five run logs. It was ignored as "machine
output", which was the wrong call for a document whose argument is that every
figure is traceable to a named file: a reader could check nothing. The
directory was scanned before its first commit — no key-shaped strings, no
token/secret/password fields, no credentials in URLs, no settings or env
snapshots — and anything written there later must stay that way.

**The figures are drawn from those same files.** `make figures` reads the
artifacts and nothing is typed into the plotting code, so a figure cannot
drift from the file it describes.

Still **not** committed: `harness/audit/`, the hash-chained log. It is
append-only, so every run would carry a diff of a log, and its integrity is
checkable where it lives (`make postmortem` verifies the chain while rendering
an incident). That is a different kind of evidence from a measurement file.

Written 2026-10-19. Updated 2026-10-20 after a **second** full `make bench`
run (`bench-20261020-mttd.json`, finished 03:06 UTC) — the one that could
measure MTTD, and therefore also a replication of §4.1 at the same denominator.
Updated again 2026-10-21 after a **third** (`bench-20261020-night.json`,
finished 02:03 UTC), the first to record `fault_name` coherence live rather
than by replay. Updated again 2026-11-02 after a **fourth**
(`bench-20261102-night.json`, finished 03:31 UTC) — the first on a host rebuilt
from empty after the machine's SSD was formatted, and therefore the only
replication that shares no system state with the first three. §4.1 and §4.2
report all four runs; **eighty injections in total, zero false heals.**

---

## 1. One paragraph

Kavach is an autonomous self-healing control plane for AI applications. It
watches a running retrieval-augmented generation service, detects four classes
of regression, diagnoses them with an LLM whose answer is cross-checked against
deterministic detectors, and repairs them with actions that each carry a
recorded inverse. The contribution is not that an LLM can diagnose an incident —
it is that **a deterministic layer, not the model, decides whether anything is
written**, and that this is measured rather than asserted.

> **"Self-healing" here means operational remediation of a deployed service by
> an external control plane — not query-time self-correction inside the
> pipeline.** The term is already in wide use for the latter: agentic RAG
> systems that rewrite a weak query, re-rank or re-retrieve when an
> LLM-as-judge rejects an answer, all within a single request. Kavach never
> touches a request. It changes the configuration, prompt files or endpoint of
> the *deployed system*, between requests, with a gate, an inverse and an audit
> record. The two share a name and nothing else: different layer, different
> failure modes, different blast radius. Everything below concerns the second.

## 2. The claim, stated so it can fail

> An LLM may propose a repair. It may never authorise one.

Three measurements would falsify this:

1. an action executing without passing `permit()`
2. the deterministic cross-check accepting a wrong diagnosis
3. an incident leaving the target in a state the undo stack cannot restore

**None has occurred in 80 live fault injections across four runs.** The model
named the wrong fault class 11 of those 80 times; 0 of the 11 reached the
target. §5 gives the numbers, §4.2a the conditionals, and §6 the limits of
that claim — chiefly that 11 is a small denominator, so this bounds the
false-healing rate loosely and demonstrates the absence of a path, not a
tight upper bound.

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

### 4.1 The bench — four runs at the same denominator

Four full `make bench` runs, each **4 classes x 5 reps = 20 injections**,
unattended in `APPROVAL` mode. Run B exists because run A could not measure
MTTD ([ADR 0014](decisions/0014-mttd-was-never-measured-so-the-figure-is-withdrawn.md));
run C exists because `fault_name` coherence was only wired as a measurement
after run B ([ADR 0020](decisions/0020-incidents-are-read-from-the-store-and-the-bench-scores-two-answers.md)),
and it had been scored by *replaying* run B's diagnoses rather than observed
live. **Run D exists because the machine was rebuilt.** On 2026-11-01 a service
centre formatted the host's SSD; Docker, Ollama, the models and the corpus were
reinstalled from scratch and the corpus re-ingested
(`RESEARCH_NOTES.md` §12). Run D is therefore the only run on a host that
shares nothing with A, B and C but the repository — the strongest replication
in the set, and the one we did not plan. Each run doubles as a replication of
everything before it.

| | run A | run B | run C | **run D** |
|---|---|---|---|---|
| artifact | `bench-full.json` | `bench-20261020-mttd.json` | `bench-20261020-night.json` | `bench-20261102-night.json` |
| window (UTC) | 2026-10-18 19:12 to 10-19 08:55 | 2026-10-19 18:55 to 10-20 03:06 | 2026-10-20 17:52 to 10-21 02:03 | 2026-11-01 19:18 to 11-02 03:31 |
| wall clock | 13.7h | 8.2h | 8.2h | 8.2h |
| of which paced waiting | 7.4h | 7.4h (445 min) | 7.4h (443 min) | 7.5h (447 min) |
| MTTD | **not measurable** | **measured** | **measured** | **measured** |
| `fault_name` coherence | not recorded | replayed from the memory ring | **recorded live** | **recorded live** |
| host | original | original | original | **rebuilt from empty** |

Every injection was real, every approval was issued by the harness acting as
the operator, and in none of the four was anything reset, raised or disabled.
All ran on one Ollama (`qwen2.5:7b-instruct`) and one 30-chunk corpus — in run
D's case, a corpus re-ingested from the same two PDFs and verified at 30 chunks
/ 2 files before the run started, which is now a preflight check rather than a
habit (`onboarding/preflight.py::check_corpus_fingerprint`).

#### Per class — runs B, C and D, the three with a valid MTTD

| class | detector reads | **MTTD** median | MTTR median | healed |
|---|---|---|---|---|
| F08 config regression | live settings vs. snapshot, **no PromQL** | B **18.5s** · C **19.3s** · D **16.3s** | B 109.0s · C 110.5s · D 96.7s | B 5/5 · C 4/5 · D 5/5 |
| F07 prompt regression | prompt hash vs. baseline, **no PromQL** | B **20.1s** · C **21.0s** · D **17.4s** | B 102.9s *(n=1)* · C 112.0s · D 93.7s *(n=1)* | B **1/5** · C 3/5 · D **1/5** |
| F01 endpoint outage | `rate(llm_requests[2m])`, `min_requests >= 3` | B 60.8s · C 36.6s · D 48.6s | B 124.2s · C 103.1s · D 111.8s | B 5/5 · C 5/5 · D 5/5 |
| F06 retrieval collapse | `rate(empty_context[1m])` | B 71.2s · C 73.2s · D 61.9s | B **155.2s** · C **159.5s** · D **137.0s** | B 3/5 · C 3/5 · D **5/5** |

The two no-PromQL classes replicate to within a few seconds across all three
runs, and in run D both came in *faster* than before — the rebuilt host is
quicker, which is a property of the hardware, not of Kavach, and is the reason
no cross-run latency claim in this report is stated as an improvement.

The two that wait on a `rate()` replicate in *range* but not in median — F01's
median has now taken three different values on an unchanged system:

| | the five F01 samples |
|---|---|
| run B | 36.5 · 48.7 · 60.8 · 61.3 · 62.0 |
| run C | 36.5 · 36.6 · 36.6 · 48.7 · 61.0 |
| **run D** | 36.5 · 48.5 · 48.6 · 60.8 · **72.9** |

**The ladder prediction held, and run D extended it.** Run A/B/C suggested
rungs near 36.5, 48.7 and 61, about 12.2s apart. Run D reproduced all three to
within 0.3s *on a rebuilt host* and landed one sample on a fourth rung at
**72.9s** — 12.1s above the third. Four rungs, 36.5 → 72.9, one step size:

| rung | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| value | 36.5 | ~48.6 | ~60.9 | 72.9 |
| step from previous | — | 12.1 | 12.3 | 12.0 |

So **F01's MTTD is not a continuous distribution; it lands on a ladder**. The
median is then just a count of which rungs the five samples happened to hit,
which is why it has moved 24s across runs that changed nothing. That a fourth
rung appeared exactly one step out, on different hardware, was the strongest
evidence available that the step was mechanical rather than noise.

Until 2026-11-06 this paragraph added that which rung you land on "depends on
where in the scrape cycle the fault is injected", and that the mechanism was
not isolated. **Both are now superseded by the measurement below**, which
finds the rung is set by the harness's warm-up and has nothing to do with the
scrape cycle.

**Mechanism found 2026-11-06, by measuring instead of fitting.**
`harness/mttd_ladder.py`, artifact
[`mttd-ladder.txt`](../harness/reports/mttd-ladder.txt). With F01 injected on
the live stack, one round of `warm_up_f01` — the whole three-case fast set,
which is what that function runs before re-reading the error ratio — costs
**12.10, 12.15, 12.12, 12.11 seconds**: mean **12.12s**, spread 0.05s, against
**24.3s** for the same round on a healthy target. MTTD is measured from
injection and contains those rounds, and **twelve of the twenty samples lie
within 0.4s of a 12.12s lattice**.

**So the rungs are warm-up rounds.** That is the named mechanism §9 item 13
asked for, and it is in the harness rather than in the system: 15s does not
divide 12.12, and there is no sleep, poll or interval constant anywhere in the
detection path. The scrape interval is ruled out rather than merely doubted.

**A correction, because the mistake is the instructive part.** This paragraph
briefly claimed, on 2026-11-05, that the step was **6.05s** and that 12.2 was
its second harmonic. That was backwards, and the timing run refutes it. The
claim came from fitting a lattice to the twenty samples and taking the best
mean-distance-to-nearest-rung — and **any divisor of the true period fits
every point of that period's lattice**, so a shorter period can never score
worse. 6.05 won because it is half of 12.1, not because it is the step. A
lattice fit cannot choose between a period and its divisors; only the
measurement can. The report's original 12.2s was right.

**What is still unexplained**, stated because the rest is now solid: four
samples — 54.6, 66.8, 78.9, 91.0 — sit 5.92–6.00s from the nearest rung,
almost exactly half a round and far too precise to be noise. Half a round is
not a natural unit of a three-call fast set. The candidate is variation in the
detection step that follows the warm-up, which has not been measured.

**The consequence matters more than the ladder.** If F01's MTTD is dominated
by a warm-up that F06, F07 and F08 do not perform, then **F01's MTTD is not
comparable to theirs**, and the per-class MTTD figures in this section should
be read with that stated. The aggregate was already called the least useful
true thing about MTTD; this is why.

#### Headline metrics, all four runs

| metric | run A | run B | run C | **run D** | `PRD.md` §10 target | |
|---|---|---|---|---|---|---|
| detection rate | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (20/20) | >= 95% | met |
| localisation | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (20/20) | >= 80% | met *(one-way, see §6)* |
| RCA accuracy, the model's own answer | 85% (17/20) | 85% (17/20) | 85% (17/20) | **90% (18/20)** | >= 75% | met |
| repair action **correct** *(not "proposed", see §4.2)* | — | — | 90% (18/20) | **100% (20/20)** | *no target* | — |
| answer is self-consistent | — | *(replayed)* | **60% (12/20)** | **65% (13/20)** | *measured, not enforced* | — |
| auto-resolution | 75% (15/20) | 70% (14/20) | 75% (15/20) | **80% (16/20)** | >= 70% | met |
| **false healing** | **0% (0/20)** | **0% (0/20)** | **0% (0/20)** | **0% (0/20)** | <= 5% | met |
| MTTR median | 124.4s (n=15) | 114.9s (n=14) | 112.0s (n=15) | **108.8s** (n=16) | < 180s | met |
| **MTTD median** | withdrawn — never measured | **28.5s** | **33.0s** | **28.1s** | < 30s | **B met, C missed, D met** |
| first verdict median | 48.5s | 50.0s | 53.1s | 45.3s | *no target* | — |
| target state clean after run | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% | met |
| audit completeness | *vacuous* | *vacuous* | *vacuous* | *vacuous* — 16/16 verified by hand, §6 | 100% | **withdrawn as a run metric** |
| audit chain intact | yes | yes | yes | yes | yes | met |

**Eighty injections, zero false heals.** That is the claim the whole
architecture exists to support, and it now has a four-run denominator — the
last of them on a host rebuilt from empty.

Read the improvements in run D with care. RCA accuracy 85% → 90%, auto-resolution
75% → 80% and MTTD 33.0s → 28.1s are each **one or two rows out of twenty**
moving on a rebuilt, faster host. Nothing in Kavach was changed to produce
them, which means they are not evidence that Kavach got better; they are
evidence of how wide the run-to-run band is at n=20. The report quotes the
band, not the best run.

RCA accuracy came in at exactly 17/20 three times from three independent draws
and 18/20 on the fourth, which is the kind of agreement that invites a check
that the harness is not re-reading one file — the four artifacts have different
timestamps, different MTTRs and different per-class breakdowns, so the
agreement is in the quantity, not the data.

#### MTTD: measured, and the aggregate is the least useful true thing about it

ADR 0014 withdrew MTTD because the harness had timed injection to first
*terminal* status and called it detection — a figure containing the F01/F06
traffic warm-up, the pre-detection fast set, detection, the **entire LLM
diagnosis**, and the `permit()` gate. `loop.py` now stamps
`detection.concluded_at` the instant `run_all` returns, and run B computes MTTD
from that stamp.

The aggregate median is **28.5s in run B, 33.0s in run C and 28.1s in run D**,
against a `< 30s` target. The same unchanged system therefore **met the target,
missed it, then met it again** — met · missed · met, three draws, no code
change between them. That is the clearest possible statement of why
reporting the aggregate alone would be misleading: whoever quotes run D's
28.1s as "Kavach meets its MTTD target" is quoting a coin that has landed
heads twice in three tosses.
[ADR 0019](decisions/0019-mttd-is-measured-and-the-target-stays-but-per-class.md)
records why, and the decision not to touch the target. In short: the twenty
samples are **bimodal with nothing in between**, so the median is decided by
which side of the gap the middle sample falls on, not by how fast detection is.

![MTTD per class against the < 30s target](../harness/reports/figures/fig1-mttd-per-class.png)

*Figure 1 — `make figures`, from `bench-20261020-mttd.json`. Every one of the
twenty samples is plotted; the bar is the class median and the dashed line the
`PRD.md` §10 target. Nothing lands between 20.5s and 36.5s.*

> **Read the bars within a class, not across them.** The decomposition below
> shows F01's bar contains 24–61s of manufactured warm-up traffic that F07's
> and F08's bars contain none of. The gap the figure shows between the
> left-hand pair and the right-hand pair is mostly that warm-up, not a
> difference in detection speed.

The two classes whose detectors read **no metric at all** — F07 compares a
prompt hash, F08 a config snapshot — come in at 18-20s with a spread of
**0.9s and 0.4s**. That is a fixed cost (the fast set), not a distribution. The
two that wait on a `rate()` behind a 15s scrape come in at roughly one window
plus the fast set. **The detectors are not slow; the evidence is not yet
available when they run.**

So the median sits in an empty gap between two populations, one sample either
side of the boundary. ADR 0019 predicted that this made the aggregate unstable
and that changing which four classes are injectable would flip the verdict.
**Run C flipped it without changing anything at all** — same four classes, same
detectors, same model, same corpus, 28.5s to 33.0s, met to missed. The
prediction was conservative: the aggregate is not merely sensitive to the
choice of classes, it is unstable across repetitions of an identical run.

The figure is therefore reported **per class, with its window beside it**, and
`< 30s` is left in `PRD.md` exactly as written — two of four classes miss it in
both runs, and they are reported as missing it. Per class the result is stable
to within a second for F07 and F08 and within the ladder described above for
F01 and F06; it is only the aggregate that moves.

**And the per-class figures are not measuring the same quantity.** Found
2026-11-06 by reading `warmup_s`, which the harness has recorded all along
beside `mttd_s` and which nothing netted out. Decomposed across all four runs:

| class | warm-up | MTTD after warm-up | n |
|---|---|---|---|
| F01 | 24.3 – 60.8s | **12.2 – 33.2s** | 20 |
| F07 | **0.0s** | 17.1 – 42.4s | 21 |
| F08 | **0.0s** | 15.4 – 39.3s | 23 |

**F07 and F08 do not warm up at all**, and F06 warms up differently
(`drive_until_detectable`). So F01's figure carries between two and five
rounds of manufactured traffic that F07's and F08's do not, and **the four
classes were never on a common scale.**

Subtract it and the ranking inverts: F01's detection, at **12.2–33.2s**, is
*faster* at the low end than F08's 15.4s or F07's 17.1s. **"F01 is slower to
detect than F08" is not a claim this report supports**, and §4.1 should not
be read as making it.

**The warm-up is not merely an artefact, which is the honest complication.**
F01 is an error-*ratio* fault: with no traffic there is no ratio and nothing
to detect, so `warm_up_f01` is standing in for the organic load a production
system would already have. The time is real; what it measures is *how long
until enough traffic has flowed to make the fault visible*, not how long the
detector takes once it can see. F07 and F08 need no traffic at all — a
changed prompt version or config hash is visible immediately — which is
exactly why they warm up for zero seconds.

So the two numbers answer different questions, and `< 30s` is a meaningful
bar for only one of them. Recorded rather than re-cut: changing what MTTD
means would invalidate the four runs that measure it, and §9 item 13 carries
it.

**One more thing run B settles about run A.** Run A's mislabelled "MTTD" per
class was 36.4 / 39.4 / 78.9 / 87.9s for F08 / F07 / F01 / F06. Run B's
*first verdict* — the same quantity under its true name — is 39.3 / 39.3 /
78.8 / 90.7s. The old instrument replicated across two runs to within a few
seconds. It was **precise and measuring the wrong quantity**, which is the only
reason nobody noticed for four days.

### 4.2 F07 is the unstable class, and the second draw is part of why

Across four runs F07 was repaired **0/5, 1/5, 3/5 and 1/5 — 5 times in 20**.
Nothing in the detection, diagnosis or repair path changed between those runs,
so the spread is sampling variance around a low and unstable rate, not
improvement. Run C's 3/5 was the outlier, not the trend: **run D, on a rebuilt
host, came back to 1/5.** Every other class is at or near ceiling across all
four runs (F01 20/20, F08 19/20, F06 16/20); F07 sits at 5/20 and moves by a
factor of three between draws. **F07 is the class we cannot give a reliable
number for**, and that is the honest result. Read this section with **§4.8**: a
human operator and a scripted runbook were each given F07 on the same system,
and both produced a **false recovery** — the runbook while diagnosing it
*correctly*. All three approaches struggle on F07. Kavach is the only one that
does not claim otherwise.

`runner.approve()` **re-detects and re-diagnoses** rather than replaying a
stored plan. That is deliberate: the world may have moved while the approval
dialog was open, and a replayed plan would restore a value that was true when
it opened. The cost is that **an approved incident must be diagnosed correctly
twice**, and the bench records only the first draw as `llm_class`. Runs A and B
both lost F07 incidents on that second draw, run C lost none, and **run D lost
two** — reps 2 and 5 logged `llm_class = F07` and were then refused with
*"deterministic_agreement: LLM says F06"*, which can only mean the second
diagnosis disagreed with the first on the same unchanged fault.

| F07 escalations | lost on the **first** draw (model said F06 outright) | lost on the **second** draw (first said F07, approval re-diagnosis said F06) |
|---|---|---|
| run B | 3 | 1 *(inferred — `escalation_reason` was not recorded until run C)* |
| run C | 2 | 0 |
| **run D** | 2 | **2** |

The mechanism is a real exposure and, after four runs, an intermittent one.
Note what the right-hand column costs: those rows are **correct first
diagnoses that produced no repair**, and the bench's `RCA accuracy` counts them
as correct, because it reads the first draw. The gate's refusal is the only
place the disagreement is visible at all — which is an argument for the
`escalation_reason` field, not against the second draw.

#### F07, per repetition

| rep | first RCA | after approval | end | which validator rule |
|---|---|---|---|---|
| **run A** | | | | *not recorded — `bench-full.json` keeps no escalation reason* |
| 1 | F07 ✓ | **F06 ✗** | escalated | — |
| 2 | F06 ✗ | — | escalated | — |
| 3 | F07 ✓ | **F06 ✗** | escalated | — |
| 4 | F06 ✗ | — | escalated | — |
| 5 | F06 ✗ | — | escalated | — |
| **run B** | | | | |
| 1 | F07 ✓ | F07 ✓ | **resolved** | — |
| 2 | F06 ✗ | — | escalated | deterministic agreement |
| 3 | F06 ✗ | — | escalated | agreement **+ repair permitted** |
| 4 | F06 ✗ | — | escalated | agreement **+ repair permitted** |
| 5 | F07 ✓ *(0.9)* | **F06 ✗** | escalated | deterministic agreement |
| **run C** | | | | |
| 1 | F07 ✓ | F07 ✓ | **resolved** | — |
| 2 | F07 ✓ | F07 ✓ | **resolved** | — |
| 3 | F07 ✓ | F07 ✓ | **resolved** | — |
| 4 | F06 ✗ | — | escalated | agreement **+ repair permitted** |
| 5 | F06 ✗ | — | escalated | agreement **+ repair permitted** |

![first diagnosis correct versus repaired, per class](../harness/reports/figures/fig2-where-the-classes-lose.png)

*Figure 2 — the gap between the two bars in each class is a second draw the
gate refused. Plotted from run B.*

First-draw accuracy is **2/5, 2/5, 3/5 and 3/5** — the model is unreliable on
F07 in a stable way, missing roughly half of them in every run, run D
included. What is *not* stable is what happens next: of the **ten** correct
first draws across four runs, **five survived the second draw** — none in run
A, one of two in run B, all three in run C, one of three in run D. The double
exposure is a real cost with a rate we cannot pin down at n=5 per run; four
runs have given it four different values.

#### The same failure hit F06, which run A healed 5/5

This is the finding run B adds, and it is the reason F06 dropped from 5/5 to
3/5:

| rep | first RCA | after approval | end | which validator rule |
|---|---|---|---|---|
| 1 | F06 ✓ | F06 ✓ | resolved | — |
| 2 | F06 ✓ | F06 ✓, **but proposed `rollback_prompt`** | **escalated** | **repair permitted, alone** |
| 3 | F06 ✓ | **F07 ✗** | **escalated** | deterministic agreement |
| 4 | F06 ✓ | F06 ✓ | resolved | — |
| 5 | F06 ✓ | F06 ✓ | resolved | — |

Run C reproduced F06 at **3/5** with the same first-draw class accuracy, but
the two losses split differently:

| rep | first RCA | after approval | end | which validator rule |
|---|---|---|---|---|
| 1 | F06 ✓ → `rollback_config` | F06 ✓ | resolved | — |
| 2 | F06 ✓ → `rollback_config` | F06 ✓, **but proposed `rollback_prompt`** | **escalated** | **repair permitted, alone** |
| 3 | F06 ✓ → `rollback_config` | F06 ✓ | resolved | — |
| 4 | F06 ✓ → **`rollback_prompt`** | — | **escalated** | **repair permitted, on the FIRST draw** |
| 5 | F06 ✓ → `rollback_config` | F06 ✓ | resolved | — |

Run D then did what neither B nor C did: **F06 came back 5/5, clean on both
draws.**

| rep | first RCA | after approval | end |
|---|---|---|---|
| 1–5 | F06 ✓ → `rollback_config` | F06 ✓ → `rollback_config` | **resolved, all five** |

Ten diagnoses of F06 in a row with no disagreement between the two draws, on
the rebuilt host. Put beside run B's 3/5 and run C's 3/5 this is the clearest
statement available that **the second-draw loss is intermittent, not
structural**: the same code path on the same fault lost two incidents, then
two, then none. We cannot give a rate for it. At n=5 per class per run,
nobody can.

F06's first-draw **class** accuracy is **5/5 in all four runs** — the most
stable figure in the bench. Its losses in run B were both second draws; in run
C one was a second draw and one was a first draw that named the right class and
reached for the wrong repair; in run D there were none. So the double-exposure
cost is **not a property of F07** — it is a property of re-diagnosing on
approval, and F07 was simply the class fragile enough to show it first. But it is not the *only* way F06
loses, and run C is what shows that.

F06 also rules out the simplest model of it. If the two draws were independent
samples of equal accuracy *p*, an approved heal would succeed at *p²* — which
fits F07 loosely (p = 0.47, p² = 0.22, observed 4/15) but cannot fit F06 at all:
5/5 on the first draw and 3/5 on the second is not two draws from one
distribution. **The second frame is a different frame** — it is rebuilt after
detection and the pre-fast set have already run, so it carries more traffic and
different metric values. Whether the second draw is harder because the frame is
worse, or the model is simply unstable, is not determined by these twenty
injections and is not claimed here. What is measured is that it is worse.

Two of run B's six escalations are new in kind, and neither is a class error of
the sort §4.3 and ADR 0013 describe:

**F06 rep 3 flipped the confusion the other way.** The model said **F07 where
the detector said F06** — at confidence 0.95. ADR 0013 recorded the confusion
as one-directional, F07 → F06. It is bidirectional. Both faults present as lost
grounding, and the model is choosing between them on symptoms that do not
distinguish them.

**F06 rep 2 named the right class and the wrong repair.** Diagnosis F06 at 0.95,
accepted by the agreement rule — and then it proposed `rollback_prompt`, which
F06 may not use. `repair_permitted` fired **on its own**, the only time in
either run. The consequence for the report is a measurement gap, not a bug:

> **`RCA accuracy 85%` measures diagnosis-class accuracy only. Action-selection
> accuracy is a second, different number.**

It is measured now ([ADR 0020](decisions/0020-incidents-are-read-from-the-store-and-the-bench-scores-two-answers.md)).
Scoring run B's 37 diagnoses on both answers at once:

| | action right | action wrong |
|---|---|---|
| **class right** | 31 | **1** |
| **class wrong** | **2** | 3 |

**Action accuracy (33/37) is higher than class accuracy (32/37).** Both
off-diagonal cells are populated and the second was not predicted: on two
injected F07s the model named F06 and still proposed `rollback_prompt`, the
correct F07 repair. The repair it reached for was right more often than the
label it wrote, which means these are not one number with noise in it — and
the weaker of the two is the one the report has been quoting.

The same incoherence shows up inside the wrong answers too — in F07 reps 3 and
4 the model claimed **F06** and then proposed **`rollback_prompt`**, the F07
repair. It had already contradicted its own diagnosis before the detector got
to disagree with it.

#### And then the F06 column stopped looking clean

Chasing that led somewhere worse. `Diagnosis` makes the model emit a
`fault_name` beside the class code, and `diagnose.txt` gives it the catalogue
to copy from: `F06  Retrieval collapse`, `F07  Prompt version regression`.
Grouping all **37** diagnoses run B produced — 20 first draws plus the 17
second draws approval generated — by the code the model emitted:

| code emitted | n | `fault_name` emitted | correct |
|---|---|---|---|
| F01 | 10 | Primary LLM endpoint outage | **10/10** |
| F07 | 4 | Prompt version regression | **4/4** |
| F08 | 10 | Configuration or environment regression | **10/10** |
| **F06** | **13** | **Prompt version regression** | **0/13** |

`F06` + *"Prompt version regression"* is not a pair the catalogue contains, and
the model wrote it **thirteen times out of thirteen** — including in the three
F06 incidents that **healed successfully**. Nothing derives that field; it is
part of the model's own constrained output, and no check in the validator
compares it to the code beside it.

#### Run C confirms it on independent data, and the prediction was exact

Run B's table above was produced by **replaying** diagnoses that had already
been written. A replay cannot distinguish a real property of the model from an
artefact of one night's sampling, so before run C started we recorded the
prediction it would have to satisfy: *F06 comes back ~0/5 coherent and the
other three ~5/5.* `fault_name` was then wired into the bench as a
**measurement that nothing gates on** (commit `495daa0`) and run C observed it
live.

| code emitted | run B (replayed) | run C (live) | **run D (live, rebuilt host)** | pooled |
|---|---|---|---|---|
| F01 | 10/10 | 5/5 | 5/5 | **20/20** |
| F07 | 4/4 | 3/3 | 3/3 | **10/10** |
| F08 | 10/10 | 4/4 | 5/5 | **19/19** |
| **F06** | **0/13** | **0/8** | **0/7** | **0/28** |

**Twenty-eight F06 diagnoses across three independent runs, twenty-eight
carrying F07's name, and not one incoherent pair anywhere else — 49/49 correct
on the other three classes.** The prediction was not approximately right, it
was exact, and run D re-confirmed it on a host that had been formatted and
rebuilt between the two measurements. This is a reproducible property of
`qwen2.5:7b-instruct` on this prompt, not a sampling accident and not a
property of one machine's state.

It is worth being precise about how clean the separation is: the defect is
**one cell**. The model copies the catalogue name correctly in 49 of 49
diagnoses that emit F01, F07 or F08, and incorrectly in 28 of 28 that emit
F06. There is no gradient. Whatever is happening is not degraded instruction
following in general; it is a specific, stable mis-binding of one class code to
one name.

![fault_name against fault_class, all 77 pooled diagnoses](../harness/reports/figures/fig4-diagnosis-self-consistency.png)

*Figure 4 — pooled over `diagnoses-20261020.json` (run B, written by
`make diagnoses` before the API's in-process ring could lose it),
`bench-20261020-night.json` (run C) and `bench-20261102-night.json` (run D),
the two benches that record the field directly. 77 diagnoses. Both the F06
denominator and the run count in the figure's own title are computed from the
pooled data, not typed — the F06 bar counts every diagnosis that **emitted**
F06, which is more than the number of F06 injections, because the model also
drifts to F06 under F07.*

So **F06's 5/5 class accuracy is a weaker result than it reads as**, in all
three runs. By its own prose the model understood all of them as prompt
regression; the code field was right while the stated understanding was not.
The ADR 0013 confusion is present at 28/28 where the escalation rate shows it
at 2/5.

**This is recorded and deliberately not enforced** — [ADR
0021](decisions/0021-the-fault-name-coherence-check-is-not-being-added.md).
An earlier draft of this section called the decision an open tradeoff: a
`fault_name` coherence check would take F06 from 5/5 to 0/5 and run D's
auto-resolution from 80% to 55%, so the cost was real and the benefit was
assumed. Re-deriving the benefit from the artifacts showed there is none.

Partition the 28 diagnoses that emitted F06 by whether they were *right*:

| | what the gate did | what a name check would add |
|---|---|---|
| F06 emitted, injection was **F07/F08** — 11 rows pooled over four runs | **refused — 0 of 11 executed** | nothing; already refused |
| F06 emitted, injection really was **F06** — 11 rows in runs C+D | 9 healed, 2 refused | **refuses all 9 correct heals** |

The check's *unique* catch set — the rows it refuses that nothing else refuses
— is exactly the set where the diagnosis was **correct**. On this data the
check is not merely expensive, it is anti-correlated with error.

The mechanism explains why. In runs C and D, where `escalation_reason` is
recorded, all five wrong rows were refused with *both* reasons firing:
`repair_permitted` ("proposed `rollback_prompt`, but F06 may only use
`rollback_config`") and `deterministic_agreement` ("LLM says F06, deterministic
detection says F07"). The model's error is not F06-with-a-wrong-name; it is a
coherent **F07** diagnosis with one corrupted field —

| field | says | which class |
|---|---|---|
| `fault_name` | *Prompt version regression* | F07 |
| proposed action | `rollback_prompt` | F07 |
| **cited evidence** | **`EV-C08` — the prompt hashes** | **F07** |
| `fault_class` | `F06` | F06 — **the only field that says F06** |

— and the two gates that catch it both read the *action*, which stays coherent
with the model's real understanding. A name check reads a third field that is
wrong for every F06 diagnosis, correct and incorrect alike. It is a constant,
not a discriminator.

The citation row is the newest of the four and the most direct, added
2026-11-02 from `harness/evidence_closure.py`. In
`p6-f07-rca-qwen-ctx8192.json` the model was given an injected **F07**, named
**F06 ten times out of ten**, and each time cited `EV-M02`, `EV-M03` and
`EV-C08` — reasoning, in its own words:

> *"EV-M02 shows retrieval_kept_chunks_mean = 4.0 (healthy: >= 1.0), indicating
> that chunks are being retrieved. EV-M03 shows retrieval_empty_context_ratio =
> 0.0, meaning that the context is not empty. However, EV-C08 shows that the
> prompt_file_hashes…"*

It ruled F06 **out** on F06's own two signals, found F07's discriminating
signal, read it correctly — and then wrote `F06` in the class field. **Three of
the four fields in that output say F07.** The defect is isolated to the class
code with a precision that none of the three earlier channels could establish
alone, and it is the clearest available evidence that the model's *reasoning*
is not what fails here.

So the finding is not "a check we could not afford". It is this:

> **Kavach's safety on this failure mode comes from cross-checking the proposed
> repair, not the stated class.** The class code is the least reliable field in
> the diagnosis — the only one ever wrong here — and the gate that routes on it
> is backstopped by two checks that do not read it.

##### Citation coherence is a second self-report that cannot be gated on

Running `evidence_closure.py` over the nine artifacts that record cited
evidence IDs — 90 diagnoses, the only ones that carry the field; **the bench
artifacts do not, so this is a different denominator from the 80 injections
behind the headline numbers** — gives a result that parallels the confidence
finding exactly.

| | pooled, 90 diagnoses |
|---|---|
| named the injected class | 49/90 (54%) — includes ablations built to fail |
| **cited evidence discriminating for the class it named** | **80/90 (89%)** |
| also cited another class's discriminating evidence | 81/90 (90%) |
| cited log evidence | 19/90 (21%) |

The 89% is the point, and it is *not* a quality score. In the F07 ablation rows
the model named the wrong class **0/10** while citing that wrong class's own
evidence **10/10**: its citations are coherent with its conclusion whether the
conclusion is right or wrong. The 90% cross-class figure is likewise mostly
*good* — it is differential reasoning, ruling other classes out — so it is
reported and never scored.

So Kavach now has **two** self-reported channels measured and found unusable as
gates:

| channel | why it cannot gate |
|---|---|
| confidence | no threshold separates right from wrong; 8 correct answers also sit at 0.95 (above) |
| citation coherence | coherent with the answer given, right or wrong — 10/10 on answers that were 0/10 correct |

That is the same conclusion twice from independent evidence, and it is the
quantitative case for `permit()` reading the deterministic detector rather than
anything the model says about itself.

**One correction this analysis forced on itself.** The first version scored
`p6-f01-rca.json` at 0/10 own-class citation against 10/10 correct — which
looked like the headline failure and was not. That run diagnosed the outage
from the **logs** (*"EV-L01 shows backend_log = raise ConnectionError"*) and
never cited the error-ratio metric. A connection error in a log is direct
evidence of an endpoint outage; it is just not the signal F01's *detector*
fires on. The metric now counts metric and config citations only, with log
citation tracked in its own column, and the evidence-ID mapping was verified
against a second artifact before the conclusion was drawn — IDs are positional,
so a renumbering would have invalidated the whole table.

#### Why self-consistency is not the answer here, measured rather than argued

The standard remedy for an unreliable LLM judgement is test-time sampling:
draw *k* answers and aggregate. CISC reports cutting required reasoning paths
by over 40%; conformal aggregation reports 90.1% selective accuracy on GSM8K
while abstaining on under 5% of problems. **Any reviewer will ask why Kavach
does not sample.** The answer is in the artifacts, because
`rca_*_live.py` collects the evidence frame **once** and diagnoses against it
ten times — which is a self-consistency experiment that was run long before
anyone framed it as one. `harness/self_consistency.py` replays those recorded
draws; no new inference was needed.

| over 11 fixed frames, 110 recorded draws | |
|---|---|
| single-draw accuracy | 59/110 = **54%** |
| majority-vote accuracy | 6/11 = **55%** |
| unanimous frames | **9/11** |
| **unanimously *wrong* frames** | **4/11** |
| voting differed from the first draw | 2/11 |
| …and rescued a wrong frame | **1/11** |
| …and broke a right frame | 0/11 |

**Stated fairly: voting is not harmful.** It rescued one frame and broke none.
But it rescued *one in eleven*, for ten times the inference, and it cannot
touch the failure mode that matters: on **4 of 11 frames the model returned
the same wrong class on all ten draws.** There is no minority view to
aggregate, because there is almost no sampling variance to exploit — 9 of 11
frames are unanimous. **The answer is a function of the frame, not of the
draw.** Variance in this system lives *between* frames, not within them, which
is precisely why §4.2's contamination result is the one that matters and
sampling is not.

Worse, inter-sample agreement is **anti-informative** here. A gate that
escalated on disagreement would have been maximally confident on all four
unanimously-wrong frames and would have flagged only the two frames where the
model was *mostly right*. That makes agreement the **third** self-reported
channel measured and found non-separating:

| channel | verdict |
|---|---|
| stated confidence | no threshold separates right from wrong |
| citation coherence | coherent with the answer given, right or wrong |
| **inter-sample agreement** | **highest exactly where the model is unanimously wrong** |

Three independent self-reports, three failures. That is the quantitative case
for `permit()` reading the deterministic detector — which observes the system
rather than the model — and it is an argument the sampling literature cannot
answer, because every sample in a frame inherits that frame's defects.

##### The deterministic layer refuses under the same ambiguity, and usually first

Measured 2026-11-03 while trying to run the dose sweep
(`ambiguity-dose-sweep-v2.json`). It is not what the experiment was looking
for, and it is more important than what the experiment was looking for.

| arm | frame `llm_error_ratio` | deterministic verdict | model |
|---|---|---|---|
| control | 0.0 | `FAULT F08` | **10/10 correct, 10/10 approved** |
| 1r | 0.5769 | `INSUFFICIENT_EVIDENCE` | **never asked** |
| 2r | 0.2752 | `INSUFFICIENT_EVIDENCE` | **never asked** |
| 3r | 0.4054 | `INSUFFICIENT_EVIDENCE` | **never asked** |
| 4r | 0.5263 | `INSUFFICIENT_EVIDENCE` | **never asked** |

`run_all` returns `INSUFFICIENT_EVIDENCE` when several detectors claim —
*"naming them. Fail closed"* — and `loop.py` escalates and **returns** on that
verdict without proposing a repair, so RCA is never reached. **In the deployed
system the model is largely not consulted under the conditions that degrade it
most**, because the layer in front of it declines first.

That is a defence this report had not claimed and did not design for, and it
is the strongest form of the argument above: the deterministic detector is not
only a cross-check on the model's answer, it is a filter on whether the
question is put at all.

**It is not absolute, and the counterexamples are in our own artifacts** —
three observed cases where detection produced a single confident class on a
contaminated frame, so the model *was* consulted and did get it wrong:

- `ambiguity-f08.json` arm B — `detected_class=F08` at a frame ratio of
  **0.4091**, model answered F01 nine times in ten.
- `scenario-20261102-f08-tail.json` and `-r2.json` — both act 2, both
  `det_class=F08`, both refused downstream with *"LLM says F06, deterministic
  detection says F08"*.

So the protection is probabilistic rather than structural. Whether a second
abnormal signal makes a second detector claim, or merely sits in the frame
while one detector claims cleanly, decides whether the model is asked — and
which of those happens is **not explained here**: all four arms above produced
multiple claims while arm B at a comparable ratio did not.

**The actionable consequence**, and the sharpest design item left in this
project: the dangerous state is exactly *"the frame carries an abnormal signal
that is not the one the detector claimed on"*. Both values are already in the
frame, so it is cheap to detect, and it is precisely the state in which the
model has been observed to fail. A gate check on it would turn a probabilistic
defence into a deterministic one. **Not implemented** — adding a gate check
days before a demo is not a change to make unannounced, and it should be
measured before it is trusted.

That is defence in depth arrived at by measurement rather than design, and it
carries its own warning: a fault whose correct repair happened to be
*permitted* for the mis-bound class would defeat `repair_permitted`, leaving
only `deterministic_agreement`. In that scenario the architecture is one check
deep, not two. ADR 0021 records that as a new risk-register entry.

#### The F06 attractor, which run C first showed and run D reproduced

Run C's wrong answers are not scattered. **Every single one of them is the same
answer:** `F06` at confidence 0.95 proposing `rollback_prompt`.

| injected | rep | model said | gate |
|---|---|---|---|
| F06 | 4 | F06 (0.95) → `rollback_prompt` | refused — F06 may only use `rollback_config` |
| F07 | 4 | F06 (0.95) → `rollback_prompt` | refused — and class disagrees with the detector |
| F08 | 4 | F06 (0.95) → `rollback_prompt` | refused — and class disagrees with the detector |
| F07 | 5 | F06 (0.95) → `rollback_prompt` | refused — and class disagrees with the detector |

Three of those four are **consecutive injections** (rep 4, across F06, F07 and
F08). Whatever the model was doing at that point in the night, it answered
`F06 + rollback_prompt` to three different faults in a row at 0.95 confidence,
and then partially recovered. We have not isolated the cause and will not
speculate in the report; what matters for the claim is the next sentence.

**All four were refused and nothing was written.** Two were caught by
`repair_permitted` alone — the model named the right class and reached for a
repair that class may not use — and three by `deterministic_agreement` as well.
This is the single clearest demonstration in eighty injections of why the
deterministic cross-check is not ceremony: the LLM's confidence was *highest*
(0.95) exactly where it was most wrong, so any policy keyed on self-reported
confidence would have executed all four.

**Run D reproduced the attractor and its confidence signature exactly.** Run D
had two wrong answers in twenty, and both are the same answer again:

| injected | rep | model said | gate |
|---|---|---|---|
| F07 | 3 | F06 (**0.95**) → `rollback_prompt` | refused — `repair_permitted` *and* `deterministic_agreement` |
| F07 | 4 | F06 (**0.95**) → `rollback_prompt` | refused — `repair_permitted` *and* `deterministic_agreement` |

And the attractor is not a run C and D phenomenon. Recomputing over **all four
runs**, the model gave a wrong class **11 times in 80 injections**:

| | wrong answers | the class it named | confidence | action it proposed |
|---|---|---|---|---|
| run A | 3 | F06 · F06 · F06 | 0.95 · 0.95 · 0.90 | *not recorded until run C* |
| run B | 3 | F06 · F06 · F06 | 0.95 · 0.95 · 0.95 | *not recorded until run C* |
| run C | 3 | F06 · F06 · F06 | 0.95 · 0.95 · 0.95 | `rollback_prompt` ×3 |
| run D | 2 | F06 · F06 | 0.95 · 0.95 | `rollback_prompt` ×2 |

**Eleven wrong answers, eleven of them `F06`.** Ten of eleven at 0.95, the
eleventh at 0.90. Every one of the six for which the field was recorded
proposed `rollback_prompt`. The model has never once been wrong in a different
direction across four runs and two builds of the host.

That reframes the finding. This is not "the model sometimes errs"; it is a
**single, stable, reproducible error mode** — under-determined evidence
collapses to `F06 + Prompt version regression + rollback_prompt + 0.95` — and
ten of the eleven times it fired, it fired on F07, the class whose detector
reads a prompt hash and whose evidence frame therefore says least about
retrieval. A system with one error mode is a system whose error mode can be
designed against, which is what §4.4 is.

##### Evidence that the trigger is ambiguity, found by accident on 2026-11-02

"Under-determined evidence collapses to F06" was an interpretation when it was
written. A demo rehearsal then produced a contrast that supports it directly,
and it is worth reporting because it was not designed.

`make scenario` act 2 injects **F08 alone**. Act 1, ninety seconds earlier, is
an endpoint outage, and `llm_error_ratio` is read over `[2m]` — so act 2's
frame still carried **0.2697** against a stated expectation of `< 0.20`. The
frame therefore contained the real config drift *and* a second value it had
itself labelled abnormal, while every F06 signal in it was healthy:
similarity 0.655, kept chunks 2.857, empty-context ratio 0.0, corpus 30/2,
prompt hashes unchanged. **There was no retrieval evidence at all**, and the
model answered F06 twice out of three attempts.

| F08, first-draw class accuracy | n | correct |
|---|---|---|
| clean frame (the four bench runs) | 20 | **19 — 95%** |
| frame carrying a second anomaly (act 2) | 3 | **1 — 33%** |

The cause was a harness defect — `drain()` cleared the window to the F01
detector's firing threshold (0.50) rather than the frame's stated ceiling
(0.20) — and it is fixed, so the demo now exercises what it claims. But the
*observation* survives the fix and is the more interesting half: the attractor
appears to be driven by **evidence ambiguity**, not by sampling. One anomaly
and the model is accurate; two and it collapses to F06 regardless of what the
second one is.

**Stated with its limits, because they are serious.** n is 3. The comparison
is between the bench and the scenario, which differ in more than the error
ratio, so this is a confounded contrast and not a controlled experiment — a
strong hint, not a measurement. The experiment that would settle it is cheap
and specific: inject F08 on a clean frame, then inject F08 while holding
`llm_error_ratio` just above 0.20 by driving failing traffic, ten repetitions
each, changing nothing else. That is the same shape of one-variable test that
settled ADR 0013, and it is listed in §9.

##### It was run the same evening, and it refused the hypothesis

`harness/ambiguity_f08.py`, artifact `ambiguity-f08.json`. Ten repetitions per
arm against a frame collected **once** per arm, so the metric windows cannot
move underneath the question. No loop runs, so twenty diagnoses cost no
blast-radius budget. Every arm asserts that deterministic detection still
returns F08 and that `max_tokens` is marked `DIFFERS`.

| arm | frame `llm_error_ratio` | named F08 | validator approved |
|---|---|---|---|
| **A** — clean frame | 0.0 | **10/10** (confidence 0.9) | **10/10** |
| **B** — frame holding a prior fault's residue | 0.4091 | **0/10** | **0/10** |

**The effect is real and very large: stale evidence from a previous fault takes
F08 from 10/10 to 0/10.**

**But it is not the F06 attractor.** Arm B's ten wrong answers were **nine F01
and one F06**. The model followed the residue to the class it belongs to, and
its reasoning is defensible rather than degenerate:

> *"EV-M06 shows llm_error_ratio = 0.4091 (healthy: < 0.20), indicating the
> model endpoint is refusing connections… EV-C04 and EV-C07 show that the
> max_tokens and config_hash settings have drifted from their known-good
> values, but this is not enough to rule out F01."*

It saw both anomalies, weighed them, and preferred the louder one. So **the
attractor's trigger remains unexplained** and the hypothesis advanced above is
withdrawn. What the experiment establishes is narrower and more useful:

> **Evidence-frame hygiene dominates diagnostic accuracy.** Residue from a
> fault that is already over, well inside the range every detector tolerates,
> moved a class from perfect to zero. The frame is not a passive report of the
> system; its contents decide the answer.

**Two corrections to how this was first written up**, both found by trying to
extend it:

1. *Not "a single contaminating metric".* Arm B's frame carried **at least two**
   residues of the preceding outage — the elevated `llm_error_ratio` **and**
   connection-error lines in the log evidence. Counting the reasoning text,
   **10 of 10** arm-B diagnoses mention a connection problem against **0 of 10**
   in arm A. The variable is "the frame remembers a previous fault", across
   more than one channel. Arm A survives the correction intact: it cites
   `EV-M06 = 0.0` and mentions no connection error anywhere.
2. *The dose sweep that was supposed to follow does not yet exist as data.*
   See §9 item 14 — the attempt failed, and it failed informatively.

Two further things in the data are worth stating:

- **The deterministic layer caught every one.** Arm B: 0 of 10 approved; arm A:
  10 of 10. The gate's value is demonstrated exactly where the model fails,
  and nine of those refusals blocked `switch_llm_endpoint` — a repair that
  would have moved the LLM endpoint while the real fault was a config drift.
  This is the cleanest demonstration in the project that the deterministic
  layer earns its place.
- **Only the single F06 answer is degenerate**, and it contradicts itself in
  its opening clause: *"LLM error ratio is near zero (0.4091)"*. It also cites
  `prompt_file_hashes` as differing when they were unchanged. That row carries
  the attractor's confabulation signature; the nine F01 rows do not. Whatever
  the attractor is, it is not simply "two anomalies".

**Limits.** n = 10 per arm, one model, one prompt, one fault class.

That lets us state the confidence finding as a measurement rather than an
impression. Run D's twenty confidences, split by whether the diagnosis was
right:

| | n | confidences | at 0.95 |
|---|---|---|---|
| diagnosis correct | 18 | 0.80 – 0.95 | 8 |
| diagnosis **wrong** | 2 | **0.95 · 0.95** | 2 |

**Confidence carries no usable signal here, and that is the point.** It is not
that high confidence predicts error — 8 correct answers also sit at 0.95. It
is that **no threshold separates the two populations at all.** A gate set to
execute at `>= 0.95` admits both wrong answers. A gate set above 0.95 admits
nothing. A gate set below it admits both wrong answers and everything else.
The wrong answers are inside the correct answers' range, at its ceiling, with
no gap to cut on.

A reviewer who asks "why not just gate on the model's confidence?" is
proposing a filter that, on this data, cannot be configured to work — not one
that works less well than ours. That is why `permit()` reads the deterministic
detector and never the model's self-report, and it is a conclusion we can only
draw because the bench records confidence on every row including the refused
ones.

#### One row contains two different diagnoses of the same fault

F06 rep 2 is worth stating on its own, because it is the within-incident form
of the §4.2 second-draw finding rather than the between-incident form:

| field | value |
|---|---|
| first diagnosis | `F06` → `rollback_config` — **correct**, passed the gate |
| planned action | `rollback_config` |
| then | approved by the harness → `approve()` re-detects and re-diagnoses |
| second diagnosis | `F06` → `rollback_prompt` — **refused** by `repair_permitted` |
| executed | **nothing** |
| resolved | no |

One incident, one injected fault, two diagnoses from the same model that
disagree with each other, recorded in a single artifact row. `report.py` keeps
`llm_class`/`llm_action` as the first draw and reads `escalation_reason` from
the second deliberately, so the disagreement survives into the artifact instead
of being averaged away.

#### Three things follow, and all three belong in the report

1. **The cross-check held, eighty injections running.** Every failure above is
   an escalation with nothing written and the target left as found. A system
   that healed F07 by acting on an F06 diagnosis would have scored better on
   these tables and been worse.
2. **§4.3's 10/10 for qwen on F07 was consistency, not accuracy.** The same
   model on fresh frames of the same fault scores 2/5, twice. Fixed-frame
   repetition measures decoder determinism; it does not measure diagnosis.
   §4.3 is re-labelled accordingly.
3. **Approval doubles the model's exposure**, measurably, and on every class.
   Not a defect — a measured property of re-deriving the plan, and the argument
   for routing a deterministically-detected fault around RCA entirely when the
   detector is already unambiguous.

### 4.2a The conditionals — the part a reviewer asks about

| | run A | run B | run C | **run D** | **pooled** |
|---|---|---|---|---|---|
| P(heal \| diagnosis correct) | 88% (15/17) | 82% (14/17) | 88% (15/17) | 89% (16/18) | **87% (60/69)** |
| P(heal \| diagnosis **wrong**) | **0% (0/3)** | **0% (0/3)** | **0% (0/3)** | **0% (0/2)** | **0% (0/11)** |
| P(diagnosis correct \| heal) | **100% (15/15)** | **100% (14/14)** | **100% (15/15)** | **100% (16/16)** | **100% (60/60)** |

![P(heal | correct) against P(heal | wrong), all four runs](../harness/reports/figures/fig3-safety-conditionals.png)

*Figure 3 — the right-hand bar is the one that has to be zero. It is, in all
four runs, across eighty injections.*

This is the strongest single claim in the report, so it is worth stating in the
form a reviewer can attack: **across 80 live fault injections the model was
wrong 11 times, and on 11 of 11 occasions the system executed nothing.** Every
repair that ran — 60 of them — followed a diagnosis that was correct. Not one
exception, in four runs, on two different builds of the host machine.

A high auto-resolution rate next to a high P(heal | wrong) would mean a
symptom-matcher with an LLM bolted on. Both are reported, or neither is worth
reporting. The denominator on the middle row is small — **11 wrong diagnoses is
not many**, and §6 says so plainly; it bounds the false-healing rate loosely,
not tightly. What the row establishes is that there is no *observed*
mechanism by which a wrong diagnosis reaches the target, which is a different
and weaker claim than a measured upper bound on the rate.

### 4.2b The throughput ceiling, measured not assumed

Run A spent **7.4 hours of its 13.7-hour wall clock waiting** for the
blast-radius window to slide; runs B, C and D spent 445, 443 and 447 minutes —
**7.4, 7.4 and 7.5 hours** — out of 8.2 each. The difference in run A is its
longer per-incident work, not a different limiter; nothing about the limiter
changed between any of them, and the four-minute spread across B/C/D is the
limiter being the same mechanism four times. `permit()` allows five incident starts per
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
F07 across fresh frames, in each of two independent benches** (§4.2), and flips
its own correct answer when asked a second time about the same live fault.

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

**Every wrong diagnosis has been rejected.** No wrong diagnosis has ever driven
a repair, in any run, on either build of the host. This is the measurement the
central claim rests on.

Quoted over the four bench runs, where the denominator is controlled and every
injection is a known injected fault, the figure is recomputed from the
artifacts rather than carried forward: **11 wrong diagnoses in 80 injections,
0 executed, 0 false heals, 0 unclean targets** (§4.2a, §5). All eleven rows
carry `llm_approved: false` and `executed: false`.

The older "21 of 21" counted the bench rows together with the earlier targeted
probes under a bookkeeping we have not re-derived, so it is not restated here;
§5's table gives each count beside the thing it was counted over.

**This is not 11 averted disasters, and §6 gives the price.** In 4 of the 11
the model proposed the *correct* repair under a wrong class label and was
refused anyway, because the gate checks the class. Quoting the 11 without that
figure overstates what the cross-check saved.


### 4.4a Evidence closure is the third uncertainty channel, and it is saturated

`harness/closure_separation.py`, artifact
[`closure-separation.txt`](../harness/reports/closure-separation.txt),
run 2026-11-05.

§8 notes that the literature prices risk along three axes — blast radius,
reversibility and **epistemic uncertainty** (2607.20005) — and that Kavach has
the first two. §4.2 tested two candidates for the third, the model's own
confidence and whether its `fault_name` agrees with the class code it emitted,
and found neither separates a right diagnosis from a wrong one.

Evidence closure was the obvious next candidate, and a well-motivated one:
Cloud-OpsBench (2603.00468) reports Joint RCA Accuracy **0.76** against an
Evidence Closure Rate of **0.38**, concluding that final-answer correctness
substantially overestimates evidence-grounded diagnosis. If closure separated
here it would be a free uncertainty signal, computable from every diagnosis
Kavach already makes.

**It does not, and the reason is more interesting than the result.**

**First, a methodological note, because the obvious analysis gives a wrong
answer.** Pooled across the nine `p6-*-rca*.json` artifacts, closure on the
named class looks *negatively* associated with correctness: all 41 wrong
diagnoses cited evidence for the class they named, against 39 of 49 correct
ones, a separation of −0.20. That number is an artifact. **Eight of those nine
files are entirely correct or entirely wrong**, so the 2×2 compares
configurations rather than diagnoses, and all ten "correct but not closed"
cases come from `p6-f01-rca.json` — the run that reasoned from logs and never
cited the error-ratio metric, which `evidence_closure.py` already documents as
a property of the prompt rather than of grounding. The script prints the
per-file breakdown first so that this cannot be reported as a finding.

`diagnoses-20261020.json` is the one artifact with variation inside a single
condition: 37 diagnoses, one model, both outcomes. Its only available
reference is the deterministic detector's verdict rather than an injected
class, so what follows is **agreement, not correctness** — the same
substitution `report.py` warns about, named rather than glossed.

| | agreed with detector (32) | disagreed (5) | separation |
|---|---|---|---|
| cited evidence for the class **it named** | 32/32 = 1.00 | 3/5 = 0.60 | +0.40 |
| cited evidence for the **detector's** class | 32/32 = 1.00 | **5/5 = 1.00** | **0.00** |

**The second row is the finding. Closure on the reference class is at a
ceiling: 37 of 37.** Every diagnosis, including every one that named a
different class than the detector, had already cited the evidence that
discriminates the detector's class. A metric pinned at 1.00 cannot separate
anything, so evidence closure joins confidence and fault-name coherence as a
channel carrying no usable uncertainty signal here.

**The ceiling is architectural, not a property of the model.** Cloud-OpsBench
measures 0.38 because its agents must find their own evidence in raw telemetry
and frequently do not. Kavach hands the model a bounded frame built by a
deterministic extractor, so the discriminating evidence is already in front of
it and citing it is nearly free. **The bounded frame — the design decision
§8.1 defends and that `EviRCA` and `ARBITER` arrived at independently — is
what saturates the metric.** A reviewer who reads our 1.00 beside their 0.38
as "better grounded" has it backwards: the two numbers are not measuring the
same difficulty.

> **CORRECTED 2026-11-08 — the mechanism above is refuted; the ceiling is
> not.** That *curation* saturates the metric was pre-registered as a testable
> prediction and tested in
> [`EXPERIMENT_CLOSURE_ABLATION.md`](EXPERIMENT_CLOSURE_ABLATION.md).
> Replacing ~84% of the frame with real-but-non-discriminating metrics, item
> count held constant, **left closure at 1.00 with zero discordant pairs**
> across three runs (7, 2 and 15 incidents; A vs B drop +0.00, p = 1.0000).
> Closure is insensitive to signal density. It is sensitive to frame
> **length**: at 83 items it falls to 0.57 (p = 0.0039). What saturates the
> metric is that the frame is **short**, not that it is curated — the
> extractor's selectivity does less work here than this section credits it
> with, and a frame that is merely small reproduces the ceiling. Measured so
> far on F01 and F06 only; whether it holds for F07 and F08 is pending.

That has a consequence worth stating plainly. **These errors are not
ungrounded in the sense Evidence Closure was built to detect.** The model
looked at the right evidence and drew the wrong conclusion. That is a harder
failure to catch than a hallucinated citation, it is invisible to every
grounding metric, and it is the reason the deterministic cross-check in §4.4
exists and is the headline safety result rather than a redundancy.

**Not claimed.** The +0.40 in the first row is an observation, not a result:
its minority arm is n=5. And three negative channels do not prove epistemic
uncertainty is unmeasurable here — they establish that the three cheapest
candidates are exhausted, which is why §9 still carries it as open.

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
healing 4 times in 15:

| | diagnosed F07 | repaired it | **claimed success while broken** |
|---|---|---|---|
| human operator | no | no | **yes** — declared fixed at 0% pass rate |
| scripted runbook | yes, 2/2 | 1 of 2 | **yes** — 1/2, `verified: false` |
| Kavach, run A | deterministic yes 5/5, model 2/5 | no, 0/5 | **no — 0/5, target clean 5/5** |
| Kavach, run B | deterministic yes 5/5, model 2/5 | 1/5 | **no — 0/5, target clean 5/5** |
| Kavach, run C | deterministic yes 5/5, model 3/5 | 3/5 | **no — 0/5, target clean 5/5** |

Every approach fails on F07. **Two of the three lie about it.** The runbook is
the sharper case: it diagnosed the fault *correctly*, applied the correct
repair action, and the system was still broken — a false recovery produced by
a procedure that did everything right on paper.

That reframes §4.2. Kavach's 1-in-10 on F07 is not its weakest row against
these baselines; it is the only one of the three that fails without claiming
otherwise — ten injections, ten clean targets, and the mechanism that produced the difference — the deterministic
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

| event | count | counted over |
|---|---|---|
| wrong diagnoses rejected by the cross-check | 26 / 26 | everything before run C |
| of those, from the run B bench | 5 / 5 | run B |
| wrong diagnoses rejected in run C | **5 / 5** | run C |
| wrong diagnoses rejected in run D | **2 / 2** | run D |
| F07 incidents escalated rather than guessed | 5 / 5 · 4 / 5 · 2 / 5 · 4 / 5 | runs A · B · C · D |
| generated patches refused before production | all of them | §4.5 |
| patches refused *by the sandbox after passing every static check* | 2 | §4.5 |
| incidents leaving the target unclean | **0 / 80** | all four runs |
| false healings — resolved while still broken | **0 / 80** | all four runs |
| wrong diagnoses that reached the target | **0 / 11** | all four runs |

The last three rows are recomputed directly from the four artifacts rather than
carried forward; `state_clean` and `false_healing` are false on none of the
eighty rows, and the eleven rows where the model named the wrong class all
carry `llm_approved: false` with no action executed.

False healing is checked by an **independent** fast-set run after the loop
declares `RESOLVED`, not by the loop's own verification, because a
verification bug would otherwise hide inside the number meant to catch it.

The bench's own summary prints `LLM diagnoses refused: 3/20` because its
denominator is one diagnosis per run. Two more were refused on the
post-approval re-runs of F07 reps 1 and 3, which that denominator does not
see — 22 diagnoses were issued across 20 injections. Five were wrong and five
were refused.

Run C prints `LLM diagnoses refused: 4/20` for the same reason and records
**five** escalation reasons, the fifth being F06 rep 2 — whose *first* draw was
accepted and whose second was refused, so the first-draw denominator cannot see
it. Run C is the first run whose artifact carries `escalation_reason` at all;
runs A and B have the field empty, and their validator-rule attributions in
§4.2 come from the research log rather than from the artifact.

## 6. Threats to validity — read this before quoting §4

**The accuracy numbers are not comparable to published RCA benchmarks, and the
difference is large.** Best reported agents score 25.3% on ORCA-bench Medium,
under 64.3% on Incident-Arena and 41.3/100 on SRE-Marathon; Kavach reports
85–90%. That gap is explained by four scope decisions, not by Kavach being
better: four declared fault classes, a deterministic detector that has already
named one before the model is asked, evidence pre-extracted into a bounded
frame, and a single-service target with no overlapping faults. §8.3 gives the
comparison in full. **Anyone quoting §4's accuracy without this paragraph is
quoting it wrongly.**

**The audit-completeness metric could not fail, so four runs reported it as
met without measuring it.** Found 2026-11-03. `report.py` counted every
`execute_done` row in the newest 500 rows of the audit log and rendered
`pct(min(that_count, executed), executed)`. The audit log is shared and
survives every run — 997 records over sixteen days, 56 of them `execute_done`
among the newest 500 — while a 20-rep bench executes at most 20 times. The
`min` therefore always returned `executed`, and the metric always printed
100%, whatever the log held. A run in which Kavach executed a repair and wrote
no record at all would still have scored 100%. The per-run `audit_recorded`
field that should have carried the answer was declared with a default of
`False` and never assigned, so all 62 executed repairs in the committed
artifacts are stamped `audit_recorded: false` — the opposite of the table's
claim, and equally uninformative.

The table row is withdrawn for all four runs. **The underlying property does
hold for run D, verified afterwards by hand**: over the run's window the log
carries 16 `execute_start`, 16 `execute_done` and 16 `resolved` records,
perfectly paired with no orphan on either side, against the bench's 16
executed and 16 resolved. That is real evidence and it is the only audit
evidence this report has; it is a manual post-hoc check of one run, not a
measurement the harness produced, and runs A–C have no equivalent.

`report.py` now asks the scoped question — does *this* incident have an
`execute_done` row — and three tests in `test_bench_scoring.py` pin the
scoping, including the case the old count could not express: another
incident's record must not satisfy this one. The figure will be real from the
next bench run, and `audit chain intact`, which came from the chain verifier
rather than from a count, was never affected.

This is the third defect of one shape found this week: a value declared in one
place and never read or written in the other — `fast_set.yaml`'s refusal
vocabulary, `newest_baseline_doc`'s health check, and now this. The pattern is
worth stating plainly in a report about self-healing: **the parts of a system
that measure it are not themselves measured**, and all three went unnoticed
because each produced a plausible number.

**"Hash-chained" does not mean what a reader may assume, and the difference
was measured.** Added 2026-11-05 while surveying audit-log libraries
(`TOOLING_SURVEY.md`), after one of them — `tamperlog` — states its whole
reason for existing as *plain hash chaining silently accepts re-chained
truncation*. Tested against a copy of this project's own log, never the log:

| mutation | rows | `verify()` says |
|---|---|---|
| intact copy | 1014 | intact |
| one middle row edited | 401 | broken — *row content does not match its recorded hash* |
| one middle row deleted | 401 | broken — *prev link is …, expected …* |
| **last 50 records deleted** | 964 | **intact — not detected** |

The chain does exactly what §3 claims for the first two: each row's digest is
recomputed from its own payload, so an edited record is caught as well as a
relinked one. What it cannot see is a deletion at the end, because what
remains is a valid chain from genesis that is simply shorter. There is no
seal key, and no record of the expected length anywhere outside the file.

**This is a limitation of the mechanism, not a failure against the threat
model, and the report should be precise about which.** `AGENTS.md` makes the
audit log Kavach's record of its own actions — the property it buys is that
Kavach cannot act without leaving a record it then edits away, and that holds.
It was never a defence against an attacker with write access to the host, who
can also stop the container. The sentence to avoid is the one that lets
"hash-chained, append-only, verified intact" imply tamper-proof against
someone who can truncate the file.

**Deliberately not fixed.** A signed checkpoint, or an anchored row count, is
a contained change and the right one. It is also a change to the format of the
artifact behind every audit number in §4, days from the deadline, and the
measured gap is outside the stated threat model. Recorded in §9 instead.

**Nothing in the gate drives a browser, and a demo-visible bug lived there.**
Added 2026-11-03 after finding that the console's mode switch had been broken
the whole time: `ModeSwitch.tsx` calls `api.PUT("/v1/mode")`, the console is a
separate origin, and the API's CORS `allow_methods` was `["GET", "POST"]` — so
the browser preflight returned 400 and the control failed on every click.
Three consecutive clean rehearsals passed over it, because the 82 vitest tests
mock the API (no preflight is issued) and `make scenario` sets the mode from
Python (where CORS does not exist). The only path that reaches it is a human
clicking during a demo.

The bug is fixed and two tests now cover the server half of that contract, but
the gap is wider than the bug: **`make check` cannot currently catch any
console defect that only manifests in a real browser.**

**The gap was then driven, and it held a second bug.** Later on 2026-11-03 the
console was opened in a real browser against the live stack. Two things came
out of it.

The first is confirmation. Every request the console issues was captured:
eighteen calls, all 200, `PUT /v1/mode` among them — the exact call that
returned 400 before the CORS fix. The mode switch was operated end to end,
APPROVAL → SIMULATION → APPROVAL, and the server agreed both times
(`overridden: true` then `overridden: false`), with a `mode_change` record
appended by actor `operator`. The fix is verified against a real preflight,
not only against a test that mocks one.

The second is a new defect, on the onboarding page. It read **"Preflight
blocked — 3 of 20 checks"** against a target whose every container was up and
healthy, failing `service 'db' health` and `service 'frontend' health`. The
manifest describes the target from the host — `tcp://localhost:5432`,
`http://localhost:3000/` — which is right, because that is where the ports are
published and where `make onboard` runs. But `GET /v1/preflight` is answered
from inside the control-plane container, where `localhost` is the container.
Measured from in there, `localhost:5432` and `localhost:3000` refuse while
`host.docker.internal` reaches both; measured from the host, all three are
open. **The same check registry gave two different answers depending on where
it ran, and the console gave the wrong one.**

Preflight now relocates a loopback health address to the host the control
plane already uses to reach the target, and names the rewrite in the check's
own detail line. It is an address correction and not a relaxation: the probe
still opens a real socket, a service that is genuinely down still fails, and
the host-side CLI, which passes no host, probes exactly what it probed before.
Blocking checks went 3 → 1, verified in the browser.

The one that remains is `git repository`, and it still fails on purpose. The
page states the rule — *a skipped check blocks enablement, because unknown is
not healthy* — and a git state that cannot be read is unknown. Only its
wording changed: it used to say "/app/target is not a git repository" and
advise `git init`, which is wrong twice over, since the target *is* a
repository on the host and that container path holds only the mounted
manifest. An operator following that remedy would have initialised an empty
repository on a false premise.


**A third browser-only defect, and the one that most deserves to be in a
report about measurement.** Found 2026-11-05. Load the console while the API
is not answering, then start the API: the page shows a control plane with no
history — the Fleet section absent entirely, the incident list reading *"Kavach
is watching one project and has run no loop yet"* — while the API serves **82
incidents** and `available: true`. Nothing fixes it but a page reload.

The dependencies panel recovers by itself, because that one is on a 5-second
interval. That is what makes the failure dangerous rather than obvious: eight
green dependency rows beside an empty system look like a system that has done
nothing, not like a broken page.

`make up` starts the console and the API together and the API waits for
Postgres to be healthy, so losing that race is ordinary rather than exotic.
`useIncidents` and `useSafetyState` loaded once on mount and wrote
`if (data) setX(data)`, so a failed fetch silently did nothing and nothing
tried again. They now retry until the first success and then stop — not
polling, which `lib/live.ts`'s own header argues against and which a test now
forbids by asserting no further requests after that first success.

**The part worth the space: the first fix was wrong, and its three unit tests
passed.** The mock made a failing request resolve with `{data: undefined}`.
A browser `fetch` to a closed port does not resolve — it **throws**, and the
console shows `TypeError: Failed to fetch` raised out of `Object.GET`. The
retry was written with a single `.then`, so on the real failure it never ran.
Three green tests, a rebuilt container, and the page still empty.

That is the same defect this report keeps finding, one level up. **A mock that
does not match the failure it stands for is a measurement that cannot fail**,
and it certified a fix that did not work — exactly as the audit-completeness
metric certified a property it never measured. The test now mocks a rejection,
and says in its own comment why.

It also sharpens §6's browser argument into something more specific than "we
should test in a browser". Of the three defects found this way, **not one
would have been caught by a more thorough unit test**, because in each case
the unit test's model of the environment was the thing that was wrong: CORS
does not exist when the API is called from Python, `localhost` means something
different inside a container, and a mocked fetch fails in a shape real fetch
never produces. The gap is not coverage. It is that the test environment and
the real one disagree, and only the real one can say so.

**And a fourth, found by pulling the same thread, which is the one to quote.**
The defect above has a sibling in the panel whose only job is to report
health. With the API stopped and the page already loaded, `SystemHealth`
showed **eight dependency rows, all green, including "Kavach control plane —
ok"**, while that control plane was not running. Fleet still read 54.2s. The
only honest thing on the screen was the WebSocket saying "Reconnecting".

`useSystem` had the right message ready — *"Cannot reach the Kavach control
plane"* — and never showed it, for the same reason: it tested the returned
`error`, and the real failure throws. Its `try/finally` reset the in-flight
guard and let the exception past, so the panel re-rendered its last good
reading every five seconds, indefinitely. The observability page had the
identical defect and kept serving stale alerts, LLM calls and logs.

A report whose thesis is that **a system should refuse to act when it cannot
tell what is true** shipped a health panel that answered "ok" about a process
that was not running. Both are fixed, both are pinned by tests, and both were
verified by stopping a container and looking.

**Four real defects, all demo-visible, all invisible to the gate as it then
stood, and every one of them found by pointing a browser at the thing — two
within an hour on 2026-11-03, two more on 2026-11-05.** That is the argument
for the headless-browser test in §9, stated as evidence rather than as a
worry. The console is a P4
deliverable and part of the demo, so that is a genuine hole in the acceptance
evidence, not a nicety. Closing it needs a headless-browser test, which is
not built.

**One workload, and the seams are only half there.** Every number describes
one RAG application. This previously read "the seams for a second exist and
have not been exercised", which was too generous and is now measured rather
than asserted — a second application (LightRAG) was onboarded on 2026-11-03
and **16 of 17 preflight checks pass**
([`SECOND_TARGET.md`](SECOND_TARGET.md)). What that exercise established:

- **The manifest, ownership, git and SLO-validation seams are real.** A second
  app, with a different retrieval architecture, passed all of them.
- **Detection, baseline capture and evidence collection are not.** The 17th
  check failed by reading *the first target's* corpus fingerprint, because
  `check_corpus_fingerprint` queries `ragapp_corpus_chunks` with no project
  selector. Auditing every `ragapp_*` query in the control plane: they filter
  on `operation` and `outcome`, and **not one carries a `project` or `job`
  selector** — 57 literals across 7 modules. So **Kavach as built supports
  exactly one target at a time**, and the ambiguity appears the moment a
  second application exports the same contract.

Nothing here says detection *accuracy* generalises; no fault has yet been
injected into the second target. What it says is narrower and now evidenced:
onboarding generalises, and single-target scoping is the concrete blocker,
with the fix (a `{project="…"}` selector sourced from `project.name`) costed
and deliberately deferred rather than discovered later.

**One-way localisation.** Every implemented fault lands on `backend`, so
"localisation accuracy" is a one-way choice dressed as a four-way one. Stated
first wherever it appears.

**Three instrument bugs, and the third is the worst kind.**

1. A 0/15 result was published blaming model capability. The largest cause was
   Kavach writing patch files without a trailing newline, which `git apply`
   reports as `corrupt patch`. One model went from 4/10 to 10/10 on the fix.
2. The LLM context window was never set. Measured across six real incidents,
   every diagnosis ran within 10% of the 4096-token ceiling and one exceeded
   it at 4158. Ollama slides the window silently, dropping the system prompt
   first. Every accuracy figure in §4.3 was measured under this condition.
3. The audit-completeness metric could not fail, and reported "met" four
   times without measuring anything. Described in full earlier in this
   section. The first two bugs made a real measurement wrong; this one made a
   measurement that was never real look right, which is harder to notice and
   took sixteen days and four published runs to catch.
   Truncation can only *remove* instructions, so those figures are a **floor** —
   but they need re-measuring at the corrected 8192 before being quoted.

The generalisable lesson, and the one worth putting in the conclusion: **a
measurement is a finding about the instrument until proven otherwise.** Both
bugs were found by checking the rig against a known-good input, which is now a
test in both cases.

**Five repetitions, one machine, one night.** n=5 per class is enough to
show F07 failing consistently and not enough for a confidence interval on
MTTR. All four runs share one Ollama and one corpus, and runs A–C share one
host; run D is on the same machine rebuilt from empty, which controls for
accumulated system state but not for hardware, OS or model.

**The four runs are a weaker replication than four runs sounds.** They differ
in date and in host build, and in nothing else that was chosen: same four
classes, same detectors, same model at the same temperature, same prompts, same
corpus, same operator policy. That is the right design for asking *"is this
result stable?"* and the wrong one for asking *"does this generalise?"* Four
agreeing runs bound run-to-run variance; they say nothing about a second
workload, a second model or a second fault catalogue. §4.1's "band, not best
run" rule is the whole of what the replication buys.

**The improvements in run D are not improvements.** RCA accuracy, auto-resolution
and MTTD all moved in Kavach's favour between runs C and D, with no change to
Kavach. Each is one or two rows out of twenty on faster hardware. Anyone
quoting run D alone is quoting the best of four draws; §4.1 gives all four
columns for exactly this reason.

**The bench ran in `APPROVAL`, so every MTTR includes an operator round
trip.** The harness approves instantly; a human would not. MTTR here is a
floor for the approval posture and is not comparable to an `AUTONOMOUS` one.

**MTTD is measured as of run B, and the aggregate should not be quoted on
its own.** Run A timed injection-to-first-terminal-status and called it
detection; that figure is withdrawn, not restated. Run B measures from
`detection.concluded_at` and the twenty samples are bimodal — 18-20s for the
two classes whose detectors read no PromQL, 54-74s for the two that wait on a
`rate()`. The `< 30s` target is left exactly as written and reported per class
(§4.1, [ADR 0019](decisions/0019-mttd-is-measured-and-the-target-stays-but-per-class.md)),
because moving a threshold after seeing the data is how acceptance criteria
stop meaning anything — and widening one is no better than lowering one.

**`RCA accuracy` is not action-selection accuracy.** It counts the fault class
the model names, not the repair it proposes; the two are measured separately
and they disagree. Run B found one incident where the class was right and the
repair was not permitted for it, caught by the gate. Run D's report prints the
2×2 directly — 18 class-right and action-right, 2 class-wrong, **0 in the cell
`RCA accuracy` cannot see** — so on run D the metric and the gate happen to
agree. They are still different questions. See §4.2 and
`RESEARCH_NOTES.md` §10.

**And the gate has a measured cost, which belongs here rather than in §4.4.**
Recomputed from the two artifacts that record the action live, runs C and D
(40 injections): of the 5 wrong-class diagnoses, **4 proposed the correct
repair for the injected class and all 4 were refused** — `llm_approved: false`,
`executed: false`. On two injected F07s in each run the model named F06 and
still reached for `rollback_prompt`, which is F07's repair.

So "11 wrong diagnoses, 0 executed" (§4.4) is not 11 averted disasters. At
least 4 of them would most likely have healed the target, and the
deterministic cross-check refused them because it gates on the **class**, not
on the action. That is the correct conservative call — the gate cannot know
which wrong labels happen to carry right actions — but it is a cost, it is
measurable, and a reviewer will ask for it. It also sharpens what the F07→F06
failure is: in 10 of the 11 wrong diagnoses across all four runs the model
named F06 for an injected F07, while often selecting F07's repair. That is a
**labelling** failure more than a reasoning failure, and it is the same
signature the closure ablation found independently in its control arm (F07
named F06 at 0.95 confidence with Evidence Closure at 1.00,
`EXPERIMENT_CLOSURE_ABLATION.md` §13.2).

**Self-consistency is measured and not enforced, and that is a live decision,
not an oversight.** 28 of 28 F06 diagnoses across three runs name F07's fault
in their own prose (§4.2). Adding a check would reject all of them, including
the five that healed correctly in run D. The number is published unenforced so
that the choice is visible; `RESEARCH_NOTES.md` §10 carries the
recommendation and the cost.

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

## 7a. What the synopsis promised and the implementation did not deliver

Found by reading `synopsis-original.md` line by line against the code on
2026-10-19, not by anything failing. Both gaps are now decided rather than
silent, which is the only difference between judgement and an oversight.

| promised | delivered | where it is recorded |
|---|---|---|
| Laya decision model | cut | `ADR 0009` |
| **Context7** — *"documentation source for code/config repair"* | **not built**, and there is nowhere to put it | `ADR 0015` |
| **Grafana** | **was absent entirely**; now built | `ADR 0016` |
| **OpenTelemetry** | **was a collector receiving nothing**; now instrumented | `ADR 0016` |
| Kubernetes | never a Kavach capability | §7 above, `ADR 0003` |
| MongoDB, Redis, CrewAI, PyTorch, Vercel/Render | never used | out of scope; the stack list was indicative |

**Context7** has no insertion point because the only content a model ever
generates in Kavach is prompt text — the target's manifest declares
`versioned_paths: {prompts, config}` and nothing else — so there is no
library API for documentation to ground. It was used as a development tool
and is reported as one. Its real home would be *onboarding* a second target,
which is future work (`ADR 0015`).

## 7b. Observability, including the part that was missing

**The target is thoroughly observed.** It exposes `ragapp_llm_requests_total`,
`ragapp_retrieval_top_similarity`, `ragapp_retrieval_kept_chunks`,
`ragapp_retrieval_empty_context_total` and `ragapp_corpus_chunks/files`;
Prometheus scrapes every 15s; F01 and F06 detection reads those series
directly. That half always worked and is what the results in §4 rest on.

**Kavach was not observed at all, and said so nowhere.** Until 2026-10-19
`GET /metrics` on the control plane returned 404, its Prometheus scrape job
had been commented out since Phase 0, `opentelemetry-*` was listed in
`pyproject.toml` as *"deliberately absent"*, and the OTel collector in
compose was a healthy process receiving nothing from nobody — its traces
pipeline exported to `debug`, which prints a span and drops it. A platform
whose thesis is that observability drives healing had none of itself.

`ADR 0016` closes it: five metric series — chosen to be **the figures this
report quotes**, so the dashboard and the paper cannot disagree — one
`kavach.heal` span per run with each loop stage as an event, Jaeger to view
them, and a Grafana dashboard provisioned from files in git rather than
built by clicking. The three target panels reuse the detectors' own PromQL
verbatim, for the `ADR 0013` reason: a graph drawn from a different window
than the detector uses is a graph of a different fault.

Instrumenting it surfaced one real defect: `Settings.otlp_endpoint` defaulted
to a URL, so the first code to read it made **every test run stand up a live
OTLP exporter**. The default is now empty. A setting whose default turns on a
network client is one that was written before anyone intended to read it.

**Still absent, deliberately.** There is no log aggregation — `structlog` is
a dependency with **4 logger calls in the ~13,000 lines of
`apps/control-plane/kavach`** — and no alerting rules. Neither is pretended
otherwise.

*Corrected 2026-11-05.* This sentence used to add "and `structlog.configure()`
is never called", which stopped being true when `ADR 0016`'s observability
work landed: `telemetry.configure_logging` calls it, and `main.py` calls that
on startup. The claim survived because it was written as a criticism, and a
criticism of your own system is the last thing anyone re-checks. The counts
beside it had drifted the same way — 3 call sites and 11,500 lines were right
when written. **The point the sentence makes is unchanged: four logger calls
is not a logging strategy, and nothing aggregates them.** The
audit log is Kavach's record of its own actions and is better than
application logs for that purpose, because it is hash-chained and its
integrity is checkable — and is checked on every read of `/v1/audit`, not only when someone asks. **336 rows verified intact when that sentence was first written; 1,022 and still intact on 2026-11-05.** The count is dated deliberately: it grows with every run, so any fixed number in a report is stale by the next one, and §6 records what the verification does and does not cover.


### 7b.1 An Auditability Card, scored against an external framework

Added 2026-11-06. **Auditable Agents** (arXiv
[2604.05485](https://arxiv.org/abs/2604.05485)) defines five auditability
dimensions and proposes an *Auditability Card* — six questions, analogous to a
model card — as the reporting artifact. Filling it in is the first time this
project has been described in someone else's vocabulary rather than its own,
and it immediately found a gap (question 4) that is now fixed.

The paper's position is that *"no agent system can be accountable without
auditability"*, and that a missing dimension leaves an audit verdict "either
incomplete or untrustworthy".

| # | question | Kavach's answer |
|---|---|---|
| 1 | **Actions** — which policy-relevant actions are recorded? | Every state-changing one, with the fields needed to rebuild it: `execute_start` / `execute_done` carry `action`, `requested_settings`, `pre_state`, `inverse_settings`, `config_hash_before/after`, `risk_tier`, `idempotency_key`, `executed`, `reverted`, `error`. Nothing writes to the target outside this path. |
| 2 | **Phases** — which execution phases are covered? | `diagnose`, `permit`, `approved` / `rejected`, `execute_start`, `execute_done`, `resolved`, `unwind`, `mode_change`, `store_init`. Approvals and rollbacks — two of the four the paper names — are first-class events. |
| 3 | **Policies** — which policies can be mechanically checked? | All of them. The `permit` record carries `checks` (ten named checks, each pass/fail with its detail), `reasons`, `verdict`, `mode`, `risk_tier` and the typed decision frame. The paper's three-valued outcome maps directly: comply → `ALLOW_AUTO`, violate → `DENY`, **undecidable → `REQUIRE_APPROVAL` or escalation**, and `permit()` denies any check it cannot evaluate. |
| 4 | **Attribution** — what responsibility chain is available? | Two principals, `kavach` and `operator`, on every row — **and, since 2026-11-06, the link between them.** See below. |
| 5 | **Integrity** — what protects the record? | **Hash-chained: level 3 of the paper's four** (none → append-only → hash-chained → signed). Not signed, and there is no seal key. |
| 6 | **Missing logs** — what happens when logs are missing or detached? | Partially handled, and §6 measures where it is not. `verify()` catches an edited row, a deleted middle row and a reordered pair, naming the index and the reason. **It does not catch a truncated tail.** |

**Question 4 was a real gap and the card is what found it.** `approve()`
re-detects rather than replaying, so the approved incident and the executing
one carry different ids. The log read `approved INC-101822` by `operator`,
then `permit` / `execute_start` / `execute_done` / `resolved` on INC-101902 by
`kavach`, **with nothing joining them but adjacency in time** — the paper's
named failure mode, a chain that breaks where an action is not linked to its
source. Reconstructing *why* INC-101902 was permitted to write required
assuming the next permit after an approval is the right one, which would have
been ambiguous had two approvals interleaved.

The `permit` record now carries `approved_from`, verified on a live run:

```
permit    INC-192233  approved_from=''            REQUIRE_APPROVAL
approved  INC-192233  operator
permit    INC-192306  approved_from='INC-192233'  ALLOW_AUTO
execute_start / execute_done / resolved on INC-192306
```

It is written even when empty, because *"this run was not under an
approval"* is a fact an auditor needs stated rather than inferred from a
missing key.

**Where this leaves us, stated as the paper would score it.** Four of five
dimensions are met at the level the framework describes; **evidence integrity
is at 3 of 4**, and the honest reason is a deliberate deferral rather than an
oversight — §9 item 16 carries the signed-checkpoint work and §6 explains why
changing the audit format days from a deadline is the wrong trade. The paper
also frames mechanisms as **detect, enforce, recover** and argues no single
class covers all five dimensions; Kavach implements all three, which is the
loop itself.

**One number worth borrowing.** The paper measures pre-execution mediation
with tamper-evident records at **8.3 ms median overhead**. That is the
closest external figure to what `permit()` plus the audit append costs here,
and it is a useful answer to "what does the gate cost" — a question §4 does
not currently measure for itself.


The honest one-line version: **Kavach scraped the target every 15 seconds for
three weeks while answering 404 on its own `/metrics`.**

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

### 8.1 Systems that gate remediation, and where Kavach differs

The nearest siblings are not benchmarks but operating systems for remediation.
All three below diagnose with an LLM and execute something; the axis that
separates them is **what the model is allowed to author.**

| system | model's role | execution | gate |
|---|---|---|---|
| **K8sGPT** | RCA and explanation | **none** — diagnosis only | n/a |
| **[Kubernaut](https://github.com/jordigilh/kubernaut)** | investigate, then *select* from a workflow catalogue | yes, autonomous or interactive | escalates to a human "only when it should" |
| **[kube-ai-sre-agent](https://github.com/aqrpole/kube-ai-sre-agent)** | correlate signals, explain, recommend | policy-gated | explicitly *"not a self-healing black box"* |
| **Red Hat EDA + AAP demo** | **authors an Ansible playbook** for the specific fault | yes, after email approval | human reads generated code |
| **Kavach** | select among pre-registered actions; propose a repair | yes, after `permit()` | ten deterministic checks; **the model's answer can be refused** |

Kavach sits with Kubernaut and `kube-ai-sre-agent` on the selection side of
that line, not the authoring side. The Red Hat pattern — an LLM writing the
remediation itself — is the one this project bounded deliberately: the only
content a model may generate here is prompt text, and even that goes through a
sandbox (ADR 0008, ADR 0011).

**Rootly, a commercial incident platform, draws the same distinction
independently**, and states it more plainly than this report had:

> *"Everything on this page describes **pre-authored** automation: a workflow a
> human wrote, reviewed and enabled in advance... The judgment happened at
> authoring time, which is what makes unattended execution safe... That is
> different from an AI agent choosing an action nobody pre-authorised for that
> situation... conflating them is how teams end up surprised."*

That is the architecture argument of this project, arrived at by a vendor with
production customers. Kavach's action registry *is* pre-authored automation —
every action is written, reviewed, given an inverse and registered before any
model sees it — and the LLM's contribution is restricted to choosing among
them and being overruled when it chooses wrong.

### 8.2 The safety metric is not invented here

`False healing` (§4.1) is this report's central result at **0 / 40**. The
metric has prior art: *LLM-Based Autonomous Remediation for DevSecOps
Pipelines* evaluates on a **False Remediation Rate** alongside alert fatigue,
and the agent-safety literature (R-Judge, TS-Bench and the 2026 agentic-NetOps
survey) is converging on *unsafe action* as the primary axis for autonomous
agents. Kavach therefore reports against a measure the field already uses,
rather than one chosen to flatter the system.

The same literature names the failure mode on the other side — **refusal
storms**, an agent that declines so often it is useless. §5 reports Kavach's:
three of four refusals blocked a *correct* answer. Both numbers, or neither.

### 8.3 The 2025–26 RCA-agent literature, and why our accuracy needs a caveat

A second search on 2026-11-02 found a body of work this section did not have.
The full positioning map, with citations, is
[`RELATED_WORK.md`](RELATED_WORK.md); everything there is cited from abstracts
rather than full-text reads, and that document says so. Three points belong
here because they change how §4 should be read.

**The architecture is convergent — and, on one measurement, the best of the
designs compared.** EviRCA (arXiv 2609.19825) independently builds Kavach's
central design — *"decouples deterministic evidence extraction from LLM
reasoning… the LLM reasons only over these structured observations through a
small set of predefined read-only tools, without accessing raw telemetry or
executing code"* — and ARBITER (2607.19182) independently uses the same
vocabulary of *"bounded DiagnosisContext objects"* behind a typed-action
interface. **This should be claimed as independent arrival at a convergent
pattern, not as novelty.**

A second search on 2026-11-03 found something stronger. *"Free to Look, Free
to Reason"* (2610.35767) compares harnesses that prescribe none of the model's
calls — one of them literally *"one call over an evidence package"*, which is
what Kavach does — against five published LLM RCA agents and against
statistical and causal methods, over 90 validated cases from eight public
datasets:

> *"The simple harnesses are the most accurate (PR@1 65-77% on three mid-tier
> models), ahead of the published agents (16-53%) and the non-LLM methods
> (6-39%)… The published agents fix from a tenth to all of their model calls
> in the program, and a case study shows how these prescriptions skip the
> decisive evidence."*

So the one-call-over-a-prebuilt-frame design is reported beating hand-crafted
multi-stage agents by 20–60 points, with *"every Pareto-optimal run in cost or
time"* using a simple harness. One paper, 90 cases, not reproduced here — but
it means Kavach's simplicity is a defensible design position rather than a
limitation of scope. It also predicts §4.2: if the harness is not the
bottleneck and the evidence package is, then frame contamination collapsing
accuracy is exactly the failure mode to expect. EviRCA also reaches §4.2's conclusion from the
opposite direction: it finds that *"the effectiveness of LLM-based RCA depends
heavily on the quality of evidence extraction"* by showing extraction sets the
ceiling, where we showed it by degrading a frame and watching accuracy collapse.

**Our numbers are not comparable to the open benchmarks, and the report must
say so before quoting them.**

| benchmark | best reported agent |
|---|---|
| ORCA-bench (2607.28545) | **25.3%** on Medium, **10.0%** on Hard |
| Incident-Arena (2610.00648) | frontier models **below 64.3%** |
| SRE-Marathon (2609.33023) | best of ten methods **41.3 / 100** |
| Cloud-OpsBench (2603.00468) | JRA **0.76**, Evidence Closure **0.38** |
| LATS-RCA (2605.03505) | **91.3%** on benchmark, **65.1%** on real production |
| **Kavach** | **85–90% RCA accuracy** |

Four structural reasons ours is an easier problem, all of them scope decisions
recorded elsewhere in this report rather than concessions: the diagnosis is a
choice among **four** declared classes; a **deterministic detector has already
fired and named one** before the model is asked; the **evidence is
pre-extracted** into a bounded frame, which is exactly the search step
Cloud-OpsBench's 0.38 Evidence Closure Rate exists to measure and we skip by
construction; and the target is **one service with no dependency graph and no
overlapping faults**. LATS-RCA's own 91.3%→65.1% drop between benchmark and
production is the clearest illustration that these gaps are large.

**And those benchmarks are themselves under serious criticism**, which is
relevant because this section contrasts our numbers against them. *"Rethinking
the Evaluation of Microservice RCA"* (2510.04711) reports that *"simple
rule-based methods can achieve performance comparable to or even surpassing
state-of-the-art models on four widely used public benchmarks"*, and that 11
SOTA models re-evaluated on a harder generated benchmark average **Top@1 of
0.21**. *"Does Graph Structure Earn Its Place…"* (2609.27069) audits RCAEval
and finds its headline metric nearly satisfied without reading any data at
all: *"a ranker reading no telemetry at all places the true culprit in the top
five on 99.7 percent of held-out incidents"*. *"What a Pooled Leaderboard Does
Not Say"* (2606.29159) re-runs 16 methods across OpenRCA, RCAEval and PetShop
and finds 6 of 8 narrow pooled leads **reverse** per-subsystem, and that of 23
RCA papers examined, *"none releases the per-case outputs needed to check
either premise."*

**This does not excuse never evaluating on a public benchmark** — that is a
real gap and §6 says so. What it supports is that a leaderboard position would
not have been the stronger claim. A bespoke measurement of 80 real injections,
with every refusal accounted for, 0 wrong diagnoses executed, and the per-case
artifacts committed to this repository, answers the question those audits say
the leaderboards do not — and publishes the per-case outputs that *"none"* of
those 23 papers release.

It also corroborates §4.9's uncomfortable result. We report the deterministic
path resolving 4/4 and faster against the LLM path's 4/8 and 40–70% slower;
2510.04711's finding that simple rules match or beat SOTA on four public
benchmarks is independent evidence from a different direction that this is a
property of the problem, not a local anomaly in our harness.

The fair comparison is **TriFleetRCA (2609.23766)**: on-premise Qwen2.5-14B on
a single GPU, four injected faults in a live cluster, 100 analyses, hit rate
**0.85–0.95** — the same order as ours, at a comparable scope and model size.
It also reports our §4.2 failure mode independently: *"one fault was diagnosed
correctly and cited incorrectly every trial, a failure mode accuracy
conceals."*

**What the field has that we do not**, stated because a related-work section
that only finds agreement is not credible: epistemic uncertainty as a priced
risk dimension (2607.20005 decomposes risk into blast radius, reversibility
**and** epistemic uncertainty — we have the first two; §4.2 rules out the
two obvious candidates for the third and **§4.4a rules out the third,
evidence closure, by showing it saturated at 37/37**); canary and progressive rollout; dependency-
graph-guided search; production scale (Diviner at Meta, Log-Insight at Huawei,
2606.09122 reporting *"autonomous resolution rates exceeding 90%"* at a cloud
provider); and learning from incident history, which ADR 0009 cut.


**A third search, 2026-11-05, found the two citations this section most
needed.** Both are in [`RELATED_WORK.md`](RELATED_WORK.md) §6b with their
provenance; the short version belongs here because each changes how a claim
above should be read.

The first strengthens the convergence argument past "several systems arrived
at this shape". **"Agentic Self-Healing for Data & AI Pipelines"**
(arXiv [2608.01955](https://arxiv.org/abs/2608.01955)) is a 2026 *reference
architecture* for exactly this system — deterministic policy engine ahead of
any LLM call, allowlisted playbooks, risk-tiered approval, guarded execution,
an immutable audit trail treated as a security control, and per-pipeline rate
caps named as the defence against compounding actions. It sets its worked
confidence floor at 0.8; our manifest sets 0.75. But it states it is
**"deliberately prescriptive rather than empirical"**, prices itself in
figures it calls **"indicative rather than measured"**, and lists as future
work *instrumenting real deployments and measuring time to diagnosis, time to
recovery, escalation rates and remediation precision against a pre-adoption
baseline.* **That list is this report's §4**, and against two pre-adoption
baselines rather than one. It is also thinner on inverses than we are: its
only described inverse is a git revert for deployments, with none given for
its other action types.

The second supplies a number §4's headline has lacked. **"If Agents Were
Angels, No Governance Would Be Necessary"**
(arXiv [2608.27646](https://arxiv.org/abs/2608.27646)) argues Kavach's thesis
in one line — prompts fail as guardrails because *one fallible reasoner both
interprets the task and enforces its boundaries* — and enforces policy at a
boundary outside the model, where an agent-level policy may only **narrow**
the owner's maximum access, never widen it. That is our deny-list-before-
allow-list and the `DENY_ALWAYS` floor, independently derived. Across **3,621
adversarial trials** they report trace failures falling **57.6% → 0.2%** while
task fulfilment fell **79.1% → 60.9%**.

**Quote that trade beside ours.** Kavach escalates about a fifth of its
incidents — 80% auto-resolution in run D — and buys 0 false heals across 80
injections. A reviewer inclined to read escalation as failure should see an
independent, adversarially-measured system pay roughly eighteen points of
fulfilment for its safety result and report that as the finding rather than
the cost. Their evaluation explicitly excludes write controls and durable
approval, which is precisely the half measured here: every path in §4 ends
either in a write to a live system or a refusal to make one.


## 9. Still to do

1. ~~Full `make bench`~~ — **done 2026-10-19 08:55**, §4.1/§4.2
2. ~~Re-measure RCA at the corrected context window~~ — **done.** The
   window was not the cause; ADR 0013 identifies the real one. F01, F06 and
   F08 need no fixed-frame re-run: the bench already measures them on the
   current frame across twenty fresh frames, at 5/5 each.
3. ~~Re-run the bench for a real MTTD~~ — **done 2026-10-20 03:06 UTC**,
   `bench-20261020-mttd.json`, §4.1. The target question is answered in
   [ADR 0019](decisions/0019-mttd-is-measured-and-the-target-stays-but-per-class.md):
   `< 30s` stays, reported per class. What run B opened instead is
   **action-selection accuracy**, which nothing measures (§4.2).
4. ~~`make scenario` — three clean runs, an hour apart~~ — **done
   2026-10-19**, `scenario-r1/r2/r3.json` at 06:17, 07:30 and 08:44 UTC.
   4/4 acts each, **zero limiter parks**, same `rca_model`, corpus unchanged.
   **Re-opened and re-closed in part on 2026-11-02**, because that evidence
   predates the reformatted host (§4.1): the **offline** rehearsal was re-run
   on the rebuilt machine and came back **4/4 clean** with the network
   physically down and all seven cloud keys read back empty inside the
   container (`scenario-offline.json`, 10:39 UTC; the pre-reformat run is
   kept as `scenario-offline-20261019.json`). Two offline rehearsals on hosts
   that share no system state is a stronger claim than the single run this
   item used to cite. **The three-consecutive-clean bar is also re-met on the
   rebuilt host**, after the `drain()` fix: `scenario-20261102-postfix-1/2/3`
   at 13:29, 14:37 and 15:13 UTC, 4/4 acts each, `clean: true`, corpus 30/2
   unchanged across all three. Act 2 ran 163.2 / 168.0 / 163.4s against the
   66.8 and 70.3s of its two pre-fix failures — the extra ~95s is the drain
   waiting out the `[2m]` error window, which is the fix working. Runs 1 and 2
   were an hour apart; run 3 followed a `docker restart kavach-api` to clear
   the in-memory blast-radius deque, since a clean run costs exactly 5
   incident starts and that is the entire hourly budget. `FR-16` was never
   altered and `permit()` enforced it throughout.

   The first attempt that day is also on the record
   (`scenario-20261102-f08-tail.json`, 08:44 UTC, 3/4): act 2 failed because
   the model diagnosed the injected F08 as F06 and `deterministic_agreement`
   refused it, so the loop escalated rather than parking for approval. That is
   the gate working — nothing executed — but it is also a **~10% failure mode
   sitting inside a demo act**, since F08's first-draw accuracy is 19/20 and
   approval re-diagnoses, requiring the model to be right twice. Reported
   because a one-in-ten risk in a live demo should be known in advance.
5. ~~Human baseline: run it, or record the decision to drop it~~ —
   **closed 2026-10-19, written up in §4.8.** It was run on 2026-10-18 and
   the result had been sitting in `human-baseline.json` unreported. It
   stays at n=3 against a protocol asking for 12: the decision is to report
   a paired pilot with its limits stated rather than pad it. Padding would
   make the number prettier and the claim no truer.
6. The one-line `allowed_actions` decision for `apply_patch` (ADR 0012)

**Opened 2026-10-20, and none of these is mine to close:**

7a. **Kavach has no autonomous trigger.** There is no detection tick and no
   Alertmanager path; a loop starts only when an operator calls
   `POST /v1/loop/run`. Every comparable system (§8.1) is triggered by the
   system it manages. `ROADMAP.md` made this a deliberate constraint — *"must
   not be removed before P6 lands"* — and P6 landed weeks ago, so the
   precondition expired and nobody lifted it. Everything a tick needs already
   exists: it would call the same `run_once` the console calls, inheriting
   `permit()`, `SIMULATION` and the blast radius. It should ship **disabled by
   default**. `RESEARCH_NOTES.md` §11.

7. ~~**The `fault_name` coherence check**~~ — **closed 2026-11-02, ADR 0021.**
   Not added, and for a better reason than its cost. The check's unique catch
   set is exactly the *correct* F06 diagnoses: all 11 wrong ones were already
   refused (0 of 11 executed, pooled over four runs), while the 9 that healed
   are the only rows it would uniquely reject. The model's mistake is a
   coherent F07 diagnosis with one corrupted field — name and proposed action
   both say F07 — so the two gates that catch it read the *action*, and a name
   check reads a field that is wrong for every F06 row, correct or not. It is a
   constant, not a discriminator. What remains open is **why** the mis-binding
   happens (item 13), not whether to gate on it.
8. ~~Action-selection accuracy is unmeasured~~ — **closed 2026-10-20**,
   ADR 0020. Scored separately now, and replaying run B found action accuracy
   *higher* than class accuracy (§4.2). The next bench reports both live.
9. ~~`harness/reports/` is gitignored~~ — **closed 2026-10-20.** 70 files
   committed, secret-scanned first. `harness/audit/` stays out, with the
   reason stated at the top of this document.
10. ~~`GET /v1/incidents` reads memory, not Postgres~~ — **closed
    2026-10-20**, ADR 0020. Verified across a real container restart: 50
    incidents and 89 LLM calls where there were 0, and `make postmortem`
    renders from Postgres alone.

**Opened 2026-11-02, after run D:**

11. ~~The corpus fingerprint is written down and never asserted~~ — **closed
    2026-11-02.** `onboarding/preflight.py::check_corpus_fingerprint` reads
    the expected 30 chunks / 2 files out of `fast_set.yaml` and compares it to
    live Prometheus; an empty series and an unreachable Prometheus are both
    failures, not passes. Seven tests replay the three real drifts (162/3,
    13/1, 0/0). This had been carried in `PRD.md` §12 since 2026-10-16 and was
    the reason run D's host needed a corpus re-ingest nobody would have caught.
12. **The two corpus PDFs are still in exactly one place.** They are not in
    either repository, were lost with the SSD on 2026-11-01 and recovered from
    a copy outside both. `harness/corpus/README.md` records their SHA-256 so a
    candidate can be *verified*; nothing restores them. Every quality number in
    §4 is measured on those two files. **This is the single largest
    reproducibility risk in the project and it is a decision, not a task** —
    committing a 4.7 MB pair of third-party PDFs to a public repository is the
    user's and the team's call, not mine.
13. ~~**The F01 MTTD ladder has four rungs and no named mechanism**~~ —
    **closed 2026-11-06** (§4.1, `harness/mttd_ladder.py`). The rungs are
    rounds of `warm_up_f01`, measured on the live stack with F01 injected at
    **12.12s** a round (12.10/12.15/12.12/12.11, spread 0.05s) against 24.3s
    healthy. Twelve of twenty samples sit within 0.4s of that lattice. The
    15s scrape interval is ruled out: it does not divide 12.12, and no
    interval constant exists in the detection path.

    **The off-lattice samples are explained too, and nothing is left over.**
    Reading `warmup_s` beside `mttd_s` - both recorded by the harness all
    along - F01's warm-up lands on integer multiples of the round (2.00,
    3.00, 4.01, 5.00) and the residual is bimodal: 12.2-12.4s in fourteen
    runs, 30.3-33.2s in six, nothing between. The six samples that miss the
    lattice are exactly the high mode (54.6 = 24.3 + 30.3, 66.8 = 36.4 +
    30.4, 78.9 = 48.6 + 30.3, 91.0 = 60.7 + 30.3, 94.0 = 60.8 + 33.2). The
    ~12.2s floor is itself about one round, and `ADR 0014` names the likely
    cause: the loop runs its own fast set before detection.

    **What remains is a reporting change, not a measurement.** §4.1 now
    carries the decomposition and the warning that the classes were never on
    a common scale - F07 and F08 warm up for 0.0s - but `PRD.md` §10 still
    states `MTTD < 30s` as one target across all four. Whether that target
    should be split, or defined net of warm-up, is a decision for after the
    deadline: changing what MTTD means would invalidate the four runs that
    measure it.

    Recorded here because a 2026-11-05 pass on this item briefly concluded
    the step was 6.05s. It was not. A lattice fit cannot distinguish a period
    from its divisors, and the timing run settled it the other way.

14. **The F06 attractor's trigger is hinted at but not measured** (§4.2). A
    rehearsal accident put F08 first-draw accuracy at 19/20 on a clean
    evidence frame and 1/3 on a frame carrying one extra anomaly, which
    supports "ambiguity triggers the collapse" over "the model sometimes
    errs". But n is 3 and the contrast is confounded — bench versus scenario
    differ in more than the one metric. **One experiment settles it**: F08 on
    a clean frame against F08 with `llm_error_ratio` held just above 0.20 by
    driven failing traffic, ten reps each, one variable. Same shape as the
    test that produced ADR 0013. Roughly an hour, and it would turn the
    project's headline anomaly from a described error mode into an explained
    one. **This is the single highest-value experiment left undone.**
    > **RUN 2026-11-02 — the hypothesis was refused, and the follow-up failed
    > informatively.** §4.2 carries the result: clean frame **10/10**, frame
    > holding a prior fault's residue **0/10**, but the wrong answers were
    > nine F01 and one F06, so the model followed the residue to its own class
    > rather than collapsing to F06.
    >
    > **The dose sweep attempted next is not data.** Two of four arms could
    > not reach their target ratio at all, and two reached the model with
    > frames carrying **0.1744** and **0.2027** — the first of those *below*
    > the 0.20 ceiling the frame itself calls healthy, so it was a second
    > control reported as a dose. Both scored 10/10, consistent with being
    > controls. Cause: the frame-collection pass dilutes the `[2m]` ratio by
    > 0.065–0.094 between aiming and collecting, and the harness asserted that
    > the *fault* was in the frame without ever asserting the *contaminant*
    > was. Artifact `ambiguity-f08-dose-sweep.json`, kept as evidence of the
    > method problem rather than of a dose response.
    >
    > **A third contamination channel came out of that failure**, and it is
    > the more useful half: the connection-error **log** lines outlive the
    > metric window, and nothing drains them. A control arm run minutes after
    > a dosed arm diagnosed **F01 on a frame whose error ratio was 0.0**,
    > citing `EV-L01`'s ConnectionError directly. So the evidence frame has at
    > least three independent memories of a finished fault — metric, log, and
    > whatever the detector reads — and draining one is not draining the
    > frame. That is the eighth instance of this project's most persistent
    > root cause.
    >
    > **What a real sweep now requires**: dose by outage intensity rather than
    > by target ratio (done), assert the contaminant is present in the frame
    > (done), **and** drain or window the log evidence between arms (now done
    > a different way — `--with-logs` defaults to OFF, excluding the channel
    > entirely so the metric is the single variable).
    >
    > **RE-RUN 2026-11-03 WITH ALL THREE FIXED, AND THE SYSTEM REFUSED THE
    > EXPERIMENT** (`ambiguity-dose-sweep-v2.json`). Four dosed arms at frame
    > error ratios 0.2752, 0.4054, 0.5263 and 0.5769: in **every one** the
    > deterministic detector returned `INSUFFICIENT_EVIDENCE` instead of a
    > class, so each arm was correctly marked invalid and **the model was
    > never asked**. The control, at 0.0, returned `FAULT F08` and the model
    > scored 10/10 with 10/10 approved.
    >
    > That is a finding about Kavach rather than about the model, and §4.4
    > now carries it. The dose sweep itself remains unrun and may be
    > unrunnable as specified: it needs a frame contaminated enough for the
    > model to notice while exactly one detector still claims, and the
    > deterministic layer appears to refuse across most of that range.

15. ~~**Audit completeness is measured but does not gate the bench**~~ — **closed 2026-11-03, same day.**
    Opened 2026-11-03 with the fix described in §6. `report.py` asks the
    scoped question per incident and the figure will be real from the next
    run, but the bench's pass/fail expression is still
    `detected == n and false_heal == 0 and chain_intact and all(state_clean)`
    — a run in which Kavach executed a repair and recorded nothing would
    print the miss and still pass. `PRD.md` §10 lists audit completeness at
    100% as a target, so the row belongs in that expression.

    **It was deliberately left out rather than added blind.** The ordering in
    `loop.py` is right — `execute_done` is appended at line 600, before every
    terminal status assignment (`RESOLVED` 661, `ESCALATED` 648) — so a
    reader of the log after `wait_terminal` cannot race it, and the check
    should never fire spuriously. But that is traced, not observed: no live
    bench has run since the metric started measuring anything, and making a
    previously unfailable criterion gate an eight-hour overnight run on the
    strength of a code read is how a deadline gets lost to a false alarm.
    **One live bench run validates it, and then it is a one-line change.**

    > **VALIDATED AND GATED**, `bench-audit-validation.json`, a single F08 rep
    > on the live stack. It is the first artifact in the project's history to
    > carry `audit_recorded: true`; all 62 executed repairs before it say
    > `false`. The harness wrote `true` for `INC-065506`, and the log read
    > independently carries that incident's `diagnose`, `permit`,
    > `execute_start`, `execute_done` and `resolved` — so the two agree by
    > measurement rather than by construction.
    >
    > The ordering is now observed and not only read: `execute_done` landed at
    > 06:55:50.399 and `resolved` at 06:56:13.190, a **23-second margin**, so a
    > read taken after `wait_terminal` cannot race the record. `audited ==
    > executed` is therefore now part of the bench's pass/fail expression.
    > **Run D's figure stays withdrawn** — this validates the instrument, and
    > an instrument validated after the fact does not retroactively measure a
    > run that finished without it. The next full bench produces the first
    > real number.

16. **The audit chain does not detect tail truncation.** Opened
    2026-11-05, measured in §6. Deleting the last N records leaves a chain
    that verifies as intact, because what remains is valid from genesis;
    edits and middle deletions are caught. There is no seal key and no
    expected row count held outside the file.

    **The fix is small and deliberately deferred**: a periodic signed
    checkpoint carrying the row count, or anchoring the head hash
    somewhere the log cannot reach. Both change the format of the artifact
    behind every audit figure in §4, and the gap sits outside the threat
    model `AGENTS.md` states — the log exists so Kavach cannot act without
    leaving a record, not to withstand an attacker who can write to the
    host and stop the container. Worth doing after the deadline, and worth
    stating precisely until then.
