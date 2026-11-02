# The second target: LightRAG, onboarded 2026-11-03

`REPORT_DRAFT.md` §6 names "one workload" as the project's top threat to
validity, and §8.3 states that Kavach's architecture is convergent with
published systems. A second application tests both claims. This document
records what was done, what passed, and the one thing that did not — which
turned out to be worth more than the onboarding.

**Status: detection onboarded, 16 of 17 preflight checks passing. Repair NOT
wired. The target is currently stopped, deliberately — see §5.**

---

## 1. Why LightRAG, and why not the other candidate

Two apps were assessed against the four implemented fault classes.

| | `danny-avila/rag_api` | **LightRAG (HKUDS)** |
|---|---|---|
| F01 LLM endpoint outage | ✗ no LLM call exists | ✓ generates |
| F06 retrieval collapse | ✓ | ✓ **graph + vector, not plain vector** |
| F07 prompt regression | ✗ no prompt file | ✓ `lightrag/prompt.py`, 900 lines |
| F08 config regression | ✓ | ✓ |
| local model, no cloud key (`PL-02`) | n/a | ✓ `lightrag/llm/ollama.py` |
| compose footprint | 2 services | 1 service |

`rag_api` is the *retrieval half* of LibreChat — `/embed`, `/query`,
`/documents`, no generation — so it exercises 2 of 4 classes. It was dropped.
An earlier note in this project claimed it would cover all four; that was
wrong, and the error was reading "RAG API" as a full pipeline.

LightRAG was chosen for the reason that makes a second target worth having:
**its retrieval architecture is different by construction.** It builds a
knowledge graph and queries it alongside a vector index. The embedding model
is held *constant* between the two targets (`nomic-embed-text`) on purpose, so
any difference in F06 behaviour is attributable to the retrieval architecture
rather than to a different embedding space.

---

## 2. How it was instrumented, and why not with an adapter

Kavach never inspects an application directly. It reads Prometheus series with
exact names and compares a live config against a baseline through an admin
endpoint. LightRAG published neither — `/metrics` was a 404 against the first
target's 88 `ragapp_*` lines.

Three routes were considered:

| | verdict |
|---|---|
| Teach Kavach's detectors LightRAG's own metric names | **rejected** — edits the exact code every number in §4 was measured with |
| External adapter sidecar reading LightRAG's API | **rejected** — covers 8 of 10 metrics; cannot reach per-query similarity scores or pool gauges, which are internal |
| Instrument inside the app | **chosen** — same approach as the first target's `backend/telemetry.py` |

The useful general finding from that comparison: **the only contract metrics an
external adapter cannot produce are exactly the ones requiring internal state.**
Everything observable from outside is derivable from outside. For a target you
cannot modify, an adapter gets you F01, F07, F08 and two of F06's three
signals.

The fork is **one new module plus four call sites, 113 lines**, deliberately
shaped so each call site only hands numbers to a function. Commit `b83c286` on
branch `kavach/ops` in the clone.

### Three things that went wrong, each worth recording

**The first instrumentation point was wrong and recorded nothing.**
`ollama_model_complete` was wrapped on the reasoning that wrapping a thin
forwarder beats editing a 240-line function. It produced zero samples:
`lightrag_server.create_role_llm_func` builds its own `role_ollama_complete`
that calls the inner `_ollama_model_if_cache` **directly**, and those role
calls — the "query LLM func" and "keyword LLM func" in the logs — are most of
the traffic. Fixed by rebinding the inner function's module global to a
wrapper that calls the saved original, so both paths are covered and the risky
body is still untouched.

**Two label values were silently wrong.** The instrumentation first emitted
`operation="generate"` and, on failure, the exception class name. The first
target emits `operation="generation"` and `outcome` in `{ok, error}`, and the
manifest's `llm_error_ratio` SLO matches `outcome="error"` *literally* while
the F01 detector matches `outcome!="ok"`. So `outcome="ConnectionError"` would
have been counted by the detector and silently missed by the SLO. **Label
values are part of the contract, exactly like metric names and bucket
boundaries.**

**LightRAG cannot be built on a default Windows checkout.** The local build
died with `exec /usr/local/bin/docker-entrypoint.sh: no such file or
directory`. Cause: git with `core.autocrlf=true` checks the script out with
CRLF, so the shebang becomes `#!/bin/sh\r` and the kernel looks for an
interpreter with a carriage return in its name. The error blames the script,
not its line endings. Fixed with `sed -i 's/\r$//'` in the Dockerfile, a no-op
on Linux. **This is an upstream bug and worth reporting.**

---

## 3. What preflight says

16 of 17 checks pass: manifest, git hygiene, service health, Docker socket,
ownership, all five SLO expressions, and the fast set.

Two deliberate differences from the first target's manifest, both recorded in
it:

- **Only metrics this target actually exports are declared as SLOs.** The
  first target also declares `chat_latency_p95` and `chat_error_ratio` over
  `http_requests_total`, which it gets from
  prometheus-fastapi-instrumentator. LightRAG has no HTTP instrumentation, so
  those expressions would return an empty series — and `check_slo_expressions`
  treats empty as a **failure**, by design, because an expression matching
  nothing is indistinguishable from a healthy one. Declaring them would fail
  preflight for a true reason.
- **`llm_latency_p95` is 12.0s, not the first target's 4.0s.** Measured, not
  copied: one LightRAG query makes at least two sequential LLM calls (keyword
  extraction, then generation), measured at ~3.8s each on
  `qwen2.5:7b-instruct`. `retrieval_similarity_p50` was deliberately left at
  the first target's 0.50 — holding it constant across two retrieval
  architectures is the comparison this target exists to make.

The fast set's three cases were each **probed against the live healthy target
before being written**, along with five alternates; all eight passed and the
three with the most distinctive keywords were kept. Two findings from probing:

- The refusal markers are *observed*, not guessed.
- **`sources_block` is a much weaker check here.** The first target appends
  `**Sources:**` only if chunks were retrieved. LightRAG appends a
  `### References` section that tracks retrieval, not use: two out-of-corpus
  questions returned a refusal **with** a References block. It still
  discriminates retrieval collapse but not grounding, and the fast set says so.

---

## 4. The one failure, and it is a Kavach bug

```
FAIL  corpus matches the fast set's fingerprint
      live corpus is 30 chunks / 2 files, the fast set was built on 2 / 2
```

**30 / 2 is the first target's fingerprint.** With both targets running,
Prometheus correctly held two labelled series —

```
project=simple-rag   job=simple-rag-backend   ragapp_corpus_chunks = 30
project=lightrag     job=lightrag-target      ragapp_corpus_chunks = 2
```

— and `check_corpus_fingerprint` queried `ragapp_corpus_chunks` with **no
project selector**, then read `result[0]`. It got whichever series Prometheus
returned first.

This is not specific to the corpus check. Auditing every `ragapp_*` query in
the control plane: they filter on `operation` and `outcome`, and **not one
carries a `project` or `job` selector.** So:

> **Kavach as built supports exactly one target at a time.** Not because the
> manifest cannot describe a second — it can, and 16 of 17 checks pass — but
> because every PromQL query in the detectors and the evidence frame is
> ambiguous the moment a second application exports the same contract.

§6's claim that "the seams for a second exist" is therefore **half true**, and
this document is the measurement that says which half. The manifest,
ownership, git and SLO-validation seams are real. Detection, baseline capture
and evidence collection are not: 57 `ragapp_*` literals across 7 modules, all
unscoped.

### The fix, and why it was not applied

Add a `{project="<name>"}` selector to every query, sourced from the
manifest's `project.name`. The Prometheus labels already exist — the scrape
jobs set `project: simple-rag` and `project: lightrag`.

Not applied, for one reason: it edits the detectors that every number in §4
was measured with, including the `[2m]` and `[10m]` windows that ADR 0013 and
ADR 0010 fought over. Doing that days before a demo, to support a target that
is not in the locked scope, is the wrong trade. It is recorded as the concrete
next step instead.

---

## 5. The target is stopped, and that is a safety decision

`docker compose -p lightrag_target down`. It is **not** running, because the
scoping bug cuts both ways: while LightRAG is up, a Kavach detector reading
`ragapp_corpus_chunks` or `ragapp_llm_requests_total` can get **LightRAG's**
series instead of the first target's. That would corrupt a bench run or a demo
rehearsal in a way that looks like a control-plane fault.

The Prometheus scrape job stays in `infra/prometheus.yml`. It reads DOWN while
the target is stopped, which is harmless — no series, no ambiguity — and the
job carries a comment saying it is additive and safe to delete.

**To bring it back up:**

```bash
cd "D:/Vit/Academics Sem-5/EDI/targets/lightrag"
docker compose -p lightrag_target up -d
```

Do not do that during a bench run, a rehearsal, or the demo.

---

## 6. What is left

| | |
|---|---|
| project-scope every `ragapp_*` query (the real blocker) | ~1 day, touches detectors |
| `PUT /v1/admin/config` with an allow-list so repairs can execute | ~half a day |
| HTTP instrumentation, so `chat_*` SLOs can be declared | ~2 hours |
| Run F01/F06/F07/F08 against it and compare per-class accuracy | the actual experiment |

That last row is the point of the whole exercise and has not been done. Until
it is, this target demonstrates that **onboarding** generalises — a second
application, a different retrieval architecture, 16 of 17 checks — and says
nothing yet about whether **detection accuracy** generalises.
