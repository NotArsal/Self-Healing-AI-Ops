"""One corpus, seven places that state its size, and nothing checking they agree.

ADDED 2026-11-05.

The target's manifest declares the fingerprint, and says what it is for:
*"Captured at onboarding; this records what a baseline must contain."* Six
other places restate it, each for its own good reason, and none of them reads
the manifest:

  `kavach/verification/fast_set.yaml`  `budget.corpus_fingerprint`
  `kavach/rca/evidence.py`             `HEALTHY_EXPECTATION`, prompt text
  `harness/report.py`                  `EXPECTED_CORPUS`
  `harness/scenario.py`                `EXPECTED_CORPUS`
  `harness/human_baseline.py`          `EXPECTED_CORPUS`
  `harness/runbook_baseline.py`        `EXPECTED_CORPUS`

Add a third document to the corpus, or re-chunk the two that are there, and
six edits have to land together. The one that matters most is the quietest:
`HEALTHY_EXPECTATION` is **prompt text the model reads**, so a stale value
there does not fail a check, it tells the model the healthy corpus is 30
chunks when it is not — and `corpus_chunks` is one of the signals F06's
diagnosis turns on. The harness copies would at least fail loudly; that one
would produce a confidently wrong diagnosis.

This is the fourth instance of one shape found this week - a fact enforced in
one place and copied without a link into others - after the baseline health
flag, the fast set's refusal vocabulary, and the service addresses that were
right on the host and wrong in the container.

Marked `target_repo` because the manifest lives in the target's repository,
which is deliberately not part of this one, and skipped when it is absent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from kavach.config import get_settings

ROOT = Path(__file__).resolve().parents[3]
FAST_SET = ROOT / "apps/control-plane/kavach/verification/fast_set.yaml"
EVIDENCE = ROOT / "apps/control-plane/kavach/rca/evidence.py"
HARNESS = [ROOT / "harness" / n for n in
           ("report.py", "scenario.py", "human_baseline.py",
            "runbook_baseline.py")]

pytestmark = pytest.mark.target_repo


def manifest_fingerprint() -> tuple[int, list[str]]:
    path = Path(get_settings().target_path) / "kavach.yaml"
    if not path.is_file():
        pytest.skip(f"target manifest not readable at {path}")
    doc: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    for section in doc.values():
        if isinstance(section, dict) and "corpus_fingerprint" in section:
            fp = section["corpus_fingerprint"]
            return int(fp["chunks"]), [str(f) for f in fp["files"]]
    pytest.skip("the manifest declares no corpus_fingerprint")


def test_the_manifest_declares_a_fingerprint_to_check_against() -> None:
    """A guard on the guard: a skip here is honest, a silent pass is not."""
    chunks, files = manifest_fingerprint()
    assert chunks > 0 and files, "the manifest's fingerprint is empty"


def test_the_fast_set_agrees_with_the_manifest() -> None:
    chunks, files = manifest_fingerprint()
    doc: dict[str, Any] = yaml.safe_load(FAST_SET.read_text(encoding="utf-8"))
    fp = (doc.get("budget") or {}).get("corpus_fingerprint") or {}
    assert int(fp.get("chunks", -1)) == chunks, (
        f"fast_set.yaml says {fp.get('chunks')} chunks, the manifest says "
        f"{chunks}. The set guards against corpus drift and has drifted.")
    assert [str(f) for f in fp.get("files", [])] == files


@pytest.mark.parametrize("path", HARNESS, ids=lambda p: p.name)
def test_a_harness_expectation_agrees_with_the_manifest(path: Path) -> None:
    chunks, files = manifest_fingerprint()
    text = path.read_text(encoding="utf-8")
    found = re.search(
        r'EXPECTED_CORPUS\s*=\s*\{[^}]*"chunks":\s*([0-9.]+)[^}]*'
        r'"files":\s*([0-9.]+)', text)
    assert found, f"{path.name} no longer declares EXPECTED_CORPUS as expected"
    assert float(found.group(1)) == float(chunks), (
        f"{path.name} expects {found.group(1)} chunks, the manifest declares "
        f"{chunks}; this harness would refuse to run against the real corpus")
    assert float(found.group(2)) == float(len(files)), (
        f"{path.name} expects {found.group(2)} files, the manifest declares "
        f"{len(files)}")


def test_the_prompt_text_the_model_reads_agrees_with_the_manifest() -> None:
    """The quiet one. `HEALTHY_EXPECTATION` is not a check - it is the
    sentence describing a healthy corpus inside the evidence frame. A stale
    number here does not fail anything; it tells the model the wrong baseline
    for a signal F06 turns on."""
    chunks, files = manifest_fingerprint()
    text = EVIDENCE.read_text(encoding="utf-8")

    said = re.search(r'"corpus_chunks":\s*"([0-9]+)', text)
    assert said, "HEALTHY_EXPECTATION no longer states corpus_chunks"
    assert int(said.group(1)) == chunks, (
        f"the evidence frame tells the model a healthy corpus is "
        f"{said.group(1)} chunks; the manifest declares {chunks}. This is "
        f"prompt text, so it fails nothing and misleads the diagnosis.")

    said_files = re.search(r'"corpus_files":\s*"([0-9]+)', text)
    assert said_files, "HEALTHY_EXPECTATION no longer states corpus_files"
    assert int(said_files.group(1)) == len(files)
    for name in files:
        assert name in text, (
            f"the evidence frame names the corpus files and does not mention "
            f"{name!r}, which the manifest declares")
