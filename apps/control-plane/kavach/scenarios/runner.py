import argparse
import sys

from kavach.scenarios.loader import ScenarioLoadError, load_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description="Kavach Scenario Runner")
    parser.add_argument(
        "name", help="Name or prefix of the scenario to load (e.g. F01)"
    )

    args = parser.parse_args()

    try:
        scenario = load_scenario(args.name)
        print(f"Success: Loaded and validated scenario: {scenario.id}")
        print(f"   Fault Class: {scenario.fault_class}")
        print(f"   Services: {len(scenario.services)}")
        print(f"   Health constraints: {len(scenario.health)}")
        if scenario.evidence:
            print(f"   Evidence items: {len(scenario.evidence)}")
    except ScenarioLoadError as e:
        print(f"Error: Failed to load scenario '{args.name}':\n{e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"Error: Unexpected error:\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
