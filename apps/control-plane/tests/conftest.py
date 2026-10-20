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


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Skip `docker`-marked tests when there is no socket to talk to.

    Deliberately a SKIP, not an xfail and not a pass: a test that needs a
    daemon and cannot find one has not verified anything, and reporting it
    green would be the same class of error as the metric ADR 0014 withdrew.
    """
    global _DOCKER_PROBE
    if not any(item.get_closest_marker("docker") for item in items):
        return
    if _DOCKER_PROBE is None:
        _DOCKER_PROBE = _docker_unreachable()
    if not _DOCKER_PROBE:
        return
    skip = pytest.mark.skip(reason=_DOCKER_PROBE)
    for item in items:
        if item.get_closest_marker("docker"):
            item.add_marker(skip)
