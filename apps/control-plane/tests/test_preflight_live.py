"""The API's preflight must agree with Docker about what is running.

THE BUG THIS PINS, found 2026-11-03 by opening the console in a browser.

The onboarding page read "Preflight blocked - 3 of 20 checks" while every
container of the target was up and healthy. Two of the three were
`service 'db' health` and `service 'frontend' health`, and both were false:
the manifest declares the target from the HOST (`tcp://localhost:5432`,
`http://localhost:3000/`) while `GET /v1/preflight` answers from inside the
control-plane container, where `localhost` is the container.

`test_preflight_relocate.py` pins the rewrite in isolation. This pins the
property that actually matters and that unit tests cannot see, because it
only exists when the two contexts are different: **a service whose container
Docker reports as running must not be reported down by the API's preflight.**

It is marked `docker` and skipped without a reachable API, so CI - which runs
`-m "not docker"` - is unaffected. Locally it runs in `make check`, which is
where this bug would have been caught on the day it was introduced instead of
surviving until somebody looked at the page.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

API = "http://127.0.0.1:8080"


def _get(path: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as r:
        data = json.load(r)
    return data if isinstance(data, dict) else {}


@pytest.mark.docker
def test_the_api_never_probes_a_service_at_its_own_loopback() -> None:
    """The invariant, stated so it does not depend on anything being up.

    Two earlier shapes of this test were wrong and both are worth recording.

    The first asserted "no service is down while some container is running".
    Stopping `rag_frontend` on purpose made it fail - but preflight calling a
    stopped service down is preflight being right. A test that fires on a
    true result is noise, and it gets deleted the first time someone takes a
    service down, taking the real check with it.

    The second wanted Docker's per-container running state, which
    `list_containers()` does not carry; reaching for the SDK directly is
    lint-banned, because `AGENTS.md` keeps the socket behind one adapter, and
    widening that module to satisfy a test is the wrong trade.

    What actually went wrong needs neither. The manifest declares the target
    from the HOST, and the API answers from inside a container, where
    `localhost` is the container. So: **a service probed at loopback by the
    containerised API is the bug**, whether or not that service is up. A
    stopped service still fails this check honestly, at the right address.
    """
    try:
        report = _get("/v1/preflight")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"no reachable Kavach API at {API}: {exc}")

    checks = report.get("checks") or []
    if not checks:
        pytest.skip(f"preflight returned no checks: {report.get('error', '')}")

    health = [c for c in checks
              if c.get("name", "").startswith("service ")
              and not c.get("skipped")
              and "skipped by design" not in c.get("detail", "")]
    if not health:
        pytest.skip("no live service health checks in this report")

    # The address actually probed is the last one named in the detail line:
    # either the declared URL, or the "probed as <url>" that replaced it.
    probing_itself = []
    for c in health:
        detail = c.get("detail", "")
        probed = detail.split("probed as ", 1)[1] if "probed as " in detail             else detail
        if any(h in probed.split(" ")[0] for h in ("localhost", "127.0.0.1")):
            probing_itself.append(f"{c['name']}: {detail}")

    assert not probing_itself, (
        "the API's preflight probed a service at loopback, which from inside "
        "the control-plane container means the control plane itself. This is "
        "the defect that made the console read 'Preflight blocked' against a "
        "healthy target - two services were reported down because nothing "
        "was listening on the container's own 5432 and 3000. " +
        " | ".join(probing_itself))


@pytest.mark.docker
def test_a_rewritten_probe_says_so() -> None:
    """Transparency, not just correctness. A check that silently probed a
    different address than the manifest declares would be a worse bug than
    the one it fixed - a reader would have no way to tell what was tested.
    """
    try:
        report = _get("/v1/preflight")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"no reachable Kavach API at {API}: {exc}")

    for c in report.get("checks") or []:
        detail = c.get("detail", "")
        if c.get("name", "").startswith("service ") and "probed as" in detail:
            assert "loopback is this container" in detail, (
                f"a probe was redirected without saying why: {detail!r}")
            break
