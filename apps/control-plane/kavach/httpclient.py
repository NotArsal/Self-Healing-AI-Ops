"""One shared HTTP client for everything that probes or writes to a target.

Opening a client per call opens a TCP connection per call. Each one then sits in
TIME_WAIT for minutes, and a single incident makes dozens: ten availability
probes, twenty golden-set queries, a read and a write per action, times every
retry of the unwind loop. On Windows the ephemeral port range is exhausted well
before that stops mattering, and `connect()` starts blocking -- which is why the
live test suite ran fine one test at a time and stalled partway through when run
as a file.

Sharing one client keeps the connections alive and reuses them. Timeouts differ
per call site, so they are passed per request rather than baked in here.
"""

from functools import lru_cache

import httpx

# Generous enough to hold a connection open across a whole incident, small
# enough not to look like a leak.
_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)

DEFAULT_TIMEOUT_S = 5.0


@lru_cache(maxsize=1)
def shared_client() -> httpx.Client:
    """The process-wide client. Deliberately never closed.

    It lives as long as the process and is safe to use from the thread pool the
    executor adapters run in.
    """
    return httpx.Client(timeout=DEFAULT_TIMEOUT_S, limits=_LIMITS)
