from fastapi import FastAPI, HTTPException

app = FastAPI()

state = {
    "f01_active": False,
    "f03_active": False
}

@app.get("/healthz")
def healthz():
    if state["f03_active"]:
        raise HTTPException(status_code=500, detail="API Crash (F03)")
    return {"status": "ok"}

@app.get("/provider/status")
def provider_status():
    if state["f01_active"]:
        raise HTTPException(status_code=503, detail="Provider Outage (F01)")
    return {"status": "ok"}

@app.post("/inject/{fault}")
def inject_fault(fault: str):
    if fault.upper() == "F01":
        state["f01_active"] = True
    elif fault.upper() == "F03":
        state["f03_active"] = True
    else:
        raise HTTPException(status_code=400, detail="Unknown fault")
    return {"status": f"injected {fault}"}

@app.post("/revert/{fault}")
def revert_fault(fault: str):
    if fault.upper() == "F01":
        state["f01_active"] = False
    elif fault.upper() == "F03":
        state["f03_active"] = False
    else:
        raise HTTPException(status_code=400, detail="Unknown fault")
    return {"status": f"reverted {fault}"}

@app.get("/v1/query")
def query():
    if state["f03_active"]:
        raise HTTPException(status_code=500, detail="API Crash (F03)")
    if state["f01_active"]:
        raise HTTPException(status_code=503, detail="Provider Outage (F01)")
    return {"answer": "30 days"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
