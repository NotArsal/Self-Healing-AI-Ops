"""The bench's own scoring, which has read the wrong field before.

`harness/report.py` produces every accuracy figure in `REPORT_DRAFT.md` and
nothing in `make check` covered it. That is how `RCA accuracy` once scored
the model against `incident.fault_class` - the DETERMINISTIC verdict, which
sits in the same record - and flattered it to a perfect score.

What is pinned here is the distinction the 2026-10-20 bench exposed: a
diagnosis carries a fault class AND a proposed repair, they can disagree,
and scoring only the class counts `(class right, action wrong)` as correct.
Replayed against the real artifact, not against invented rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.report import Run  # noqa: E402

from kavach.rca.validate import permitted_repair  # noqa: E402

ARTIFACT = ROOT / "harness" / "reports" / "diagnoses-20261020.json"


def _run(fault_class: str, llm_class: str, llm_action: str) -> Run:
    r = Run(rep=1, fault_class=fault_class)
    r.llm_class = llm_class
    r.llm_action = llm_action
    return r


def test_the_two_accuracies_are_scored_independently() -> None:
    both = _run("F06", "F06", "rollback_config")
    assert both.diagnosis_correct and both.action_correct

    # INC-210032, the incident that opened this: right class, forbidden
    # repair, accepted by the agreement rule and refused by repair_permitted.
    # The old scoring counted it in the 17/20 and it healed nothing.
    class_only = _run("F06", "F06", "rollback_prompt")
    assert class_only.diagnosis_correct, "the class WAS right"
    assert not class_only.action_correct, "a forbidden repair scored as correct"

    neither = _run("F07", "F06", "rollback_config")
    assert not neither.diagnosis_correct and not neither.action_correct


def test_the_action_is_scored_against_the_injected_class_not_the_claimed_one() -> None:
    """The whole point of the second figure.

    A model that names F06 and proposes `rollback_config` is internally
    consistent. On an injected F07 it is still wrong about the world, and
    scoring it against its own claim would measure coherence rather than
    accuracy - and would mark this row correct.
    """
    self_consistent_but_wrong = _run("F07", "F06", "rollback_config")
    assert not self_consistent_but_wrong.action_correct


def test_an_incident_that_never_reached_the_model_scores_no_action() -> None:
    assert not _run("F06", "", "").action_correct


def test_the_table_the_harness_consults_is_the_one_the_gate_consults() -> None:
    """A copied lookup that drifted is how the accuracy column read the wrong
    field once already. `report.py` imports `permitted_repair` rather than
    re-typing it, so this only checks the four implemented classes are in it."""
    table = permitted_repair()
    assert {"F01", "F06", "F07", "F08"} <= set(table)
    assert table["F06"] == "rollback_config"
    assert table["F07"] == "rollback_prompt"


@pytest.mark.skipif(not ARTIFACT.exists(), reason="run B artifact not present")
def test_replaying_run_b_reproduces_the_joint_distribution() -> None:
    """The regression guard, against the real file rather than fixtures.

    `diagnoses-20261020.json` holds all 37 diagnoses from the 2026-10-20
    bench. Scored the new way:

        class right, action right   31
        class right, action WRONG    1   <- the cell the old scoring hid
        class WRONG, action right    2   <- and the cell nobody predicted
        class WRONG, action wrong    3

    Both off-diagonal cells are populated, which is the result. **Action
    accuracy (33/37) is HIGHER than class accuracy (32/37)**: on two
    F07 injections the model named F06 and still proposed `rollback_prompt`,
    the correct F07 repair. The repair it reached for was right more often
    than the label it wrote, so the two are not one measurement with a
    rounding error - they are measuring different things, and the class is
    the weaker of the two.

    If these counts move without the artifact moving, the scoring changed
    meaning.
    """
    rows: list[dict[str, Any]] = json.loads(
        ARTIFACT.read_text(encoding="utf-8"))["rows"]

    joint: dict[tuple[bool, bool], int] = {}
    for row in rows:
        diag = row.get("diagnosis")
        detected = str(row.get("detection_class") or "")
        if not diag or not detected:
            continue
        # The detector is authoritative, and on this bench it was right on
        # all 20 injections - so its class stands in for the injected one.
        r = _run(detected, str(diag.get("fault_class") or ""),
                 str(diag.get("candidate_repair") or ""))
        key = (r.diagnosis_correct, r.action_correct)
        joint[key] = joint.get(key, 0) + 1

    assert sum(joint.values()) == 37, "the artifact is not run B"
    assert joint == {(True, True): 31, (True, False): 1,
                     (False, True): 2, (False, False): 3}, joint

    class_ok = joint[(True, True)] + joint[(True, False)]
    action_ok = joint[(True, True)] + joint[(False, True)]
    assert class_ok == 32
    assert action_ok == 33
    assert action_ok > class_ok, (
        "the finding is that the proposed repair was right MORE often than "
        "the fault class; if that inverts, the report's framing is stale")
