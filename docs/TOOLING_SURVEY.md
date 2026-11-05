# Tooling survey — what we would adopt, and what we would not

**Why this exists.** Two of Kavach's components are hand-rolled where a
reviewer will reasonably ask "why not use a library?": the hash-chained audit
log (`kavach/audit/log.py`) and the deterministic verification set
(`kavach/verification/fast.py`). This records what the alternatives actually
are, so the answer is a survey result rather than an opinion.

**How this was assembled, because it bounds what it is worth.** Searched
2026-11-05. **Every entry below is from a search-result snippet and a README
at most — no repository was cloned, no test suite was run, no license file was
read in full, and no maintenance history was checked.** Star counts and commit
counts are as reported at the time of reading. Treat this as a map of what
exists, not as due diligence. Nothing here was adopted.

---

## The headline: for our two hand-rolled pieces, there is no mature option

This was the surprise, and it is the useful finding. Both searches returned
long lists of small, recent, single-maintainer projects rather than one
obvious library. That changes the answer to "why did you write your own" from
a preference into a constraint.

### Hash-chained audit logs

The field is a cluster of 2026 projects doing the same thing at roughly the
same size: `auditchain`, `nexuscone`, `tamperlog`, `chainverify`,
`evidence-chain`, `hash-chain-integrity-log`, `ChainTrail`. The most complete
looked to be **`auditchain`** (MIT, on PyPI, async-first, zero runtime
dependencies, SQLite/JSONL/Postgres backends, signed checkpoints, optional
Ed25519).

**Verdict: would not adopt now, and one of them identifies a real gap in ours.**

Swapping the audit log this late would invalidate the chain in
`harness/audit/kavach.jsonl`, which is the evidence behind §4's audit claims —
997 records at last count, verified intact. That is a bad trade for a
dependency.

But **`tamperlog`**'s premise is worth recording honestly: it adds Merkle
checkpoints with externally anchored roots specifically because *plain hash
chaining silently accepts re-chained truncation*. **That is true of ours, and
it was measured rather than assumed** — on a copy of the real log, never the
log itself:

| mutation | rows | `verify()` says |
|---|---|---|
| intact copy | 1014 | intact |
| **last 50 records deleted** | 964 | **intact — not detected** |
| one middle row edited | 401 | broken: *row content does not match its recorded hash* |
| one middle row deleted | 401 | broken: *prev link is …, expected …* |

So the chain does what it claims for edits and for deletions in the middle,
and a tail truncation leaves a shorter chain that is perfectly valid from
genesis. `auditchain` names the same hole from the other side: without a seal
key, anyone who can write the log can rewrite and re-seal it. Kavach has no
seal key, and nothing records the expected row count outside the file.

This is not a defect against the threat model `AGENTS.md` states — the audit
log guards against Kavach's own actions going unrecorded, not against an
attacker with write access to the host — but the report should say which of
the two it does, rather than letting "hash-chained" imply both. **Recorded as
an open item rather than fixed**: a signed checkpoint is a contained change,
and this close to the deadline a change to the audit format is the last thing
to touch.

### Deterministic RAG evaluation

Same shape: `ekowbaah/rag-eval-harness` (provider-neutral, deterministic, no
network calls, precision@k / recall@k / MRR / nDCG@k with per-metric regression
tolerances), `Agampal007/llm-eval-harness` (retrieval, answer and abstention
metrics, bootstrap CIs, NumPy only), and several that advertise determinism but
ship an LLM judge as the default or an opt-in.

**Verdict: would not adopt, and the reason is a scope difference rather than
quality.** Those harnesses score *retrieval quality* against a golden set.
`fast.py` answers a narrower question — *is this system healthy enough that a
repair can be called verified* — in three string checks with no ranking metric
anywhere, deliberately, per `FR-07b`. A richer evaluator would make the
recovery path slower and give the verification step a tunable surface, which
is the opposite of what a gate wants.

Two ideas from them are worth stealing and cost nothing: **per-metric
regression tolerances** rather than a single pass/fail, and **abstention as a
scored outcome** rather than a failure. Kavach already treats refusal as
correct behaviour in the loop; it does not score it in the fast set.

---

## Adjacent repositories worth knowing about

Not adopted, and listed because they are what a reviewer may ask whether we
looked at.

| repo | what it is | why not |
|---|---|---|
| **AgentGuard** (`asher0913/agent-guard`) | policy gateway returning `allow` / `require_approval` / `deny` for tool calls | same verdict vocabulary as `permit()`, but 0 stars / 3 commits, no inverse actions, no blast radius, and no post-action verification. Cited in `RELATED_WORK.md` §6b as evidence of convergence, not as a candidate |
| **Open Policy Agent** | general policy engine, Rego | the real option if the gate were ever extracted. Rejected for this project because `permit()`'s ten checks are the contribution: expressing them in Rego would move the thing being evaluated into a dependency, and `AGENTS.md` requires the deny-list and `DENY_ALWAYS` floor be enforced in code we test |
| `systempromptio/awesome-ai-agent-governance` | curated list of agent-governance tooling | useful as a pointer for future work |
| `kaushikb11/awesome-llm-agents` | curated list of agent frameworks | same |

---

## What this survey changed

1. **Two design decisions are now defended by evidence** rather than by
   assertion: there is no mature library for either piece.
2. **One real limitation found and written down** — tail truncation and the
   absence of a seal key. `REPORT_DRAFT.md` §6 carries it; it is a gap in what
   "hash-chained" implies, not in what the threat model claims.
3. **Two cheap ideas noted** for the fast set: per-metric tolerances, and
   scoring abstention rather than treating it as absence of failure.

Nothing here was adopted, and nothing here should be adopted before the
deadline. A dependency added to a system whose contribution is its safety
properties has to be read before it is trusted, and none of these has been.

---

## Second pass, 2026-11-06: beyond self-healing

Broader sweep, asked for explicitly: repositories outside the self-healing
niche that bear on this project. **Same provenance limit as above — search
snippets and repository descriptions, nothing cloned, nothing run, nothing
adopted.** Star counts and "2026" labels come from aggregator pages rather
than independent checks, and several of the roundups consulted are vendor- or
affiliate-authored. Treat every claim here as "this exists", not "this is
good".

### The two that matter, because they converge on our distinctive parts

Kavach's architecture is convergent (§1 above, and `RELATED_WORK.md` §6b).
What was *not* obviously convergent until this search is the two pieces the
report treats as its own: verifying an agent's claim of success, and a
hash-chained record of what it did. Both now have independent counterparts.

**`agent-claimcheck`** checks an agent's **success claims against recorded
tool receipts**, and routes traces it cannot verify to a **human review
queue**. That is Kavach's fast set and its escalation path, arrived at from
the agent-tooling side rather than the operations side: the premise is the
same — *an agent saying it worked is not evidence it worked* — which is the
premise behind this project's false-healing metric. Its own benchmark is
described as synthetic, so the idea converges, not the evidence.

**`AgentLens`** keeps an **append-only, hash-chained event log** of LLM calls
and tool invocations, for post-incident forensics. Same mechanism as
`kavach/audit/log.py` and the same stated purpose. Worth knowing it also
inherits the tail-truncation property measured in §6: a hash chain detects
edits, not a deletion at the end.

**`yzhao062/awesome-auditable-ai`** is the curated list this project should
have found earlier — papers, tools, benchmarks and standards for *auditing*
agents, covering reliability, monitoring, **failure attribution** and
**decision records**. It is the closest thing to a map of the field Kavach
actually sits in, and a better starting point for future related-work passes
than searching "self-healing".

### Our fault-injection choice, defended from outside

The survey of chaos tooling matters because `PRD.md` §6 picks Toxiproxy and a
reviewer may ask why not Chaos Mesh or LitmusChaos, which are the two CNCF
options every roundup leads with.

The answer the sources give is scope, and it favours our choice. **Chaos Mesh
and LitmusChaos are Kubernetes-native** — pod kills, network chaos, IO chaos,
time skew, experiments defined as Kubernetes custom resources. Kavach's target
is a Docker Compose application with no Kubernetes anywhere, so most of what
those platforms do has nothing to act on here. One comparison puts the split
plainly: Chaos Mesh when Kubernetes topology is part of what you are
validating, **Toxiproxy for in-test, single-connection faults**, and another
recommends Toxiproxy specifically as the starting point for CI-pipeline fault
injection. F01 is exactly a single-connection fault.

**`Chaos Toolkit` is the one worth a future look**, and not as a replacement:
it is Python, it integrates *with* Toxiproxy, and it also speaks Prometheus
and OpenTelemetry — the two things Kavach already runs on. It would be a way
to express the injection catalogue declaratively rather than as four Python
injectors, *after* the deadline and only if a fifth fault class makes the
current approach feel cramped. **Not a change to make now:** `inject.py` is
working, measured, and the thing every number in §4 was produced with.

**`ChaosBlade`** (host and container level, CLI-first) and **`Pumba`** (Docker,
containerd, Podman) are the nearest non-Kubernetes alternatives if Toxiproxy
ever stops fitting. Pumba is the closer match to our runtime.

### LLM observability, and why none of it is adopted

`Langfuse`, `Opik` (Apache-2.0, self-hostable), `LangWatch` and Arize
`Phoenix` all trace LLM calls with evaluation attached. Kavach records its own
LLM calls already — model, latency, tokens, the class claimed and the
validator's verdict, visible on the observability page and in
`/v1/llm-calls`.

**Not adopted, for the reason §4.4 gives.** Those platforms centre on
*evaluating the model*, usually with an LLM judge. `FR-07b` forbids a judge
anywhere in the recovery path, because a nondeterministic verification step
cannot be the thing that decides whether a repair worked. What Kavach needs
from a trace is already in the audit log, which is hash-chained and whose
integrity is checkable — a property none of these advertise. One note on
licensing if this is ever revisited: Phoenix is **Elastic License 2.0**,
source-available rather than OSI-approved, which matters for an academic
artifact.

**`Latitude`** is the interesting outlier: it groups agent failures from
production traces and hands them to a coding agent to fix. That is the
closest thing in this list to self-healing applied to the agent itself rather
than to a workload, and it is a reasonable "where this goes next" citation for
§9 rather than a dependency.

### What this pass changed

1. **The convergence claim extends to the two pieces we thought were ours.**
   `RELATED_WORK.md` §6b said the verdict vocabulary was converging while the
   closed loop was not; `agent-claimcheck` and `AgentLens` are evidence that
   claim-verification and hash-chained audit are converging too. That is worth
   saying before a reviewer says it.
2. **The Toxiproxy choice has an external defence** rather than only an
   internal one.
3. **One curated list worth reading properly** — `awesome-auditable-ai` — which
   is a better map of this field than any search phrased around self-healing.
4. **Still nothing adopted**, and nothing should be before the deadline.
