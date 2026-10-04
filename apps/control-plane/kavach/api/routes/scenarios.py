from fastapi import APIRouter, HTTPException

from kavach.scenarios.loader import ScenarioLoadError, load_scenario
from kavach.scenarios.schema import Scenario

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("/{name}", response_model=Scenario)
async def get_scenario(name: str) -> Scenario:
    try:
        scenario = load_scenario(name)
        return scenario
    except ScenarioLoadError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/validate")
async def validate_scenario(name: str) -> dict[str, str]:
    try:
        scenario = load_scenario(name)
        return {"status": "ok", "message": f"Scenario {scenario.id} is valid."}
    except ScenarioLoadError as e:
        raise HTTPException(status_code=400, detail=str(e))
