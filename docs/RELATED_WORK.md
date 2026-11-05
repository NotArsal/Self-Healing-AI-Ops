# Related work

**How this was assembled, because it bounds what it is worth.** Searched
2026-11-02 across the arXiv/research index for LLM-based root-cause analysis,
agentic SRE benchmarks, safe remediation gating, and self-consistency methods.
**Every paper below is cited from its abstract, not from a full-text read.**
Numbers quoted are the authors' own headline figures as stated in their
abstracts. Nothing here has been reproduced, and where a comparison to Kavach
would need a detail an abstract does not give, this document says so instead of
guessing. Treat it as a positioning map, not a survey.

---

## 1. The architecture is convergent, not novel — and that is the useful finding

Kavach's central design decision — a deterministic evidence-extraction stage
that builds a bounded frame, an LLM that reasons only over that frame through
read-only access, and a deterministic gate that decides what may execute — was
arrived at independently and is now the dominant pattern in the 2025–26
literature.

**EviRCA** (arXiv [2609.19825](https://arxiv.org/abs/2609.19825)) is the
closest architectural twin:

> *"a framework for LLM-based RCA that decouples deterministic evidence
> extraction from LLM reasoning. A system-agnostic extraction stage converts raw
> metrics, traces, and logs into a compact set of faithful multimodal evidence
> cards, while the LLM reasons only over these structured observations through a
> small set of predefined read-only tools, without accessing raw telemetry or
> executing code."*

That is a description of `rca/evidence.py` plus `rca/engine.py`. EviRCA reports
40.6–43.9% correct on OpenRCA against up to 15.2% for prior baselines, with
15–26× fewer tokens and 3–20× lower execution time. **Its conclusion is also
ours**, reached from the opposite direction (§4.2):

> *"the bottleneck lies in judging the evidence that the extraction stage has
> already surfaced, rather than searching for it, suggesting that the
> effectiveness of LLM-based RCA depends heavily on the quality of evidence
> extraction."*

EviRCA establishes this by showing extraction quality determines the ceiling.
We established it by **degrading** a frame and watching F08 accuracy fall from
10/10 to 0/10 while the fault evidence stayed present and correct. Two
independent routes to the same claim.

**ARBITER** ([2607.19182](https://arxiv.org/abs/2607.19182)) independently uses
the same vocabulary — it *"assembles bounded DiagnosisContext objects, and
exposes a finite typed-action interface that separates planning from
execution,"* with *"deterministic schema checks, policy gates,
resource/disruption budgets, approval, and bounded execution forming the safety
substrate."* Every one of those clauses maps onto something in `permit()`.

**Others in the same family.** TAMO
([2504.20462](https://arxiv.org/abs/2504.20462)) unifies multimodal telemetry
into time-aligned representations before reasoning. Log-Insight
([2607.08529](https://arxiv.org/abs/2607.08529)), deployed at Huawei, runs
symbolic stages that *"hand the LLM a compact, pre-ranked evidence dossier"*,
reducing millions of events by 1,000–7,000×. GALA+
([2608.08968](https://arxiv.org/abs/2608.08968)) and MetaRCA
([2603.02032](https://arxiv.org/abs/2603.02032)) add service-dependency and
causal-graph structure to bound exploration. *"How Far Can Root Cause Analysis
Go on Real-World Telemetry Data?"*
([2607.13548](https://arxiv.org/abs/2607.13548)) makes a methodological choice
we also make: *"We compute the evidence once, offline, and supply it identically
to every arm."*

**What this means for the report.** The architecture should be presented as a
*convergent* design with independent corroboration, not as a novel
contribution. Claiming novelty for the pattern invites a reviewer to produce
EviRCA. Claiming independent arrival at the same pattern, plus a measurement the
pattern's own authors did not make, is defensible.

---

## 2. Our accuracy numbers need the difficulty caveat stated before they are read

This is the most important section for credibility.

| benchmark | best reported agent |
|---|---|
| ORCA-bench ([2607.28545](https://arxiv.org/abs/2607.28545)) | **25.3%** RCA accuracy on Medium, **10.0%** on Hard |
| Incident-Arena ([2610.00648](https://arxiv.org/abs/2610.00648)) | frontier models **below 64.3%** |
| SRE-Marathon ([2609.33023](https://arxiv.org/abs/2609.33023)) | best of 10 methods **41.3 / 100** |
| Cloud-OpsBench ([2603.00468](https://arxiv.org/abs/2603.00468)) | JRA **0.76**, Evidence Closure **0.38** |
| EviRCA on OpenRCA | **40.6–43.9%** |
| LATS-RCA ([2605.03505](https://arxiv.org/abs/2605.03505)) | **91.3%** on the LO2 benchmark, **65.1%** on real production incidents |

Kavach reports 85–90% RCA accuracy. **A reviewer familiar with this literature
will read that as a benchmarking error unless the difference in difficulty is
stated first.** The honest account of why our setting is easier:

- **Four fault classes, not open-ended.** ORCA-bench starts from *"ambiguous
  user-facing reports"*; our diagnosis is a choice among four known classes with
  a declared catalogue in the prompt.
- **A deterministic detector has already fired** and named a class before the
  model is asked. The model's answer is cross-checked against it. Most
  benchmarks give the agent no such prior.
- **Evidence is pre-extracted** into a bounded frame. Agents in ORCA-bench and
  Incident-Arena must find their own evidence through Prometheus, Jaeger and
  OpenSearch; Cloud-OpsBench's Evidence Closure Rate of 0.38 against JRA 0.76
  exists precisely to measure that search step, which we skip by construction.
- **One service, one instance.** No dependency graph, no cross-service
  propagation, no Kubernetes platform layer.
- **No time pressure or overlapping faults.** SRE-Marathon injects *"overlapping
  faults according to a seeded, production-calibrated schedule"* and reports
  that agents *"almost never complete repairs while the faults remain active."*

LATS-RCA's 91.3%-on-benchmark against 65.1%-on-production is the cleanest
available illustration of the gap, and it comes from authors who built both.
The closest peer on difficulty and setup is **TriFleetRCA**
([2609.23766](https://arxiv.org/abs/2609.23766)): on-premise Qwen2.5-14B on a
single GPU, four injected faults in a live Kubernetes cluster, 100 analyses,
hit rate **0.85–0.95**. That is the same order as ours, on a comparable number
of fault classes with a comparably sized local model — which is the comparison
to put in the report, rather than the open-ended benchmarks.

---

## 3. What we measured that this literature has not

Four results from `REPORT_DRAFT.md` that the surveyed work does not appear to
contain. These are the contribution claims, and each is stated with the limit
that applies to it.

**3.1 A reproducible single-cell mapping defect, confirmed across a machine
rebuild.** Every diagnosis emitting F06 carried F07's catalogue name — 28 of 28
across three runs — against 49 of 49 coherent on the other three classes, and
the result survived a complete reinstall of Docker, Ollama, the model weights
and the database. TriFleetRCA reports the same *class* of failure (*"one fault
was diagnosed correctly and cited incorrectly every trial, a failure mode
accuracy conceals"*) which corroborates that the phenomenon is real and not
local to us — but it reports it as an observation in passing, not as a measured
and reproduced property. **Limit:** one model, one prompt.

**3.2 Two self-reported channels measured and shown non-separating.** Neither
confidence nor citation coherence distinguishes a correct diagnosis from a wrong
one in our data: 8 of 18 correct answers sit at the same 0.95 as both wrong
ones, and citations are coherent with the stated class 10/10 even in an arm
where the stated class is 0/10 correct. The self-consistency literature (CISC
[2502.06233](https://arxiv.org/abs/2502.06233), Mirror-Consistency
[2410.10857](https://arxiv.org/abs/2410.10857), CGES
[2511.02603](https://arxiv.org/abs/2511.02603), conformal aggregation
[2605.14098](https://arxiv.org/abs/2605.14098)) is largely built on the premise
that these signals carry usable information. **This is the result most worth
arguing in the report**, and §4 below explains why the standard remedy does not
apply.

**3.3 Frame contamination as a measured failure mode, with three channels.** A
stale `[2m]` error-ratio metric plus residual connection-error log lines — both
well inside every detector's tolerance — took F08 from 10/10 to 0/10. We then
found that the evidence frame has at least three independent memories of a
finished fault (metric window, log lines, detector signal), and that draining
one is not draining the frame. EviRCA names evidence quality as the bottleneck;
we have a controlled arm showing what a *specific* contamination does and an
enumeration of the channels it arrives through. **Limit:** n=10 per arm, one
fault class, and the contaminated arm carried two residues rather than one, so
the variable is "the frame remembers a prior fault", not a single metric.

**3.4 A bounded-authority safety result at a stated denominator.** 80
injections, 11 wrong diagnoses, 0 executed, 0 false heals, with the blast-radius
limiter (`FR-16`: 5 incident starts/hour, 3 actions/incident) enforced
throughout and a mandatory declared inverse per action. The remediation-safety
papers in §5 report comparable constructs; what we add is the *refusal*
accounting at a fixed denominator with every refused row's reason recorded.

---

## 4. Why the literature's standard fix does not apply to us

The dominant proposal for unreliable LLM judgements is test-time
sampling — self-consistency, weighted majority voting, confidence-informed
aggregation, conformal abstention. CISC reports cutting required reasoning paths
by over 40%; conformal aggregation reports 90.1% selective accuracy on GSM8K by
abstaining on under 5% of problems.

**We measured it rather than arguing it**, because the artifacts already
contained the experiment: `rca_*_live.py` diagnoses ten times against one fixed
frame, which is self-consistency by another name.
`harness/self_consistency.py` replays 110 recorded draws over 11 frames.

| | |
|---|---|
| single-draw accuracy | 54% |
| majority-vote accuracy | 55% |
| unanimous frames | 9/11 |
| **unanimously wrong frames** | **4/11** |
| frames voting rescued | 1/11 |
| frames voting broke | 0/11 |

Voting is not harmful — one rescue, no breaks — but it buys one frame in eleven
for ten times the inference, and it cannot touch the dominant failure: on four
frames the model returned the same wrong class on all ten draws. Inter-sample
agreement is in fact **anti-informative** here, peaking exactly on the
unanimously wrong frames.

The reason is structural rather than incidental: self-consistency corrects
**sampling** variance, and our error is driven by the **evidence**, which every
sample in an arm sees identically. A misleading frame is not noise to be
averaged out; it is a shared premise. Mirror-Consistency's observation that
*"inconsistent minority views often illuminate areas of uncertainty"* cuts the
same way — in our arm there was barely a minority view to learn from.

This is the argument for Kavach's actual design: the deterministic cross-check
reads **the system**, not the frame the model was handed, so it is the one
signal in the loop that a contaminated frame cannot corrupt. The point
generalises — **any** aggregation over a single evidence frame inherits that
frame's defects, however many samples it draws.

---

## 5. Safety gating: where Kavach sits

| mechanism | Kavach | closest published analogue |
|---|---|---|
| allow-listed actions, deny-list first | `permit()`, action registry | ARBITER's *"finite typed-action interface"* |
| mandatory declared inverse per action | every repair declares one | *Rebooting Microreboot*'s typed ISA with *"explicit side-effect semantics"* ([2604.09963](https://arxiv.org/abs/2604.09963)) |
| sandbox before production write | `executor/sandbox.py` | GuardedAct's *"lightweight digital-twin sandbox"* ([2609.11264](https://arxiv.org/abs/2609.11264)) |
| rate cap on autonomous action | `FR-16` blast radius | GuardedAct's blast-radius labels; CMDP's bounded false-remediation rate ([2607.20005](https://arxiv.org/abs/2607.20005)) |
| human approval tier | three modes, `REQUIRE_APPROVAL` | CMDP's *"context-adaptive human-in-the-loop gate"* |
| no-regression guarantee | unwind on failed verification | STRATUS's Transactional No-Regression ([2506.02009](https://arxiv.org/abs/2506.02009)) |
| append-only audit | hash-chained log | Diviner's evidence-linked trajectories ([2610.21281](https://arxiv.org/abs/2610.21281)) |

**Quantitative points worth citing.** GuardedAct reports collateral damage
falling from 25.6% to 5.2% with sandbox-first verification, at roughly 8s added
MTTR. *Rebooting Microreboot* reports typed actuation reducing *"agent-caused
harm by 95% in simulation and 0% harm online"*, and states the principle Kavach
also relies on: *"Agents are explicitly untrusted; safety derives from the ISA
and microkernel."* Both give external support for the architectural claim that
bounded, typed authority rather than better prompting is what makes this safe.

### What this literature has that Kavach does not

Stated plainly, because a related-work section that only finds agreement is not
credible.

- **Epistemic uncertainty as a first-class risk dimension.** The CMDP paper
  decomposes risk into blast radius, reversibility **and epistemic
  uncertainty**. Kavach has the first two. Our own measurements rule out the
  obvious third (confidence, citation coherence — §3.2), which makes this an
  open problem for us rather than an oversight, but it is still a gap.
  §4.2's frame-staleness result suggests evidence recency as a candidate
  substitute.
- **Canary and progressive rollout.** GuardedAct, ARBITER and AegisML-class
  systems shift traffic gradually. Kavach's repairs are config and prompt
  rollbacks against a single-instance target, where traffic splitting does not
  apply — a scope consequence, not a defect, but it should be said.
- **Service-dependency graphs.** GALA+, MetaRCA and TAMO all exploit topology
  to bound the search. Our target is one service, so there is nothing to exploit.
- **Scale.** Diviner operates at Meta; Log-Insight at Huawei;
  *"Autonomous Incident Resolution at Hyperscale"*
  ([2606.09122](https://arxiv.org/abs/2606.09122)) reports *"autonomous
  resolution rates exceeding 90% for common incident categories"* in production
  at a major cloud provider. Our denominator is 80 injections on one laptop.
- **Learning from history.** Diviner's *Adapt* stage and MetaRCA's reusable
  causal graph both improve from past incidents. Kavach's knowledge base was cut
  (ADR 0009) and every diagnosis starts cold.

---

## 6. Methodology papers that name mistakes we actually made

Worth citing in the methods section, because they describe failures this project
committed and then corrected — which is more honest than citing them as
standards we met from the start.

**Refuse, Decompose, Refresh** ([2609.20538](https://arxiv.org/abs/2609.20538))
opens with *"An AI evaluation can be perfectly reproducible and still support
the wrong claim,"* and prescribes abstaining when a clean reference stream lacks
support. Our failed dose sweep is a textbook case: four arms, two unreachable,
and two that reached the model carrying frames *below* the abnormality threshold
they were supposed to exceed — reproducible, and would have supported a
dose-response claim that the data did not contain. The fix we applied (assert
the contaminant is present in the frame, and mark the arm invalid otherwise) is
this paper's *Refuse* action.

**SSCBench** ([2610.11514](https://arxiv.org/abs/2610.11514)) studies *"the
evidential validity problem in agent fault-injection evaluation"* — whether the
observations that could refute an injected assertion were actually visible to
the agent before the affected fact was used. That is the question our frame
contamination raises, and it is the right frame for reporting it.

**Rethinking Tool Design for Agentic RCA**
([2610.05009](https://arxiv.org/abs/2610.05009)) reports *"cases in which agents
override correct diagnostic recommendations after consulting additional
evidence."* That is our second-draw loss on F07 — the model diagnoses correctly,
then flips on the post-approval re-diagnosis — observed independently.

**Recoverability and Verifier Strength**
([2610.27465](https://arxiv.org/abs/2610.27465)) proposes measuring verifier
strength and recoverability before allowing a step to run unattended. Kavach's
`runner.approve()` re-detects and re-diagnoses rather than replaying, which is a
strong recoverability posture; the paper's framing gives it a name and a way to
quantify it.

---

## 6a. A second search, 2026-11-03: the simple harness is not a compromise

Four papers found overnight change the positioning in §1 from "convergent" to
something stronger, and one of them justifies a decision this project already
made for other reasons. Abstracts only, as above.

### The architecture is not just common — it outperforms the elaborate ones

**"Free to Look, Free to Reason: Simple LLM Harnesses Outdiagnose
Hand-Crafted Root Cause Analysis Agents"**
([2610.35767](https://arxiv.org/abs/2610.35767)) compares three harnesses that
prescribe none of the model's calls — including *"one call over an evidence
package"* — against five published LLM RCA agents and against statistical and
causal methods, on 90 validated cases from eight public datasets:

> *"The simple harnesses are the most accurate (PR@1 65-77% on three mid-tier
> models), ahead of the published agents (16-53%) and the non-LLM methods
> (6-39%)… The published agents fix from a tenth to all of their model calls
> in the program, and a case study shows how these prescriptions skip the
> decisive evidence."*

**"One call over an evidence package" is exactly what Kavach does.** The
evidence frame is built deterministically, handed to the model once, and the
model prescribes nothing about its own investigation. This paper reports that
design beating hand-crafted multi-stage agents by 20–60 points, and adds that
*"every Pareto-optimal run in cost or time uses a simple harness."*

So §8.3 should not merely claim convergence. It can claim that the design
Kavach arrived at is the one that measures best among those compared — with
the caveat that this is one paper on 90 cases and we have not reproduced it.

It also sharpens §4.2's finding. If the harness is not the bottleneck and the
evidence package is, then *frame contamination destroying accuracy* is exactly
the failure mode this literature would predict, and our controlled arm is a
measurement of it.

### The public benchmarks we did not use are under serious criticism

Three papers argue the standard leaderboards overstate method quality, which
matters because §8.3 contrasts Kavach's 85–90% against them.

- **"Rethinking the Evaluation of Microservice RCA"**
  ([2510.04711](https://arxiv.org/abs/2510.04711)): *"simple rule-based
  methods can achieve performance comparable to or even surpassing
  state-of-the-art (SOTA) models on four widely used public benchmarks."*
  Re-evaluating 11 SOTA models on a harder generated benchmark gives *"low
  Top@1 accuracies, averaging 0.21, with the best-performing model reaching
  merely 0.37."*
- **"Does Graph Structure Earn Its Place…"**
  ([2609.27069](https://arxiv.org/abs/2609.27069)) audits RCAEval directly and
  finds its headline metric nearly satisfied without reading any data: *"a
  ranker reading no telemetry at all places the true culprit in the top five
  on 99.7 percent of held-out incidents, scoring Avg@5 0.488"*, against a
  uniform-random 0.137. It also reports a *"non-uniform column schema that
  silently zeroes telemetry for most RE1 cases."*
- **"What a Pooled Leaderboard Does Not Say"**
  ([2606.29159](https://arxiv.org/abs/2606.29159)) re-runs 16 methods across
  OpenRCA, RCAEval and PetShop and finds that of 8 pooled leads whose margin
  is below the cross-subsystem spread, **6 reverse**; that *"the input table
  that one released runner reads is not the one its documentation
  describes"*; and that of 23 RCA papers examined, *"none releases the
  per-case outputs needed to check either premise."*

**What this licenses us to say, and what it does not.** It does *not* excuse
never evaluating on a public benchmark — that remains a real gap and §6 should
keep saying so. What it does support is that a leaderboard position would not
have been the stronger claim: a bespoke measurement of 80 real injections with
every refusal accounted for, 0 executed wrong diagnoses and per-case artifacts
committed, is answering the question these audits say the leaderboards do not.
Kavach already publishes the per-case outputs that *"none"* of those 23 papers
release.

### Independent support for our own P2-vs-P3 result

§4.9 reports the uncomfortable finding that the deterministic path resolved
4/4 and faster, while the LLM path resolved 4/8 and 40–70% slower — that RCA
*subtracts* on this workload. 2510.04711's "simple rule-based methods
comparable to or surpassing SOTA" is independent corroboration from a
different direction, and it is worth citing beside our own number rather than
leaving ours looking like a local anomaly.

### Datasets worth knowing about, with the caveat attached

| | |
|---|---|
| [RCAEval](https://github.com/phamquiluan/rcaeval) (MIT, WWW'25) | 9 datasets, **735 failure cases**, 15 reproducible baselines, on Hugging Face. The obvious external evaluation — read 2609.27069's audit first. |
| [OpenRCA](https://github.com/microsoft/openrca) (MIT, ICLR'25) | Microsoft; the benchmark EviRCA reports on. |
| [awesome-failure-diagnosis](https://github.com/phamquiluan/awesome-failure-diagnosis) | ~151 curated resources, same author as RCAEval. |
| [awesome-AIOps](https://github.com/OpsPAI/awesome-AIOps) | Broader AIOps list: papers, tools, benchmarks, datasets. |

---

## 6b. A third search, 2026-11-05: the enforcement boundary has a measured precedent

**Provenance, which differs from the rest of this document.** The two searches
above read abstracts only. Of the three papers here, **2608.01955 was read as
full HTML text** and is cited at section level; **2608.27646 and 2608.21310
were read from their arXiv abstract pages** via a summarising fetch, not from
the PDFs, which did not parse. None has been reproduced. Where a number is
given below it is the authors' own, as stated on those pages.

### The closest architectural match declines to measure itself

**"Agentic Self-Healing for Data & AI Pipelines"**
([2608.01955](https://arxiv.org/abs/2608.01955)) proposes a seven-layer
reference architecture whose component list is, point for point, Kavach:
telemetry over OpenTelemetry and Prometheus; a **deterministic policy engine
that handles known failures before any LLM call**; a planner that may select
only from an **allowlisted playbook library**; risk-tiered approval; guarded
execution through a workflow engine rather than agent shell access; an
immutable audit trail the paper says should be treated as a security control;
**per-pipeline action limits and rate caps**, which it names as the defence
against *compounding actions*; and escalation as the planner's only permitted
output when no playbook applies. Its worked policy requires a diagnosis
confidence of at least 0.8 before acting; Kavach's manifest requires 0.75.

Two differences matter, and both favour this report.

The paper is **"deliberately prescriptive rather than empirical"** (its §1),
its platform comparison is scored from vendor documentation, and its cost
claims are **"indicative rather than measured"** (its §6). It names as future
work: instrumenting real deployments and measuring **time to diagnosis, time
to recovery, escalation rates, and remediation precision against a
pre-adoption baseline.** That list is §4 of this report — MTTD, MTTR,
escalation accounted for per incident, and not one but two pre-adoption
baselines, human and scripted runbook.

Second, on inverses it is thinner than Kavach rather than equivalent: its only
described inverse is *git revert plus redeploy* for deployments, and it
**describes no inverse for its other action types.** Kavach's manifest refuses
to register a repair that does not declare one, and `has_inverse` is asserted
for all four actions.

**This is the strongest version of the convergence claim in section 1.** It is
no longer only that several systems arrived at this shape; it is that a 2026
reference architecture recommends this shape, explicitly does not measure it,
and asks for precisely the measurements this report supplies.

### Enforcing policy outside the model has a quantified precedent

**"If Agents Were Angels, No Governance Would Be Necessary: Out-of-Band Policy
Enforcement at a Trusted Tool Boundary"**
([2608.27646](https://arxiv.org/abs/2608.27646)) makes Kavach's thesis
directly: prompts are unreliable as guardrails because **one fallible reasoner
both interprets the task and enforces its boundaries.** Its OBPE boundary sits
outside the agent's reasoning, checks each requested operation against policy,
and — the part that matches `permit()` most exactly — lets an agent-level
policy **narrow** the data owner's maximum access and never widen it. Kavach
spells the same rule as a deny-list evaluated before the allow-list and a
`DENY_ALWAYS` floor the manifest validator will not let a target raise.

It also supplies a number this report has not had: across **3,621 trials**
over four models and 20 adaptive red-team tasks, trace failures fell from
**57.6% to 0.2%**, while task fulfilment fell from **79.1% to 60.9%.**

That trade is the same shape as ours and is worth quoting next to section 4's
headline. Kavach gives up roughly a fifth of its incidents to escalation —
80% auto-resolution in run D — and buys 0 false heals in 80 injections. A
reader inclined to read escalation as failure should see that an independent
system, measured adversarially, paid about eighteen points of fulfilment for
its safety result and reported that as the point rather than the cost.

The authors are explicit that **write controls and durable approval were
outside their evaluation**, which is the half Kavach covers: every path
measured here ends in a write to a live system or a refusal to make one.

### A correct answer can hide ungrounded reasoning, measured at 5,000 trajectories

**"Beyond Fault Localization: A Trajectory-Level Study"**
([2608.21310](https://arxiv.org/abs/2608.21310), v1 Aug 2026, v2 Oct 2026)
analyses **5,000 agent trajectories** across ten framework-and-backbone
configurations on RCABench, using fault-propagation paths as a causal
reference. Its headline is that **a correct localisation can conceal a
poorly-grounded reconstruction of the causal chain** — the answer is right and
the process behind it is not — and that trajectories, not final answers, are
what should be evaluated.

This is independent corroboration of section 4.2's self-consistency finding,
reached by a different route and at a far larger n. We found a model emitting
a correct class code beside a `fault_name` belonging to a different class, in
13 of 37 judged diagnoses, including three that healed correctly. They found
the general case: outcome-level scoring cannot see reasoning quality. Their
remedy is a trajectory-level evaluation harness; ours was to measure the
contradiction and **deliberately gate nothing on it**, so that the headline
numbers could not be flattered by the fix.

### The tooling has converged on the verdict triple too, at toy scale

Worth one line because a reviewer may raise it. A 2026 cohort of
"agent policy engine" repositories returns `allow` / `require_approval` /
`deny` — Kavach's `ALLOW_AUTO` / `REQUIRE_APPROVAL` / `DENY` with
`REQUIRE_SANDBOX` added. The nearest, **AgentGuard**
(`asher0913/agent-guard`), gates tool calls with deterministic rules, risk
scores and stable rule ids for audit. It is MIT, **0 stars and 3 commits at
the time of reading**, has no inverse actions, no blast-radius mechanism, and
**no post-action verification** — evaluation happens only before execution.
The verdict vocabulary is converging; the closed loop around it is not.

**One claim deliberately not made.** A search for peer-reviewed measurement of
rate limiting as a control on compounding agent actions returned mostly vendor
and practitioner writing. That is suggestive, not established — one search is
not a literature review, and section 4.2b should not be sold as the first
measurement of a throughput ceiling on that basis. It is enough to say the
control is widely recommended and that this report measures its cost in heals
per hour.

---

## 7. One-paragraph positioning statement

For the abstract or introduction:

> Autonomous incident remediation with LLMs has converged on a common
> architecture — deterministic evidence extraction, an advisory model reasoning
> over a bounded frame, and a deterministic gate controlling execution — arrived
> at independently by several 2025–26 systems. Kavach implements that pattern on
> a deliberately small scope: four fault classes injected into a separate,
> pre-existing RAG application, diagnosed by a 7B local model behind a gate with
> a bounded blast radius and a mandatory inverse per action. Its contribution is
> not the architecture but the measurement: 80 real injections with 0 false
> heals and every refusal accounted for; a reproducible single-cell defect in
> the model's class-to-name mapping that survived a full machine rebuild; two
> self-reported reliability channels measured and shown to carry no separating
> signal; and a controlled demonstration that stale evidence from a finished
> fault — not model sampling noise — is what destroys diagnostic accuracy, which
> implies that the test-time-sampling remedies dominant in the literature cannot
> fix this failure mode.
