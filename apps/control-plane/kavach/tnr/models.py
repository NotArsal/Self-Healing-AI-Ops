from typing import Any

from pydantic import BaseModel


class Action(BaseModel):
    name: str
    params: dict[str, Any]


class UndoRecord(BaseModel):
    original_action: Action
    inverse_action: Action
    pre_state_witness: dict[str, Any]
    applied: bool = False


class Verdict(BaseModel):
    decision: str  # ALLOW, DENY
    reason: str | None = None
