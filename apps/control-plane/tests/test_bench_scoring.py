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

from harness.report import CATALOGUE, Run  # noqa: E402
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


# --- self-consistency: measured, never gated --------------------------------


def _named(llm_class: str, fault_name: str) -> Run:
    r = Run(rep=1, fault_class="F06")
    r.llm_class = llm_class
    r.llm_fault_name = fault_name
    return r


def test_the_catalogue_is_parsed_from_the_prompt_the_model_reads() -> None:
    """Not re-typed. `diagnose.txt` is the list the model is told to copy a
    name out of, so it is the only authority on a correct pair; a constant
    here would be a copy that can drift from the prompt in use."""
    assert CATALOGUE["F06"] == "Retrieval collapse"
    assert CATALOGUE["F07"] == "Prompt version regression"
    assert {"F01", "F06", "F07", "F08"} <= set(CATALOGUE)


def test_an_answer_that_contradicts_itself_is_flagged() -> None:
    """The exact pair run B emitted thirteen times out of thirteen: the F06
    class code with F07's name beside it."""
    assert _named("F06", "Retrieval collapse").fault_name_coherent is True
    assert _named("F06", "Prompt version regression").fault_name_coherent is False
    assert _named("F07", "Prompt version regression").fault_name_coherent is True


def test_unjudgeable_is_none_and_never_false() -> None:
    """A diagnosis that never happened, or a class the catalogue does not
    list, is ABSENT. Reporting it as incoherent would invent a finding, which
    is the substitution ADR 0014 exists about."""
    assert _named("", "").fault_name_coherent is None
    assert _named("F06", "").fault_name_coherent is None
    assert _named("F99", "Something").fault_name_coherent is None


def test_coherence_is_scored_against_the_models_own_class_not_the_injected_one() -> None:
    """A different question from accuracy. This one asks only whether the
    answer agrees with itself: wrong about the world, right about its own
    claim, still counts as coherent."""
    r = _named("F07", "Prompt version regression")   # injected F06, so WRONG
    assert r.fault_class == "F06" and not r.diagnosis_correct
    assert r.fault_name_coherent is True


@pytest.mark.skipif(not ARTIFACT.exists(), reason="run B artifact not present")
def test_replaying_run_b_reproduces_thirteen_self_contradictions() -> None:
    """Pins the finding against the real file: every F06 diagnosis in the
    2026-10-20 bench carried F07's name, including three that healed."""
    rows: list[dict[str, Any]] = json.loads(
        ARTIFACT.read_text(encoding="utf-8"))["rows"]
    judged = incoherent = 0
    for row in rows:
        diag = row.get("diagnosis")
        if not diag:
            continue
        r = _named(str(diag.get("fault_class") or ""),
                   str(diag.get("fault_name") or ""))
        if r.fault_name_coherent is None:
            continue
        judged += 1
        if not r.fault_name_coherent:
            incoherent += 1
    assert (judged, incoherent) == (37, 13), (judged, incoherent)


# --- audit completeness -----------------------------------------------------
#
# FOUND 2026-11-03. The metric could not fail. `report.py` counted every
# `execute_done` in the newest 500 rows of the audit log and rendered
# `pct(min(that, executed), executed)`. The log is shared and persistent -
# 997 records over sixteen days, 56 `execute_done` among the newest 500 -
# while a 20-rep bench executes at most 20 times, so the `min` always
# returned `executed` and the figure was always 100%. Four runs reported
# "audit completeness 100%, met" and not one of them measured anything.
#
# It is now per-incident. These pin the scoping, which is the whole fix:
# a row for a DIFFERENT incident must not satisfy this incident.


def _audit_body(rows: list[dict[str, str]]) -> tuple[int, dict[str, Any]]:
    return 200, {"rows": rows, "chain_intact": True}


def test_an_execution_is_recorded_only_by_its_own_incidents_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug, pinned. Another incident's `execute_done` used to count."""
    import harness.report as rep

    monkeypatch.setattr(rep, "api", lambda *a, **k: _audit_body([
        {"incident_id": "other-1", "event": "execute_done"},
        {"incident_id": "other-2", "event": "execute_done"},
        {"incident_id": "mine", "event": "execute_start"},
    ]))
    assert rep.audit_has_execution("mine") is False, (
        "two unrelated execute_done rows satisfied this incident, which is "
        "exactly how the log-wide count always reached 100%")

    monkeypatch.setattr(rep, "api", lambda *a, **k: _audit_body([
        {"incident_id": "other-1", "event": "execute_done"},
        {"incident_id": "mine", "event": "execute_done"},
    ]))
    assert rep.audit_has_execution("mine") is True


def test_a_start_without_a_done_is_not_a_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An action that began and never recorded finishing is the case the
    metric exists to catch."""
    import harness.report as rep

    monkeypatch.setattr(rep, "api", lambda *a, **k: _audit_body(
        [{"incident_id": "mine", "event": "execute_start"}]))
    assert rep.audit_has_execution("mine") is False


def test_an_unreachable_audit_log_is_an_unrecorded_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed. A bench run reports the miss rather than aborting, and
    never credits a record it could not read."""
    import harness.report as rep

    monkeypatch.setattr(rep, "api", lambda *a, **k: (503, {}))
    assert rep.audit_has_execution("mine") is False
    monkeypatch.setattr(rep, "api", lambda *a, **k: (200, "not a dict"))
    assert rep.audit_has_execution("mine") is False
    assert rep.audit_has_execution("") is False


# --- the catalogue, and its two copies --------------------------------------
#
# ADDED 2026-11-05. `report.py` derives CATALOGUE by PARSING `diagnose.txt`,
# and its docstring says why: the model is told to copy a name out of that
# list, so the prompt is the only authority on what a correct pair looks like,
# and "copies of this table are exactly how `RCA accuracy` once came to read
# the wrong field".
#
# It then names the two copies that already exist - in `dump_diagnoses.py` and
# `figures.py` - and nothing checks them against the prompt. All three agree
# today, at eight entries each; that was verified before this test was written.
#
# Why it matters more than the usual drift: the fault_name coherence result in
# REPORT_DRAFT.md §4.2 - 13 of 37 diagnoses naming a class other than the code
# they emitted - is SCORED against this mapping. If the table were wrong the
# finding would be measuring a mapping mismatch rather than model
# incoherence. `figures.py` is worse still, because it renders the figure that
# accompanies that text: a drifted copy there puts a figure and a sentence
# that disagree in front of a reviewer, with nothing failing.


def _copy_from(filename: str, pattern: str) -> dict[str, str]:
    import re

    text = (ROOT / "harness" / filename).read_text(encoding="utf-8")
    return dict(re.findall(pattern, text))


def test_the_catalogue_was_parsed_and_is_not_empty() -> None:
    """`_prompt_catalogue` returns {} rather than raising when the prompt's
    format moves - a measurement that cannot be taken is reported absent, not
    zero. That is right for the harness and would make every test below pass
    vacuously, so it is checked first."""
    assert CATALOGUE, (
        "report.py parsed no catalogue from diagnose.txt, so fault_name "
        "coherence is being scored against an empty mapping and every "
        "diagnosis is reported as unjudgeable")
    assert "F06" in CATALOGUE and "F07" in CATALOGUE


@pytest.mark.parametrize(
    "filename,pattern",
    [("dump_diagnoses.py", r'\("(F\d\d)",\s*"([^"]+)"\)'),
     ("figures.py",
      r'"(F\d\d)":\s*"((?:Primary|Retrieval|Prompt|Config|Container|Database'
      r'|Token)[^"]*)"')],
)
def test_a_copy_of_the_catalogue_agrees_with_the_prompt(
    filename: str, pattern: str,
) -> None:
    copy = _copy_from(filename, pattern)
    assert copy, (
        f"found no class-to-name table in {filename}; if it was removed, "
        f"delete this case, because as written it now checks nothing")

    wrong = {k: (v, CATALOGUE.get(k)) for k, v in copy.items()
             if CATALOGUE.get(k, "").strip() != v.strip()}
    assert not wrong, (
        f"{filename} disagrees with the catalogue in diagnose.txt, which is "
        f"the list the model is told to copy from: {wrong}. §4.2's "
        f"fault_name coherence result is scored against that mapping.")

    absent = sorted(set(CATALOGUE) - set(copy))
    assert not absent, (
        f"{filename} is missing {absent}, which the prompt offers the model. "
        f"A diagnosis naming one of those would be unscoreable there while "
        f"being scoreable in report.py.")
