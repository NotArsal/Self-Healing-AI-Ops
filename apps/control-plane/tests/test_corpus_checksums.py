"""The source documents must be the ones every measurement was taken on.

`check_corpus_fingerprint` asserts the corpus AFTER ingestion, by reading
`ragapp_corpus_chunks` and `ragapp_corpus_files` out of Prometheus. That
catches drift in the database, which is where the corpus drifted all three
times it drifted.

It cannot catch the case upstream of it: a file in the corpus directory that
has the right NAME and the wrong BYTES. 30 chunks / 2 files is not a unique
fingerprint - a different 919.pdf that happens to chunk to 13 would satisfy
the live check exactly, and every number in the report would then describe a
corpus nobody can identify.

The digests live in `corpus/checksums.sha256`; see `corpus/README.md` for why
the PDFs themselves are not in this repository.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CHECKSUMS = ROOT / "corpus" / "checksums.sha256"


def corpus_dir() -> Path:
    """Derived, never a literal - see the 2026-11-01 fix that removed one
    maintainer's absolute path from three places. The default is a sibling of
    the repository rather than something inside it, because the files are
    deliberately not tracked."""
    env = os.environ.get("KAVACH_CORPUS_DIR")
    return Path(env) if env else ROOT.parent / "dox"


def parse(text: str) -> dict[str, str]:
    """`sha256sum` format: digest, a space, a mode flag, then the name."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition(" ")
        out[name.lstrip("*").strip()] = digest
    return out


@pytest.fixture
def expected() -> dict[str, str]:
    if not CHECKSUMS.is_file():
        pytest.fail(f"the digests are tracked in git and must exist: "
                    f"{CHECKSUMS}")
    digests = parse(CHECKSUMS.read_text(encoding="utf-8"))
    assert digests, f"no digests parsed out of {CHECKSUMS}"
    return digests


def test_the_digests_cover_exactly_the_fast_sets_two_files(
    expected: dict[str, str],
) -> None:
    """A digest list that has drifted from the fingerprint's file list would
    verify the wrong documents and report success. This is the same failure
    mode as a hardcoded constant in `test_preflight_corpus.py`, so it is
    guarded the same way: read the live set, never re-type it."""
    import yaml

    path = ROOT / "apps/control-plane/kavach/verification/fast_set.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    files = doc["budget"]["corpus_fingerprint"]["files"]
    assert sorted(expected) == sorted(files), (
        "corpus/checksums.sha256 and fast_set.yaml disagree about which "
        "documents the corpus contains")


def test_the_corpus_on_disk_is_the_corpus_that_was_measured(
    expected: dict[str, str],
) -> None:
    """Skipped when the corpus is absent - it is not in the repository, so CI
    and a fresh clone legitimately do not have it. Present, it must match:
    a file with the right name and the wrong bytes is the one corruption the
    live fingerprint check cannot see."""
    where = corpus_dir()
    if not where.is_dir():
        pytest.skip(f"corpus directory not present: {where} "
                    f"(set KAVACH_CORPUS_DIR to point at it)")

    missing = [n for n in expected if not (where / n).is_file()]
    if missing:
        pytest.skip(f"corpus directory {where} is missing {missing}; "
                    f"nothing to verify")

    for name, want in sorted(expected.items()):
        got = hashlib.sha256((where / name).read_bytes()).hexdigest()
        assert got == want, (
            f"{name} is not the document the measurements were taken on.\n"
            f"  expected {want}\n  found    {got}\n"
            f"Ingesting this file would silently change every quality number "
            f"in docs/REPORT_DRAFT.md. See corpus/README.md.")


def test_no_document_has_been_added_to_the_corpus_directory(
    expected: dict[str, str],
) -> None:
    """An ADDED file is drift too, and the first version of this file missed it.

    The checks above iterate over the two EXPECTED documents, so a third PDF
    dropped into the directory satisfied every one of them and the suite stayed
    green - which is exactly the 2026-10-04 incident, where a syllabus PDF was
    added and the corpus went to 162 chunks / 3 files. `test_an_extra_document_
    fails_too` in `test_preflight_corpus.py` guards that for the LIVE corpus;
    nothing guarded it for the directory people re-ingest FROM.

    Found 2026-11-02 when a 9.6 MB book was put in the corpus directory. The
    live corpus was untouched, so nothing broke - but `corpus/README.md`'s
    restore procedure uploads from this directory, and the next person to
    follow it loosely would have ingested all three and spent an afternoon
    wondering why a healthy system fails its own verification.
    """
    where = corpus_dir()
    if not where.is_dir():
        pytest.skip(f"corpus directory not present: {where}")

    found = {p.name for p in where.iterdir()
             if p.is_file() and p.suffix.lower() == ".pdf"}
    extra = sorted(found - set(expected))
    assert not extra, (
        f"unexpected document(s) in the corpus directory {where}: {extra}.\n"
        f"The fingerprint every measurement in this project rests on is "
        f"30 chunks / 2 files ({sorted(expected)}). Re-ingesting this "
        f"directory as it stands would break it, and the fast set then fails "
        f"on a HEALTHY system - so a correct detection and a correct repair "
        f"still end in `escalated`.\n"
        f"Either move the file out of this directory, or - if it is genuinely "
        f"meant to join the corpus - add it to corpus/checksums.sha256, update "
        f"budget.corpus_fingerprint in fast_set.yaml, and RE-MEASURE every "
        f"quality number in docs/REPORT_DRAFT.md. They are not comparable "
        f"across corpora.")
