"""A target panel must draw the window its detector reads.

THE CLAIM THIS PINS, added 2026-11-05.

`REPORT_DRAFT.md` §7b states that the dashboard's target panels "reuse the
detectors' own PromQL verbatim, for the `ADR 0013` reason: a graph drawn from
a different window than the detector uses is a graph of a different fault."

That was true when checked and nothing asserted it. The dashboard is a JSON
file that Grafana itself can export after a UI edit, so the realistic drift is
not someone retyping an expression by hand - it is someone widening a range
selector in the browser, exporting, and committing a panel that no longer
shows what the detector decided on. `ADR 0013` is in this repository because a
window mismatch has already cost this project a wrong conclusion once.

DIRECTION MATTERS, and this asserts the useful one. It does not require every
detector query to appear on a panel: four of nine deliberately do not, because
they are inputs to a verdict rather than things worth graphing. It requires
the converse - **every panel that draws a target metric must draw it with an
expression some detector actually uses** - because that is the direction in
which a mismatch misleads a reader.
"""

from __future__ import annotations

import json
from pathlib import Path

from kavach.detection import endpoint_outage as f01
from kavach.detection import retrieval_collapse as f06

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD = ROOT / "infra" / "grafana" / "dashboards" / "kavach.json"

# A plain gauge, read straight off the target and used by no detector. It is
# on the corpus panel beside `ragapp_corpus_chunks` because the fingerprint is
# "30 chunks / 2 files" and showing one half of it would be worse than showing
# neither. Listed explicitly so that adding a second such exemption is a
# deliberate edit to this set rather than a silent widening.
NOT_A_DETECTOR_QUERY = {"ragapp_corpus_files"}


def _norm(expr: str) -> str:
    """Whitespace-insensitive, everything else exact.

    The detectors write their queries across several lines for readability and
    Grafana stores them with its own wrapping, so comparing raw strings would
    fail on formatting alone. Metric names, label matchers, range selectors
    and functions all still have to match exactly - which is the whole point.
    """
    return " ".join(expr.split())


def detector_queries() -> dict[str, str]:
    out: dict[str, str] = {}
    for module, label in ((f01, "F01"), (f06, "F06")):
        for key, expr in module.QUERIES.items():
            out[f"{label}.{key}"] = _norm(expr)
    return out


def panel_expressions() -> list[str]:
    doc = json.loads(DASHBOARD.read_text(encoding="utf-8"))

    def walk(node: object) -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            expr = node.get("expr")
            if isinstance(expr, str) and expr.strip():
                found.append(expr)
            for value in node.values():
                found += walk(value)
        elif isinstance(node, list):
            for value in node:
                found += walk(value)
        return found

    return walk(doc)


def test_the_dashboard_and_the_detectors_both_still_exist() -> None:
    """A guard on the guard. If either side came back empty the test below
    would pass by finding nothing to disagree about."""
    assert DASHBOARD.is_file(), f"no provisioned dashboard at {DASHBOARD}"
    assert panel_expressions(), "the dashboard declares no PromQL at all"
    assert detector_queries(), "the detectors declare no queries at all"


def test_every_target_panel_uses_a_detectors_own_expression() -> None:
    queries = set(detector_queries().values())
    offenders: list[str] = []
    checked = 0
    for raw in panel_expressions():
        expr = _norm(raw)
        if "ragapp_" not in expr:
            continue  # a Kavach self-metric; this test is about target panels
        if expr in NOT_A_DETECTOR_QUERY:
            continue
        checked += 1
        if expr not in queries:
            offenders.append(expr)

    assert checked, (
        "no panel draws a target metric, so this test checked nothing")
    assert not offenders, (
        "these panels draw a target metric with an expression no detector "
        "uses, so the graph and the verdict are reading different windows - "
        "which ADR 0013 records as having already produced one wrong "
        "conclusion in this project:\n  " + "\n  ".join(offenders))


def test_the_three_fault_signals_are_actually_on_a_panel() -> None:
    """The report names these as the target panels. If one is dropped from the
    dashboard the sentence in §7b stops being true, and a reviewer opening
    Grafana during the demo finds the fault it describes ungraphed."""
    queries = detector_queries()
    on_panel = {_norm(e) for e in panel_expressions()}
    for name in ("F01.llm_error_ratio", "F06.kept_chunks_mean",
                 "F06.empty_context_ratio"):
        assert queries[name] in on_panel, (
            f"{name} is no longer drawn by any panel, so REPORT_DRAFT.md "
            f"§7b's claim about the target panels is now false")
