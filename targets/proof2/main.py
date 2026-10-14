"""Proof #2 target application.

A deliberately small AI-ish service that is *honestly* recoverable: the injected
fault and the runtime configuration are separate pieces of state, so switching to
the backup model routes around a broken primary without pretending the primary
healed. That separation is what lets Kavach report MITIGATED-with-debt rather
than RESOLVED, and what makes the undo observable.
"""

import zlib

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# The injected fault, and the runtime config, are deliberately independent.
# `provider_primary_down` is the world being broken; `active_model` is the knob
# Kavach is allowed to turn. Collapsing these two is what made the previous
# version unable to express "mitigated but still degraded".
state: dict[str, object] = {
    "provider_primary_down": False,
    "api_down": False,
    "active_model": "primary",
}

# The backup model answers a deterministic minority of questions wrongly. The
# degradation is stipulated (this is a stub app); the *measurement* of it by the
# golden-set runner is real. crc32 keeps it stable across processes, unlike
# builtin hash(), which is salted per interpreter and would make the demo flicker.
# Tuned against targets/proof2/golden_set.yaml: 2 of its 20 cases answer wrongly,
# a 10% quality drop. That sits inside the declared 15% tolerance and above the
# 0.85 quality threshold, so F01 verifies as MITIGATED with a real negative
# quality delta. Changing the golden set may change this rate -- recheck it.
BACKUP_WRONG_MODULUS = 10
BACKUP_WRONG_REMAINDER = 0

GROUNDED_ANSWER = "30 days"
BACKUP_WRONG_ANSWER = "I am not able to determine that from the provided context."


def _backup_answers_wrongly(question: str) -> bool:
    return zlib.crc32(question.encode()) % BACKUP_WRONG_MODULUS == BACKUP_WRONG_REMAINDER


@app.get("/healthz")
def healthz() -> dict[str, str]:
    if state["api_down"]:
        raise HTTPException(status_code=500, detail="API unavailable")
    return {"status": "ok"}


@app.get("/provider/status")
def provider_status() -> dict[str, str]:
    """Health of the PRIMARY provider, independent of which model is active.

    This stays 503 after a successful switch to backup. That is the point: the
    debt trigger needs to observe the primary recovering, which is impossible if
    this endpoint reports the active model's health instead.
    """
    if state["provider_primary_down"]:
        raise HTTPException(status_code=503, detail="Primary provider unavailable")
    return {"status": "ok"}


@app.get("/v1/admin/model")
def get_model() -> dict[str, str]:
    return {"model": str(state["active_model"])}


class ModelReq(BaseModel):
    model: str


@app.post("/v1/admin/model")
def set_model(req: ModelReq) -> dict[str, str]:
    if req.model not in ("primary", "backup"):
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")
    state["active_model"] = req.model
    return {"status": "ok", "model": req.model}


class QueryReq(BaseModel):
    question: str = "What is the refund window?"


@app.post("/v1/query")
def query(req: QueryReq) -> dict[str, str]:
    if state["api_down"]:
        raise HTTPException(status_code=500, detail="API unavailable")

    active = str(state["active_model"])
    if active == "primary" and state["provider_primary_down"]:
        raise HTTPException(status_code=503, detail="Primary provider unavailable")

    if active == "backup" and _backup_answers_wrongly(req.question):
        return {"answer": BACKUP_WRONG_ANSWER, "model": active}

    return {"answer": GROUNDED_ANSWER, "model": active}


@app.post("/inject/{fault}")
def inject_fault(fault: str) -> dict[str, str]:
    match fault.upper():
        case "F01":
            state["provider_primary_down"] = True
        case "F03":
            state["api_down"] = True
        case _:
            raise HTTPException(status_code=400, detail="Unknown fault")
    return {"status": f"injected {fault}"}


@app.post("/revert/{fault}")
def revert_fault(fault: str) -> dict[str, str]:
    match fault.upper():
        case "F01":
            state["provider_primary_down"] = False
        case "F03":
            state["api_down"] = False
        case _:
            raise HTTPException(status_code=400, detail="Unknown fault")
    return {"status": f"reverted {fault}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
