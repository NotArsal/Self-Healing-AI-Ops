import os
from pathlib import Path

import yaml

from kavach.catalogue.schema import ActionDef, Catalogue, FaultDef


class CatalogueValidationError(Exception):
    pass


_CATALOGUE_CACHE: Catalogue | None = None


def load_catalogue(base_dir: str = "catalogue_data") -> Catalogue:
    """Loads all yaml files in the catalogue directory and merges them."""
    global _CATALOGUE_CACHE
    if _CATALOGUE_CACHE:
        return _CATALOGUE_CACHE

    root_dir = Path(os.getcwd()) / base_dir
    catalogue = Catalogue()

    if not root_dir.exists():
        return catalogue

    for filepath in root_dir.glob("**/*.yaml"):
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

            for act_data in data.get("actions", []):
                act = ActionDef(**act_data)
                catalogue.actions[act.name] = act

            for f_data in data.get("faults", []):
                fault = FaultDef(**f_data)
                catalogue.faults[fault.fault_class] = fault

    # Validate inverses exist
    for act_name, act in catalogue.actions.items():
        if act.inverse.name != "noop" and act.inverse.name not in catalogue.actions:
            raise CatalogueValidationError(
                f"Action '{act_name}' specifies inverse '{act.inverse.name}', but it is not defined in the catalogue."
            )

    _CATALOGUE_CACHE = catalogue
    return catalogue


def reset_catalogue() -> None:
    global _CATALOGUE_CACHE
    _CATALOGUE_CACHE = None
