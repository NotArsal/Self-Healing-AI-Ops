"""The A-Lock — writer exclusivity, `ARCHITECTURE.md` section 6.0.

One writer per project. The executor takes it before any mutation and the
rollback path takes the SAME lock, so execution and unwinding can never
interleave: an unwind that ran while a second action was mid-write would
restore a pre-state that no longer describes anything.

PROCESS-LOCAL, AND THAT IS A STATED LIMIT
A threading lock holds for the life of one control plane. The real guarantee is
a Postgres advisory lock, which survives a restart and covers replicas, and it
arrives with the database. Until then this closes the window that actually
exists - the console and a harness racing inside one process - and does not
close the one that does not exist yet.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class LockBusyError(RuntimeError):
    """Another writer holds the lock for this project."""


class WriterLock:
    """Per-project, non-reentrant, never blocking."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._holders: dict[str, str] = {}
        self._guard = threading.Lock()

    def _lock_for(self, project: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(project, threading.Lock())

    def holder(self, project: str) -> str:
        return self._holders.get(project, "")

    @contextmanager
    def hold(self, project: str, incident_id: str) -> Iterator[None]:
        """Acquire or raise. Never waits.

        Refusing beats queueing: a caller blocked on a lock has no way to
        report why it is stuck, and a second incident waiting to write to a
        target that is mid-repair should escalate rather than queue behind it.
        """
        lock = self._lock_for(project)
        if not lock.acquire(blocking=False):
            raise LockBusyError(
                f"{project} is being written by {self._holders.get(project, 'another incident')}; "
                f"{incident_id} will not interleave with it"
            )
        self._holders[project] = incident_id
        try:
            yield
        finally:
            self._holders.pop(project, None)
            lock.release()


writer_lock = WriterLock()
