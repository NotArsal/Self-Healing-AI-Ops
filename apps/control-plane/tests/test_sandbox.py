"""The sandbox, and the guard that matters more than the sandbox.

Most of this file is about what the docker adapter REFUSES. The sandbox's
job is to protect the system under management from an unproven repair, so a
sandbox operation that reached the target's containers would destroy the
thing it exists to protect. That is the worst failure available to this
component, and it is the one worth most of the tests.

The live half (does a clone actually come up, seed and answer?) is marked
`docker` and skipped without a socket, the same as `test_docker_socket.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from kavach.executor import sandbox
from kavach.executor.adapters import docker

# --- 1. the guard, which points the opposite way to every other one --------


@pytest.mark.parametrize("project", [
    "target_rag-app",      # the system under management
    "kavach",              # the control plane itself
])
def test_the_adapter_refuses_the_protected_projects(project: str) -> None:
    """`permit()` stops repairs reaching the wrong project. This stops the
    SANDBOX MACHINERY reaching it, which is a different direction of travel
    and needs its own guard."""
    with pytest.raises(docker.DockerAdapterError, match="refusing to operate"):
        docker.compose("down", Path("infra/sandbox-compose.yml"),
                       project=project)


@pytest.mark.parametrize("project", ["", "kavach-sandbox-2", "rag", "sandbox"])
def test_the_adapter_refuses_anything_that_is_not_the_sandbox(
    project: str,
) -> None:
    """An allow-list of exactly one, not a deny-list with gaps. A typo that
    happened to miss the deny-list must still be refused."""
    with pytest.raises(docker.DockerAdapterError):
        docker.compose("ps", Path("infra/sandbox-compose.yml"),
                       project=project)


def test_the_adapter_refuses_a_subcommand_outside_the_allow_list() -> None:
    """`docker compose` has subcommands that are not safe to expose, and a
    passthrough would be the arbitrary-execution path FR-27 forbids."""
    with pytest.raises(docker.DockerAdapterError, match="not allow-listed"):
        docker.compose("exec", Path("infra/sandbox-compose.yml"), "sh")


def test_exec_refuses_a_container_outside_the_sandbox() -> None:
    with pytest.raises(docker.DockerAdapterError, match="only sandbox"):
        docker.exec_in("rag_db", "psql", "-c", "drop table document_chunks;")


@pytest.mark.parametrize("argv", [
    ("psql", "-c", "delete from document_chunks;"),
    ("pg_dump", "--clean"),
    ("pg_restore",),
    ("bash",),
    ("sh", "-c", "rm -rf /"),
])
def test_the_read_only_path_refuses_anything_that_could_write(
    argv: tuple[str, ...],
) -> None:
    """`read_from` is the ONE function that may be pointed at the target, so
    it is the one that has to be narrow: a known reader, and no flag that
    turns a reader into a writer."""
    with pytest.raises(docker.DockerAdapterError, match="refusing"):
        docker.read_from("rag_db", *argv)


def test_the_read_only_path_allows_the_one_thing_seeding_needs() -> None:
    """It must still permit the dump, or the sandbox can never hold a corpus
    and every verification run in it is meaningless. Asserted on the GUARD,
    not by running docker: the call is expected to fail at the socket here."""
    with pytest.raises(docker.DockerAdapterError) as exc:
        docker.read_from("rag_db", "pg_dump", "-U", "postgres",
                         "--data-only", "--table=document_chunks")
    assert "refusing" not in str(exc.value), (
        "the guard rejected pg_dump, which seeding depends on"
    )


# --- 2. the sandbox is a different system from the target ------------------


def _compose() -> dict[str, Any]:
    """Read the sandbox compose file the same way the module finds it."""
    path = sandbox._root() / sandbox.SANDBOX_COMPOSE
    loaded: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded


def test_the_sandbox_shares_no_host_port_with_the_target() -> None:
    """Production holds 5432, 8000, 3000 and 8474. A clone that reused one
    could not start, and a safety mechanism that cannot start is not one."""
    target_ports = {"5432", "8000", "3000", "8474", "21434", "21435", "9090"}
    for name, svc in _compose()["services"].items():
        for mapping in svc.get("ports") or []:
            host = str(mapping).split(":")[0]
            assert host not in target_ports, (
                f"sandbox service {name} binds host port {host}, which the "
                f"target already holds"
            )


def test_the_sandbox_container_names_cannot_collide_with_the_target() -> None:
    """Container names are GLOBAL in Docker, not scoped per project, and the
    target hardcodes `rag_backend` and `rag_db`. This is why the sandbox is a
    standalone compose file rather than an override."""
    for name, svc in _compose()["services"].items():
        cn = svc.get("container_name", "")
        assert cn.startswith("kavach_sandbox"), (
            f"sandbox service {name} would create container {cn!r}, which is "
            f"not namespaced and could collide with the target"
        )


def test_the_sandbox_never_mounts_the_targets_prompts() -> None:
    """THE property `apply_patch` depends on. A model-authored prompt tried
    in the sandbox must be physically incapable of reaching production."""
    backend = _compose()["services"]["backend"]
    for mount in backend.get("volumes") or []:
        src = str(mount).split(":")[0]
        assert "Target_RAG-App" not in src and not src.endswith("/prompts"), (
            f"sandbox backend mounts {src!r}, which may be the target's own "
            f"prompts directory"
        )
    assert any("sandbox-prompts" in str(m) or "SANDBOX_PROMPTS" in str(m)
               for m in backend.get("volumes") or []), (
        "the sandbox backend must mount its OWN prompts directory"
    )


def test_the_sandbox_never_changes_the_embedding_model() -> None:
    """`AGENTS.md` denied mutation: changing EMBED_MODEL makes the target's
    db.py DROP TABLE document_chunks. The sandbox copies that table."""
    env = _compose()["services"]["backend"]["environment"]
    assert env["EMBED_MODEL"] == "nomic-embed-text"


def test_the_sandbox_runs_the_targets_own_backend_image() -> None:
    """A sandbox built from different source would verify a different
    application, and its verdict would mean nothing."""
    build = _compose()["services"]["backend"]["build"]
    assert "Target_RAG-App" in str(build.get("context", "")), (
        "the sandbox must build from the target's backend context"
    )


# --- 3. state, which is the half that is easy to forget --------------------


def test_a_sandbox_without_a_corpus_is_not_usable() -> None:
    """A healthy clone with an empty database answers every question with a
    refusal, so a repair tried in it looks like a failure whatever it did."""
    assert not sandbox.SandboxState(created=True, healthy=True,
                                    corpus_rows=0).usable
    assert sandbox.SandboxState(created=True, healthy=True,
                                corpus_rows=30).usable


def test_an_unhealthy_sandbox_is_not_usable() -> None:
    assert not sandbox.SandboxState(created=True, healthy=False,
                                    corpus_rows=30).usable


# --- 4. live, when a socket is present -------------------------------------


@pytest.mark.docker
def test_a_real_sandbox_comes_up_seeded_and_isolated() -> None:
    """The whole slice, end to end, against real containers."""
    state = sandbox.ensure()
    assert state.usable, f"sandbox not usable: {state.problems}"
    assert state.corpus_rows == 30, (
        f"sandbox holds {state.corpus_rows} chunks, expected the target's 30"
    )
    # Isolation, checked rather than assumed: the sandbox's prompts directory
    # is not the target's.
    assert "Target_RAG-App" not in str(sandbox.prompts_dir())
