import os
from pathlib import Path

import yaml

from kavach.catalogue.schema import ActionDef, Catalogue, FaultDef


class CatalogueValidationError(Exception):
    pass


_CATALOGUE_CACHE: Catalogue | None = None


def load_catalogue(base_dir: str | None = None, app_roles: set[str] | None = None) -> Catalogue:
    """Loads all yaml files in the catalogue directory and merges them."""
    global _CATALOGUE_CACHE
    if _CATALOGUE_CACHE:
        catalogue = _CATALOGUE_CACHE
    else:
        if base_dir is None:
            base_dir = os.environ.get("KAVACH_CATALOGUE_DIR", "catalogue_data")
    
        dirs_to_search = [d.strip() for d in base_dir.split(",")]
        catalogue = Catalogue()
    
        for d in dirs_to_search:
            root_dir = Path(os.getcwd()) / d
            if not root_dir.exists():
                continue
    
            for filepath in root_dir.glob("**/*.yaml"):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
        
                    for act_data in data.get("actions", []):
                        act = ActionDef(**act_data)
                        catalogue.actions[act.name] = act
        
                    for f_data in data.get("faults", []):
                        if "id" in f_data and "fault_class" not in f_data:
                            f_data["fault_class"] = f_data.pop("id")
                        fault = FaultDef(**f_data)
                        catalogue.faults[fault.fault_class] = fault
    
        # Validate inverses exist
        for act_name, act in catalogue.actions.items():
            if act.inverse.name != "noop" and act.inverse.name not in catalogue.actions:
                raise CatalogueValidationError(
                    f"Action '{act_name}' specifies inverse '{act.inverse.name}', but it is not defined in the catalogue."
                )
    
        _CATALOGUE_CACHE = catalogue

    if app_roles is not None:
        filtered = Catalogue(actions=catalogue.actions.copy())
        for f_class, f_def in catalogue.faults.items():
            if f_def.applies_to_roles and not set(f_def.applies_to_roles).intersection(app_roles):
                continue
            filtered.faults[f_class] = f_def
        return filtered

    return catalogue


def reset_catalogue() -> None:
    global _CATALOGUE_CACHE
    _CATALOGUE_CACHE = None
