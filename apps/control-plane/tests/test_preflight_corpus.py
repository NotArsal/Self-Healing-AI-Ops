"""The corpus fingerprint check, which `PRD.md` §12 carried to P6 unbuilt.

The fingerprint sat in `fast_set.yaml` and nothing asserted it. The corpus
drifted three times - 162/3, 13/1, 0/0 - and the system whose job is noticing
failures noticed none of them.

What is pinned here is the thing that makes it matter rather than cosmetic:
the fast set is the post-repair verification the loop runs before it may
return RESOLVED, so on the wrong corpus it fails on a HEALTHY system and a
correct repair still ends in `escalated`. A check that passed when the corpus
was wrong would therefore be worse than no check at all.
"""

from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import yaml

from kavach.config import get_settings
from kavach.onboarding.manifest import load
from kavach.onboarding.preflight import check_corpus_fingerprint

ROOT = Path(__file__).resolve().parents[3]
# Derived, never a literal - see the 2026-11-01 fix that removed one
# maintainer's absolute path from three places.
TARGET_MANIFEST = Path(get_settings().target_path) / "kavach.yaml"

pytestmark = pytest.mark.target_repo


def _prometheus(chunks: float | None, files: float | None) -> Any:
    """A fake Prometheus answering the two corpus queries.

    None means "query valid, no series" - the case that is indistinguishable
    from healthy if you only check for an exception, and the reason
    check_slo_expressions treats an empty result as a failure too.
    """
    def fake(url: str | Any, timeout: int = 0) -> Any:
        target = url if isinstance(url, str) else url.full_url
        value = chunks if "chunks" in target else files
        result = ([] if value is None
                  else [{"metric": {}, "value": [0, str(value)]}])
        body = json.dumps({"status": "success", "data": {"result": result}})

        class _Resp(io.StringIO):
            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *a: object) -> None:
                return None

        return _Resp(body)
    return fake


@pytest.fixture
def manifest() -> Any:
    if not TARGET_MANIFEST.is_file():
        pytest.skip(f"target repository not present: {TARGET_MANIFEST}")
    return load(TARGET_MANIFEST)


@pytest.fixture
def expected() -> tuple[int, int]:
    """Read from the set itself, never re-typed - a constant here could drift
    from the file the check actually reads, which is the whole failure mode."""
    path = ROOT / "apps/control-plane/kavach/verification/fast_set.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    fp = doc["budget"]["corpus_fingerprint"]
    return int(fp["chunks"]), len(fp["files"])


def test_the_matching_corpus_passes(
    manifest: Any, expected: tuple[int, int], monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks, files = expected
    monkeypatch.setattr(urllib.request, "urlopen", _prometheus(chunks, files))
    r = check_corpus_fingerprint(manifest, ROOT, "http://prom:9090")
    assert r.passed, r.detail
    assert str(chunks) in r.detail


def test_the_13_1_corpus_that_shipped_a_false_escalation_fails(
    manifest: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real 2026-10-16 state: the database was reset and 1662.pdf was
    gone. fv-01 retrieved zero chunks and no F06 cycle could return RESOLVED,
    while every component was behaving correctly."""
    monkeypatch.setattr(urllib.request, "urlopen", _prometheus(13, 1))
    r = check_corpus_fingerprint(manifest, ROOT, "http://prom:9090")
    assert not r.passed
    assert "13 chunks / 1 files" in r.detail
    assert "re-ingest" in r.remediation


def test_an_extra_document_fails_too(
    manifest: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-10-04: 162/3, a syllabus PDF had been ADDED. Drift in the
    generous direction is still drift - the fast set's latencies and the
    retrieval thresholds were all measured on 30/2."""
    monkeypatch.setattr(urllib.request, "urlopen", _prometheus(162, 3))
    r = check_corpus_fingerprint(manifest, ROOT, "http://prom:9090")
    assert not r.passed


def test_the_empty_corpus_fails(
    manifest: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-11-01, after the machine was reformatted."""
    monkeypatch.setattr(urllib.request, "urlopen", _prometheus(0, 0))
    r = check_corpus_fingerprint(manifest, ROOT, "http://prom:9090")
    assert not r.passed


def test_a_metric_nobody_exports_is_a_failure_not_a_pass(
    manifest: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty query result is indistinguishable from healthy if you only
    catch exceptions. check_slo_expressions exists because of that exact
    mistake, so this check must not repeat it."""
    monkeypatch.setattr(urllib.request, "urlopen", _prometheus(None, None))
    r = check_corpus_fingerprint(manifest, ROOT, "http://prom:9090")
    assert not r.passed
    assert "no series" in r.detail


def test_prometheus_being_unreachable_is_a_failure_not_a_pass(
    manifest: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(url: Any, timeout: int = 0) -> Any:
        raise OSError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    r = check_corpus_fingerprint(manifest, ROOT, "http://prom:9090")
    assert not r.passed
    assert "connection refused" in r.detail


def test_the_check_reads_the_live_set_not_a_constant(
    expected: tuple[int, int],
) -> None:
    """If someone edits fast_set.yaml's fingerprint, the check must follow it.
    A hardcoded 30/2 here would pass while the real set expected something
    else - the same class of bug as `RCA accuracy` reading the wrong field."""
    chunks, files = expected
    assert (chunks, files) == (30, 2), (
        "the fast set's fingerprint changed; that is allowed, but the report's "
        "quality numbers were all measured on 30 chunks / 2 files and must be "
        "re-measured before this constant is updated")
