"""The live event bus behind the console's incident timeline.

In-process fan-out: one `asyncio.Queue` per connected WebSocket, plus a bounded
replay buffer so a console that connects mid-incident still sees the stages that
already happened instead of an empty timeline.

WHY NOT REDIS
`ARCHITECTURE.md` §4.3 names Redis pub/sub for this, and it is the right answer
the moment there is more than one control-plane process. There is one. Redis
would add a container, a dependency and a failure mode to move messages between
two objects in the same interpreter. Everything that would have to change is
behind `publish` and `subscribe` in this file.

# ponytail: single-process fan-out. Swap this module for Redis pub/sub when a
# second control-plane replica exists - the call sites do not change.

THREAD SAFETY MATTERS HERE
`loop.run_once` is synchronous and runs in a worker thread, so its events are
published from *off* the event loop. `publish_threadsafe` hops back onto the
loop with `call_soon_threadsafe`; calling `publish` directly from the worker
thread would mutate asyncio queues from the wrong thread.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from itertools import count
from typing import Any

# A slow or wedged browser must not grow memory without bound, and it must not
# be able to stall the healing loop. Both limits are deliberately small: the
# timeline for one incident is a couple of dozen events.
QUEUE_MAX = 256
REPLAY_MAX = 500


class EventBus:
    """Fan-out for loop progress events. One instance per process."""

    def __init__(self, replay_max: int = REPLAY_MAX) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._replay: deque[dict[str, Any]] = deque(maxlen=replay_max)
        self._seq = count(1)

    # --- producing ----------------------------------------------------------

    def publish(
        self,
        stage: str,
        status: str,
        message: str,
        incident_id: str = "",
    ) -> dict[str, Any]:
        """Record an event and hand it to every subscriber. Never blocks."""
        event = {
            "seq": next(self._seq),
            "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "incident_id": incident_id,
            "stage": stage,
            "status": status,
            "message": message,
        }
        self._replay.append(event)
        for q in list(self._subscribers):
            # Drop for this subscriber only. A console that cannot keep up loses
            # timeline lines; it does not slow the heal down, and it does not
            # take other consoles with it.
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)
        return event

    def publish_threadsafe(
        self,
        loop: asyncio.AbstractEventLoop,
        stage: str,
        status: str,
        message: str,
        incident_id: str = "",
    ) -> None:
        """Publish from a worker thread, onto `loop`."""
        loop.call_soon_threadsafe(
            self.publish, stage, status, message, incident_id
        )

    # --- consuming ----------------------------------------------------------

    def replay(self, after_seq: int = 0) -> list[dict[str, Any]]:
        return [e for e in self._replay if e["seq"] > after_seq]

    async def subscribe(self) -> AsyncGenerator[dict[str, Any], None]:
        """Yield events as they arrive. Unsubscribes on exit, including errors.

        Typed as an AsyncGenerator rather than an AsyncIterator so a caller can
        `aclose()` it. Breaking out of `async for` only suspends the generator,
        so the `finally` below has not run and the subscriber is still
        registered - a WebSocket handler that returns early would otherwise
        leak a queue that is filled forever and read by nobody.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()
