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


# --- the two comparison baselines -------------------------------------------
#
# ADDED 2026-11-06. §4.8 is the section the deck leans on hardest - it is
# where "every approach fails on F07, and two of the three lie about it"
# comes from - and its numbers come from two artifacts that no test read.
# Verified by hand first; every figure matched.
#
# The field names are not the obvious ones (`correct`, not
# `diagnosis_correct`, in the runbook; `declared_resolved_at_s`, not
# `resolve_s`, in the human runs), which is exactly the kind of detail a
# hand-written summary gets subtly wrong.

HUMAN = REPORTS / "human-baseline.json"
RUNBOOK = REPORTS / "runbook-baseline.json"


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        pytest.skip(f"missing artifact {path.name}")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return list(doc.get("runs", []))


def test_the_runbook_baseline_matches_its_table() -> None:
    rows = _rows(RUNBOOK)
    assert len(rows) == 8, (
        f"§4.8 says the runbook is 4 classes x 2 reps; the artifact has "
        f"{len(rows)} rows")

    correct = sum(1 for r in rows if r.get("correct"))
    verified = sum(1 for r in rows if r.get("verified"))
    false_recoveries = sum(1 for r in rows if r.get("false_recovery"))
    resolved = [r["resolved_s"] for r in rows if r.get("resolved_s") is not None]

    assert (correct, verified, false_recoveries) == (8, 7, 1), (
        f"§4.8's runbook table says 8/8 correct, 7/8 verified, 1/8 false "
        f"recovery; the artifact says {correct}/8, {verified}/8, "
        f"{false_recoveries}/8")
    assert abs(statistics.median(resolved) - 37.5) < 0.05, (
        f"§4.8 says a 37.5s median resolve; the artifact gives "
        f"{statistics.median(resolved):.1f}s")


def test_the_human_baseline_matches_its_table() -> None:
    """Including the paired Kavach column, which is the whole point of the
    run: the same incidents, observed in SIMULATION, so the comparison is
    paired rather than two unpaired samples."""
    rows = _rows(HUMAN)
    assert len(rows) == 3, f"§4.8 describes three runs; artifact has {len(rows)}"

    operator_correct = sum(1 for r in rows if r.get("diagnosis_correct"))
    gave_up = sum(1 for r in rows if r.get("gave_up"))
    false_recoveries = sum(1 for r in rows if r.get("false_recovery"))
    kavach_correct = sum(1 for r in rows if r.get("kavach_correct"))

    assert (operator_correct, gave_up, false_recoveries) == (0, 2, 1), (
        f"§4.8 says 0/3 correct, 2 give-ups, 1 false recovery; the artifact "
        f"says {operator_correct}, {gave_up}, {false_recoveries}")
    assert kavach_correct == 2, (
        f"§4.8 says Kavach was 2/3 correct on the identical incidents; the "
        f"artifact says {kavach_correct}/3. That sentence is the comparison "
        f"the deck quotes.")


def test_the_f07_false_recovery_is_the_one_the_report_names() -> None:
    """§4.8's sharpest claim is about which fault each approach lied on. If
    the false recovery ever moves to another class, the argument moves with
    it and the prose would not notice."""
    human = [r for r in _rows(HUMAN) if r.get("false_recovery")]
    assert [r["fault_class"] for r in human] == ["F07"], (
        "the human baseline's false recovery is no longer the F07 run that "
        "§4.8 builds its comparison on")

    runbook = [r for r in _rows(RUNBOOK) if r.get("false_recovery")]
    assert [r["fault_class"] for r in runbook] == ["F07"], (
        "the runbook's false recovery is no longer on F07, so §4.8's "
        '"every approach fails on F07" no longer follows from the artifacts')
