"""A rollback target must come from a baseline taken on a healthy system.

THE GAP THIS PINS, found 2026-11-03.

`baseline.py` computes `healthy` as "the fast set passed, no SLO breached,
and the corpus did not move during the capture", and refuses to save a
capture that fails it. Its own docstring gives the reason: *"A baseline
captured while a fault is present would make the fault look normal forever
after."*

That refusal is overridable with `--force`, and `newest_baseline_doc` did not
re-check. It defined "usable" as "records a rerank_threshold" and took the
newest match, so a forced capture would be selected for being newest alone -
and the rollback target for F06, F07 and F08 would be values measured while
the system was broken. Every repair would then restore the fault.

The write path refused and the read path did not, which is the same shape as
the other defects found this week: a rule enforced in one place and assumed
everywhere else. Four `healthy: false` captures are committed under
`harness/baselines/`, so forced or pre-refusal captures do reach disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kavach.api.runner import newest_baseline, newest_baseline_doc

ROOT = Path(__file__).resolve().parents[3]
BASELINES = ROOT / "harness" / "baselines"
PROJECT = "simple-rag"


def _write(path: Path, name: str, **fields: Any) -> None:
    doc: dict[str, Any] = {"rerank_threshold": 0.35, "healthy": True}
    doc.update(fields)
    (path / name).write_text(json.dumps(doc), encoding="utf-8")


def test_the_real_baselines_still_select_the_same_capture() -> None:
    """The no-change proof. Today's newest capture is healthy, so adding the
    filter must pick exactly what it picked before."""
    if not BASELINES.is_dir():
        import pytest

        pytest.skip(f"no baselines directory at {BASELINES}")
    doc, name = newest_baseline_doc(BASELINES, PROJECT)
    assert name, "no usable baseline found for the first target"
    assert doc.get("healthy") is True
    assert isinstance(doc.get("rerank_threshold"), int | float)


def test_an_unhealthy_newer_capture_is_skipped(tmp_path: Path) -> None:
    """The fix. A forced capture must not become the rollback target just by
    being newest - restoring values measured while broken would make every
    repair reinstate the fault."""
    _write(tmp_path, f"baseline-{PROJECT}-20260101T000000+0000.json",
           healthy=True, rerank_threshold=0.35)
    _write(tmp_path, f"baseline-{PROJECT}-20260202T000000+0000.json",
           healthy=False, rerank_threshold=0.99)

    doc, name = newest_baseline_doc(tmp_path, PROJECT)
    assert "20260101" in name, (
        f"selected {name}, which is the unhealthy newer capture; its "
        f"rerank_threshold would become the F06 rollback target")
    assert doc["rerank_threshold"] == 0.35
    assert newest_baseline(tmp_path, PROJECT)[0] == 0.35


def test_a_capture_that_does_not_say_is_not_assumed_good(tmp_path: Path) -> None:
    """Absent `healthy` is unusable, not implicitly true: a capture that does
    not record it was written by something that did not measure it."""
    path = tmp_path / f"baseline-{PROJECT}-20260303T000000+0000.json"
    path.write_text(json.dumps({"rerank_threshold": 0.5}), encoding="utf-8")
    doc, name = newest_baseline_doc(tmp_path, PROJECT)
    assert not name and not doc


def test_no_usable_baseline_returns_nothing_rather_than_a_guess(
    tmp_path: Path,
) -> None:
    """`runner.py`'s own rule is "a real baseline or nothing"."""
    assert newest_baseline_doc(tmp_path, PROJECT) == ({}, "")
    assert newest_baseline(tmp_path, PROJECT) == (None, "")
