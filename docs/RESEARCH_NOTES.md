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

1. `make bench` full 4×5 run — **running in the background now**
2. Re-measure RCA accuracy at `num_ctx=8192` (see §4a); rebuild the API
   image first, or the container keeps the old window
2. Postmortem renderer (§3.1)
3. Report and slides — cite AIOpsLab and ITBench in related work
4. `make scenario`, three consecutive clean runs an hour apart
5. Decide the human baseline: run it with a teammate, or record the decision
   to drop it. It is currently neither.
6. The one-line `allowed_actions` decision for `apply_patch` (ADR 0012)
