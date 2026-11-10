"""The statistics behind every p-value the closure ablation reports.

ADDED 2026-11-10, after an audit found that nothing tested them. These four
functions produce the numbers `EXPERIMENT_CLOSURE_ABLATION.md` quotes and
`REPORT_DRAFT` §4.4a repeats, and one of them had a defect that survived
three full runs: the McNemar pairing treated each of 168 correlated
diagnoses as an independent observation while the cluster bootstrap beside it
resampled incidents, so the two disagreed about what an observation was. On
the 2026-11-09 run that read p=0.0007 per diagnosis against p=0.1250 per
incident - the difference between a result and none.

`test_cells_pairs_on_the_incident_not_the_diagnosis` is the regression test
for exactly that. The rest are hand-computed reference values, because a
statistic checked only against its own output is not checked.

No network, no model, no artifact on disk.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness import closure_ablation_report as rep


def obs(fault_class: str, incident: int, arm: str, rep_no: int,
        closed: bool) -> dict[str, Any]:
    return {"fault_class": fault_class, "incident": incident, "arm": arm,
            "rep": rep_no, rep.PRIMARY: closed, "error": ""}


# --------------------------------------------------------------------------
# exact McNemar
# --------------------------------------------------------------------------

@pytest.mark.parametrize(("b", "c", "expected"), [
    # Two-sided exact binomial at p=0.5, doubling the smaller tail. Each value
    # below is computed by hand from the binomial coefficients, not from this
    # implementation's own output.
    (0, 0, 1.0),            # no discordant pairs says nothing
    (1, 0, 1.0),            # one discordant pair CANNOT be significant
    (5, 5, 1.0),            # perfectly balanced
    (4, 2, 0.6875),         # 2*(1+6+15)/64
    (7, 3, 0.34375),        # 2*(1+10+45+120)/1024
    (8, 0, 0.0078125),      # 2/256    - the F07 A-vs-E figure
    (10, 0, 0.001953125),   # 2/1024
    (11, 0, 0.0009765625),  # 2/2048   - the 2026-11-10 A-vs-B figure
    (13, 0, 0.000244140625),  # 2/8192 - the 2026-11-09 A-vs-B figure
])
def test_mcnemar_matches_hand_computed_exact_values(
    b: int, c: int, expected: float,
) -> None:
    pairs = [(True, False)] * b + [(False, True)] * c
    got_b, got_c, p = rep.mcnemar(pairs)
    assert (got_b, got_c) == (b, c)
    assert p == pytest.approx(expected, rel=1e-12)


def test_mcnemar_ignores_concordant_pairs() -> None:
    """Concordant pairs carry no information and must not shift the p-value."""
    discordant = [(True, False)] * 8
    bare = rep.mcnemar(discordant)
    padded = rep.mcnemar(discordant + [(True, True)] * 40 + [(False, False)] * 9)
    assert bare == padded


def test_mcnemar_is_symmetric_in_its_arguments() -> None:
    """Swapping the arms swaps b and c and leaves the p-value alone."""
    _b, _c, p1 = rep.mcnemar([(True, False)] * 7 + [(False, True)] * 3)
    _b2, _c2, p2 = rep.mcnemar([(False, True)] * 7 + [(True, False)] * 3)
    assert p1 == pytest.approx(p2)


# --------------------------------------------------------------------------
# clustering - the regression test for the defect found 2026-11-10
# --------------------------------------------------------------------------

def test_cells_pairs_on_the_incident_not_the_diagnosis() -> None:
    """Three reps of one incident are ONE pairing unit, not three.

    If this fails, the McNemar is back to treating correlated reps as
    independent and every p-value it prints is too small.
    """
    rows = [obs("F07", 1, "A", r, True) for r in (1, 2, 3)]
    rows += [obs("F07", 1, "B", r, False) for r in (1, 2, 3)]
    rows += [obs("F07", 2, "A", r, True) for r in (1, 2, 3)]
    rows += [obs("F07", 2, "B", r, False) for r in (1, 2, 3)]

    cells = rep.cells(rows, rep.PRIMARY)

    assert len(cells) == 4, (
        "PAIRING UNIT REGRESSION: expected one cell per (class, incident, "
        f"arm) = 4, got {len(cells)} from 12 diagnoses.")
    pairs = [(cells[k], cells[(k[0], k[1], "B")])
             for k in cells if k[2] == "A"]
    b, c, p = rep.mcnemar(pairs)
    assert (b, c) == (2, 0), "two incidents, so two discordant pairs"
    assert p == pytest.approx(0.5)  # 2/4 - two pairs prove nothing


def test_cells_takes_the_majority_of_reps() -> None:
    """2-of-3 closes the cell; 1-of-3 does not. Ties cannot occur at 3 reps."""
    rows = [obs("F01", 1, "A", 1, True), obs("F01", 1, "A", 2, True),
            obs("F01", 1, "A", 3, False),
            obs("F01", 2, "A", 1, True), obs("F01", 2, "A", 2, False),
            obs("F01", 2, "A", 3, False)]
    cells = rep.cells(rows, rep.PRIMARY)
    assert cells[("F01", 1, "A")] is True
    assert cells[("F01", 2, "A")] is False


def test_cells_separates_classes_that_share_an_incident_number() -> None:
    """Incident 1 of F07 and incident 1 of F08 are different incidents.

    The key is (class, incident, arm) rather than (incident, arm) for this
    reason: every class numbers its incidents from 1.
    """
    rows = [obs("F07", 1, "A", 1, True), obs("F08", 1, "A", 1, False)]
    cells = rep.cells(rows, rep.PRIMARY)
    assert cells == {("F07", 1, "A"): True, ("F08", 1, "A"): False}


# --------------------------------------------------------------------------
# cluster bootstrap
# --------------------------------------------------------------------------

def test_cluster_bootstrap_resamples_incidents_not_diagnoses() -> None:
    """Two incidents that disagree must give a wide interval, not a tight one.

    With 2 clusters the resampled rate can only be 0.0, 0.5 or 1.0, so a
    correct cluster bootstrap spans the whole range. A bootstrap over the 6
    individual diagnoses would concentrate near 0.5 and report a narrow
    interval that the data does not support.
    """
    rows = [obs("F01", 1, "A", r, True) for r in (1, 2, 3)]
    rows += [obs("F01", 2, "A", r, False) for r in (1, 2, 3)]

    rate, lo, hi = rep.cluster_bootstrap(rows, rep.PRIMARY, draws=2000)

    assert rate == pytest.approx(0.5)
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(1.0)


def test_cluster_bootstrap_is_reproducible() -> None:
    """A fixed seed, because a p-value that moves between runs is not one."""
    rows = [obs("F01", i, "A", r, i % 3 != 0)
            for i in range(1, 16) for r in (1, 2, 3)]
    assert (rep.cluster_bootstrap(rows, rep.PRIMARY, draws=1000)
            == rep.cluster_bootstrap(rows, rep.PRIMARY, draws=1000))


def test_cluster_bootstrap_is_empty_safe() -> None:
    rate, lo, hi = rep.cluster_bootstrap([], rep.PRIMARY, draws=10)
    assert rate != rate and lo != lo and hi != hi   # all nan


# --------------------------------------------------------------------------
# the perfect-arm ceiling
# --------------------------------------------------------------------------

def test_perfect_arm_ceiling_replaces_the_degenerate_interval() -> None:
    """57 perfect incidents bound the failure rate at ~5%, not at zero.

    `1 - 0.05 ** (1/57) = 0.0511995`. The bootstrap reports [1.00, 1.00] for
    this arm, which is arithmetically right and reads as certainty.
    """
    rows = [obs("F01", i, "A", r, True)
            for i in range(1, 58) for r in (1, 2, 3)]
    assert rep.perfect_arm_ceiling(rows, rep.PRIMARY) == pytest.approx(
        0.0511995, abs=1e-7)


def test_perfect_arm_ceiling_shrinks_as_incidents_accumulate() -> None:
    """More perfect incidents buy a tighter ceiling, which is the whole point."""
    def ceiling(n: int) -> float:
        rows = [obs("F01", i, "A", r, True)
                for i in range(1, n + 1) for r in (1, 2, 3)]
        return rep.perfect_arm_ceiling(rows, rep.PRIMARY)

    assert ceiling(10) > ceiling(57) > ceiling(500)
    assert ceiling(1) == pytest.approx(0.95)    # one success bounds nothing


def test_perfect_arm_ceiling_is_nan_for_an_imperfect_arm() -> None:
    """For any other arm the bootstrap interval is the better statistic."""
    rows = [obs("F01", i, "A", r, True)
            for i in range(1, 20) for r in (1, 2, 3)]
    rows += [obs("F01", 20, "A", r, False) for r in (1, 2, 3)]
    got = rep.perfect_arm_ceiling(rows, rep.PRIMARY)
    assert got != got, "a single miss must disqualify the ceiling"


def test_perfect_arm_ceiling_needs_every_rep_closed() -> None:
    """One failed rep in one incident is enough to disqualify it."""
    rows = [obs("F01", 1, "A", 1, True), obs("F01", 1, "A", 2, False),
            obs("F01", 2, "A", 1, True)]
    got = rep.perfect_arm_ceiling(rows, rep.PRIMARY)
    assert got != got


# --------------------------------------------------------------------------
# within-cell spread
# --------------------------------------------------------------------------

def test_within_cell_spread_is_zero_for_deterministic_reps() -> None:
    rows = [obs("F01", i, "A", r, True)
            for i in range(1, 6) for r in (1, 2, 3)]
    assert rep.within_cell_variance(rows, rep.PRIMARY) == 0.0


def test_within_cell_spread_is_one_when_reps_disagree() -> None:
    """The statistic is a mean max-minus-min, which is why §7's refutation
    condition is conservative: the range of three Bernoulli draws is at least
    as large as any spread measure one could put in its place."""
    rows = [obs("F01", 1, "A", 1, True), obs("F01", 1, "A", 2, False),
            obs("F01", 1, "A", 3, True)]
    assert rep.within_cell_variance(rows, rep.PRIMARY) == 1.0


def test_within_cell_spread_ignores_single_rep_cells() -> None:
    """One rep has no spread, and counting it as 0 would dilute the mean."""
    rows = [obs("F01", 1, "A", 1, True),
            obs("F01", 2, "A", 1, True), obs("F01", 2, "A", 2, False)]
    assert rep.within_cell_variance(rows, rep.PRIMARY) == 1.0
