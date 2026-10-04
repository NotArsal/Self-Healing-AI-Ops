from pathlib import Path

import yaml
from pydantic import ValidationError

from kavach.scenarios.schema import Scenario


class ScenarioLoadError(Exception):
    pass


def load_scenario_from_yaml(file_path: str | Path) -> Scenario:
    path = Path(file_path)
    if not path.exists():
        raise ScenarioLoadError(f"Scenario file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ScenarioLoadError(f"Invalid YAML format: {e}")

    try:
        scenario = Scenario(**data)
    except ValidationError as e:
        raise ScenarioLoadError(f"Scenario schema validation failed:\n{e}")

    # P03: Health state exists for required services
    # We ensure that every service in 'services' has an entry in 'health'
    missing_health = set(scenario.services.keys()) - set(scenario.health.keys())
    if missing_health:
        raise ScenarioLoadError(f"Health state missing for services: {missing_health}")

    return scenario


def get_scenario_path(name: str) -> Path:
    """Resolve a scenario name like 'F01' to its YAML file in the scenarios directory."""
    root_dir = Path(__file__).parent.parent.parent.parent.parent
    scenarios_dir = root_dir / "scenarios"

    # Simple prefix matching for convenience
    for file in scenarios_dir.glob(f"{name}*.yaml"):
        return file

    for file in scenarios_dir.glob(f"{name}*.yml"):
        return file

    raise ScenarioLoadError(
        f"No scenario file matching '{name}' found in {scenarios_dir}"
    )


def load_scenario(name: str) -> Scenario:
    path = get_scenario_path(name)
    return load_scenario_from_yaml(path)
