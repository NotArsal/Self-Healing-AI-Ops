# Experiment: Kavach on a 64× larger corpus

**Date:** 2026-11-18/19 (UTC 18:38 – 23:41 on 2026-11-18)
**Status:** Complete. The target was restored to the paper's corpus afterwards and `make check` passed on it.
**Scope:** A separate robustness experiment, chosen by the owner on 2026-11-19 over making the larger
corpus official. **No number in `REPORT_DRAFT.md` changes.** Those were measured on the paper's
corpus (30 chunks / 2 files) and remain valid.

## Question

Does Kavach still detect, diagnose and heal correctly when the target's document store is much
larger and mostly unrelated to the fast-verification questions? And how well does the target itself
answer from the new documents?

## Setup

| | Paper corpus | Experiment corpus |
|---|---|---|
| Files | `919.pdf`, `1662.pdf` | the same two, plus `swe_at_google.pdf` (*Software Engineering at Google*) and `belonging_sonia_gandhi.pdf` (*Belonging*, Sonia Gandhi) |
| Chunks | 30 | **1,909** (+987, +892) |

- **Loading:** both books went through the target's own `POST /v1/upload`, the same path a user
  would take (about 40 s each).
- **Backup:** the target database was backed up first (`EDI/dox-extra/ragdb-before-books.dump`).
- **Baseline:** a fresh baseline was captured on the larger corpus. The target manifest's corpus
  fingerprint was set to 1909/4 only for that capture, then restored with `git checkout`. The
  capture reported no problems.
- **Bench:** `make bench`'s own code, `harness/report.py --reps 2 --expect-corpus 1909,4`.
  - The new flag still refuses any corpus but the one stated.
  - It writes to its own file and cannot overwrite the paper's `bench.json`.
- **Same as the paper's run:** model `openai/gpt-oss-120b` via Groq, APPROVAL mode, the same
  5 classes, paced under the 5-starts-an-hour limit ("Nothing is being reset"). The bench took
  4 h 15 min.

## Result 1: Kavach is unaffected

Reference: `bench-20261112-all-parallel.json`, the most recent full bench on the paper's corpus
with the same model and the same parallel detection (ADR 0026).

| | Paper corpus (25 runs) | Larger corpus (10 runs) |
|---|---|---|
| Healed | 24 / 25 | **10 / 10** |
| Fault class right (LLM's own answer) | 24 / 25 | **10 / 10** |
| False healing | 0 | **0** |
| Target clean after run | 25 / 25 | **10 / 10** |
| MTTD, median | 40.7 s | **40.8 s** |
| MTTR, median | 70.2 s | **76.2 s** |

Per class (medians; the larger corpus has n = 2 per class):

| Class | MTTD paper | MTTD larger | MTTR paper | MTTR larger |
|---|---|---|---|---|
| F01 endpoint outage | 40.7 s | 40.8 s | 70.1 s | 76.2 s |
| F02 latency | 323.0 s | 330.0 s | 437.2 s | 447.5 s |
| F06 retrieval collapse | 59.9 s | 54.2 s | 94.8 s | 94.7 s |
| F07 prompt regression | 13.0 s | 14.0 s | 53.2 s | 56.3 s |
| F08 config regression | 11.5 s | 13.1 s | 48.6 s | 54.7 s |

**Reading:** on a 64× larger corpus, every figure is within run-to-run noise of the paper's.
- F06 matters most here, because retrieval collapse is the class most exposed to the corpus. Its
  detection does not depend on corpus size: kept-chunks falls to zero while raw similarity stays
  healthy.
- F02's slow detection (~5.5 min) is **not** a corpus effect: it is the same on the paper's
  corpus. It is the latency SLO's window.

## Result 2: the target's own answers (8 of 13)

`harness/corpus_answers.py`, ground truth copied from each book's extracted text before the run. A
case passes only if the answer is not a refusal, contains the fact, and cites the right file.

| Question | Result |
|---|---|
| Hyrum's Law; Beyoncé Rule; what TAP stands for; LGTM; Piper; Sonia Gandhi's parents; where she met Rajiv Gandhi | pass |
| Control: LSTM ROC-AUC (original corpus) | pass, cites `1662.pdf` |
| "Beyonce Rule", **without the accent** | **fail**: "I don't know"; the same question with "é" passes |
| What the Varsity in Cambridge was | **fail**: "I don't know" |
| The town Sonia Gandhi's family lived in (Orbassano) | **fail**: right book cited, answer too vague ("a small town in northern Italy") |
| The province Orbassano is in (Torino) | **fail**: answered "Piemonte", which is the region |
| How the book defines software engineering | **fail as scored**: the answer, "multiperson development of multiversion programs", is a definition the book also quotes. It is grounded and correct, but not the expected one. Counted as a fail, because the scoring was fixed before the run. |

These are properties of the **target's** RAG pipeline, which Kavach does not change: retrieval is
sensitive to one accented letter, and the small answer model drops detail. They are not Kavach
faults.

## A bug this experiment found

The first bench attempt failed its first heal. The bench saw `AWAITING_APPROVAL` and approved within
3 s, and got **409**. The worker stored the status before it had parked the plan and freed the run
slot, and the hypotheses writes added on 2026-11-18 had widened that gap. The run was stopped after
one injection, the fault was confirmed reverted, and the stray plan was rejected with a reason.

The fix was tested first (`tests/test_park_race.py`) and committed as `e590eb5`. The bench was then
re-run from the start. The aborted log is kept as `bench-corpus-1909x4-aborted-approve-race.log`.

## Limits

- **n = 2 per class** (10 runs), against 25 in the reference. Enough to see that nothing broke,
  not enough to claim the rates are equal.
- **The fast verification set still asks about the original two documents.** Verification
  therefore shows that the original knowledge still answers; it does not measure answer quality on
  the new books. Result 2 measures that, separately.
- **Every fault is injected on `backend`.** A larger corpus does not change that 1-way
  localisation.
- **One model, one run of the answer test.**

## Restoration

- Book chunks deleted (1,879 rows); the target reads 30 chunks / 2 files again.
- The uploaded copies were removed.
- The experiment baseline was moved out of `harness/baselines/` to
  `EDI/dox-extra/baseline-corpus-1909x4.json`, so the paper's baseline is current again.
- The fast set passed on the restored corpus, and `make check` passed (829 + 143), including the
  sandbox test that seeds 30 rows.
- The books themselves stay in `EDI/dox-extra/`, outside both repositories.

## Artifacts

Committed: `harness/reports/bench-corpus-1909x4.json` and `.log`,
`bench-corpus-1909x4-aborted-approve-race.log`, `corpus-answers-1909x4.json`, and
`harness/corpus_answers.py`.

Kept locally and not committed: `EDI/dox-extra/baseline-corpus-1909x4.json`, beside the books. Baselines stay out
of git by the project's rule ("measurements of a particular moment, not source"), and this one
also holds the full text of the target's prompt files.
