"""Preflight gave two different answers depending on where it ran.

THE BUG THIS PINS, found 2026-11-03 by opening the console in a real browser.

The onboarding page reported **"Preflight blocked - 3 of 20 checks"** against
a target whose every container was up and healthy. Two of the three were
`service 'db' health` and `service 'frontend' health`.

The manifest describes the target from the HOST - `tcp://localhost:5432`,
`http://localhost:3000/` - which is the correct thing for it to say, because
that is where the target publishes its ports and where `make onboard` runs.
But `GET /v1/preflight` is answered from inside the control-plane container,
where `localhost` is the container. Measured from in there: `localhost:5432`
and `localhost:3000` refuse, while `host.docker.internal` reaches both. So
the probe asked the control plane whether it was a Postgres, got
ECONNREFUSED, and reported the target's database down while it was serving.

The same check registry gave two different answers depending on where it ran,
and the console - the demo surface, and a P4 deliverable - gave the wrong one.
This is the second defect found by driving a real browser, after the CORS bug
that broke the mode switch. Both were invisible to all 563 gate tests.

WHAT MUST NOT CHANGE: the probe still opens a real socket. `relocate` moves
an address, it does not excuse a check. A service that is genuinely down
fails whether or not its URL was rewritten, and the rewrite is named in the
check's detail so no reader is told the declared address was probed when a
different one was.
"""

from __future__ import annotations

from kavach.onboarding.preflight import relocate


def test_a_loopback_host_is_moved_and_the_port_and_path_survive() -> None:
    assert relocate("tcp://localhost:5432", "host.docker.internal") == (
        "tcp://host.docker.internal:5432", True)
    assert relocate("http://127.0.0.1:3000/", "host.docker.internal") == (
        "http://host.docker.internal:3000/", True)
    assert relocate("http://localhost:8000/healthz", "evidence.host") == (
        "http://evidence.host:8000/healthz", True)


def test_the_host_side_cli_is_untouched() -> None:
    """No `service_host` means probe exactly what the manifest declares, so
    `make onboard` keeps measuring what it measures today."""
    for url in ("tcp://localhost:5432", "http://127.0.0.1:3000/"):
        assert relocate(url, "") == (url, False)


def test_a_non_loopback_address_is_never_rewritten() -> None:
    """A manifest that already names a reachable host means it; silently
    redirecting that would probe something the operator did not ask about."""
    for url in ("tcp://db.internal:5432", "http://10.0.0.4:3000/",
                "http://rag_backend:8000/healthz"):
        assert relocate(url, "host.docker.internal") == (url, False)


def test_a_url_without_a_port_keeps_having_none() -> None:
    assert relocate("http://localhost/healthz", "elsewhere") == (
        "http://elsewhere/healthz", True)


def test_the_second_return_value_is_what_the_detail_line_reads() -> None:
    """`check_services` prints the rewrite only when one happened. If this
    flag were always True the page would claim a redirect that never
    occurred; always False and it would hide one that did."""
    _, moved = relocate("tcp://localhost:5432", "host.docker.internal")
    assert moved is True
    _, not_moved = relocate("tcp://db.internal:5432", "host.docker.internal")
    assert not_moved is False
