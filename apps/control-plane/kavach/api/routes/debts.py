from typing import Any

from fastapi import APIRouter

from kavach.debt.ledger import get_active_debts_async

router = APIRouter(prefix="/debts", tags=["debts"])


@router.get("/")
async def get_debts() -> list[dict[str, Any]]:
    debts = await get_active_debts_async()
    return [debt.model_dump() for debt in debts]

