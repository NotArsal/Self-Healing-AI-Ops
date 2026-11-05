"""What is the F01 MTTD ladder's step, and what makes it?

`REPORT_DRAFT.md` §4.1 records that F01's MTTD is quantised rather than
continuous, puts the step at **12.2s**, and says the cause is still a
hypothesis because 12.2 is close to but not equal to the 15s Prometheus
scrape interval. §9 item 13 carries it as open: four rungs, no named
mechanism.

This narrows it. Pooled over the four bench runs, n=20:

  36.5 36.5 36.5 36.6 36.6 48.5 48.6 48.7 48.7 54.6 60.8 60.8 61.0 61.3
  62.0 66.8 72.9 78.9 91.0 94.0

THE STEP IS HALF WHAT WAS REPORTED. Scored as mean distance to the nearest
lattice point, a period near **6.05s** fits far better than 12.2s, and 12.2
is simply its second harmonic - it looked like the step because the two most
populated rungs happen to sit two steps apart. Sixteen of the twenty values land
within 0.3s of a 6.05s rung, and seventeen within 0.5s.

That also explains the "two ladders" the raw numbers suggest. Residues mod
12.1 cluster at 0.2 and at 6.2, which is one lattice at half-period offsets,
not two mechanisms.

WHAT THE MECHANISM IS NOT. There is no sleep, poll or interval constant
anywhere in the detection path; the only timer in the system is Prometheus,
at a 15s scrape and a 15s evaluation interval. Neither divides 6.05.

THE REMAINING CANDIDATE, AND IT IS NOT TESTED HERE. `warm_up_f01` loops up
to six rounds, and each round runs the WHOLE three-case fast set before
re-reading the error ratio. MTTD is measured from injection and therefore
contains those rounds. If a chat call against a disabled LLM endpoint costs
about two seconds, a round costs about six, and the ladder is one round -
not a scrape boundary at all, but the harness's own warm-up granularity.

That predicts something checkable: the step should equal three failed chat
calls, and should MOVE if the fast set's case count changes. Confirming it
needs F01 injected with the round duration timed directly, which is a live
run this script does not perform. Stated as the leading candidate, not as
the answer.
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

    best = min(candidates, key=lambda p: misfit(values, p))
    print(f"best fit: {best:.2f}s")
    # The epsilon is not fussiness: without it a value whose offset is
    # exactly 0.30 computes as 0.30000000000000004 and is counted as a miss,
    # which turned 16 into 11 the first time this was run.
    close = sum(1 for v in values
                if min(v % 6.05, 6.05 - (v % 6.05)) <= 0.3 + 1e-9)
    print(f"{close} of {len(values)} values lie within 0.3s of a 6.05s rung")
    print()
    print("residue mod 12.1, showing one lattice at half-period offsets")
    print("rather than two separate mechanisms:")
    for v in values:
        print(f"  {v:6.1f}  ->  {v % 12.1:5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
