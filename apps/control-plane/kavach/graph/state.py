import operator
from typing import Annotated, TypedDict

from kavach.llm.rca import RCAResponse
from kavach.scenarios.schema import Scenario
from kavach.tnr.models import Action, UndoRecord


class IncidentState(TypedDict, total=False):
    scenario: Scenario

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
    
    # Loop tracking for circuit breaker
    loop_count: int

    # Gate feedback
    gate_verdict: str | None
    gate_reason: str | None
