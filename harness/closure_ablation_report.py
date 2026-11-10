"""Read a closure-ablation artifact and report it the way the paper needs.

Separate from `closure_ablation.py` on purpose. That script injects faults
and calls a model; this one touches nothing and can be re-run any number of
times against a finished artifact. Re-analysis should never require
re-measuring, and an analysis that can only be produced by the run that
collected the data cannot be checked by anyone else.

WHAT THIS ADDS over the run's own summary:

  * bootstrap confidence intervals on every arm's rate, which
    `docs/EXPERIMENT_CLOSURE_ABLATION.md` §5 requires and the run does not
    produce
  * within-cell variance across repetitions, which is the check that decides
    whether an arm difference is an effect or sampling noise - §7 names
    "within-cell variance exceeds the A-to-B gap" as a refutation condition
    and nothing computed it
  * the primary comparison stated against its pre-registered threshold, so
    the verdict is read off rather than argued

CLUSTERING, AND WHY THE NAIVE CI WOULD BE WRONG. Each incident contributes
`reps` observations per arm, and those are not independent - they share a
frame, a fault and a detector verdict. A bootstrap over individual
diagnoses would therefore understate the interval. This resamples
INCIDENTS, not diagnoses, which is the standard cluster bootstrap and is
the honest unit here.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "harness" / "reports" / "closure-ablation.json"
PRIMARY = "closed_detector"
PREREGISTERED_DROP = 0.15
# A diagnosis the model declines to make. Kavach never executes an UNKNOWN,
# so these are safe outcomes and must not be pooled with confident errors.
ABSTENTIONS = ("UNKNOWN", "")


def say(*parts: object) -> None:
    print(*parts, flush=True)


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"no artifact at {path}")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def usable(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in doc.get("observations", []) if not o.get("error")]


def cluster_bootstrap(
    rows: list[dict[str, Any]], field: str, draws: int = 10_000, seed: int = 11,
) -> tuple[float, float, float]:
    """(rate, lo, hi) at 95%, resampling INCIDENTS rather than diagnoses."""
    by_cluster: dict[tuple[str, int], list[bool]] = defaultdict(list)
    for o in rows:
        by_cluster[(o["fault_class"], o["incident"])].append(bool(o[field]))
    clusters = list(by_cluster.values())
    if not clusters:
        return float("nan"), float("nan"), float("nan")

    flat = [v for c in clusters for v in c]
    rate = sum(flat) / len(flat)

    rng = random.Random(seed)
    sampled: list[float] = []
    for _ in range(draws):
        picked = [clusters[rng.randrange(len(clusters))]
                  for _ in range(len(clusters))]
        values = [v for c in picked for v in c]
        if values:
            sampled.append(sum(values) / len(values))
    sampled.sort()
    lo = sampled[int(0.025 * len(sampled))]
    hi = sampled[int(0.975 * len(sampled)) - 1]
    return rate, lo, hi


def perfect_arm_ceiling(rows: list[dict[str, Any]], field: str) -> float:
    """One-sided 95% upper bound on the per-incident failure rate, or nan.

    WHY THIS EXISTS. The cluster bootstrap is degenerate at the boundary: when
    every incident closes, every resample also closes, so it reports
    `[1.00, 1.00]` - a zero-width interval on a finite sample. That is correct
    arithmetic and a misleading number. Arms A and E print it on every run,
    and a reader is entitled to read a zero-width interval as certainty.

    Observing k perfect incidents out of k says the failure probability is at
    most `1 - 0.05 ** (1 / k)` with 95% confidence (the exact one-sided
    Clopper-Pearson bound, which for 57 incidents is about 0.05). Returns nan
    unless the arm is actually perfect, because for any other arm the
    bootstrap interval is the better statistic and this bound would be loose.
    """
    by_cluster: dict[tuple[str, int], list[bool]] = defaultdict(list)
    for o in rows:
        by_cluster[(o["fault_class"], o["incident"])].append(bool(o[field]))
    clusters = list(by_cluster.values())
    if not clusters or not all(all(c) for c in clusters):
        return float("nan")
    return float(1.0 - 0.05 ** (1.0 / len(clusters)))


def cells(rows: list[dict[str, Any]], field: str
          ) -> dict[tuple[str, int, str], bool]:
    """One outcome per (class, incident, arm), by majority of its reps.

    THE PAIRING UNIT IS THE INCIDENT, NOT THE DIAGNOSIS. Reps of one incident
    share a frame and a draw, and the measured within-cell spread is 0.01 -
    they are very nearly the same observation three times. Pairing per
    diagnosis treated 168 correlated outcomes as independent and inflated
    every p-value: on the 2026-11-09 run A vs B read p=0.0007 per diagnosis
    and p=0.1250 per incident, which is the difference between a significant
    result and none. `cluster_bootstrap` had always resampled incidents; the
    McNemar beside it had not, and the two disagreed about what an
    observation was.

    Majority rather than `all` or `any` because it degrades gracefully if
    reps ever stop being deterministic. On that run all three rules gave
    identical b and c.
    """
    grouped: dict[tuple[str, int, str], list[bool]] = defaultdict(list)
    for o in rows:
        grouped[(o["fault_class"], o["incident"], o["arm"])].append(
            bool(o[field]))
    return {k: sum(v) * 2 > len(v) for k, v in grouped.items()}


def mcnemar(pairs: list[tuple[bool, bool]]) -> tuple[int, int, float]:
    b = sum(1 for a, x in pairs if a and not x)
    c = sum(1 for a, x in pairs if x and not a)
    n = b + c
    if n == 0:
        return b, c, 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return b, c, min(1.0, 2 * tail)


def within_cell_variance(rows: list[dict[str, Any]], field: str) -> float:
    """Mean spread across repetitions of the SAME (incident, arm) cell.

    If this is as large as the between-arm gap, the gap is sampling noise.
    """
    cells: dict[tuple[str, int, str], list[bool]] = defaultdict(list)
    for o in rows:
        cells[(o["fault_class"], o["incident"], o["arm"])].append(bool(o[field]))
    spreads = [max(v) - min(v) for v in cells.values() if len(v) > 1]
    return sum(spreads) / len(spreads) if spreads else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", nargs="?", default=str(DEFAULT))
    ap.add_argument("--draws", type=int, default=10_000)
    args = ap.parse_args()

    doc = load(Path(args.artifact))
    rows = usable(doc)
    arms = sorted({o["arm"] for o in rows})
    labels: dict[str, str] = doc.get("arms", {})

    say("=" * 78)
    say("CLOSURE ABLATION - analysis")
    say("=" * 78)
    say(f"  artifact   {args.artifact}")
    say(f"  collected  {doc.get('at')}   model {doc.get('model')}"
        f"   shuffled {doc.get('shuffled')}")
    say(f"  usable     {len(rows)} of {len(doc.get('observations', []))}"
        f"   dropped arms {len(doc.get('dropped', []))}")

    clusters = len({(o["fault_class"], o["incident"]) for o in rows})
    say(f"  incidents  {clusters}  (the bootstrap unit; diagnoses within an "
        f"incident share a frame and are not independent)")
    say("")

    say("  closure on the DETECTOR's class, 95% cluster-bootstrap CI")
    say(f"  {'arm':4} {'label':30} {'rate':>6}  {'95% CI':>16} {'n':>5}")
    rates: dict[str, float] = {}
    for arm in arms:
        sub = [o for o in rows if o["arm"] == arm]
        rate, lo, hi = cluster_bootstrap(sub, PRIMARY, args.draws)
        rates[arm] = rate
        ceiling = perfect_arm_ceiling(sub, PRIMARY)
        note = ("" if ceiling != ceiling          # nan: not a perfect arm
                else f"  <- zero width because the arm is perfect; the"
                     f" 95% one-sided bound on its per-incident failure"
                     f" rate is {ceiling:.3f}")
        say(f"  {arm:4} {labels.get(arm, '')[:30]:30} {rate:6.2f}"
            f"  [{lo:.2f}, {hi:.2f}]{'':>4} {len(sub):>5}{note}")

    spread = within_cell_variance(rows, PRIMARY)
    say("")
    say(f"  within-cell spread across repetitions: {spread:.2f}")
    say("    (mean max-min within one incident+arm. If this is as large as")
    say("     the A-to-B gap below, that gap is sampling noise - which")
    say("     EXPERIMENT_CLOSURE_ABLATION.md section 7 names as a refutation.)")

    say("")
    say("  OUTCOME SPLIT - an abstention is not an error (section 13.1)")
    say(f"  {'arm':4} {'correct':>9} {'abstained':>11} {'confident wrong':>16}"
        f" {'mean conf':>10}")
    for arm in arms:
        sub = [o for o in rows if o["arm"] == arm]
        ok = sum(1 for o in sub if o["named"] == o["fault_class"])
        abstained = sum(1 for o in sub if o["named"] in ABSTENTIONS)
        bad = [o for o in sub
               if o["named"] != o["fault_class"]
               and o["named"] not in ABSTENTIONS]
        mean_conf = (sum(float(o.get("confidence") or 0.0) for o in bad)
                     / len(bad)) if bad else 0.0
        say(f"  {arm:4} {ok:>9} {abstained:>11} {len(bad):>16}"
            f" {mean_conf:>10.2f}")
    say("    Only a confident wrong class executes a repair - an UNKNOWN")
    say("    diagnosis never does. An arm that abstains degrades safely.")

    say("")
    say("  PAIRED against arm A (McNemar, exact, two-sided)")
    cell = cells(rows, PRIMARY)
    for arm in [a for a in arms if a != "A"]:
        pairs = [(cell[k], cell[(k[0], k[1], arm)])
                 for k in cell
                 if k[2] == "A" and (k[0], k[1], arm) in cell]
        if not pairs:
            continue
        b, c, p = mcnemar(pairs)
        drop = rates.get("A", 0.0) - rates.get(arm, 0.0)
        say(f"    A vs {arm}: incidents={len(pairs):3}  drop={drop:+.2f}"
            f"  discordant b={b} c={c}  p={p:.4f}")

    say("")
    say("  PRE-REGISTERED VERDICT (prediction 2: arm B drops >= "
        f"{PREREGISTERED_DROP:.2f} and p < 0.05)")
    if "A" in rates and "B" in rates:
        pairs = [(cell[k], cell[(k[0], k[1], "B")])
                 for k in cell
                 if k[2] == "A" and (k[0], k[1], "B") in cell]
        _, _, p = mcnemar(pairs)
        drop = rates["A"] - rates["B"]
        met = drop >= PREREGISTERED_DROP and p < 0.05
        say(f"    drop {drop:+.2f}, p {p:.4f}  ->  "
            + ("MET: the bounded frame's curation saturates closure"
               if met else
               "NOT MET. Per section 7 this does not become a smaller claim by "
               "re-reading it; if arm B holds, curation is not the cause "
               "and section 4.4a's explanation is wrong."))
    else:
        say("    arms A and B are not both present")

    if clusters < 8:
        say("")
        say(f"  WARNING: {clusters} incidents is a pacing or smoke run. The "
            f"intervals above are reported for completeness and are not "
            f"evidence; section 5 asks for >= 15 incidents per class.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
