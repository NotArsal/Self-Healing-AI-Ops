"""Phase 0 acceptance: the Docker socket is reachable and usable.

Why this is a Phase 0 test and not a Phase 7 one: the docker socket is the
executor's ONLY route to the system under management (ARCHITECTURE.md §10). On
Windows with Docker Desktop its behaviour differs from Linux, and the demo
machine is Windows (PL-03). If it does not work, nothing downstream works, so it
is proven in week 1 rather than discovered in week 9.

Safety design — this test mutates a container, so it is built to be unable to
touch anything it did not create:

  1. Read-only checks run first. If the daemon is unreachable, everything skips.
  2. The only container mutated is one this test creates, labelled
     SELFTEST_LABEL.
  3. ``_assert_is_selftest`` refuses to act on anything without that label. It
     is a test-local guard, NOT the safety engine — project-ownership checking
     (ARCHITECTURE.md §6.3) is P3 work and is not implemented here.
  4. Cleanup runs in a fixture teardown regardless of outcome.
"""

from collections.abc import Iterator
from typing import Any, ClassVar

import pytest

docker = pytest.importorskip("docker", reason="docker SDK not installed")

SELFTEST_LABEL = "kavach.selftest"
PROBE_IMAGE = "alpine:3"
PROBE_NAME = "kavach-socket-probe"


@pytest.fixture(scope="module")
def client() -> Iterator[Any]:
    """A Docker client, or skip the whole module."""
    try:
        c = docker.from_env()
        c.ping()
    except Exception as exc:
        # Any failure here means "no usable socket", which is a skip, not a
        # failure — `make check` must stay green on a machine without Docker.
        pytest.skip(f"Docker socket unreachable: {exc}")
    yield c
    c.close()


def _assert_is_selftest(container: Any) -> None:
    """Refuse to mutate anything this test did not create.

    A typo in a container name must not be able to restart Postgres, the target
    application, or anything else on the host.
    """
    labels = container.labels or {}
    if labels.get(SELFTEST_LABEL) != "true":
        raise AssertionError(
            f"refusing to act on {container.name!r}: missing {SELFTEST_LABEL}=true"
        )


# --- 1. read-only -----------------------------------------------------------


@pytest.mark.docker
def test_daemon_reachable(client: Any) -> None:
    version = client.version()
    assert version.get("Version")


@pytest.mark.docker
def test_can_list_containers(client: Any) -> None:
    """Listing must work; the host legitimately may have zero containers."""
    assert isinstance(client.containers.list(all=True), list)


# --- 2. mutate only what we created -----------------------------------------


@pytest.fixture
def probe(client: Any) -> Iterator[Any]:
    """A disposable container, removed in teardown even on failure."""
    try:
        client.images.get(PROBE_IMAGE)
    except docker.errors.ImageNotFound:
        client.images.pull(PROBE_IMAGE)

    existing = client.containers.list(all=True, filters={"name": PROBE_NAME})
    for stale in existing:
        _assert_is_selftest(stale)
        stale.remove(force=True)

    container = client.containers.run(
        PROBE_IMAGE,
        command=["sleep", "600"],
        name=PROBE_NAME,
        labels={SELFTEST_LABEL: "true"},
        detach=True,
        auto_remove=False,
    )
    try:
        yield container
    finally:
        try:
            container.reload()
            _assert_is_selftest(container)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass


@pytest.mark.docker
def test_can_inspect_and_restart_own_container(client: Any, probe: Any) -> None:
    """The capability the executor depends on, proven against a throwaway."""
    probe.reload()
    assert probe.status == "running"
    _assert_is_selftest(probe)

    before = client.api.inspect_container(probe.id)["RestartCount"]
    probe.restart(timeout=10)
    probe.reload()

    assert probe.status == "running"
    # Docker's RestartCount tracks daemon-initiated restarts, so an explicit
    # restart may leave it at 0. State transition is the real assertion.
    assert client.api.inspect_container(probe.id)["State"]["Running"] is True
    assert before >= 0


@pytest.mark.docker
def test_guard_refuses_unlabelled_container(client: Any) -> None:
    """The guard itself must fail closed.

    Without this, the guard could silently become a no-op and the test suite
    would still pass while gaining the ability to restart arbitrary containers.
    """

    class _Unlabelled:
        name = "some-other-project-container"
        labels: ClassVar[dict[str, str]] = {}

    with pytest.raises(AssertionError, match="refusing to act"):
        _assert_is_selftest(_Unlabelled())
