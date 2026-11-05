"""A loopback default must be overridden for the container, or it means the container.

THE BUG CLASS THIS CLOSES AT THE SOURCE, added 2026-11-05.

On 2026-11-03 the console's onboarding page reported "Preflight blocked - 3 of
20 checks" against a target whose every container was up and healthy. The
cause was not in preflight: the addresses it probed were loopback, it ran
inside the control-plane container, and `localhost` there is the container.
`test_preflight_relocate.py` and `test_preflight_live.py` pin that fix.

This pins the thing that made it possible, one level up. `config.py` writes
its defaults from the HOST's point of view, which is right - `make onboard`,
the harness and a developer's shell all run there. Compose then overrides each
of them for the container. Nothing checked that it still did.

So the next instance of the bug is not a repeat of the old one. It is someone
adding a setting to `config.py` with a sensible `http://localhost:...`
default, not adding a line to the api service's environment, and shipping a
control plane that quietly dials itself. Everything passes: the field has a
default, the host-side tooling works, and the containerised API fails in a way
that looks like the dependency being down.

Seven settings currently carry a loopback default and all seven are
overridden, so this needs no exemption list. If one is ever genuinely meant to
stay loopback inside the container, that needs an argument in this file rather
than a quiet deletion - `console_origin` looks like such a case and is not
one, since the origin a browser sends is the browser's, not the API's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from kavach.config import Settings

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "infra" / "docker-compose.yml"
LOOPBACK = ("localhost", "127.0.0.1", "[::1]")


def api_environment() -> dict[str, Any]:
    """The api service's environment, as compose declares it.

    Compose accepts both a mapping and a `KEY=value` list. Only the mapping
    form is used here, but the list form is handled so that switching style
    does not silently empty this test.
    """
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    env = (doc.get("services", {}).get("api", {}) or {}).get("environment")
    if isinstance(env, dict):
        return env
    if isinstance(env, list):
        out: dict[str, Any] = {}
        for item in env:
            key, _, value = str(item).partition("=")
            out[key.strip()] = value
        return out
    return {}


def loopback_defaults() -> dict[str, str]:
    return {
        name: field.default
        for name, field in Settings.model_fields.items()
        if isinstance(field.default, str)
        and any(h in field.default for h in LOOPBACK)
    }


def test_the_compose_file_still_configures_the_api() -> None:
    """A guard on the guard. An empty read would make the test below pass by
    having nothing to check, which is how the audit-completeness metric
    managed to report 100% for four runs."""
    assert COMPOSE.is_file(), f"no compose file at {COMPOSE}"
    assert api_environment(), (
        "the api service declares no environment in docker-compose.yml, so "
        "this test cannot tell an override from an omission")
    assert loopback_defaults(), (
        "no setting has a loopback default any more; if that is real, this "
        "test is obsolete, but check the parsing first")


@pytest.mark.parametrize("name", sorted(loopback_defaults()))
def test_a_loopback_default_is_overridden_for_the_container(name: str) -> None:
    env = api_environment()
    key = f"KAVACH_{name.upper()}"
    assert key in env, (
        f"Settings.{name} defaults to {Settings.model_fields[name].default!r}, "
        f"which inside the control-plane container means the container "
        f"itself, and docker-compose.yml does not set {key} for the api "
        f"service. The containerised API will dial itself and report the "
        f"dependency as unreachable - the same defect that made the console "
        f"read 'Preflight blocked' against a healthy target on 2026-11-03. "
        f"Add {key} to the api service's environment, or argue in "
        f"test_container_addresses.py why this one is meant to stay loopback.")


def test_the_override_is_not_itself_loopback() -> None:
    """Present is not the same as correct.

    An override that repeats the host-side value is the bug with a line of
    YAML in front of it. The exception is an address the CONTAINER does not
    dial: `console_origin` is the Origin header a browser sends, so loopback
    is what it must be, and the API compares against it rather than
    connecting to it.
    """
    browser_facing = {"KAVACH_CONSOLE_ORIGIN"}
    env = api_environment()
    offenders = []
    for name in loopback_defaults():
        key = f"KAVACH_{name.upper()}"
        if key in browser_facing or key not in env:
            continue
        value = str(env[key])
        # `${VAR:-fallback}` - judge the fallback, which is what compose uses
        # when nothing is exported, and so what a default `make up` gets.
        fallback = value.split(":-", 1)[1].rstrip("}") if ":-" in value else value
        if any(h in fallback for h in LOOPBACK):
            offenders.append(f"{key}={fallback}")
    assert not offenders, (
        "these are overridden in compose but still resolve to loopback, so "
        "the override changes nothing and the container still dials itself: "
        + ", ".join(offenders))
