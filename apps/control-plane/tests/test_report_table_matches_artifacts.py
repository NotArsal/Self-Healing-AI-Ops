"""The report's headline table must still equal what the artifacts say.

ADDED 2026-11-05, after finding two figures in `REPORT_DRAFT.md` that had
gone stale - an audit row count of 336 against a live 1,022, and "all 568
gate tests" against a suite of 618. Neither was wrong when written, which is
exactly how both survived being read.

The acceptance table in §4.1 is the part of the report that must never drift,
because it is the part a reviewer checks. This recomputes it from the four
committed bench artifacts and compares against the numbers in the markdown.

WHAT IT DOES AND DOES NOT GUARANTEE. It proves the prose agrees with the
JSON. It cannot prove the JSON describes a run that happened - nothing in a
repository can - which is why the artifacts are committed whole rather than
summarised, so the two can be compared by hand as well as here.

The run order is fixed by the table itself: A, B, C, D are `bench-full`,
`bench-20261020-mttd`, `bench-20261020-night` and `bench-20261102-night`, in
that order, which is the order §4.1 introduces them.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "docs" / "REPORT_DRAFT.md"
REPORTS = ROOT / "harness" / "reports"

RUNS = [
    ("A", "bench-full.json"),
    ("B", "bench-20261020-mttd.json"),
    ("C", "bench-20261020-night.json"),
    ("D", "bench-20261102-night.json"),
]


def rows_of(fname: str) -> list[dict[str, Any]]:
    path = REPORTS / fname
    if not path.is_file():
        pytest.skip(f"missing artifact {fname}")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return [r for r in doc.get("runs", []) if not r.get("error")]


def table_row(label: str) -> list[str]:
    """The cells of one row of the §4.1 headline table."""
    for line in REPORT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.lstrip("|").strip().startswith(label):
            return [c.strip() for c in stripped.strip("|").split("|")]
    pytest.fail(f"no row starting {label!r} in the report's headline table")


def test_the_table_is_still_shaped_the_way_this_test_reads_it() -> None:
    """A guard on the guard. If the table moved or was reformatted, every
    comparison below would skip or fail for the wrong reason, so the shape is
    asserted before any number is."""
    cells = table_row("detection rate")
    assert len(cells) >= 6, f"unexpected table shape: {cells}"
    assert "20/20" in cells[1], (
        f"the first data column is not run A's detection rate: {cells[1]!r}")


@pytest.mark.parametrize("run,fname", RUNS, ids=[r for r, _ in RUNS])
def test_detection_and_false_healing(run: str, fname: str) -> None:
    """The two claims the architecture exists to support."""
    rows = rows_of(fname)
    column = RUNS.index((run, fname)) + 1

    detected = sum(1 for r in rows if r.get("detected"))
    assert f"{detected}/{len(rows)}" in table_row("detection rate")[column]

    false_heals = sum(1 for r in rows if r.get("false_healing"))
    assert false_heals == 0, (
        f"{fname} contains {false_heals} false heal(s); the report's "
        f"headline is 'eighty injections, zero false heals'")
    assert f"0/{len(rows)}" in table_row("**false healing**")[column]


@pytest.mark.parametrize("run,fname", RUNS, ids=[r for r, _ in RUNS])
def test_rca_accuracy_and_auto_resolution(run: str, fname: str) -> None:
    rows = rows_of(fname)
    column = RUNS.index((run, fname)) + 1

    # The MODEL's own answer against the INJECTED class - never det_class,
    # which is the deterministic verdict sitting in the same record and is
    # the substitution that once flattered this number to a perfect score.
    correct = sum(1 for r in rows
                  if r.get("llm_class") == r.get("fault_class"))
    assert f"{correct}/{len(rows)}" in table_row("RCA accuracy")[column], (
        f"{fname} scores {correct}/{len(rows)} RCA accuracy; the report says "
        f"{table_row('RCA accuracy')[column]}")

    resolved = sum(1 for r in rows if r.get("resolved"))
    assert f"{resolved}/{len(rows)}" in table_row("auto-resolution")[column]


@pytest.mark.parametrize("run,fname", RUNS, ids=[r for r, _ in RUNS])
def test_mttr_median(run: str, fname: str) -> None:
    rows = rows_of(fname)
    column = RUNS.index((run, fname)) + 1
    values = [r["mttr_s"] for r in rows if r.get("mttr_s") is not None]
    assert values, f"{fname} records no MTTR"
    median = statistics.median(values)

    cell = table_row("MTTR median")[column]
    stated = re.search(r"([0-9]+\.[0-9])s", cell)
    assert stated, f"no MTTR figure in {cell!r}"
    assert abs(float(stated.group(1)) - median) < 0.05, (
        f"{fname} has a median MTTR of {median:.1f}s; the report says "
        f"{stated.group(1)}s")


def test_the_eighty_injection_denominator() -> None:
    """The sentence the whole architecture is defended by."""
    total = sum(len(rows_of(f)) for _, f in RUNS)
    false_heals = sum(
        1 for _, f in RUNS for r in rows_of(f) if r.get("false_healing"))
    assert (total, false_heals) == (80, 0), (
        f"the committed artifacts contain {total} usable injections and "
        f"{false_heals} false heals; the report claims eighty and zero")
    assert "Eighty injections, zero false heals" in REPORT.read_text(
        encoding="utf-8")
