import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from kavach.catalogue.schema import ActionDef, Catalogue, FaultDef


class CatalogueValidationError(Exception):
    pass


def _merged(existing: BaseModel | None, data: dict[str, Any]) -> dict[str, Any]:
    """Overlay a later definition on an earlier one, field by field.

    Assignment replaced the whole entry, so a per-fault file that redefined F03
    without a `risk` or a `detect` silently dropped core.yaml's. Every fault then
    loaded as LOW, which made `sandbox_required` unreachable for every real
    fault. Only fields the later file actually declares override.
    """
    if existing is None:
        return data
    return {**existing.model_dump(), **data}


_CATALOGUE_CACHE: Catalogue | None = None


def load_catalogue(
    base_dir: str | None = None, app_roles: set[str] | None = None
) -> Catalogue:
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

            # Sorted, because the overlay order below is the file order and
            # glob's is the filesystem's: core.yaml must be read before f03.yaml.
            for filepath in sorted(root_dir.glob("**/*.yaml")):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

                    for act_data in data.get("actions", []):
                        act = ActionDef(
                            **_merged(
                                catalogue.actions.get(act_data.get("name", "")),
                                act_data,
                            )
                        )
                        catalogue.actions[act.name] = act

                    for f_data in data.get("faults", []):
                        if "id" in f_data and "fault_class" not in f_data:
                            f_data["fault_class"] = f_data.pop("id")
                        fault = FaultDef(
                            **_merged(
                                catalogue.faults.get(f_data.get("fault_class", "")),
                                f_data,
                            )
                        )
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
            if f_def.applies_to_roles and not set(f_def.applies_to_roles).intersection(
                app_roles
            ):
                continue
            filtered.faults[f_class] = f_def
        return filtered

    return catalogue


def reset_catalogue() -> None:
    global _CATALOGUE_CACHE
    _CATALOGUE_CACHE = None
