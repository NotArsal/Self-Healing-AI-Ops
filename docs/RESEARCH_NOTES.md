# Research notes — where Kavach sits, and what is worth adding

**Written 2026-10-19.** Sources are linked. Anything here that is a judgement
rather than a citation says so.

This exists because "what else could we add" is the question most likely to be
answered badly under deadline pressure — by adding breadth that makes the
claim weaker rather than depth that makes it defensible.

---

## 1. The two benchmarks the report should name

Neither was referenced anywhere in this project until now, and both describe
exactly the methodology Kavach already uses. Citing them converts "we invented
a test harness" into "we implemented the accepted evaluation methodology".

### AIOpsLab (Microsoft Research, arXiv [2501.06706](https://arxiv.org/pdf/2501.06706))

> *a framework that not only deploys microservice cloud environments, injects
> faults, generates workloads, and …*

That is a description of `harness/`. AIOpsLab covers the whole incident
lifecycle — detection, localisation, root cause, mitigation — which is the
same four stages `PRD.md` §10 measures.

**Use it like this:** Kavach is a narrow, deep instance of the AIOpsLab
pattern. AIOpsLab is broad (generic microservices) and has no safety engine.
Kavach is narrow (one RAG workload, four fault classes) and its contribution
is the thing AIOpsLab does not have: a deterministic gate that can refuse the
model. Narrow-and-gated is a defensible contribution; "we also built a
benchmark" would not be.

### ITBench (IBM, arXiv [2502.05352](https://www.alphaxiv.org/abs/2502.05352))

Positioned explicitly as broader than AIOpsLab, which it says *"focuses
primarily on SRE tasks"*. It has a public leaderboard (Artificial Analysis
runs an implementation) for Kubernetes RCA from offline incident snapshots.

**Use it like this:** one sentence in related work establishing that
benchmarking agents on IT automation is an active field with published
leaderboards, and that Kavach reports per-class numbers with denominators in
the same spirit.

### Also worth one line

- **"No Human Required: An Autonomous AI SRE Agent for Elasticsearch"**
  (arXiv [2604.03933](https://arxiv.org/html/2604.03933v1)) — proactive
  staging of remediations against known failure signatures. The honest
  contrast: Kavach deliberately does *not* act proactively, because a
  pre-staged action has no incident to bound its blast radius.

---

## 2. The industry read, and why it flatters this project

From a 2026 survey of AI SRE tooling ([Zentor](https://zentor.ai/blog/best-ai-sre-tools)):

> *detection and triage are largely solved, investigation is the hot frontier
> where the vendor claims cluster, remediation is genuinely automatable only
> in bounded cases, and postmortems are low-hanging fruit almost nobody has
> picked.*

Three of those four sentences are about Kavach.

- **"Remediation is genuinely automatable only in bounded cases."** This is
  the project's entire thesis, arrived at independently. Four fault classes,
  a closed action catalogue, every action with an inverse, a fixed-HIGH tier
  for the one generated action. The report should quote this and say: we
  built the bounded case and measured it.
- **"Postmortems are low-hanging fruit almost nobody has picked."** See §3.1.
- Traversal's piece ([here](https://www.traversal.com/blog/can-ai-sre-find-root-cause))
  argues general LLMs *"stall at symptoms"* and that the limit is structural
  rather than a matter of model size. Kavach has a measurement that speaks to
  this directly: the deterministic cross-check rejected 21 of 21 wrong
  diagnoses. That is independent corroboration from a commercial vendor, and
  it supports the design rather than merely agreeing with it.

---

## 3. What to add, ranked by value per hour

### 3.1 Auto-generated postmortem — **do this one**

**Effort: low. Value: high. Demo value: very high.**

Every input already exists and is already written down:

- the hash-chained audit log — every step, in order, with timestamps
- the evidence frame — the EV-ids the diagnosis cited
- the `permit()` decision — verdict, tier, mode, reasons
- the undo stack — the inverse, and whether it ran
- `pre_fast` / `post_fast` — the fast set before and after

Nothing needs collecting. It is a renderer over `Incident` plus the audit
rows, producing a Markdown postmortem per incident: what broke, what the
evidence said, what the model proposed, what the gate decided, what was
written, what verified, how long each stage took.

Why it is worth the hour: the industry note above says almost nobody has
picked this, it demonstrates the audit trail is real rather than decorative,
and in a live demo "and here is the postmortem it wrote itself" is a better
closing beat than a terminal full of JSON.

### 3.2 Traces into the evidence frame — **only if time allows**

**Effort: medium. Value: medium. Honesty value: high.**

The OTel collector is running in `infra/` and the control plane contains no
OpenTelemetry code at all, so "logs, metrics, traces" is currently two out of
three. The evidence frame has `EV-M*` (metrics), container logs, config and
health — no span data.

Two options, and the cheap one is probably right:

- **Cheap:** stop claiming traces. One sentence in the report: the collector
  is deployed, RCA consumes metrics and logs, and span-level evidence is
  future work. Costs nothing and is true.
- **Real:** add an `EV-T*` block carrying span latency percentiles per
  operation. This would genuinely help `F02`-style latency faults — which
  were dropped, partly for want of this signal.

Recommendation: take the cheap option before the deadline, and name the real
one as future work. A half-wired trace path that RCA does not consult is worse
than an honest gap.

### 3.3 A provider comparison as a first-class result — **nearly free**

Already measured, just not yet written up as a contribution:

| model | applies | where it runs |
|---|---|---|
| gpt-oss-120b | 10 / 10 | Groq |
| gemini-3.8-flash | 7 / 10 | Google |
| llama3.1 / 3.2 / qwen2.5:7b | 0 / 30 | local, Ollama |

The interesting part is not that bigger models are better. It is **what they
fail at**: the local models diagnose correctly (10/10 on F07/F08 in earlier
runs) and cannot write a unified diff, failing on content — these files' lines
begin with `- `, so a deleted line needs two minus signs and they write one.
Diagnosis and patch-writing are separable capabilities, and the gap between
them is where a safety gate earns its place.

Pair it with the correction in ADR 0011: the first version of this measurement
said 0 of 15 and blamed the models, when the largest single cause was Kavach
writing patch files without a trailing newline. **A measurement is a finding
about the instrument until proven otherwise** — that is a more valuable
sentence for a report than any of the numbers.

### 3.4 Second target workload — **no, not before the deadline**

It would prove generality, which is the strongest criticism available against
the project ("you healed one app"). It is also days of work: a second
manifest, baseline, fast set, injectors and detector tuning.

Better answer for the same criticism, at an hour's cost: write the
"onboarding a second workload" section of the report as a concrete procedure
against the existing seams — `DetectorSpec`/`DetectorRegistry`, the action
registry, `kavach.yaml` — and state honestly that it has not been exercised.
A reviewer respects a named limitation more than a rushed second target.

---

## 4. What NOT to add

**Capacity and autoscaling** — the "what if Flipkart Big Billion Days slows
down" question. The honest answer is that Kavach would detect nothing it
recognises, return `UNKNOWN` or `INSUFFICIENT_EVIDENCE`, and escalate to a
human, which is correct behaviour.

Do not add it. A traffic surge is a capacity problem; HPA and Karpenter solve
it and solve it well. Kavach heals **correctness and configuration**
regressions in AI applications. Conflating the two would weaken a claim that
is currently sharp, and `FR-30` plus `AGENTS.md` forbid any scaling action
anyway. The right report sentence is one that draws the boundary deliberately
rather than apologising for it.

**Proactive remediation** — pre-staging fixes against known signatures (the
Elasticsearch paper). Attractive and wrong here: an action taken before an
incident has no incident to bound its blast radius, and the blast radius is
load-bearing.

**More fault classes** — F02, F03, F05 and F09 were each dropped for a stated
reason that is still true. Reviving one to make the catalogue look fuller
would mean an injector that does not honestly inject, which `AGENTS.md`
forbids outright.

---

## 4a. A latent bug found while writing this, and what it costs

**Every LLM diagnosis this project has measured ran within 10% of its
context window, and at least one exceeded it.**

Measured across six real incidents on 2026-10-19, from the API's own
records:

| incident | prompt | completion | total | window |
|---|---|---|---|---|
| INC-191611 | 3753 | 405 | **4158** | 4096 — **over** |
| INC-191650 | 3752 | 322 | 4074 | 4096 |
| INC-191014 | 3744 | 263 | 4007 | 4096 |
| INC-190935 | 3746 | 283 | 4029 | 4096 |
| INC-191351 | 3420 | 349 | 3769 | 4096 |
| INC-191321 | 3420 | 310 | 3730 | 4096 |

Ollama was serving a 4096-token window and `num_ctx` was never set.
Exceeding it is not an error: Ollama slides the window and discards the
OLDEST tokens — the system prompt and the opening of the instructions — so
the model loses the rules it is being judged against and still returns a
well-formed reply. Nothing in the response says it happened.

`num_ctx` is now set to 8192 explicitly, roughly double the worst case
observed and well inside what qwen2.5 and llama3.x support. Verified
served at 8192, still entirely on GPU.

**What this costs, stated plainly.** Every RCA accuracy figure this project
has published was measured under a window that was sometimes exceeded. The
direction of the error is knowable: truncation can only remove instructions,
so the published numbers are a **floor**, not a ceiling, and the model may be
better than recorded. They should be re-measured before the report quotes
them. The `make bench` run started tonight uses the containerised API, whose
image predates this fix, so its LLM-accuracy column carries the same caveat;
its MTTR figures do not, because repairs are driven by the deterministic
path.

This belongs in the report as a methods note rather than being quietly
corrected. It is the second instrument bug found in two days — see ADR 0011
on the missing trailing newline — and two is a pattern worth naming.

## 5. Open items, in the order I would do them

1. ~~`make bench` full 4×5 run~~ — **finished 2026-10-19 08:55.** 20/20
   injections, 0 false heals, target clean 20/20, chain intact. It also
   produced the finding below.
2. ~~Postmortem renderer~~ (§3.1) — **built**, `make postmortem`
3. ~~Re-measure RCA accuracy at `num_ctx=8192`~~ — **done, and the window
   was innocent.** F07 scores 0/10 at both 4096 and 8192; the cause is the
   evidence frame's PromQL range, not the context window. See
   `docs/decisions/0013`. F01, F06 and F08 need no fixed-frame re-run —
   the bench measures all three on the current frame across fresh frames and
   scores 5/5 each, which is strictly better evidence than a frozen frame.
   F07 is the only class the frame change broke.
4. Report and slides — cite AIOpsLab and ITBench in related work
5. Re-state the MTTD acceptance target with its window arithmetic. 48.5s
   median against a < 30s target, where two of four detectors claim on 60s
   rate windows. The target was set before the detectors existed.
6. `make scenario`, three consecutive clean runs an hour apart
7. Decide the human baseline: run it with a teammate, or record the decision
   to drop it. It is currently neither.
8. The one-line `allowed_actions` decision for `apply_patch` (ADR 0012)

---

## 6. What the bench found that no single run could

**F07 healed 0 times out of 5**, and the reason is a property of the design
rather than a bug.

`runner.approve()` re-detects and re-diagnoses instead of replaying the
parked plan — deliberately, because the world may have moved while the
approval dialog was open and a replayed plan would restore a value that was
true when it opened. The cost is that **an approved incident is diagnosed
twice, and the model has to be right both times.** qwen2.5:7b got F07 right
on 2 of 5 first frames; both of those then flipped to F06 on the second
frame and the cross-check correctly refused them.

Three consequences worth writing up:

- The headline §4.3 result — qwen 10/10 on F07 — was **decoder determinism
  on one frozen frame**, not accuracy. Across fresh frames the same model
  scores 2/5. This is the same class of error as the two instrument bugs in
  §4a and ADR 0011: the measurement described the rig, not the system.
- **The safety property held under the failure.** Five F07 injections, five
  escalations, nothing written, target left as found every time. A system
  that healed F07 by acting on an F06 diagnosis would look better on the
  results table and be worse.
- There is a cheap, honest improvement available: when the deterministic
  detector is unambiguous, do not re-run RCA on the approved path. The
  operator approved a decision that deterministic detection reached; routing
  the re-derivation through a model that may disagree with it discards the
  approval. `runner.approve()` already carries a comment describing exactly
  this failure for F01. The bench shows it is not hypothetical — it is the
  whole F07 column. **Recommended, and not done:** it changes approval
  semantics, which is the operator's call, not an overnight one.


---

## 7. Two persistence findings, one fixed and one left for you

Both surfaced while rebuilding the API image for the `num_ctx` fix.

### 7.1 The audit log lived in the container's writable layer — FIXED

`/app/harness/audit/kavach.jsonl` had no volume and no bind mount behind
it. `docker compose down`, `up --build`, or any rebuild would have
destroyed the hash-chained log without a word — 213 rows at the time,
including every incident from the overnight bench.

Copied out and verified intact before anything was touched, then
bind-mounted and migrated. A recreate and then a full rebuild took it to
215 rows with the chain still intact, which is the test. Evidence that only
exists inside a container is not evidence, it is a cache.

A second hole came out of the same investigation and is also fixed: the
first audit row any incident wrote was `permit`, and a diagnosis the
cross-check refuses returns long before the gate. **Every refusal — the
exact evidence for "no wrong diagnosis has ever driven a repair" — was
absent from the append-only log.** There is now a `diagnose` row on both
arms, so the denominator is recoverable from the log and not just the
numerator.

### 7.2 `GET /v1/incidents` reads memory only — ~~NOT fixed, your call~~ **FIXED 2026-10-20**

> **Closed by [ADR 0020](decisions/0020-incidents-are-read-from-the-store-and-the-bench-scores-two-answers.md).**
> `Incident.from_dict` inverts what the store persists, so the existing API
> mappers serve a restored incident and the reconstruction layer this note
> worried about was not needed. Verified against a real container restart:
> 50 incidents and 89 LLM calls where there were 0, and `make postmortem`
> renders an incident that exists only in Postgres. A restored incident is
> readable and **cannot be approved** — `_awaiting` is memory and is never
> repopulated. Alerts still read memory, on purpose; the reasoning is in the
> ADR.

Incidents **are** durably stored. All 137 of them are in Postgres with full
RCA payloads, on a volume, and `IncidentStore.get()` and `.recent()` both
exist. Nothing has been lost.

But neither incident route uses them:

- `GET /v1/incidents` returns `runner.incidents()` — the in-memory cache
- `GET /v1/incidents/{id}` 404s when memory misses, with the record sitting
  in Postgres

So after any API restart the console's history is empty and
`make postmortem` prints "no incidents recorded yet", even though the data
is right there. For a demo whose closing beat is the postmortem, that is
worth knowing before the day.

**Why it is not fixed here.** The stored payload does not validate directly
as `IncidentOut` — `routes._detection()` and `routes._rca()` do real shape
transformation, so the fallback needs an `Incident.from_dict()` or a
dict-shaped path through those helpers. That is a new reconstruction layer
on the API's read path, which is more than a fallback and more than should
be added unprompted at the end of an unattended run. The durable data is
safe either way, so there is no urgency and no risk in waiting for a
decision.

## 8. The control plane spent 83 minutes on a model nobody chose

Found at 05:03 on 2026-10-19, while starting the P8 three-run rehearsal.
Three of the four acts failed. The cause was not in any of them.

`infra/docker-compose.yml` declares
`KAVACH_LLM_MODEL: ${KAVACH_LLM_MODEL:-llama3.2}`. Compose reads `.env` from
**the compose file's directory**, so a `docker compose -f infra/...` invoked
without `--env-file .env` never sees the repo-root `.env` — and every
defaulted variable quietly takes the fallback written in the compose file.
The rebuild at 03:46 was issued that way. `.env` said
`qwen2.5:7b-instruct`; the running API said `llama3.2`.

`Makefile` line 18 documents this exact trap, which is why `COMPOSE` carries
`--env-file .env`. The rebuild was done by hand, bypassing it.

**What it cost, precisely.** Four incidents between 03:52 and 05:08 were
diagnosed by the wrong model. All four escalated with nothing written, because
`llama3.2` answered F06 to an F01 fault and the deterministic cross-check
refused it. The target was left clean each time.

**What it did not cost.** Every published figure predates the rebuild:

| artifact | model recorded | when |
|---|---|---|
| overnight bench (20 injections) | `qwen2.5:7b-instruct` | last incident 03:23 |
| `p6-f07-rca-qwen.json` | `qwen2.5:7b-instruct` | 2026-10-17 17:13 |
| the three ADR 0013 A/B runs | `qwen2.5:7b-instruct` | 03:36, 03:39, 03:42 |

Establishing that took a query against Postgres, because **no artifact
recorded which model produced it.** That is the actual defect. `/v1/system`
has reported the live model all along (`Ollama, Kavach path | model ...`) and
nothing read it.

**Fixed:** `harness/kavach_baseline.py` gains `rca_model()`, and both
`report.py` and `scenario.py` now stamp `rca_model` into their JSON artifact
and print it in the preflight header. `llm/client.py` already carried the rule
this violated — *a result that cannot say which model produced it is not a
result* — stated for `LlmResponse.provider` and never applied to the harness.

**Not fixed, and worth a thought:** nothing *refuses* to run when the live
model differs from the one `.env` names. Recording it makes the mistake
visible afterwards; it does not prevent it. A preflight comparison would, but
the harness does not read `.env` today and adding dotenv parsing to four
scripts to guard one class of operator error is a worse trade than printing
the model where a human sees it before the first act.

The cheap discipline, meanwhile: bring the stack up with `make up`, never a
bare `docker compose`.

## 9. Thirteen harness scripts cannot run from a clean shell

**Found:** 2026-10-20, auditing after the same bug hit twice.

`report.py` and `scenario.py` both read `KAVACH_TARGET_ADMIN_TOKEN` from
`os.environ` only. No Makefile target exports it, so both 401'd on their
first config write - `make offline` died on it, and `make bench` would have
wasted an eight-hour overnight run. Both now read through `Settings`, which
anchors to the repository root (`config.py`, `_env_files`).

A full audit found **thirteen more** with the same defect and no
`--admin-token` flag to work around it:

> `ablation_undo`, `human_baseline`, `kavach_baseline`, `p5_gate_live`,
> `p6_f01_live`, `p6_f07_live`, `p6_f08_live`, `rca_f01_live`,
> `rca_f07_live`, `rca_f08_live`, `runbook_baseline`, `stability_f07`,
> `window_sweep_f06`

Only `patch_live.py` reads `settings.target_admin_token` directly.

**Deliberately not fixed.** Each has already produced its artifact, and the
two on the critical path - the bench and the demo - are repaired. The
consequence is recorded rather than patched: **anyone reproducing these
results must export `KAVACH_TARGET_ADMIN_TOKEN` first**, or they will see a
401 that looks like a target fault.

The pattern is worth more than the fix. Every one of these scripts was
written, run successfully, and committed - because the author's shell
happened to have the variable exported. A script that works only in the
environment it was written in is not reproducible, and nothing in
`make check` can see the difference.

---

## 10. Every F06 diagnosis contradicts itself, and nothing checks

**Found:** 2026-10-20, investigating why F06 dropped from 5/5 to 3/5 between
the two benches (`bench-20261020-mttd.json`, report draft §4.1). The anomaly
was real. What it led to is bigger than the anomaly.

### The observation

`Diagnosis` (`rca/schema.py`) requires the model to emit **both** a
`fault_class` code and a `fault_name`. `diagnose.txt` line 149 asks for *"the
short name from the list above"*, and the list twenty lines earlier reads
`F06  Retrieval collapse` and `F07  Prompt version regression`. Both names
are correct in the prompt.

Every diagnosis in run B, grouped by the class code the model emitted:

| code emitted | n | `fault_name` emitted | correct? |
|---|---|---|---|
| F01 | 10 | Primary LLM endpoint outage | **10/10** |
| F07 | 4 | Prompt version regression | **4/4** |
| F08 | 10 | Configuration or environment regression | **10/10** |
| **F06** | **13** | **Prompt version regression** | **0/13** |

Thirty-seven diagnoses in all: twenty first draws plus the seventeen second
draws that approval produced.

`F06` + *"Prompt version regression"* is not a valid pair in the catalogue the
model was given. It emitted that pair **thirteen times out of thirteen** — in
the three F06 incidents that **resolved successfully**, as well as in the ones
that escalated. There is no lookup table to blame: `fault_name` is a required
field of the model's own constrained output, and no code in `kavach/` derives
or rewrites it.

### Why it matters more than the F06 anomaly it came from

**1. It is a free confusion signal that nothing reads.** The deterministic
validator has ten checks and `deterministic_agreement` compares the *code* to
the detector. Nothing compares `fault_name` to the catalogue entry for the code
beside it. A one-line check would have flagged **every F06 diagnosis in this
bench**, including the ones that healed.

**2. `F06 5/5` is a weaker result than it reads as.** F06's class accuracy is
5/5 first-draw in both benches. But by the model's own prose it understood all
five as *prompt regression* — it wrote F07's name, and in `INC-210032` it also
proposed F07's repair (`rollback_prompt`, rejected by `repair_permitted`,
below). The code field was right while the stated understanding was not. That
is the ADR 0013 confusion present at **13/13**, where the escalation rate shows
it at 2/5.

**3. Fixing it would invert the headline numbers, so it is not being fixed
here.** A `fault_name` coherence check added to the validator would reject
every F06 diagnosis, taking F06 from 5/5 to 0/5 and auto-resolution from 70% to
55%, days before a demo. That is a decision for the project owner, not a
quiet tightening — **it is recorded, not applied.** `AGENTS.md` forbids
weakening a check to make something pass; it does not license adding one whose
effect on the results has not been agreed.

Recommendation if there is time: add the check, re-run the bench, and report
the *before* and *after*. The finding is that Kavach can heal correctly from a
diagnosis that contradicts itself, and the honest version of that is two
numbers, not one.

### The second gap, from the same investigation — **FIXED 2026-10-20**

> **Closed by [ADR 0020](decisions/0020-incidents-are-read-from-the-store-and-the-bench-scores-two-answers.md).**
> `report.py` now records `llm_action` and `escalation_reason`, scores the
> repair against the **injected** class, and prints the joint table. Replayed
> over run B's 37 diagnoses it found what is written below **and one more
> thing nobody predicted**: two incidents where the class was WRONG and the
> repair was RIGHT. Action accuracy 33/37 beats class accuracy 32/37 — the
> repair the model reached for was right more often than the label it wrote.
> The rest of this section is the state before that measurement.

**The bench scores the class the model names, not the repair it picks.**
`harness/report.py` records `llm_class` only; `candidate_repair` is on the wire
and unread. The validator does check it, as `repair_permitted`. Run B's six
escalations split:

| rules that fired | n | what the model did |
|---|---|---|
| agreement only | 3 | named the wrong class |
| agreement **+** repair permitted | 2 | wrong class **and** an action that class may not use |
| **repair permitted only** | **1** | **right class, wrong repair** |

`INC-210032` is that last row: detection F06, diagnosis F06 at 0.95, agreement
satisfied — and `rollback_prompt` proposed for a retrieval collapse. **The
harness counts it in the 17/20 as a correct diagnosis.** It healed nothing.

To measure it: `report.py`'s `Run` would carry `llm_action` from
`rca.diagnosis.candidate_repair` and `escalation_reason` verbatim, and report
**class accuracy** and **action accuracy** separately with the joint cell
`(class right, action wrong)` called out, because that is the cell a reviewer
asks about. Both fields already come back from `GET /v1/incidents/{id}` —
which is how this note exists.

### Two smaller things run B settles

**The F06/F07 confusion is bidirectional.** ADR 0013 recorded it one way.
`INC-230050` is the reverse: detector F06, model F07 at 0.95, with
`rollback_prompt` proposed. Both faults present as lost grounding and the model
is choosing between them on evidence that does not separate them.

**The second draw is where classes lose, not the first.** `runner.approve()`
re-detects and re-diagnoses by design. F06 is 5/5 on the first draw in both
benches and both of its run-B failures were second draws; F07 is 2/5 first-draw
in both, and of four correct first draws across the two runs, one survived the
second. The frames are not identical — the second is rebuilt after detection
and the pre-fast set have run — so whether the second draw is harder or the
model is unstable is **not determined** by these forty injections.

**None of this produced a false heal.** Forty injections, forty clean targets.
The gate caught every failure above, including the one the metrics score as
correct, which is an argument for the gate rather than against the metric.

---

## 11. Kavach cannot start healing by itself, and the constraint that says so expired

**Found:** 2026-10-20, surveying comparable projects on GitHub for related
work. The survey's most useful output was not a feature to copy. It was a
question none of them would have to answer and this project does.

### The gap

There is **no background detection tick and no inbound alert path.** Grepping
the control plane for a scheduler, a repeating task, or an Alertmanager
webhook returns nothing; the only `while True` is the event bus's per-
subscriber queue. A loop starts exactly one way: a human or a harness calls
`POST /v1/loop/run`.

Every comparable system is triggered by the system under management:

| | trigger |
|---|---|
| Red Hat EDA + AAP demo | Prometheus → Alertmanager → Event-Driven Ansible |
| Kubernaut | detects signals itself, autonomous mode end to end |
| SRE-Agent-App | continuous OODA loop |
| **Kavach** | **an operator presses a button** |

So the honest answer to *"is it autonomous?"* today is: **it executes
autonomously once a human triggers it.** For a project whose title is
"autonomous self-healing", that is a weak sentence to have to say.

### The constraint was deliberate, and its precondition expired

`ROADMAP.md`, written before the safety engine existed:

> **No background detection tick, so no unattended healing.** A timer that
> detected and healed on its own would need the mode gate, and `permit()`
> does not exist until P6 (`docs/decisions/0006`, amendment). The loop
> therefore runs when an operator asks it to, from the console or a harness.
> **This is the constraint that keeps the missing safety engine honest, and it
> must not be removed before P6 lands.**

That was right. **P6 landed, and so did P8.** `permit()`, the three modes, the
blast radius, the circuit breaker, the audit chain and the approval flow all
exist and are measured. The condition attached to the constraint was met weeks
ago and nobody went back to lift it — a scaffold that outlived the thing it
was holding up, which is the same shape as `log_level` being dead
(ADR 0018) and `otlp_endpoint` being dead (ADR 0016), one layer up.

### What adding it would actually cost

Small, and that is the point — every hard part is already built. The tick
would call the same `run_once` path the console calls, so it inherits
`permit()`, `SIMULATION` as default, the blast radius that already paces
`make bench` to eight hours, and the audit chain. Nothing new is trusted.

**It should ship disabled.** `KAVACH_DETECT_INTERVAL_S=0` meaning off, so
unattended healing is something an operator turns on rather than something a
deployment discovers. Shipping a genuinely unattended healer on by default,
days before a graded demo, would be the one change in this project most likely
to produce an unexplained incident during it.

### What the survey said about the rest

Ranked by value over cost, and only the first is recommended before the
deadline:

1. **Autonomous trigger** — above.
2. **Graduate unknowns into knowns.** The strongest idea found, from a
   practitioner write-up: *"build the feedback loop that converts unknowns to
   knowns... continuously shrink the surface area of unknowns."* Kavach's
   `ESCALATED` incidents are exactly that surface, and promoting a repeatedly-
   escalated pattern into a deterministic detector would be a genuine
   contribution rather than a feature. It is also a phase, not a weekend.
   **Further work.**
3. **An MCP interface** (Kubernaut, NetworkOps both expose one). Demonstrable,
   and it adds no research value: it is another way to call routes that exist.
4. **Evidence redaction before a cloud provider** (K8sGPT anonymises before
   sending). Kavach's RCA normally runs against local Ollama, but
   `harness/reports/` holds Groq and Gemini artifacts, so that path is real.
   Credentials are already redacted on the way into the log buffer (ADR 0018);
   whether the *evidence frame* needs the same treatment is **unchecked**, and
   is written here as a question rather than a finding.

**Two things explicitly NOT gaps.** Auto-opening a pull request with the fix
(`carlossg/kubernetes-agent`) is forbidden by `AGENTS.md` — Kavach never
pushes to the target's remote — so its absence is a boundary, not an
omission. Delivering alerts to a human (the Red Hat demo emails the approval)
was decided against in ADR 0018: alerts here are displayed, never delivered,
because this project has no on-call rotation.

### Lesson

> **A constraint written with an expiry condition does not expire by itself.**
> "Not before P6" reads as temporary and behaves as permanent, because the
> phase that satisfies it is busy with its own work and nothing points back.

The practical form: a constraint that names a release condition should name
the file that lifts it, or it becomes architecture by default. This one was
found by comparison with other projects, not by reading our own roadmap — and
it had been sitting in `ROADMAP.md` in bold the whole time.
