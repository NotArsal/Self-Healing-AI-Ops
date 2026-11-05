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
