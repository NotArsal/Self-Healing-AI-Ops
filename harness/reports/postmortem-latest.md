# Incident INC-191650 — RESOLVED

*simple-rag, detected 2026-10-18T19:16:50+00:00*

## What happened

resolved: rollback_config applied {'rerank_threshold': 0.999} -> {'rerank_threshold': 0.35}

## Timeline

| stage | at | detail |
|---|---|---|
| permit | 2026-10-18T19:17:29+00:00 | — |
| execute_start | 2026-10-18T19:17:29.749+00:00 | — |
| execute_done | 2026-10-18T19:17:29.764+00:00 | — |
| resolved | 2026-10-18T19:17:54.265+00:00 | — |

**Detected to resolved:** 64.0s

## What the evidence said

- Detector verdict: **FAULT**
- Fault class: **F06** on **backend**
- Diagnosed by: **llm_rca**
- Model (qwen2.5:7b-instruct): **F06** at confidence 0.95, citing EV-M02, EV-M03, EV-C08
- Agrees with the deterministic detector: **yes**
- Validator accepted: **yes**

> EV-M02 shows retrieval_kept_chunks_mean = 0.0 (healthy: >= 1.0), and EV-M03 shows retrieval_empty_context_ratio = 1.0 (healthy: < 0.20). These values indicate that the retrieval process is not providing any chunks to the context, which is consistent with F06. EV-C08 shows prompt_file_hashes = {'answer.txt': 'd55c73a23f33', 'query_expansion.txt': 'bbc6a7fee760'}, which differs from its baseline, indicating a change in the prompt files. This change, combined with the loss of grounding, suggests that the rerank filter is discarding the retrieved chunks, leading to answers with no grounding.

## What the gate decided

- Verdict: **ALLOW_AUTO** (risk MEDIUM, mode APPROVAL)

## What was written

- Action: **rollback_config** (risk MEDIUM)
- Requested: `{'rerank_threshold': 0.35}`
- Inverse held: `{'rerank_threshold': 0.999}`
- Executed: **yes**, reverted: **no**

## Did it work

- Fast set before: **0% (fail)**
- Fast set after: **100% (pass)**
- Verification took 24.4s against a 120s budget
- Corpus unchanged: **yes** (30 → 30 chunks)

## Audit chain

- No audit log was supplied, so integrity is **not claimed** here.

---

*Written by Kavach from its own audit record. Every figure above was recorded during the incident; none was recomputed afterwards.*