from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kavach.main import app
from kavach.scenarios.loader import ScenarioLoadError, load_scenario_from_yaml

client = TestClient(app)


def test_f01_scenario_loads() -> None:
    root_dir = Path(__file__).parent.parent.parent.parent
    f01_path = root_dir / "scenarios" / "F01.yaml"

    # Should not raise an exception
    scenario = load_scenario_from_yaml(f01_path)

    assert scenario.id == "scenario-f01-demo"
    assert scenario.fault_class == "F01"
    assert len(scenario.services) == 5
    assert scenario.health["model_primary"] == "unhealthy"


def test_scenario_api() -> None:
    response = client.get("/scenarios/F01")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "scenario-f01-demo"


def test_scenario_validate_api() -> None:
    response = client.post("/scenarios/F01/validate")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "Scenario scenario-f01-demo is valid.",
    }


def test_missing_health_raises_error(tmp_path: Path) -> None:
    yaml_content = """
id: test
fault_class: TEST
services:
  api:
    role: app
health: {}
    """
    p = tmp_path / "test.yaml"
    p.write_text(yaml_content)

    with pytest.raises(ScenarioLoadError, match="Health state missing for services"):
        load_scenario_from_yaml(p)
