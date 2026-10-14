from typing import Literal

from pydantic import BaseModel, Field


class InverseDef(BaseModel):
    name: str
    # Map inverse action parameters to original action's parameters or state
    # e.g. {"target": "$target"} means the inverse action's "target" gets the original action's "target" param
    params_mapping: dict[str, str] = Field(default_factory=dict)


class EffectDef(BaseModel):
    """How an action is realised against a live application.

    Without this, an action can only mutate Kavach's own simulated state dict --
    the gap logged as contract defects #3 and #4 during proof #2. `key` names an
    entry in the application's declared `reversible_state`, so the binding is
    data and the executor never dispatches on an action's name.
    """

    kind: Literal["reversible_state"]
    key: str
    # Template for the value to write; "$param" reads the action's param.
    value: str


class ActionDef(BaseModel):
    name: str
    inverse: InverseDef
    # Simple state mutations: keys are state variables, values are templates or constants
    # e.g. {"active_model": "$fallback"} means set active_model to the fallback param of the action
    mutations: dict[str, str] = Field(default_factory=dict)
    # Absent means the action is simulation-only; it cannot touch a live target.
    effect: EffectDef | None = None


class DetectDef(BaseModel):
    signal: str
    condition: str
    threshold_pct: float | None = None
    window_s: int | None = None
    requires: list[str] = Field(default_factory=list)


class RepairDef(BaseModel):
    action: str
    params: dict[str, str] = Field(default_factory=dict)


class FaultDef(BaseModel):
    fault_class: str
    name: str = ""
    applies_to_roles: list[str] = Field(default_factory=list)
    detect: DetectDef | None = None
    evidence: list[str] = Field(default_factory=list)
    repair: RepairDef | None = None
    verify: list[str] = Field(default_factory=list)
    risk: str = "LOW"
    # Legacy: keeping recommended_actions for backward compatibility if needed, though replaced by `repair`
    recommended_actions: list[str] = Field(default_factory=list)


class Catalogue(BaseModel):
    actions: dict[str, ActionDef] = Field(default_factory=dict)
    faults: dict[str, FaultDef] = Field(default_factory=dict)
