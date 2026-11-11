"""F02 primary LLM endpoint latency degradation.

Adds a Toxiproxy `latency` toxic to the `ollama-primary` listener only, so
every model call the target makes through its configured `llm_base_url` is
answered, correctly, but late. The backup listener is never touched; it is
where the repair, `switch_llm_endpoint`, sends the target.

WHY 12s, MEASURED 2026-11-10 (`harness/sweep_f02_latency.py`,
`harness/reports/f02-latency-sweep.json`, 3 chats per value, jitter 0)

    added   chat wall time   generation calls > 8s   LLM errors
    0       6.2-10.1s        0/3                     0
    4.0s    ~30s             0/3                     0
    6.0s    ~42s             0/3                     0
    7.5s    ~51s             2/3   (unreliable)      0
    9.0s    ~60s             3/3                     0
    12.0s   ~78s             3/3                     0

The detector fires at generation p95 > 8.0s (2 x the declared `llm_latency_p95
< 4.0`). 9s is the first reliable value; 12s is taken because it clears the 8s
bucket edge by ~5s and still leaves ~17s under the target's 30s read timeout,
so no call errors and F02 never turns into F01. Every LLM call in a chat (four
embeddings, query expansion, generation) uses the same listener, hence a chat
of ~6 x 12s; that is what a slow endpoint does, and it is not trimmed.

WHY A SUBCLASS OF F01
Same admin API, same two listeners, same backup-must-be-up precondition and the
same scope and corpus assertions. Only what is changed on the primary differs:
F01 disables the listener, F02 adds a toxic to it. Reusing F01's assertions
means the "backup untouched" check is one piece of code for both faults.
"""

from __future__ import annotations

from typing import Any

from harness.faults.base import InjectionRecord
from harness.faults.f01_endpoint_outage import F01EndpointOutage, _call

TOXIC = "f02_latency"
LATENCY_MS = 12_000


class F02LatencyDegradation(F01EndpointOutage):
    fault_class = "F02"
    fault_name = "latency_degradation"
    service = "backend"

    def _toxics(self) -> list[dict[str, Any]]:
        return list(_call(f"/proxies/{self.proxy}/toxics") or [])

    def is_active(self) -> bool:
        return any(t.get("name") == TOXIC for t in self._toxics())

    def inject(self) -> InjectionRecord:
        before = self._proxy(self.proxy)
        toxics = self._toxics()
        if before.get("enabled") is not True or toxics:
            raise RuntimeError(
                f"{self.proxy!r} is not a clean pre-state (enabled="
                f"{before.get('enabled')}, toxics={[t.get('name') for t in toxics]}). "
                f"Revert a previous run first.")
        if not self.backup_is_up():
            raise RuntimeError(
                f"{self.backup!r} is not enabled, so the repair would switch the "
                f"target onto a dead path. Not injecting.")

        self.record.pre_state = {
            "proxy": dict(before), "toxics": toxics,
            "backup": dict(self._proxy(self.backup)),
        }
        self.record.corpus_before = self._corpus_probe()
        toxic = {"name": TOXIC, "type": "latency", "stream": "downstream",
                 "attributes": {"latency": LATENCY_MS, "jitter": 0}}
        _call(f"/proxies/{self.proxy}/toxics", "POST", toxic)
        self.record.applied = {"proxy": self.proxy, "toxic": toxic}
        self._stamp_injected()
        return self.record

    def revert(self) -> InjectionRecord:
        if "toxics" not in self.record.pre_state:
            return self.record  # nothing was injected; removing a guess is not a revert
        if self.is_active():
            _call(f"/proxies/{self.proxy}/toxics/{TOXIC}", "DELETE")
        self.record.corpus_after = self._corpus_probe()
        self._stamp_reverted()
        return self.record

    def restored_exactly(self) -> tuple[bool, str]:
        want = self.record.pre_state.get("toxics")
        if want is None:
            return False, "no pre-state captured"
        live = self._toxics()
        enabled = self._proxy(self.proxy).get("enabled")
        if live != want or enabled is not True:
            return False, f"not restored: toxics {live}, enabled={enabled}"
        return True, "primary listener has no toxics and is enabled, as captured"
