"""The sandbox: an isolated clone of the target, for trying a repair first.

`permit()` already returns `REQUIRE_SANDBOX` — for a HIGH-tier action after
approval, and for a MEDIUM one in AUTONOMOUS (`safety/engine.py`). Until now
nothing answered that verdict, so it was a decision with no destination.
This is the destination.

WHAT A SANDBOX IS HERE
A second compose project, `kavach-sandbox`, defined by
`infra/sandbox-compose.yml`: the target's own backend image built from the
same context, its own Postgres, its own volume, its own prompts directory,
and every host port remapped. Production holds 5432, 8000, 3000 and 8474,
so a clone that reused them could not start, and a safety mechanism that
cannot start is not one.

It deliberately omits the frontend (the sandbox verifies answers through the
API, not a UI) and Toxiproxy (that exists to INJECT endpoint faults, and the
sandbox is for trying repairs). The backend talks to the host Ollama
directly, which is also one less moving part.

THE PART THAT IS EASY TO GET WRONG IS STATE
A fresh clone has an empty corpus, and a fast set run against an empty
corpus fails for a reason that has nothing to do with the repair being
tried. `seed()` copies the target's `document_chunks` across with
`pg_dump --data-only`, read through the adapter's read-only path. Thirty
rows; it costs a second and it is the difference between a verification that
means something and one that does not.

`PRD.md` §12 predicted this: *"Sandbox cloning is harder than it looks
(ports, volumes, state)."* All three were real. Ports collide, the target's
`container_name` is hardcoded and globally unique in Docker so a compose
override collides on the name, compose APPENDS volume lists so an override
would have mounted two things on `/app/prompts`, and the corpus does not
come for free.

WHAT THIS MODULE MAY NOT DO
Every container operation goes through `executor/adapters/docker.py`
(`AGENTS.md` rule 14), whose guard refuses any compose project that is not
`kavach-sandbox`. This module cannot reach the target's containers even by
mistake — and a sandbox that destroyed the system it exists to protect
would be the worst failure available to it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kavach.executor.adapters import docker
from kavach.target import TargetEndpoints

SANDBOX_COMPOSE = "infra/sandbox-compose.yml"
SANDBOX_BACKEND = "kavach_sandbox_backend"
SANDBOX_DB = "kavach_sandbox_db"
SANDBOX_HEALTH = "http://127.0.0.1:18000/healthz"
SANDBOX_CHAT = "http://127.0.0.1:18000/v1/chat"
SANDBOX_CONFIG = "http://127.0.0.1:18000/v1/admin/config"
SANDBOX_PROMPTS = "infra/sandbox-prompts"

# The target's containers, read from only, and only to copy the corpus.
TARGET_DB = "rag_db"


class SandboxError(RuntimeError):
    """The sandbox could not be created, seeded or verified."""


@dataclass
class SandboxState:
    created: bool = False
    healthy: bool = False
    corpus_rows: int = 0
    seconds: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """A sandbox is usable only if it is healthy AND holds the corpus.

        Both halves matter. A healthy sandbox with no corpus answers every
        question with "I don't know", so a repair tried in it would look
        like a failure whatever it did.
        """
        return self.created and self.healthy and self.corpus_rows > 0


def _root() -> Path:
    """The repository root, found by looking for the compose file itself.

    NOT `parents[N]`. The first version counted wrong - `parents[3]` is
    `apps/`, not the root - and a test caught it. A magic index silently
    means a different directory the moment a file moves; searching for the
    artifact that has to be there cannot.

    Not a setting either: `KAVACH_KAVACH_ROOT` is `/app` inside the API
    container, where `infra/` is not mounted. The sandbox is a host-side
    operation regardless, since it drives the docker CLI.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / SANDBOX_COMPOSE).is_file():
            return parent
    raise SandboxError(
        f"cannot find {SANDBOX_COMPOSE} above {here}; the sandbox is a "
        f"host-side operation and needs the repository on disk"
    )


def _get_json(url: str, timeout: float = 10.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


# The sandbox backend's own healthcheck requires Ollama, so when Ollama is
# down the sandbox reports "container is unhealthy" and says nothing about
# why. That cost a diagnosis: the first time it happened the message sent me
# into container logs to find a dependency that was simply not running.
OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"


def ollama_reachable(timeout: float = 5.0) -> bool:
    """Is the model host up? Checked separately so a failure can say so."""
    try:
        _get_json(OLLAMA_TAGS, timeout)
        return True
    except Exception:
        return False


def health(timeout: float = 10.0) -> bool:
    try:
        return bool(_get_json(SANDBOX_HEALTH, timeout).get("status") == "ok")
    except Exception:
        return False


def corpus_rows() -> int:
    """How many chunks the sandbox database holds."""
    try:
        out = docker.exec_in(
            SANDBOX_DB, "psql", "-U", "postgres", "-d", "ragdb", "-tAc",
            "select count(*) from document_chunks;",
        )
        return int(out.strip() or 0)
    except Exception:
        return 0


def create(timeout_s: float = 600.0) -> None:
    """Bring the sandbox up, building the backend from the target's context."""
    root = _root()
    compose_file = root / SANDBOX_COMPOSE
    prompts = root / SANDBOX_PROMPTS
    prompts.mkdir(parents=True, exist_ok=True)
    docker.compose("up", compose_file, "-d", "--wait", timeout_s=timeout_s)


def destroy(remove_volumes: bool = True) -> None:
    """Tear the sandbox down.

    Volumes go with it by default: a sandbox that kept its database between
    runs would carry one run's repair into the next one's verification,
    which is the contamination this project has been bitten by six times in
    other forms.
    """
    args = ["-v"] if remove_volumes else []
    docker.compose("down", _root() / SANDBOX_COMPOSE, *args, timeout_s=180.0)


def seed(target_db: str = TARGET_DB) -> int:
    """Copy the target's corpus into the sandbox. Returns the row count.

    Read from production through the adapter's read-only path, which refuses
    any argv that could write. `--data-only` because the sandbox backend
    creates its own schema on startup; only the rows are missing.
    """
    dump = docker.read_from(
        target_db, "pg_dump", "-U", "postgres", "-d", "ragdb",
        "--data-only", "--table=document_chunks",
    )
    if "document_chunks" not in dump:
        raise SandboxError(
            "the dump from the target contains no document_chunks data; "
            "seeding would leave the sandbox unable to answer anything"
        )
    docker.exec_in(SANDBOX_DB, "psql", "-U", "postgres", "-d", "ragdb", "-q",
                   stdin=dump)
    return corpus_rows()


def ensure(wait_s: float = 180.0) -> SandboxState:
    """Create, seed and verify a sandbox, reusing a usable one.

    Idempotent on purpose. Creating a fresh clone costs a container build
    and a minute of startup; an incident that needs the sandbox twice should
    not pay that twice, and a sandbox left healthy from a previous incident
    is a sandbox, not a liability - `destroy()` is what makes it fresh.
    """
    state = SandboxState()
    t0 = time.perf_counter()
    try:
        # Before blaming the sandbox for being unhealthy, check the thing its
        # healthcheck depends on. A dependency that is simply not running
        # should not read as a broken clone.
        if not ollama_reachable():
            state.problems.append(
                "the model host at 127.0.0.1:11434 is not reachable, so the "
                "sandbox backend's healthcheck cannot pass. This is not a "
                "sandbox fault: start Ollama and try again"
            )
            return state
        if health():
            state.created = True
        else:
            create()
            state.created = True

        deadline = time.time() + wait_s
        while time.time() < deadline:
            if health():
                state.healthy = True
                break
            time.sleep(5)
        if not state.healthy:
            state.problems.append(
                f"sandbox did not become healthy within {wait_s}s")
            return state

        state.corpus_rows = corpus_rows()
        if state.corpus_rows == 0:
            state.corpus_rows = seed()
        if state.corpus_rows == 0:
            state.problems.append(
                "sandbox has no corpus after seeding; any verification run "
                "against it would fail for a reason unrelated to the repair")
    except docker.DockerAdapterError as exc:
        state.problems.append(f"docker: {exc}")
    except Exception as exc:
        state.problems.append(f"{type(exc).__name__}: {exc}")
    finally:
        state.seconds = round(time.perf_counter() - t0, 1)
    return state


def prompts_dir() -> Path:
    """The sandbox's OWN prompts directory.

    The whole reason the sandbox exists for `apply_patch`: a model-authored
    prompt written in here is physically incapable of reaching the target,
    because the two are different directories on different mounts.
    """
    return _root() / SANDBOX_PROMPTS


def endpoints() -> TargetEndpoints:
    """Where the sandbox answers, as a `TargetClient` can consume it.

    Built from this module's own constants rather than from settings: a
    caller that could point "the sandbox" at port 8000 by configuration is a
    caller that could run a model's patch against production by typo.
    """
    import os

    # Matches the fallback in `infra/sandbox-compose.yml` ON PURPOSE: compose
    # sets this inside the sandbox container and this client authenticates
    # against it, so the two defaults must be the same literal or the sandbox
    # is unusable when the variable is unset. See that file for why a default
    # is appropriate for the sandbox and not for `target_admin_token`.
    return TargetEndpoints(
        health=SANDBOX_HEALTH, chat=SANDBOX_CHAT, config=SANDBOX_CONFIG,
        admin_token=os.environ.get("KAVACH_ADMIN_TOKEN", "local-dev-token"),
    )
