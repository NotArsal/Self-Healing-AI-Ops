# The corpus every number in this project was measured on

The two PDFs below are **not in this repository** and are not redistributed
with it. What is tracked here is enough to prove that a given pair of files is
the right pair: their SHA-256 digests, in `checksums.sha256`.

| file | bytes | sha256 (abbrev) |
|---|---:|---|
| `919.pdf` | 4,239,563 | `b896d03a…cef68` |
| `1662.pdf` | 472,381 | `10a332a0…32850` |

Ingested, these two produce the fingerprint the whole verification layer is
pinned to: **30 chunks / 2 files** — 13 chunks from `919.pdf`, 17 from
`1662.pdf`. That pair of numbers is declared in
`apps/control-plane/kavach/verification/fast_set.yaml` under
`budget.corpus_fingerprint` and asserted by `check_corpus_fingerprint`.

## Why this file exists

The fast set is the post-repair verification the loop runs before it may
return `RESOLVED`. Every one of its cases reads from these two documents.

On the **wrong** corpus the fast set fails on a *healthy* system, so a correct
detection and a correct repair still end in `escalated`. That is not
hypothetical — it was observed on 2026-10-16, when the target's database had
been reset and `1662.pdf` was gone (13 chunks / 1 file). The corpus has
drifted three times: 162/3 on 2026-10-04, 13/1 on 2026-10-16, and 0/0 on
2026-11-01 after the machine was reformatted.

So losing these two files does not merely cost a re-download. It costs:

- **reproducibility** — every quality figure in `docs/REPORT_DRAFT.md` (MTTD,
  MTTR, RCA accuracy, the F06 self-consistency result) was measured on 30/2
  and is not comparable against any other corpus;
- **the demo** — a mismatched corpus makes Kavach escalate correct repairs,
  which looks like a Kavach defect rather than a data problem.

## Provenance

<!-- TODO(arsal): fill this in. Where did 919.pdf and 1662.pdf come from, and
     under what licence? This is the one thing in here nobody else can
     reconstruct, and it is the reason the files are not committed. -->

**Not yet recorded.** The files were excluded from git on the assumption that
they may not be redistributable; if that turns out to be wrong, committing
them outright is strictly better than this file.

## Where the originals live

- **Working copy:** `<repo>/../dox/` (i.e. beside this repository, not inside
  it). This is what `KAVACH_CORPUS_DIR` defaults to.
- **Backup:** <!-- TODO(arsal): paste the Drive/OneDrive link here once
  uploaded. Until this line is filled in, the files exist on exactly one
  disk and this document is a description of a risk rather than a mitigation. -->
  **not yet created.**

## Restoring the corpus from scratch

1. Put both PDFs in a directory, e.g. `../dox/`.
2. Verify they are the right files — this is the step the digests exist for:

   ```bash
   cd ../dox && sha256sum -c "<repo>/corpus/checksums.sha256"
   ```

   Both lines must say `OK`. A `FAILED` line means the file is not the one the
   measurements were taken on; re-ingesting it will silently change every
   number in the report.

3. Bring the target up (`make up`) and upload both to the target backend:

   ```bash
   curl -F "files=@919.pdf" -F "files=@1662.pdf" \
        http://localhost:8000/api/v1/upload
   ```

4. Confirm the fingerprint landed, rather than trusting the upload:

   ```bash
   curl -s "http://localhost:9091/api/v1/query?query=ragapp_corpus_chunks"
   curl -s "http://localhost:9091/api/v1/query?query=ragapp_corpus_files"
   ```

   These must read `30` and `2`. Anything else and the fast set will fail on a
   healthy system.

`tests/test_corpus_checksums.py` runs step 2 automatically whenever the
corpus directory is present, so an accidental swap is caught by `make check`
rather than by a confusing escalation eight hours into a bench run.
