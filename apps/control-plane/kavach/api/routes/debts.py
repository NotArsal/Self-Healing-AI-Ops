from typing import Any
from fastapi import APIRouter
from kavach.debt.ledger import _ledger

router = APIRouter(prefix="/debts", tags=["debts"])


@router.get("/")
def get_debts() -> list[dict[str, Any]]:
    return [debt.model_dump() for debt in _ledger.values()]
