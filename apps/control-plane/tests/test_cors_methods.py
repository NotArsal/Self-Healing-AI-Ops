"""The CORS method list must cover every method the console actually calls.

THE BUG THIS PINS, found 2026-11-03.

`ModeSwitch.tsx` calls `api.PUT("/v1/mode")`. The console runs on a different
origin from the API (3001 vs 8080) and sends `content-type: application/json`,
so the browser issues a CORS preflight - and `allow_methods` was
`["GET", "POST"]`. Measured against the live API from the console's own
origin, before the fix:

    OPTIONS /v1/mode      Access-Control-Request-Method: PUT   -> 400
    OPTIONS /v1/loop/run  Access-Control-Request-Method: POST  -> 200

So the mode selector failed every time a human clicked it, in the one
component a demo puts on screen.

WHY NOTHING CAUGHT IT, which is the more useful half. The vitest suite mocks
the API, so no preflight is ever issued. `make scenario` sets the mode from
Python, where CORS does not exist. Three clean rehearsals passed over this
bug because the only path that reaches it is a browser, and nothing in the
gate drives one. This test closes that gap without needing a browser: it
reads the methods out of the console's source and asserts the server permits
each one.

It is deliberately source-derived rather than a hardcoded list. A hardcoded
`{"GET", "POST", "PUT"}` here would pass while the console moved on to DELETE,
which is the same drift that produced the bug.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CONSOLE = ROOT / "apps" / "console"
MAIN = ROOT / "apps" / "control-plane" / "kavach" / "main.py"

# Methods a browser may send cross-origin WITHOUT a preflight, so they need no
# entry in `allow_methods` to work. Everything else does.
# https://fetch.spec.whatwg.org/#cors-safelisted-method
CORS_SAFELISTED = {"GET", "HEAD", "POST"}


def console_methods() -> set[str]:
    """Every HTTP method the console's generated client is called with."""
    found: set[str] = set()
    for path in CONSOLE.rglob("*.ts*"):
        if "node_modules" in path.parts or "generated" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        found |= set(re.findall(r"\bapi\.(GET|POST|PUT|DELETE|PATCH)\s*\(",
                                text))
    return found


def allowed_methods() -> list[str]:
    """The server's `allow_methods`, read from the source that configures it."""
    text = MAIN.read_text(encoding="utf-8")
    found = re.search(r"allow_methods=\[([^\]]*)\]", text)
    assert found, "main.py no longer configures CORS allow_methods"
    return re.findall(r'"([A-Z]+)"', found.group(1))


def test_the_console_calls_something() -> None:
    """A guard on the guard: if the scrape finds nothing, the test below would
    pass vacuously and prove the opposite of what it claims."""
    methods = console_methods()
    assert methods, (
        "found no api.<METHOD>( calls in the console; this test would then "
        "pass without checking anything")
    assert "GET" in methods, "a console that never reads is not this console"


def test_every_method_the_console_uses_is_permitted_cross_origin() -> None:
    used = console_methods()
    allowed = set(allowed_methods())
    needs_preflight = used - CORS_SAFELISTED
    missing = needs_preflight - allowed
    assert not missing, (
        f"the console calls {sorted(missing)} but kavach/main.py's CORS "
        f"allow_methods is {sorted(allowed)}. A cross-origin request with "
        f"one of those methods triggers a preflight the server will refuse, "
        f"so the control that uses it is broken in the browser while every "
        f"Python-driven test and rehearsal still passes.")


@pytest.mark.parametrize("method", sorted(CORS_SAFELISTED - {"HEAD"}))
def test_the_safelisted_methods_are_allowed_anyway(method: str) -> None:
    """GET and POST are safelisted, so they would work without being listed.
    They are listed regardless, and should stay listed - relying on the
    safelist is a subtlety nobody should have to know to read this config."""
    assert method in allowed_methods()


def test_a_real_preflight_succeeds_for_every_method_the_console_uses() -> None:
    """Drives the middleware, not the config literal.

    The test above reads `allow_methods` out of the source, which catches the
    list being wrong but not the middleware being absent, mounted after a
    route, or configured with an origin that does not match. This issues the
    actual OPTIONS preflight a browser would send, through the real app.

    Still not a browser - it cannot catch a console-side mistake - but it
    does cover the server half of the contract that three clean rehearsals
    walked straight past.
    """
    from fastapi.testclient import TestClient

    from kavach.config import Settings
    from kavach.main import create_app

    origin = Settings().console_origin
    if not origin:
        pytest.skip("CORS middleware is only mounted when console_origin is set")

    client = TestClient(create_app())
    failures: list[str] = []
    for method in sorted(console_methods() - CORS_SAFELISTED):
        response = client.options(
            "/v1/mode",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type",
            },
        )
        allowed = response.headers.get("access-control-allow-methods", "")
        if response.status_code != 200 or method not in allowed:
            failures.append(
                f"{method}: HTTP {response.status_code}, "
                f"allow-methods={allowed!r}")
    assert not failures, (
        "a browser preflight from the console's own origin would be refused "
        "for: " + "; ".join(failures))
