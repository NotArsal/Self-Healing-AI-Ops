"""A fast set's refusal vocabulary must be the set's, and must still be read.

THE BUG THIS PINS, found 2026-11-03 by auditing which `fast_set.yaml` keys
the code actually reads.

`fast_set.yaml` has always declared `refusal_markers` and `sources_marker`.
`fast.py` ignored both and used module constants. For the first target that
is invisible: the constants were written from that set and kept in step by
hand, so the two say the same thing.

It stops being invisible with a second target. LightRAG refuses with
"I'm sorry, but the information you provided does not contain…" and marks
citations with "### References". Against the hardcoded values its
`non_refusal` check would have passed **on a refusal** - a verification set
reporting success on a broken answer, which is the failure mode this project
cares most about - and its `sources_block` could never have passed at all.

Three keys were dead: `refusal_markers`, `sources_marker` and `checks`.
The first two are now read. **`checks` is deliberately still not read**, and
that is a safety decision rather than an oversight: letting a target choose
which checks run would let a target disable one, and `AGENTS.md` forbids
weakening a check. A target may describe its own vocabulary; it may not
decide what is verified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from kavach.verification.fast import (
    REFUSAL_MARKERS,
    SOURCES_MARKER,
    load_markers,
)

ROOT = Path(__file__).resolve().parents[3]
FIRST_TARGET_SET = (ROOT / "apps/control-plane/kavach/verification"
                    / "fast_set.yaml")


def test_the_first_targets_set_still_means_what_the_constants_meant() -> None:
    """The no-change proof. Reading markers from the set only stays safe while
    that set declares what the constants said; if it ever diverges, the
    behaviour every published number was measured with has changed."""
    markers, marker = load_markers(FIRST_TARGET_SET)
    assert set(markers) == set(REFUSAL_MARKERS), (
        f"the first target's fast set now declares {sorted(markers)}, which "
        f"differs from the constants {sorted(REFUSAL_MARKERS)} that every "
        f"measurement in REPORT_DRAFT.md was taken with")
    assert marker == SOURCES_MARKER


def test_markers_are_lowercased_for_the_comparison() -> None:
    """`run` compares against a lowercased answer, and the first target's set
    writes `**Sources:**` with capitals. A case-preserving read would have
    made `sources_block` never match, failing every case on a healthy
    system."""
    _, marker = load_markers(FIRST_TARGET_SET)
    assert marker == marker.lower()
    raw = yaml.safe_load(FIRST_TARGET_SET.read_text(encoding="utf-8"))
    assert raw["sources_marker"] != raw["sources_marker"].lower(), (
        "this test is only meaningful while the set declares a marker with "
        "capitals; if that changes, the lowercasing is no longer load-bearing")


def test_a_sets_own_vocabulary_is_used(tmp_path: Path) -> None:
    """The actual fix: a different target's words are honoured."""
    doc: dict[str, Any] = {
        "cases": [],
        "refusal_markers": ["I'm sorry", "do not have information"],
        "sources_marker": "### References",
    }
    path = tmp_path / "other_set.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    markers, marker = load_markers(path)
    assert "i'm sorry" in markers
    assert "do not have information" in markers
    assert marker == "### references"
    # And the first target's words are NOT silently mixed in.
    assert "don't know" not in markers


def test_a_set_that_declares_nothing_falls_back_to_the_constants(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bare.yaml"
    path.write_text(yaml.safe_dump({"cases": []}), encoding="utf-8")
    markers, marker = load_markers(path)
    assert markers == REFUSAL_MARKERS
    assert marker == SOURCES_MARKER


def test_checks_is_still_not_read_and_that_is_deliberate() -> None:
    """Guards the safety decision, not an implementation detail.

    If someone later wires `checks` through, this fails and makes them argue
    for it: a target that can list which checks apply is a target that can
    remove one, and the three checks are the verification contract rather
    than a preference.
    """
    source = (ROOT / "apps/control-plane/kavach/verification"
              / "fast.py").read_text(encoding="utf-8")
    assert '"checks"' not in source and "'checks'" not in source, (
        "fast.py now reads `checks` from the set. A target could then "
        "disable `non_refusal` or `sources_block` by omitting it, which is a "
        "target weakening its own verification - AGENTS.md forbids that. If "
        "this is intended, it needs a decision record, not a test edit.")
