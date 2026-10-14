"""Build an incident Scenario from an application's own `kavach.yaml`.

Proof #2 logged "no dynamic target resolution" as contract defect #1: incidents
could only come from scenario files Kavach shipped. Everything an incident needs
is already an obligation in the manifest, so this projects one onto the other and
no onboarded application needs a hand-written scenario.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from kavach.preflight.schema import KavachManifest
from kavach.scenarios.schema import (
    ObjectiveDef,
    PermissionDef,
    Scenario,
    ServiceDef,
    TargetBinding,
)


class TargetLoadError(Exception):
    pass


def load_target(manifest_path: str | Path) -> TargetBinding:
    path = Path(manifest_path)
    if not path.exists():
        raise TargetLoadError(f"Manifest not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise TargetLoadError(f"Invalid YAML in {path}: {e}") from e

    try:
        manifest = KavachManifest(**data)
    except ValidationError as e:
        raise TargetLoadError(f"Manifest failed validation:\n{e}") from e

    return TargetBinding(manifest_path=str(path.resolve()), manifest=manifest)


def scenario_from_target(
    target: TargetBinding,
    fault_class: str,
    measured: dict[str, float],
    health: dict[str, str],
    scenario_id: str,
) -> Scenario:
    """Project a manifest plus live measurements into an incident Scenario.

    `measured` carries the objective values observed at detection time, so the
    objectives on the resulting Scenario describe the breach that was actually
    seen rather than a value typed into a file.
    """
    manifest = target.manifest

    objectives: dict[str, ObjectiveDef] = {}
    if manifest.objectives:
        for name in ("availability", "latency", "quality", "cost"):
            metrics = getattr(manifest.objectives, name)
            if not metrics or name not in measured:
                continue
            # First declared metric per category; multi-metric categories are a
            # contract feature v1 does not consume yet.
            metric = metrics[0]
            objectives[name] = ObjectiveDef(
                value=measured[name],
                threshold=metric.threshold,
                weight=metric.weight,
                comparator=metric.comparator,
            )

    return Scenario(
        id=scenario_id,
        fault_class=fault_class,
        services={
            name: ServiceDef(role=svc.role, depends_on=svc.depends_on)
            for name, svc in manifest.services.items()
        },
        health=health,
        objectives=objectives or None,
        tolerance=(
            manifest.tolerance.model_dump(exclude_none=True)
            if manifest.tolerance
            else None
        ),
        permissions=PermissionDef(
            allowed_actions=manifest.permissions.allowed_actions,
            max_risk_tier=manifest.permissions.max_risk_tier,
            forbidden_services=manifest.permissions.forbidden_services,
        ),
        evidence=[],
        state={},
        debt=(
            {k: v.model_dump() for k, v in manifest.debt.items()}
            if manifest.debt
            else None
        ),
        target=target,
    )
