import time
from typing import Any

from pydantic import BaseModel


class ActiveDebt(BaseModel):
    incident_id: str
    scenario_id: str
    fault_class: str
    created_at: float
    trigger_condition: str
    trigger_value: float
    max_age_s: int
    repayment_action: str

# In-memory ledger
_ledger: dict[str, ActiveDebt] = {}

def record_debt(incident_id: str, scenario_id: str, fault_class: str, debt_def: Any) -> None:
    """Record a debt when an incident is mitigated."""
    debt = ActiveDebt(
        incident_id=incident_id,
        scenario_id=scenario_id,
        fault_class=fault_class,
        created_at=time.time(),
        trigger_condition=debt_def.trigger.condition,
        trigger_value=debt_def.trigger.value,
        max_age_s=debt_def.max_age_s,
        repayment_action=debt_def.repayment_action
    )
    _ledger[incident_id] = debt

def get_active_debts() -> list[ActiveDebt]:
    return list(_ledger.values())

def clear_debt(incident_id: str) -> None:
    _ledger.pop(incident_id, None)
