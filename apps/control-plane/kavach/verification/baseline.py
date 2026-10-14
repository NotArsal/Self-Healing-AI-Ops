"""The healthy baseline an application was measured at during onboarding.

Deltas are only meaningful against a healthy reference. Measuring them against
the values observed at detection time compares a repair to the outage, which
makes a degraded repair look like an improvement.

Stored as a file beside the manifest rather than in Postgres: it is captured once
per onboarding, read on every verification, and belongs to the application rather
than to any incident.
"""

import json
from pathlib import Path

BASELINE_FILENAME = ".kavach_baseline.json"


def baseline_path(manifest_path: str | Path) -> Path:
    return Path(manifest_path).parent / BASELINE_FILENAME


def save_baseline(manifest_path: str | Path, measured: dict[str, float]) -> Path:
    path = baseline_path(manifest_path)
    path.write_text(json.dumps(measured, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_baseline(manifest_path: str | Path) -> dict[str, float] | None:
    """None when onboarding never captured one -- callers must not invent values."""
    path = baseline_path(manifest_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): float(v) for k, v in data.items()}
