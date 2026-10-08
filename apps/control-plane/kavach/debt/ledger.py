import time
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from pydantic import BaseModel

from kavach.api.db import get_db_session

class ActiveDebt(BaseModel):
    id: str
    incident_id: str
    action_name: str
    action_params: dict[str, Any]
    trigger_type: str
    trigger_condition: str
    created_at: float
    max_age_s: int
    status: str

async def record_debt_async(
    incident_id: str, action_name: str, action_params: dict[str, Any], debt_def: Any
) -> None:
    """Record a debt when an incident is mitigated, using Postgres."""
    debt_id = f"debt-{uuid4().hex[:8]}"
    trigger_cond = debt_def.trigger.condition if hasattr(debt_def, "trigger") else "unknown"
    max_age_s = debt_def.max_age_s if hasattr(debt_def, "max_age_s") else 86400
    
    # We will use raw SQL for simplicity, matching the pattern in incidents.py
    async with get_db_session() as session:
        import json
        await session.execute(
            text(
                "INSERT INTO remediation_debt (id, incident_id, action_name, action_params, trigger_type, trigger_condition, max_age_s, status) "
                "VALUES (:id, :inc, :act, :params, :tt, :tc, :age, :st)"
            ),
            {
                "id": debt_id,
                "inc": incident_id,
                "act": action_name,
                "params": json.dumps(action_params),
                "tt": "promql", # hardcoded for v1
                "tc": trigger_cond,
                "age": max_age_s,
                "st": "PENDING"
            },
        )
        await session.commit()

async def get_active_debts_async() -> list[ActiveDebt]:
    """Fetch all PENDING debts from Postgres."""
    async with get_db_session() as session:
        result = await session.execute(
            text("SELECT id, incident_id, action_name, action_params, trigger_type, trigger_condition, EXTRACT(EPOCH FROM created_at) as created_at, max_age_s, status FROM remediation_debt WHERE status = 'PENDING'")
        )
        rows = result.fetchall()
        
    debts = []
    for r in rows:
        debts.append(
            ActiveDebt(
                id=r.id,
                incident_id=r.incident_id,
                action_name=r.action_name,
                action_params=r.action_params if isinstance(r.action_params, dict) else {},
                trigger_type=r.trigger_type,
                trigger_condition=r.trigger_condition,
                created_at=r.created_at,
                max_age_s=r.max_age_s,
                status=r.status
            )
        )
    return debts

async def clear_debt_async(incident_id: str) -> None:
    """Mark debt as REPAID in Postgres."""
    async with get_db_session() as session:
        await session.execute(
            text("UPDATE remediation_debt SET status = 'REPAID' WHERE incident_id = :inc"),
            {"inc": incident_id}
        )
        await session.commit()

async def escalate_debt_async(incident_id: str) -> None:
    """Mark debt as ESCALATED in Postgres."""
    async with get_db_session() as session:
        await session.execute(
            text("UPDATE remediation_debt SET status = 'ESCALATED' WHERE incident_id = :inc"),
            {"inc": incident_id}
        )
        await session.commit()
