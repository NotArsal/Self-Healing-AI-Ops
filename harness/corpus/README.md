# The corpus every quality number is measured on

**The two PDFs themselves are NOT in this repository**, and that is the problem
this file exists to make visible rather than to solve.

They were uploaded to the target through `POST /v1/upload` and lived in exactly
two places: the target's Postgres volume (`target_rag-app_pgdata`) and its
`uploads/` directory, which is gitignored there. On 2026-11-01 a service centre
formatted the machine's SSD; the volume went with it and the repository
restored intact without them. They were recovered from a copy outside both
repositories, which is luck, not a process.

## What the corpus must be

`kavach/verification/fast_set.yaml` pins the fingerprint, and
`onboarding/preflight.py::check_corpus_fingerprint` now asserts it:

| | |
|---|---|
| chunks | **30** |
| files | **2** |

| file | chunks | SHA-256 | bytes |
|---|---|---|---|
| `919.pdf` | 13 (ids 1-13) | `b896d03a934249aa8bd34f825d902bfce505e4a86234f1050aa0cc951b2cef68` | 4,239,563 |
| `1662.pdf` | 17 (ids 14-30) | `10a332a0a08d9456568dbc509357fc88952cd8d5ee15df3e342696114d632850` | 472,381 |

Ingest order matters only for the chunk ids, not the fingerprint: `919.pdf`
first, then `1662.pdf`, reproduces the ids recorded above.

## Verifying a candidate file is the right one

```
sha256sum 919.pdf 1662.pdf
```

A matching digest is proof. A matching *filename* is not — the names are
submission ids and say nothing about content.

## Restoring the corpus

With the target running and the embedding model warm:

```
curl -X POST http://localhost:8000/v1/upload -F "files=@919.pdf"
curl -X POST http://localhost:8000/v1/upload -F "files=@1662.pdf"
```

Then confirm, and do not skip this:

```
curl -s http://localhost:8000/metrics | grep ragapp_corpus
```

It must read `ragapp_corpus_chunks 30` and `ragapp_corpus_files 2`.

**Warm the model first.** A cold `nomic-embed-text` takes ~13s for its first
embedding against the backend's 30s read timeout, and the upload of the larger
file times out. One throwaway embedding is enough:

```
curl -s http://localhost:11434/api/embeddings -d '{"model":"nomic-embed-text","prompt":"warm"}' -o /dev/null
```

## Why the fingerprint is not cosmetic

Every fast-set case reads from these two documents, and the fast set is the
**post-repair verification the loop runs before it may return `RESOLVED`** — as
well as the independent check the bench scores false healing with. On the wrong
corpus it FAILS on a healthy system, so a correct detection and a correct
repair still end in `escalated`.

That is not hypothetical. `PRD.md` §12 records 2026-10-16: the corpus had
drifted to 13 chunks / 1 file, `fv-01` retrieved zero chunks, and no F06 cycle
could return `RESOLVED`.

The corpus has now drifted three times — **162/3** (2026-10-04, a syllabus PDF
added), **13/1** (2026-10-16, database reset), **0/0** (2026-11-01, SSD
formatted) — and nothing caught any of them, because the fingerprint was
written down and never asserted. `RESEARCH_NOTES.md` §12 has the full account.

## Still not solved

Recording a checksum does not restore a file. If both PDFs are lost again,
this directory tells you precisely what you have lost and lets you verify a
recovered candidate — it does not bring them back. Putting the documents under
version control, or in any backup that is not one laptop, is a decision for
the team and has not been taken.
