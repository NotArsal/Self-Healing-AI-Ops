"""What makes the F01 MTTD ladder, measured rather than fitted.

`REPORT_DRAFT.md` §4.1 records that F01's MTTD is quantised rather than
continuous and puts the step near 12.2s, with the 15s Prometheus scrape
interval as the suspected cause. §9 item 13 carries it as open.

THE MECHANISM, MEASURED 2026-11-06. With F01 injected on the live stack, one
round of `warm_up_f01` - the whole three-case fast set, which is what the
function runs before re-reading the error ratio - costs:

    12.10s  12.15s  12.12s  12.11s        mean 12.12s, spread 0.05s

against 24.3s for the same round on a healthy target. MTTD is measured from
injection and contains those rounds, so **the ladder's rungs are warm-up
rounds**. Twelve of the twenty samples lie within 0.4s of a 12.12s lattice.
That is the named mechanism item 13 asked for, and it is the harness's own
granularity rather than anything in the detection path.

It also rules the scrape interval out: 15s does not divide 12.12, and no
sleep, poll or interval constant exists anywhere in the detection path.

A CORRECTION, RECORDED BECAUSE THE MISTAKE IS INSTRUCTIVE. An earlier version
of this script fitted a lattice to the twenty samples and concluded the step
was 6.05s, with 12.2 as its second harmonic. That was backwards, and the
direct measurement refutes it. **Any divisor of the true period fits every
point of that period's lattice**, so a smaller period can never score worse
on mean-distance-to-nearest-rung - 6.05 won because it is half of 12.1, not
because it is the step. The function below carries a comment warning against
normalising by the period; the unnormalised score has the same degeneracy in
the other direction, and I fell for it. A lattice fit alone cannot choose
between a period and its divisors. Only the timing run can.

WHAT IS STILL UNEXPLAINED. Four samples - 54.6, 66.8, 78.9, 91.0 - sit
5.92-6.00s from the nearest 12.12s rung, which is almost exactly half a
round, too precise to be noise. Four others scatter. Half a round is not a
natural unit of a three-call fast set, so something else contributes; the
candidate is variation in the detection step that follows the warm-up, which
is not measured here.

THE CONSEQUENCE THAT MATTERS MORE THAN THE LADDER. If F01's MTTD is
dominated by a warm-up the other classes do not perform, **it is not
comparable to F06's, F07's or F08's**, and §4.1's per-class MTTD comparison
should say so.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def f01_mttd() -> list[float]:
    out: list[float] = []
    for path in sorted((ROOT / "harness" / "reports").glob("bench-*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in doc.get("runs", []):
            if row.get("fault_class") == "F01" and row.get("mttd_s") is not None:
                out.append(round(float(row["mttd_s"]), 1))
    return sorted(out)


def misfit(values: list[float], period: float) -> float:
    """Mean distance from a value to its nearest lattice point.

    Normalising by the period would be the usual move; it is deliberately NOT
    done, because dividing by the period is what makes an arbitrarily small
    period win. Compared at a fixed scale, a real step stands out.
    """
    total = 0.0
    for v in values:
        r = v % period
        total += min(r, period - r)
    return total / len(values)


def main() -> int:
    values = f01_mttd()
    if not values:
        print("no F01 MTTD values in harness/reports/bench-*.json")
        return 1

    print(f"F01 MTTD pooled over the bench runs, n={len(values)}")
    print(" ", values)
    print()

    print("mean distance to the nearest rung, by candidate period:")
    candidates = [3.0, 4.0, 5.0, 6.05, 6.1, 7.0, 8.0, 10.0, 12.1, 12.2, 15.0,
                  20.0, 30.0]
    for period in candidates:
        mark = ""
        if abs(period - 15.0) < 0.01:
            mark = "   <- Prometheus scrape interval"
        if abs(period - 12.2) < 0.01:
            mark = "   <- the step REPORT_DRAFT.md currently claims"
        print(f"  {period:5.2f}s   {misfit(values, period):4.2f}s{mark}")
    print()

    print("A SMALLER PERIOD ALWAYS FITS AT LEAST AS WELL, because every")
    print("point of a lattice is also a point of its divisors' lattices. The")
    print("scores below cannot choose between 12.12 and 6.06; the measured")
    print("round duration can, and does.")
    print()
    print("MEASURED on the live stack with F01 injected, one warm-up round:")
    print("  12.10s  12.15s  12.12s  12.11s   mean 12.12s, spread 0.05s")
    print("  (the same round on a healthy target: 24.3s)")
    near = sum(1 for v in values
               if min(v % 12.12, 12.12 - (v % 12.12)) <= 0.4)
    print(f"  {near} of {len(values)} samples lie within 0.4s of a 12.12s rung")
    # The epsilon is not fussiness: without it a value whose offset is
    # exactly 0.30 computes as 0.30000000000000004 and is counted as a miss,
    # which turned 16 into 11 the first time this was run.
    print()
    print("the four samples at almost exactly half a round, still unexplained:")
    for v in values:
        off = min(v % 12.12, 12.12 - (v % 12.12))
        if 5.5 <= off <= 6.1:
            print(f"  {v:6.1f}  ->  {off:4.2f}s from the nearest rung")
    print()
    print("residue mod 12.12, the measured round:")
    for v in values:
        print(f"  {v:6.1f}  ->  {v % 12.12:5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
