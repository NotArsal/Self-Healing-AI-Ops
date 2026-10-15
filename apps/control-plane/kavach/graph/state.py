import operator
from typing import Annotated, TypedDict

from kavach.llm.rca import RCAResponse
from kavach.scenarios.schema import Scenario
from kavach.tnr.models import Action, UndoRecord


class IncidentState(TypedDict, total=False):
    scenario: Scenario
    incident_id: str

    # LLM Diagnosis
    diagnosis: RCAResponse | None

    # Detected fault class
    fault_class: str | None

    # Generated plan
    plan: list[Action]

    # Actions that passed the gate
    approved_actions: list[Action]

    # Execution & Reversibility
    undo_stack: Annotated[list[UndoRecord], operator.add]

    # Verification
    verification_passed: bool | None
    verification_deltas: dict[str, float] | None

    # Final Outcome
    outcome: str | None  # RESOLVED, MITIGATED, ESCALATED, UNRECOVERABLE

    # State tracking
    simulation_state: dict[str, str]

    mode: str | None
    idempotency_key: str | None
    # Loop tracking for circuit breaker
    loop_count: int

    # Sandbox Execution (F-SBX)
    sandbox_required: bool | None
    sandbox_passed: bool | None
    # The sandbox's own scratch state. Kept apart from simulation_state so a
    # sandbox run cannot leave a mutation behind in the incident it was meant to
    # protect -- it has no undo record, because nothing was applied.
    sandbox_state: dict[str, str]

    # State keys an unwind did not put back at their witnessed value. Appended to,
    # so a later successful unwind cannot erase an earlier failure. Non-empty means
    # UNRECOVERABLE: the undo stack is the core guarantee (AGENTS.md 4a) and an
    # unwind nobody checks is indistinguishable from no unwind at all.
    unwind_unrestored: Annotated[list[str], operator.add]

    # Risk tier of the diagnosed fault, from the catalogue. Drives the mode policy.
    risk_tier: str | None

    # Gate feedback
    gate_verdict: str | None
    gate_reason: str | None
