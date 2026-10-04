from typing import Any
from pydantic import BaseModel, Field


class InverseDef(BaseModel):
    name: str
    # Map inverse action parameters to original action's parameters or state
    # e.g. {"target": "$target"} means the inverse action's "target" gets the original action's "target" param
    params_mapping: dict[str, str] = Field(default_factory=dict)


class ActionDef(BaseModel):
    name: str
    inverse: InverseDef
    # Simple state mutations: keys are state variables, values are templates or constants
    # e.g. {"active_model": "$fallback"} means set active_model to the fallback param of the action
    mutations: dict[str, str] = Field(default_factory=dict)


class FaultDef(BaseModel):
    fault_class: str
    # Recommended actions for this fault to be used by the planner
    recommended_actions: list[str] = Field(default_factory=list)


class Catalogue(BaseModel):
    actions: dict[str, ActionDef] = Field(default_factory=dict)
    faults: dict[str, FaultDef] = Field(default_factory=dict)
