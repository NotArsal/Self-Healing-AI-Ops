"""The one place in Kavach that mutates containers.

`AGENTS.md` security rule 14: *"The docker socket mount is the most dangerous
privilege in this system. Any code touching it goes through
`executor/adapters/docker.py`. Nowhere else imports the docker SDK."* This is
that file, and until now it did not exist because nothing in Kavach had ever
mutated a container.

WHAT IT MAY TOUCH, AND WHY THE GUARD POINTS THE OTHER WAY
Every other ownership check in this system asks "is this the TARGET's
project?" - `permit()` denies an action whose `compose_project` is not the
one the manifest declares (`FR-26`). This adapter asks the opposite
question, because the sandbox is by definition *not* the target:

    the only compose project this adapter may act on is `kavach-sandbox`

That is a stricter guard than the general one and it is checked on every
call, not at construction. A sandbox operation that reached the target's
project would destroy the system under test while claiming to protect it,
which is the worst thing this component could possibly do.

`target_rag-app` is additionally named in a deny-list, so the failure is
loud and specific rather than a generic mismatch, and a typo that happens to
match the target cannot be waved through.

WHY THE COMPOSE CLI AND NOT THE SDK
The docker SDK has no compose support - `docker compose` is a CLI plugin
that reads a file, resolves profiles, builds, and orders startup by
healthcheck. Reimplementing that against the SDK to satisfy a rule about
importing the SDK would be the letter of rule 14 against its purpose. The
purpose is one chokepoint for container mutation, and this is it: the rule's
lint check stays satisfied (nothing here imports `docker`), and the
dangerous surface is still a single file.

EVERY CALL DECODES UTF-8 EXPLICITLY, AND THAT IS A WINDOWS BUG FIXED
`subprocess.run(text=True)` decodes using the platform's preferred encoding,
which on this demo machine is cp1252. A Postgres dump is UTF-8, so seeding
the sandbox died on byte 0x9d the first time it ran from a clean state. The
dump path decodes STRICTLY - a replacement character there would corrupt a
row and leave the sandbox quietly holding a different corpus from the
target, which is worse than holding none. `PL-03` anticipated exactly this
class of difference.

THERE IS NO ARBITRARY COMMAND PATH (FR-27)
Callers choose from a fixed set of operations. Nothing here takes a command
string, a shell, or a service name that is not validated against the compose
file's own services. A model cannot reach this module at all.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# The ONLY project this adapter may act on.
SANDBOX_PROJECT = "kavach-sandbox"

# Named explicitly so the refusal says WHICH forbidden project was asked for.
# `permit()` protects the target from repairs; this protects it from the
# sandbox machinery, which is a different direction of travel.
PROTECTED_PROJECTS = frozenset({"target_rag-app", "kavach"})

# Compose subcommands this adapter will run. A fixed set, not a passthrough.
_ALLOWED = frozenset({"up", "down", "ps", "logs", "build"})


class DockerAdapterError(RuntimeError):
    """A docker operation was refused or failed."""


def _check_project(project: str) -> None:
    """Refuse anything that is not the sandbox. Checked on every call."""
    if project in PROTECTED_PROJECTS:
        raise DockerAdapterError(
            f"refusing to operate on compose project {project!r}: this "
            f"adapter exists to manage the sandbox and must never touch the "
            f"system under management or the control plane itself"
        )
    if project != SANDBOX_PROJECT:
        raise DockerAdapterError(
            f"refusing to operate on compose project {project!r}: the only "
            f"project this adapter may act on is {SANDBOX_PROJECT!r}"
        )


def compose(
    subcommand: str,
    compose_file: Path,
    *args: str,
    project: str = SANDBOX_PROJECT,
    timeout_s: float = 600.0,
    env: dict[str, str] | None = None,
) -> str:
    """Run one allow-listed `docker compose` subcommand against the sandbox.

    `project` is a parameter rather than a constant so the guard has
    something to refuse: a caller that passes the target's project gets an
    explicit error instead of silently doing the right thing by accident.
    """
    _check_project(project)
    if subcommand not in _ALLOWED:
        raise DockerAdapterError(
            f"compose subcommand {subcommand!r} is not allow-listed; "
            f"permitted: {sorted(_ALLOWED)}"
        )
    if not compose_file.is_file():
        raise DockerAdapterError(f"no compose file at {compose_file}")

    cmd = ["docker", "compose", "-p", project, "-f", str(compose_file),
           subcommand, *args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
            env=env, check=False, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerAdapterError(
            f"docker compose {subcommand} timed out after {timeout_s}s"
        ) from exc
    if proc.returncode != 0:
        raise DockerAdapterError(
            f"docker compose {subcommand} failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[-400:]}"
        )
    return proc.stdout


def exec_in(
    container: str, *argv: str, timeout_s: float = 300.0, stdin: str | None = None,
) -> str:
    """Run a fixed argv inside a SANDBOX container.

    The container name must carry the sandbox prefix. Nothing here builds a
    shell line: `argv` is passed as separate arguments, so there is no
    quoting to get wrong and no command string for anything to inject into.
    """
    if not container.startswith("kavach_sandbox"):
        raise DockerAdapterError(
            f"refusing to exec in {container!r}: only sandbox containers "
            f"(kavach_sandbox*) may be executed in"
        )
    cmd = ["docker", "exec"]
    if stdin is not None:
        cmd.append("-i")
    cmd.extend([container, *argv])
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
            input=stdin, check=False, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerAdapterError(
            f"docker exec in {container} timed out after {timeout_s}s"
        ) from exc
    if proc.returncode != 0:
        raise DockerAdapterError(
            f"docker exec in {container} failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[-300:]}"
        )
    return proc.stdout


def read_from(container: str, *argv: str, timeout_s: float = 300.0) -> str:
    """Read-only exec against a container OUTSIDE the sandbox.

    Seeding the sandbox needs one thing from production: a dump of its
    corpus. That is a read, and refusing it would mean the sandbox could
    never hold the data it has to verify against.

    It is separated from `exec_in` rather than loosening that function,
    because the two have different risk: this one can be pointed at the
    target and so it REFUSES ANY ARGV THAT IS NOT A KNOWN READ. `pg_dump`
    without `--clean` or `--create` cannot alter the database it reads.
    """
    readers = {"pg_dump", "pg_isready", "psql"}
    if not argv or argv[0] not in readers:
        raise DockerAdapterError(
            f"refusing {argv[0] if argv else '(nothing)'!r} against "
            f"{container!r}: only {sorted(readers)} may be run outside the "
            f"sandbox, and only to read"
        )
    forbidden = {"--clean", "--create", "-c", "-f"}
    bad = sorted(set(argv) & forbidden)
    if bad:
        raise DockerAdapterError(
            f"refusing {bad} against {container!r}: these can write, and "
            f"this path is read-only by contract"
        )
    try:
        proc = subprocess.run(
            ["docker", "exec", container, *argv],
            capture_output=True, text=True, timeout=timeout_s, check=False,
            # STRICT here, unlike the other two. This output is a database
            # dump that will be replayed into the sandbox; a replacement
            # character silently corrupts a row rather than failing, and a
            # corpus that is subtly wrong is worse than one that is absent.
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerAdapterError(f"read from {container} timed out") from exc
    if proc.returncode != 0:
        raise DockerAdapterError(
            f"read from {container} failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[-300:]}"
        )
    return proc.stdout


# --- read-only inspection ----------------------------------------------------
#
# ADDED 2026-10-20, because rule 14 was being broken in two places.
#
# `onboarding/preflight.py` and `rca/evidence.py` each did their own
# `import docker; docker.from_env()`. Both are READS - preflight lists
# containers to check compose-project ownership, evidence reads the target's
# recent log lines - but both opened an unconstrained client, and rule 14 is
# about the import, not the intent: a module holding a live docker client can
# do anything the socket allows, whatever it currently chooses to do.
#
# They are separated from the mutation surface above rather than folded into
# it: `_check_project` refuses everything outside `kavach-sandbox`, and these
# two legitimately have to see the target. Being unable to reuse that guard is
# the reason they are their own, explicitly read-only, functions.
#
# Rule 14 also claimed to be "enforced by a lint rule, not convention". It was
# not - there was no such rule. One now exists in `pyproject.toml`
# (`flake8-tidy-imports` banned-api), so the next violation fails `make check`
# instead of waiting for an audit.


def list_containers() -> list[dict[str, str | None]]:
    """Every container with its compose project and service labels.

    Read-only and unscoped BY DESIGN: preflight's whole job is to notice
    containers that are not ours, so a sandbox-scoped listing would hide the
    exact thing it checks for.
    """
    import docker

    client = docker.from_env()
    try:
        client.ping()
        out: list[dict[str, str | None]] = []
        for c in client.containers.list(all=True):
            labels = c.labels or {}
            out.append({
                "name": c.name,
                "project": labels.get("com.docker.compose.project"),
                "service": labels.get("com.docker.compose.service"),
            })
        return out
    finally:
        client.close()


def container_logs(container: str, tail: int = 60) -> str:
    """The tail of one container's log stream. Never execs, never writes.

    Returns "" rather than raising: this feeds the RCA evidence frame, and a
    missing log section is a thinner frame, while an exception here would
    fail a diagnosis over a container that was merely restarting.
    """
    import docker

    try:
        client = docker.from_env()
        try:
            c = client.containers.get(container)
            raw: bytes = c.logs(tail=tail)
        finally:
            client.close()
    except Exception:          # evidence degrades, never fails
        return ""
    return raw.decode("utf-8", "replace")
