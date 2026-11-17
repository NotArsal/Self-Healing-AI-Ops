"""The incident lifecycle is one table, and every move goes through it (ADR 0030).

Before ADR 0030 an incident's status was set in 19 places across the loop,
the runner and the startup settle, and nothing said which moves were legal:
an APPROVED incident could have been set back to ESCALATED by any of them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kavach import loop
from kavach.loop import IllegalTransitionError, Incident, IncidentStatus, legal, transition

S = IncidentStatus

LEGAL = [
    (S.DETECTED, S.NO_FAULT), (S.DETECTED, S.ESCALATED), (S.DETECTED, S.HEALING),
    (S.HEALING, S.AWAITING), (S.HEALING, S.RESOLVED), (S.HEALING, S.ESCALATED),
    (S.AWAITING, S.APPROVED), (S.AWAITING, S.ESCALATED),
]


@pytest.mark.parametrize(("frm", "to"), LEGAL)
def test_every_move_the_loop_makes_is_legal(frm: IncidentStatus, to: IncidentStatus) -> None:
    inc = Incident(incident_id="INC-1", project="p", status=frm)
    transition(inc, to)
    assert inc.status is to


@pytest.mark.parametrize(("frm", "to"), [
    (S.RESOLVED, S.ESCALATED),   # a finished heal cannot be re-labelled
    (S.APPROVED, S.AWAITING),    # an approval cannot be taken back
    (S.ESCALATED, S.RESOLVED),
    (S.DETECTED, S.RESOLVED),    # nothing resolves without a repair
    (S.DETECTED, S.APPROVED),    # nothing is approved that was never parked
    (S.NO_FAULT, S.HEALING),
])
def test_an_illegal_move_is_refused_and_changes_nothing(
    frm: IncidentStatus, to: IncidentStatus,
) -> None:
    inc = Incident(incident_id="INC-1", project="p", status=frm)
    with pytest.raises(IllegalTransitionError, match=f"{frm} -> {to}"):
        transition(inc, to)
    assert inc.status is frm


def test_finished_states_have_no_way_out() -> None:
    for final in (S.NO_FAULT, S.RESOLVED, S.ESCALATED, S.APPROVED):
        assert not any(legal(final, to) for to in S)


def test_legal_reads_stored_strings_too() -> None:
    """The startup settle works on database rows, where status is a string."""
    assert legal("AWAITING_APPROVAL", S.APPROVED)
    assert not legal("RESOLVED", S.ESCALATED)
    assert not legal("not a status", S.ESCALATED)


def test_nothing_sets_a_status_except_transition() -> None:
    """The point of the table is lost the moment one write goes around it."""
    root = Path(loop.__file__).parent
    direct = re.compile(r"\.status\s*=\s*(loop\.)?IncidentStatus\.|\[\"status\"\]\s*=")
    offenders = [
        f"{path.relative_to(root)}:{n}"
        for path in root.rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if direct.search(line) and "def transition" not in line and "# lifecycle-ok" not in line
    ]
    assert not offenders, f"status set outside transition(): {offenders}"
