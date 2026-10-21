"""Test configuration.

The fault harness lives at the repository root, outside the control plane
(ARCHITECTURE.md §3), so that injection code can never be imported by the
shipped package. The tests do need it, so the repo root goes on sys.path here
rather than making `harness` a dependency of `kavach`.

IT ALSO MAKES THE `docker` MARKER MEAN WHAT IT SAYS. `pyproject.toml` declares
it as "requires a reachable Docker socket; skipped when absent", and until
2026-10-20 nothing skipped: the marker only labelled. `make test` runs a bare
`pytest -q`, so on a machine without Docker - or with Docker up but Ollama
down - `test_sandbox.py` asserted `state.usable` and FAILED the gate.

That contradicted a published promise. `AGENTS.md` PL-02 requires the suite to
run offline, `README.md` calls `make check` the gate, and the whole report
rests on a reviewer being able to clone and check the work. The gate passed
here only because this machine happens to run Docker and Ollama.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _docker_unreachable() -> str:
    """Empty string when the socket is usable, else why it is not.

    Probed once per session: `from_env()` plus `ping()` on a dead socket costs
    a connection timeout, and paying that per test would be slower than the
    tests being skipped.
    """
    try:
        import docker
    except ImportError:
        return "docker SDK not installed"
    try:
        client = docker.from_env()
        try:
            client.ping()
        finally:
            client.close()
    except Exception as exc:                      # any failure here is a skip
        return f"Docker socket unreachable: {type(exc).__name__}: {exc}"
    return ""


_DOCKER_PROBE: str | None = None


def _target_repo_missing() -> str:
    """Empty string when the target's manifest is readable, else why not.

    THE TARGET IS A SEPARATE REPOSITORY (`AGENTS.md`), not a submodule and not
    vendored, so a clone of Kavach alone does not have it. Three tests read its
    `kavach.yaml` to assert that Kavach's detector windows and permitted
    repairs still AGREE with what the target declares - which is a real and
    valuable check, and simply cannot run where the file is absent.

    Same contract as the docker probe: a test that cannot reach what it
    verifies is SKIPPED, never passed. CI reports these as skipped and says so
    in its summary rather than quietly reporting a smaller green suite.
    """
    try:
        from kavach.config import get_settings
        path = Path(get_settings().target_path) / "kavach.yaml"
    except Exception as exc:                       # misconfigured is also a skip
        return f"target manifest unreadable: {type(exc).__name__}: {exc}"
    if not path.is_file():
        return f"target repository not present: {path} does not exist"
    return ""


_TARGET_PROBE: str | None = None


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Skip `docker`-marked tests when there is no socket to talk to.

    Deliberately a SKIP, not an xfail and not a pass: a test that needs a
    daemon and cannot find one has not verified anything, and reporting it
    green would be the same class of error as the metric ADR 0014 withdrew.
    """
    global _DOCKER_PROBE, _TARGET_PROBE
    for marker, probe in (("docker", _docker_unreachable),
                          ("target_repo", _target_repo_missing)):
        if not any(item.get_closest_marker(marker) for item in items):
            continue
        cached = _DOCKER_PROBE if marker == "docker" else _TARGET_PROBE
        if cached is None:
            cached = probe()
            if marker == "docker":
                _DOCKER_PROBE = cached
            else:
                _TARGET_PROBE = cached
        if not cached:
            continue
        skip = pytest.mark.skip(reason=cached)
        for item in items:
            if item.get_closest_marker(marker):
                item.add_marker(skip)
