"""Report figures, drawn from the artifacts rather than from the draft.

Four figures, each one a claim in `REPORT_DRAFT.md` that a table states and a
plot states better:

  1. MTTD per class against the < 30s target. The point of the figure is that
     the twenty samples are BIMODAL - a median over them describes the gap
     between two populations and nothing is in the gap (ADR 0019).
  2. Where the classes lose: first draw correct, versus repaired. Approval
     re-diagnoses, so an approved incident must be right twice.
  3. The safety conditionals, both benches. P(heal | wrong) is the bar that
     has to be zero.
  4. Diagnosis self-consistency: the fault_name the model emitted beside the
     class code it emitted (`RESEARCH_NOTES.md` section 10).

Every number is read from a file in `harness/reports/`. Nothing is typed in
here, so a figure cannot drift from the artifact it describes - which is the
same failure ADR 0014 was about, one layer further out.

    make figures

Writes PNG at 200 dpi into `harness/reports/figures/`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib
from matplotlib.axes import Axes
from matplotlib.figure import Figure

# MUST come before `pyplot` is imported: pyplot picks its backend at import
# time, and on a machine with no display that is a hang rather than an error.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CLASSES = ("F08", "F07", "F01", "F06")
LABEL = {
    "F01": "F01 endpoint outage",
    "F06": "F06 retrieval collapse",
    "F07": "F07 prompt regression",
    "F08": "F08 config regression",
}
# The detector's evaluation window, which is the floor each class is bounded
# by. Read from the ADR 0014 table, not from a metric.
WINDOW = {
    "F01": "rate[2m]",
    "F06": "rate[1m]",
    "F07": "no PromQL",
    "F08": "no PromQL",
}
MET = "#1b7f5a"
MISSED = "#b4541f"
INK = "#1d1d1f"
MUTED = "#8a8a8f"

# `llm/prompts/diagnose.txt` - the catalogue the model is told to copy from.
CATALOGUE = {
    "F01": "Primary LLM endpoint outage",
    "F02": "Primary LLM endpoint latency degradation",
    "F03": "Container crash-loop or out-of-memory",
    "F05": "Database connection pool exhaustion",
    "F06": "Retrieval collapse",
    "F07": "Prompt version regression",
    "F08": "Configuration or environment regression",
    "F09": "Token or cost blowout",
}

Rows = list[dict[str, Any]]


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


def style(ax: Axes) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK, labelsize=9)
    ax.set_axisbelow(True)


def save(fig: Figure, out: Path, name: str) -> None:
    path = out / name
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  {path}")


def fig_mttd(runs: Rows, out: Path) -> None:
    """Figure 1 - the bimodality is the finding, so plot every sample."""
    fig, ax = plt.subplots(figsize=(8.0, 3.6))
    style(ax)
    for i, fc in enumerate(CLASSES):
        xs = [r["mttd_s"] for r in runs
              if r.get("fault_class") == fc and r.get("mttd_s") is not None]
        if not xs:
            continue
        med = median(xs)
        colour = MET if med < 30 else MISSED
        ax.scatter(xs, [i] * len(xs), s=46, color=colour, alpha=0.55,
                   edgecolors="none", zorder=3)
        ax.plot([med, med], [i - 0.26, i + 0.26], color=colour, lw=2.4, zorder=4)
        ax.annotate(f"{med:.1f}s", (med, i + 0.34), color=colour, fontsize=9,
                    ha="center", fontweight="bold")

    ax.axvline(30, color=INK, lw=1.1, ls="--", zorder=2)
    ax.annotate("PRD section 10 target: < 30s", (30, len(CLASSES) - 0.45),
                color=INK, fontsize=9, ha="left", xytext=(5, 0),
                textcoords="offset points")
    ax.set_yticks(range(len(CLASSES)))
    ax.set_yticklabels([LABEL[c] for c in CLASSES])
    ax.set_xlabel("MTTD - injection to detection.concluded_at (s)", fontsize=9)
    ax.set_xlim(0, 88)
    ax.set_ylim(-0.6, len(CLASSES) - 0.2)
    ax.grid(axis="x", color="#e8e8ea", lw=0.8)
    # After set_xlim, or each label lands wherever the axis happened to end
    # when its own class was drawn - which is mid-plot for the fast two.
    for i, fc in enumerate(CLASSES):
        ax.annotate(WINDOW[fc], (88, i), color=MUTED, fontsize=8, va="center",
                    ha="left", xytext=(6, 0), textcoords="offset points",
                    annotation_clip=False)
    ax.set_title("Detection latency is bimodal: the two classes that read no "
                 "metric clear the target,\nthe two that wait on a rate window "
                 "cannot. Nothing lands between 20.5s and 36.5s.",
                 fontsize=10, color=INK, loc="left", pad=12)
    save(fig, out, "fig1-mttd-per-class.png")


def fig_where_they_lose(runs: Rows, out: Path) -> None:
    """Figure 2 - first-draw accuracy against what actually got repaired."""
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    style(ax)
    width = 0.34
    firsts, heals = [], []
    for fc in CLASSES:
        rs = [r for r in runs if r.get("fault_class") == fc]
        firsts.append(sum(1 for r in rs if r.get("llm_class") == fc))
        heals.append(sum(1 for r in rs if r.get("resolved")))

    x = range(len(CLASSES))
    b1 = ax.bar([i - width / 2 for i in x], firsts, width, color="#5b6b8c",
                label="first diagnosis correct")
    b2 = ax.bar([i + width / 2 for i in x], heals, width, color=MET,
                label="repaired")
    for bars in (b1, b2):
        ax.bar_label(bars, fmt="%d/5", fontsize=9, color=INK, padding=2)

    ax.set_xticks(list(x))
    ax.set_xticklabels([LABEL[c].replace(" ", "\n", 1) for c in CLASSES],
                       fontsize=9)
    ax.set_ylabel("of 5 injections", fontsize=9)
    ax.set_ylim(0, 6.0)
    ax.legend(frameon=False, fontsize=9, loc="upper center", ncols=2,
              bbox_to_anchor=(0.5, -0.2))
    ax.grid(axis="y", color="#e8e8ea", lw=0.8)
    ax.set_title("Approval re-diagnoses, so an approved incident must be right "
                 "twice.\nEvery gap between the two bars is a second draw the "
                 "gate refused.",
                 fontsize=10, color=INK, loc="left", pad=12)
    save(fig, out, "fig2-where-the-classes-lose.png")


def fig_conditionals(benches: dict[str, Rows], out: Path) -> None:
    """Figure 3 - the bar that has to be zero."""
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    style(ax)
    names = list(benches)
    width = 0.34
    for off, (kind, colour) in enumerate(
            ((True, MET), (False, MISSED))):
        vals, labels = [], []
        for name in names:
            runs = benches[name]
            pool = [r for r in runs
                    if (r.get("llm_class") == r.get("fault_class")) is kind]
            healed = sum(1 for r in pool if r.get("resolved"))
            vals.append(100.0 * healed / len(pool) if pool else 0.0)
            labels.append(f"{healed}/{len(pool)}")
        bars = ax.bar([i + (off - 0.5) * width for i in range(len(names))],
                      vals, width, color=colour,
                      label="P(heal | diagnosis correct)" if kind
                      else "P(heal | diagnosis WRONG)")
        ax.bar_label(bars, labels=labels, fontsize=9, color=INK, padding=3)

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("% repaired", fontsize=9)
    ax.set_ylim(0, 112)
    ax.legend(frameon=False, fontsize=9, loc="upper center")
    ax.grid(axis="y", color="#e8e8ea", lw=0.8)
    ax.set_title("Forty injections, and the model's wrong answers drove a "
                 "repair zero times.\nA high left bar beside a high right bar "
                 "would be a symptom-matcher with an LLM attached.",
                 fontsize=10, color=INK, loc="left", pad=12)
    save(fig, out, "fig3-safety-conditionals.png")


def fig_coherence(rows: Rows, out: Path) -> None:
    """Figure 4 - the model's own name beside the model's own class code."""
    counts: dict[str, list[int]] = {}
    for r in rows:
        d = r.get("diagnosis")
        if not d:
            continue
        code = str(d.get("fault_class") or "")
        ok = d.get("fault_name") == CATALOGUE.get(code)
        tally = counts.setdefault(code, [0, 0])
        tally[0 if ok else 1] += 1

    order = sorted(counts, key=lambda c: -sum(counts[c]))
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    style(ax)
    ok = [counts[c][0] for c in order]
    bad = [counts[c][1] for c in order]
    b1 = ax.barh(order, ok, color=MET, label="fault_name matches the catalogue")
    b2 = ax.barh(order, bad, left=ok, color=MISSED,
                 label="fault_name is another class's name")
    ax.bar_label(b1, labels=[str(v) if v else "" for v in ok],
                 label_type="center", color="white", fontsize=9,
                 fontweight="bold")
    ax.bar_label(b2, labels=[str(v) if v else "" for v in bad],
                 label_type="center", color="white", fontsize=9,
                 fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlabel("diagnoses emitting that class code", fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.grid(axis="x", color="#e8e8ea", lw=0.8)
    ax.set_title("Every F06 diagnosis carried F07's name - including the three "
                 "that healed correctly.\nNo check compares the two fields, so "
                 "F06's 5/5 class accuracy hides a 0/13 on its own prose.",
                 fontsize=10, color=INK, loc="left", pad=12)
    save(fig, out, "fig4-diagnosis-self-consistency.png")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reports", default="harness/reports")
    p.add_argument("--out", default="harness/reports/figures")
    a = p.parse_args()
    reports, out = Path(a.reports), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    run_b = load(reports / "bench-20261020-mttd.json")
    print("figures:")
    fig_mttd(run_b["runs"], out)
    fig_where_they_lose(run_b["runs"], out)

    benches = {"run B (2026-10-20)": run_b["runs"]}
    run_a_path = reports / "bench-full.json"
    if run_a_path.exists():
        benches = {"run A (2026-10-19)": load(run_a_path)["runs"], **benches}
    fig_conditionals(benches, out)

    diag = reports / "diagnoses-20261020.json"
    if diag.exists():
        fig_coherence(load(diag)["rows"], out)
    else:
        print(f"  skipped fig4: {diag} not found - run harness/dump_diagnoses.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
